"""Hardware-independent tool geometry inspection with orbit and zoom.

Depth-sorted CAD triangles are projected into the widget's viewport. This is
an inspection preview, not a material removal or collision simulation.
"""

import math
import subprocess
import sys
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from kivy.clock import Clock
from kivy.graphics import Mesh
from kivy.graphics.instructions import RenderContext
from kivy.metrics import dp
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_mesh
from carveracontroller.desktop_components import Action, AdaptiveGrid, Surface, label

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
    def __init__(self, definition, **kwargs):
        super().__init__(**kwargs)
        self.definition = definition
        self.vertices, self.indices, self.fmt = build_tool_mesh(definition)
        points = [self.vertices[i : i + 3] for i in range(0, len(self.vertices), 12)]
        low = [min(p[i] for p in points) for i in range(3)]
        high = [max(p[i] for p in points) for i in range(3)]
        self.model_center = [(a + b) / 2 for a, b in zip(low, high)]
        self.span = max(b - a for a, b in zip(low, high)) or 1
        self.yaw, self.tilt, self.zoom = 0.6, -0.2, 1.0
        self.renderer = RenderContext(use_parent_projection=True, use_parent_modelview=True)
        self.canvas.add(self.renderer)
        self.renderer.shader.vs = VERTEX_SHADER
        self.renderer.shader.fs = FRAGMENT_SHADER
        with self.renderer:
            self.mesh = Mesh(vertices=[], indices=[], fmt=self.fmt, mode="triangles")
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.trigger, size=self.trigger)
        self.trigger()

    def redraw(self, *_):
        cy, sy = math.cos(self.yaw), math.sin(self.yaw)
        ct, st = math.cos(self.tilt), math.sin(self.tilt)
        projected = []
        for i in range(0, len(self.vertices), 12):
            x, y, z = [self.vertices[i + j] - self.model_center[j] for j in range(3)]
            projected.append((cy * x - sy * y, st * (sy * x + cy * y) + ct * z))
        span_x = max(p[0] for p in projected) - min(p[0] for p in projected)
        span_z = max(p[1] for p in projected) - min(p[1] for p in projected)
        factor = min(self.width / max(span_x, 0.01), self.height / max(span_z, 0.01)) * 0.8 * self.zoom
        transformed = []
        for i in range(0, len(self.vertices), 12):
            p = self.vertices[i : i + 3]
            x, y, z = [p[j] - self.model_center[j] for j in range(3)]
            x, y = cy * x - sy * y, sy * x + cy * y
            y, z = ct * y - st * z, st * y + ct * z
            nx, ny, nz = self.vertices[i + 3 : i + 6]
            nx, ny = cy * nx - sy * ny, sy * nx + cy * ny
            ny, nz = ct * ny - st * nz, st * ny + ct * nz
            shade = 0.35 + 0.65 * abs(ny)
            rgba = self.vertices[i + 6 : i + 10]
            transformed.append(
                (
                    self.center_x + x * factor,
                    self.center_y + z * factor,
                    y,
                    nx,
                    ny,
                    nz,
                    *(c * shade for c in rgba[:3]),
                    1,
                    0,
                    0,
                )
            )
        triangles = [self.indices[i : i + 3] for i in range(0, len(self.indices), 3)]
        triangles.sort(key=lambda tri: sum(transformed[index][2] for index in tri))
        vertices = []
        for tri in triangles:
            for index in tri:
                v = list(transformed[index])
                v[2] = 0
                vertices.extend(v)
        self.mesh.vertices = vertices
        self.mesh.indices = list(range(len(vertices) // 12))

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
            self.trigger()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def zoom_by(self, factor):
        self.zoom = max(0.4, min(3, self.zoom * factor))
        self.trigger()

    def fit(self):
        self.zoom = 1
        self.trigger()

    def dispose(self):
        self.trigger.cancel()


class ToolPreview(Surface):
    def __init__(self, definition, on_close=None, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kwargs)
        exact = bool(definition.geometry_path)
        self.add_widget(label("CAD geometry" if exact else "Dimension-based illustrative tool", size=16))
        self.view = _ToolCanvas(definition)
        self.add_widget(self.view)
        self.add_widget(label("Drag to orbit · scroll to zoom · tip registered at Z = 0", size=12, height=24))
        dims = []
        for caption, value in [
            ("Diameter", definition.diameter),
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
        controls.bind(minimum_height=controls.setter("height"))
        for text, action in [
            ("Fit", self.view.fit),
            ("Zoom +", lambda: self.view.zoom_by(1.15)),
            ("Zoom −", lambda: self.view.zoom_by(1 / 1.15)),
        ]:
            controls.add_widget(Action(text, action=action))
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
