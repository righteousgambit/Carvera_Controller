"""Hardware-independent tool geometry inspection with orbit and zoom.

Depth-sorted CAD triangles are projected into the widget's viewport. This is
an inspection preview, not a material removal or collision simulation.
"""

import subprocess
import sys
import threading
import webbrowser
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

from kivy.clock import Clock
from kivy.graphics import Mesh
from kivy.graphics.instructions import RenderContext
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.tool_visualization.mesh_builder import VERTEX_FORMAT, build_tool_mesh
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, DesktopScrollView, Surface, label
from carveracontroller.desktop_tool_drawing import ToolDrawing
from carveracontroller.machine.tool_preview import PreviewPose, mesh_center, project_mesh

VERTEX_SHADER = """$HEADER$
attribute vec3 v_pos;
attribute vec4 v_color;
varying vec4 mesh_color;
void main() {
    mesh_color = v_color;
    frag_color = v_color;
    tex_coord0 = vec2(0.0);
    gl_Position = projection_mat * modelview_mat * vec4(v_pos, 1.0);
}"""
FRAGMENT_SHADER = """$HEADER$
varying vec4 mesh_color;
void main() { gl_FragColor = mesh_color; }"""


class _ToolCanvas(StencilView):
    def __init__(self, definition, on_status=None, **kwargs):
        super().__init__(**kwargs)
        self.definition = replace(definition)
        self.on_status = on_status or (lambda text: None)
        self.vertices, self.indices, self.fmt = [], [], VERTEX_FORMAT
        self.model_center = (0, 0, 0)
        self.yaw, self.tilt, self.zoom = 0.6, -0.2, 1.0
        self.closed = threading.Event()
        self.preparing = True
        self.projecting = False
        self.generation = 0
        self.pending = None
        self.renderer = RenderContext(use_parent_projection=True, use_parent_modelview=True)
        self.canvas.add(self.renderer)
        self.renderer.shader.vs = VERTEX_SHADER
        self.renderer.shader.fs = FRAGMENT_SHADER
        with self.renderer:
            self.mesh = Mesh(vertices=[], indices=[], fmt=self.fmt, mode="triangles")
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.queue_redraw, size=self.queue_redraw)
        self.prepare_event = Clock.schedule_once(self.prepare, 0)

    def prepare(self, *_):
        if self.closed.is_set():
            return
        self.on_status("Preparing cutter geometry… · Close remains available")

        def work():
            prepared, error = None, None
            try:
                mesh = build_tool_mesh(self.definition, cancelled=self.closed.is_set)
                center = mesh_center(mesh[0], self.closed.is_set)
                prepared = (mesh, center)
            except InterruptedError:
                pass
            except (ValueError, ArithmeticError, OSError):
                error = "Tool geometry could not be prepared; check the registered CAD asset and dimensions."
            Clock.schedule_once(lambda _dt: finish(prepared, error), 0)

        def finish(prepared, error):
            self.preparing = False
            if self.closed.is_set():
                return
            if error:
                self.on_status(error)
                return
            if prepared is not None:
                (self.vertices, self.indices, self.fmt), self.model_center = prepared
                self.queue_redraw()

        try:
            threading.Thread(target=work, daemon=True, name="tool-preview-geometry").start()
        except (RuntimeError, OSError):
            self.preparing = False
            self.on_status("Tool geometry worker could not start; close and reopen to retry.")

    def queue_redraw(self, *_):
        self.generation += 1
        self.trigger()

    def redraw(self, *_):
        if self.closed.is_set() or not self.vertices:
            return
        self.generation += 1
        self.pending = (self.generation, PreviewPose(self.yaw, self.tilt, self.zoom, *self.size, *self.center))
        if not self.projecting:
            self.launch_projection()

    def launch_projection(self):
        if self.closed.is_set() or self.pending is None:
            return
        generation, pose = self.pending
        self.pending = None
        self.projecting = True
        self.on_status("Preparing view… · Drag to orbit · scroll to zoom")

        def work():
            result, error = None, None
            try:
                result = project_mesh(
                    self.vertices,
                    self.indices,
                    self.model_center,
                    pose,
                    lambda: self.closed.is_set() or generation != self.generation,
                )
            except InterruptedError:
                pass
            except (ValueError, ArithmeticError, OSError):
                error = "Tool view could not be prepared; the previous view is retained."
            Clock.schedule_once(lambda _dt: finish(result, error), 0)

        def finish(result, error):
            self.projecting = False
            if self.closed.is_set():
                return
            if generation == self.generation and pose == PreviewPose(
                self.yaw, self.tilt, self.zoom, *self.size, *self.center
            ):
                if error:
                    self.on_status(error)
                elif result is not None:
                    self.mesh.vertices, self.mesh.indices = result
                    self.on_status("Drag to orbit · scroll to zoom · tip registered at Z = 0")
            if self.pending is not None:
                self.launch_projection()

        try:
            threading.Thread(target=work, daemon=True, name="tool-preview-projection").start()
        except (RuntimeError, OSError):
            self.projecting = False
            self.pending = None
            self.on_status("Tool view worker could not start; the previous view is retained.")

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            if touch.is_mouse_scrolling:
                self.zoom_by(1.15 if touch.button == "scrollup" else 1 / 1.15)
            else:
                touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.yaw += touch.dx * 0.012
            self.tilt = max(-1.3, min(1.3, self.tilt + touch.dy * 0.008))
            self.queue_redraw()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def zoom_by(self, factor):
        self.zoom = max(0.4, min(3, self.zoom * factor))
        self.queue_redraw()

    def fit(self):
        self.zoom = 1
        self.queue_redraw()

    def dispose(self):
        self.closed.set()
        self.generation += 1
        self.pending = None
        self.prepare_event.cancel()
        self.trigger.cancel()


