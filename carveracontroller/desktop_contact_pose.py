"""Detached retained CAD poses in the left viewing pane; controls stay in the workbench."""

import threading

from kivy.clock import Clock
from kivy.graphics import Mesh
from kivy.graphics.instructions import RenderContext
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.tool_visualization.mesh_builder import VERTEX_FORMAT
from carveracontroller.desktop_tool_preview import FRAGMENT_SHADER, VERTEX_SHADER
from carveracontroller.machine.contact_pose_view import project_contact_pose_view
from carveracontroller.machine.tool_preview import PreviewPose


class ContactPoseCanvas(StencilView):
    """Every visible original face, depth sorted on a cancellable worker."""

    def __init__(self, scene, status, **kwargs):
        super().__init__(**kwargs)
        self.scene = scene
        self.status = status
        self.names = tuple(b.name for b in scene.bodies)
        self.surfaces_only = False
        self.yaw, self.tilt, self.zoom = 0.6, -0.25, 1.0
        self.pan = (0.0, 0.0)
        self.closed = threading.Event()
        self.generation = 0
        self.projecting = False
        self.pending = None
        self.meshes = []
        self.worker = None
        self.renderer = RenderContext(use_parent_projection=True, use_parent_modelview=True)
        self.renderer.shader.vs = VERTEX_SHADER
        self.renderer.shader.fs = FRAGMENT_SHADER
        self.canvas.add(self.renderer)
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.queue_redraw, size=self.queue_redraw)
        self.queue_redraw()

    def queue_redraw(self, *_):
        self.generation += 1
        self.trigger()

    def redraw(self, *_):
        if self.closed.is_set() or min(self.size) <= 0:
            return
        self.pending = (
            self.generation,
            PreviewPose(
                self.yaw,
                self.tilt,
                self.zoom,
                self.width,
                self.height,
                self.center_x + self.pan[0],
                self.center_y + self.pan[1],
            ),
            self.names,
            self.surfaces_only,
        )
        if not self.projecting:
            self.launch()

    def launch(self):
        if self.closed.is_set() or self.pending is None:
            return
        generation, pose, names, surfaces_only = self.pending
        self.pending = None
        self.projecting = True
        self.status("Preparing complete pose view… · Return to program remains available")

        def work():
            result, error = None, None
            try:
                result = project_contact_pose_view(
                    self.scene,
                    pose,
                    names,
                    surfaces_only=surfaces_only,
                    cancelled=lambda: self.closed.is_set() or generation != self.generation,
                )
            except InterruptedError:
                pass
            except (ValueError, ArithmeticError) as exc:
                error = str(exc)
            Clock.schedule_once(lambda _dt: complete(result, error), 0)

        def complete(result, error):
            self.projecting = False
            if self.closed.is_set():
                return
            if generation == self.generation:
                if error:
                    self.status(error + " · Previous view retained")
                elif result is not None:
                    self.renderer.clear()
                    self.meshes = []
                    with self.renderer:
                        for vertices, indices in result:
                            self.meshes.append(
                                Mesh(vertices=vertices, indices=indices, fmt=VERTEX_FORMAT, mode="triangles")
                            )
                    self.status(
                        f"{sum(len(i) // 3 for _v, i in result)} displayed triangles · {len(names)} bodies\n"
                        "Drag to orbit · right drag to pan · scroll to zoom · Esc to return. Cyan/red: original contacting faces; amber: envelope only."
                    )
            if self.pending is not None:
                self.launch()

        try:
            self.worker = threading.Thread(target=work, daemon=True, name="contact-pose-projection")
            self.worker.start()
        except (RuntimeError, OSError):
            self.projecting = False
            self.pending = None
            self.status("Pose-view worker could not start; previous view retained")

    def set_bodies(self, names, surfaces_only=False):
        self.names = tuple(names)
        self.surfaces_only = surfaces_only
        self.pan = (0.0, 0.0)
        self.zoom = 1.0
        self.queue_redraw()

    def fit(self):
        self.zoom, self.pan = 1.0, (0.0, 0.0)
        self.queue_redraw()

    def zoom_by(self, factor):
        self.zoom = max(0.1, min(20.0, self.zoom * factor))
        self.queue_redraw()

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
            if getattr(touch, "button", "left") == "right":
                self.pan = (self.pan[0] + touch.dx, self.pan[1] + touch.dy)
            else:
                self.yaw += touch.dx * 0.012
                self.tilt = max(-1.5, min(1.5, self.tilt + touch.dy * 0.008))
            self.queue_redraw()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            return True
        return super().on_touch_up(touch)

    def dispose(self):
        self.closed.set()
        self.generation += 1
        self.pending = None
        self.trigger.cancel()


class ContactPoseStage:
    """Replace only the pane's imagery, retaining the exact active viewer and camera."""

    def __init__(self, workspace, scene, status, current, on_close):
        self.workspace, self.on_close = workspace, on_close
        prior = getattr(workspace, "contact_pose_stage", None)
        if prior is not None:
            prior.close()
        self.previous = workspace.machine.gcode_viewer
        self.previous_caption = workspace.model_caption.text
        self.closed = False
        self.canvas = ContactPoseCanvas(scene, status)
        self.current = current
        if self.previous.parent is not workspace.model_card:
            self.canvas.dispose()
            raise ValueError("The machine pane is showing another owned inspection")
        self.index = workspace.model_card.children.index(self.previous)
        workspace.model_card.remove_widget(self.previous)
        workspace.model_card.add_widget(self.canvas, index=self.index)
        self.caption = (
            f"Nominal contact pose · T{scene.pose.tool} · move {scene.pose.segment_index + 1} · Esc to return"
        )
        workspace.contact_pose_stage = self
        workspace._update_model_caption(self.previous_caption)
        self.event = Clock.schedule_interval(self.check, 0.25)

    def check(self, *_):
        if not self.current():
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.event.cancel()
        self.canvas.dispose()
        ws = self.workspace
        if self.canvas.parent is ws.model_card:
            ws.model_card.remove_widget(self.canvas)
            if self.previous.parent is None:
                ws.model_card.add_widget(self.previous, index=min(self.index, len(ws.model_card.children)))
        if getattr(ws, "contact_pose_stage", None) is self:
            ws.contact_pose_stage = None
            ws._update_model_caption(getattr(ws, "_program_model_caption", self.previous_caption))
        self.on_close()
