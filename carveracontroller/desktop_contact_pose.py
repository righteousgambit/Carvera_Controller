"""Detached retained CAD poses in the left viewing pane; controls stay in the workbench."""

from __future__ import annotations

import threading

from kivy.clock import Clock
from kivy.graphics import Callback, ClearBuffers, ClearColor, Color, Fbo, Mesh, Rectangle, RenderContext
from kivy.graphics.opengl import (
    GL_CULL_FACE,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_FUNC,
    GL_DEPTH_TEST,
    GL_DEPTH_WRITEMASK,
    GL_LEQUAL,
    GL_STENCIL_TEST,
    glClear,
    glDepthFunc,
    glDepthMask,
    glDisable,
    glEnable,
    glGetBooleanv,
    glGetIntegerv,
    glIsEnabled,
)
from kivy.uix.widget import Widget

from carveracontroller.addons.tool_visualization.mesh_builder import VERTEX_FORMAT
from carveracontroller.desktop_tool_preview import FRAGMENT_SHADER
from carveracontroller.machine.contact_pose_material import ContactMaterial
from carveracontroller.machine.pose_view_buffers import pose_camera, prepare_pose_buffers
from carveracontroller.machine.tool_preview import PreviewPose

POSE_VERTEX_SHADER = """$HEADER$
attribute vec3 v_pos;
attribute vec3 v_normal;
attribute vec4 v_color;
uniform vec3 preview_center;
uniform vec3 preview_translation;
uniform vec4 preview_rotation;
uniform float preview_scale;
uniform vec2 preview_offset;
uniform float preview_depth;
varying vec4 mesh_color;
void main() {
    vec3 p = v_pos + preview_translation - preview_center;
    float x = preview_rotation.x * p.x - preview_rotation.y * p.y;
    float y = preview_rotation.y * p.x + preview_rotation.x * p.y;
    float z = preview_rotation.w * y + preview_rotation.z * p.z;
    float depth = preview_rotation.z * y - preview_rotation.w * p.z;
    float ny = preview_rotation.y * v_normal.x + preview_rotation.x * v_normal.y;
    ny = preview_rotation.z * ny - preview_rotation.w * v_normal.z;
    mesh_color = vec4(v_color.rgb * (0.35 + 0.65 * abs(ny)), v_color.a);
    frag_color = mesh_color;
    tex_coord0 = vec2(0.0);
    gl_Position = projection_mat * modelview_mat * vec4(
        preview_offset + vec2(x, z) * preview_scale, 0.0, 1.0);
    gl_Position.z = -depth * preview_depth * gl_Position.w;
}"""