class ToolPreview(Surface):
    def __init__(self, definition, on_close=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kwargs)
        exact = bool(definition.geometry_path)
        self.add_widget(label("CAD geometry" if exact else "Dimension-based illustrative tool", size=16))
        self.hint = label("Preparing cutter geometry…", size=12, height=36)
        self.view = _ToolCanvas(definition, on_status=self.preview_status)
        self.drawing = ToolDrawing(definition, size_hint_y=None, height=dp(320))
        self.drawing_scroll = DesktopScrollView(do_scroll_x=False)
        self.drawing_scroll.add_widget(self.drawing)
        self.mode = Choice(text="3D geometry", values=("3D geometry", "Dimensioned drawing"))
        self.mode.bind(text=self.select_mode)
        self.add_widget(self.mode)
        self.viewport = BoxLayout()
        self.viewport.bind(height=lambda _obj, height: setattr(self.drawing, "height", max(dp(320), height)))
        self.viewport.add_widget(self.view)
        self.add_widget(self.viewport)
        self.hint.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
        self.add_widget(self.hint)
        dims = []
        for caption, value in [
            ("Diameter", definition.diameter),
            ("Shank", definition.shank_diameter),
            ("Overall", definition.length),
            ("Cutting length", definition.flute_length),
            ("Stickout", definition.stickout),
        ]:
            dims.append(f"{caption}: {value:g} mm" if value is not None else f"{caption}: unknown")
        details = label(" · ".join(dims), size=12, height=48)
        details.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
        self.add_widget(details)
        if definition.stickout is None:
            self.add_widget(label("Full cutter shown · installed stickout not configured", size=12, height=24))
        controls = AdaptiveGrid(max_cols=3, min_width=110, row_height=36, spacing=dp(8))
        self.view_actions = []
        controls.bind(minimum_height=controls.setter("height"))
        for text, action in [
            ("Fit", self.view.fit),
            ("Zoom +", lambda: self.view.zoom_by(1.15)),
            ("Zoom −", lambda: self.view.zoom_by(1 / 1.15)),
        ]:
            button = Action(text, action=action)
            self.view_actions.append(button)
            controls.add_widget(button)
        parsed = urlparse(definition.source_url)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            controls.add_widget(Action("Manufacturer", action=lambda: webbrowser.open(definition.source_url)))
        drawing = Path(definition.drawing_path).expanduser() if definition.drawing_path else None
        if drawing and drawing.is_file():

            def open_drawing():
                if sys.platform == "darwin":
                    subprocess.Popen(["open", str(drawing)])
                elif sys.platform == "win32":
                    import os

                    os.startfile(str(drawing))
                else:
                    subprocess.Popen(["xdg-open", str(drawing)])

            controls.add_widget(Action("Drawing", action=open_drawing))
        if on_close:
            controls.add_widget(Action("Close", action=on_close))
        self.add_widget(controls)

    def dispose(self):
        self.view.dispose()
        self.drawing.dispose()

    def preview_status(self, text):
        self.preview_message = text
        if not hasattr(self, "mode") or self.mode.text == "3D geometry":
            self.hint.text = text

    def select_mode(self, _choice, value):
        self.viewport.clear_widgets()
        drawing = value == "Dimensioned drawing"
        self.viewport.add_widget(self.drawing_scroll if drawing else self.view)
        for button in self.view_actions:
            button.disabled = drawing
        self.hint.text = (
            "Nominal dimension schematic · inserted length is derived · holder gauge length is not inferred"
            if drawing
            else getattr(self, "preview_message", "Preparing cutter geometry…")
        )