class ContactPoseCanvas(Widget):
    """Retained complete GPU buffers; camera changes update only uniforms.

    An isolated depth-buffered FBO supplies consistent occlusion in the window
    and PNG exports. Its texture clips to the pane without leaking GL state.
    """

    def __init__(self, scene, status, **kwargs):
        super().__init__(**kwargs)
        self.scene, self.status = scene, status
        self.names = tuple(b.name for b in scene.bodies)
        self.surfaces_only = False
        self.yaw, self.tilt, self.zoom = 0.6, -0.25, 1.0
        self.pan = (0.0, 0.0)
        self.closed = threading.Event()
        self.generation = 0
        self.projecting = False
        self.pending = None
        self.meshes = []
        self.body_drawings = {}
        self.worker = None
        self.buffers = self.accepted_key = self.displayed_scene = self.projection_error = None
        self.camera_updates = 0
        self.renderer = Fbo(size=(1, 1), with_depthbuffer=True)
        self.renderer.shader.vs = POSE_VERTEX_SHADER
        self.renderer.shader.fs = FRAGMENT_SHADER
        with self.canvas:
            self.canvas.add(self.renderer)
            Color(1, 1, 1, 1)
            self.image = Rectangle(texture=self.renderer.texture, pos=self.pos, size=self.size)
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.queue_redraw, size=self.queue_redraw)
        self.queue_redraw()

    def setup_depth(self, *_):
        self.gl_state = (
            bool(glIsEnabled(GL_DEPTH_TEST)),
            bool(glIsEnabled(GL_CULL_FACE)),
            bool(glIsEnabled(GL_STENCIL_TEST)),
            glGetIntegerv(GL_DEPTH_FUNC)[0],
            bool(glGetBooleanv(GL_DEPTH_WRITEMASK)[0]),
        )
        glDisable(GL_CULL_FACE)
        glDisable(GL_STENCIL_TEST)
        glEnable(GL_DEPTH_TEST)
        glDepthMask(True)
        glDepthFunc(GL_LEQUAL)
        glClear(GL_DEPTH_BUFFER_BIT)

    def reset_depth(self, *_):
        depth, cull, stencil, func, mask = self.gl_state
        for flag, enabled in ((GL_DEPTH_TEST, depth), (GL_CULL_FACE, cull), (GL_STENCIL_TEST, stencil)):
            (glEnable if enabled else glDisable)(flag)
        glDepthFunc(func)
        glDepthMask(mask)

    def queue_redraw(self, *_):
        self.trigger()

    def camera_pose(self):
        return PreviewPose(
            self.yaw,
            self.tilt,
            self.zoom,
            self.width,
            self.height,
            self.width / 2 + self.pan[0],
            self.height / 2 + self.pan[1],
        )

    def update_camera(self, buffers):
        camera = pose_camera(buffers, self.camera_pose())
        for name, value in (
            ("preview_center", camera.center),
            ("preview_rotation", camera.rotation),
            ("preview_scale", camera.scale),
            ("preview_offset", camera.offset),
            ("preview_depth", camera.depth_scale),
        ):
            self.renderer[name] = value
            for _body, context, _meshes in self.body_drawings.values():
                context[name] = value
        self.camera_updates += 1
        self.renderer.ask_update()

    def redraw(self, *_):
        if self.closed.is_set() or min(self.size) <= 0:
            return
        size = tuple(max(1, int(v)) for v in self.size)
        if self.renderer.size != size:
            self.renderer.size = size
            self.image.texture = self.renderer.texture
        self.image.pos, self.image.size = self.pos, self.size
        if self.buffers is not None:
            try:
                self.update_camera(self.buffers)
            except (ValueError, ArithmeticError) as exc:
                self.projection_error = str(exc)
                self.status(str(exc) + " · Previous view retained")
                return
        key = (self.scene, self.names, self.surfaces_only)
        if self.accepted_key is not None and self.accepted_key[0] is key[0] and self.accepted_key[1:] == key[1:]:
            if self.pending is not None or (
                self.projecting and (self.active_key[0] is not key[0] or self.active_key[1:] != key[1:])
            ):
                self.generation += 1
                self.pending = None
            return
        if self.pending is None or self.pending[1] is not key[0] or self.pending[2:] != key[1:]:
            # Camera motion does not cancel the object-space preparation.
            active = getattr(self, "active_key", None)
            if (
                active is not None
                and active[0] is key[0]
                and active[1:] == key[1:]
                and self.projecting
                and self.active_generation == self.generation
                and self.pending is None
            ):
                return
            self.generation += 1
            self.pending = (self.generation, *key)
        if not self.projecting:
            self.launch()

    def launch(self):
        if self.closed.is_set() or self.pending is None:
            return
        generation, scene, names, surfaces_only = self.pending
        self.active_key = (scene, names, surfaces_only)
        self.active_generation = generation
        self.pending = None
        self.projecting = True
        previous = self.buffers
        self.status("Preparing complete GPU geometry… · Return to program remains available")

        def work():
            result, error = None, None
            try:
                result = prepare_pose_buffers(
                    scene,
                    names,
                    surfaces_only=surfaces_only,
                    previous=previous,
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
            if (
                generation == self.generation
                and self.scene is scene
                and self.names == names
                and self.surfaces_only == surfaces_only
            ):
                if result is not None:
                    try:
                        pose_camera(result, self.camera_pose())
                        drawings = {}
                        for body in result.bodies:
                            prior = self.body_drawings.get(body.name)
                            if prior is not None and prior[0].batches is body.batches:
                                context, meshes = prior[1:]
                            else:
                                context = RenderContext(use_parent_projection=True, use_parent_modelview=True)
                                context.shader.vs = POSE_VERTEX_SHADER
                                context.shader.fs = FRAGMENT_SHADER
                                meshes = [
                                    Mesh(vertices=v, indices=i, fmt=VERTEX_FORMAT, mode="triangles")
                                    for v, i in body.batches
                                ]
                                for mesh in meshes:
                                    context.add(mesh)
                            drawings[body.name] = (body, context, meshes)
                        # Build every changed body before publishing any instance
                        # or evicting the previous complete accepted frame.
                        for body, context, _meshes in drawings.values():
                            context["preview_translation"] = body.translation
                        self.renderer.clear()
                        with self.renderer:
                            ClearColor(0, 0, 0, 0)
                            ClearBuffers()
                            Callback(self.setup_depth)
                            for _body, context, _meshes in drawings.values():
                                self.renderer.add(context)
                            Callback(self.reset_depth)
                        self.body_drawings = drawings
                        self.meshes = [mesh for _body, _context, meshes in drawings.values() for mesh in meshes]
                        self.buffers = result
                        self.update_camera(result)
                        self.accepted_key = (scene, names, surfaces_only)
                        self.displayed_scene, self.projection_error = scene, None
                        self.status(
                            f"{result.triangles} displayed triangles · {len(names)} bodies\n"
                            "Drag to orbit · right drag to pan · scroll to zoom · Esc to return. "
                            "Cyan/red: original contact faces; amber: envelope only; blue: remaining cells; purple: target."
                        )
                    except (ValueError, ArithmeticError, RuntimeError) as exc:
                        error = str(exc)
                if error:
                    self.projection_error = error
                    self.status(error + " · Previous view retained")
            if self.pending is not None:
                self.launch()

        try:
            self.worker = threading.Thread(target=work, daemon=True, name="contact-pose-buffers")
            self.worker.start()
        except (RuntimeError, OSError):
            self.projecting = False
            self.pending = None
            self.projection_error = "Pose-view worker could not start"
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

    def __init__(self, workspace, scene, status, current, on_close, caption=None):
        self.workspace, self.on_close = workspace, on_close
        self.material: ContactMaterial | None = None
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
        self.caption = caption or (
            f"Nominal contact pose · T{scene.pose.tool} · move {scene.pose.segment_index + 1} · Esc to return"
        )
        workspace.contact_pose_stage = self
        workspace._update_model_caption(self.previous_caption)
        self.event = Clock.schedule_interval(self.check, 0.25)

    def update_scene(self, scene, caption):
        if self.closed:
            return
        canvas = self.canvas
        prior = tuple(b.name for b in canvas.scene.bodies)
        canvas.scene = scene
        if canvas.names == prior:
            canvas.names = tuple(b.name for b in scene.bodies)
        else:
            canvas.names = tuple(n for n in canvas.names if n in {b.name for b in scene.bodies})
        self.caption = caption
        self.workspace._update_model_caption(self.previous_caption)
        canvas.queue_redraw()

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
