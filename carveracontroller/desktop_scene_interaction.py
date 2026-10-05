"""Viewport picking and reviewed placement gestures; never moves a machine."""

import threading

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RenderContext
from kivy.graphics.transformation import Matrix
from kivy.metrics import dp

from carveracontroller.desktop_components import AdaptiveGrid, Choice, QuantityField, Surface, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.machine.scene_inspection import GEOMETRY_GROUPS
from carveracontroller.machine.scene_interaction import (
    homogeneous_point,
    inverse_projection,
    pick_geometry,
    placement_delta,
    plane_point,
    subtract,
)


class SceneInteraction:
    MODES = ("View", "Pick component", "Move XY", "Move Z")

    def __init__(self, workspace, page):
        self.workspace = workspace
        self.viewer = workspace.machine.gcode_viewer
        self.mode = Choice(text="View", values=self.MODES)
        self.snap = QuantityField(text="1 mm", kind="length", minimum=0, maximum=100)
        self.note = content_label(
            "Pick a rendered surface, or drag the selected stock/vise handle to review placement."
        )
        panel = Surface(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None)
        panel.bind(minimum_height=panel.setter("height"))
        panel.add_widget(label("Scene interaction", 15, height=24, bold=True))
        controls = AdaptiveGrid(max_cols=2, min_width=145, row_height=34, spacing=dp(6))
        controls.add_widget(self.mode)
        controls.add_widget(self.snap)
        panel.add_widget(controls)
        panel.add_widget(content_label("Grid snap · 0 disables · local preview coordinates"))
        panel.add_widget(self.note)
        page.add_widget(panel, index=page.children.index(workspace.object_inspector) + 1)
        self.mode.bind(text=self._mode_changed)
        self.request = 0
        self.picking = False
        self.gesture = None
        self.overlay = RenderContext()
        self.viewer.canvas.after.add(self.overlay)
        self.overlay["projection_mat"] = Window.render_context["projection_mat"]
        self.overlay["modelview_mat"] = Matrix()
        with self.overlay:
            self.color = Color(0.25, 0.8, 0.75, 0)
            self.handle = Line(circle=(0, 0, dp(8)), width=1.5)
            self.guide = Line(points=[], width=1.5)
        self.event = Clock.schedule_interval(self.refresh_handle, 0.1)
        self.viewer.scene_interaction = self

    def dispose(self):
        self.request += 1
        self.gesture = None
        self.event.cancel()
        self.color.a = 0
        self.viewer.canvas.after.remove(self.overlay)
        self.viewer.scene_interaction = None

    def _mode_changed(self, *_):
        self.request += 1
        self.gesture = None
        self.guide.points = []
        self.note.text = (
            "Drag the selected stock/vise handle · release to review placement"
            if self.mode.text.startswith("Move")
            else "Click a rendered surface to inspect its component"
            if self.mode.text == "Pick component"
            else "Orbit, pan and zoom the scene"
        )
        if self.mode.text.startswith("Move"):
            self.workspace.enter_preview()
        self.refresh_handle()

    def _inverse(self):
        return inverse_projection(self.viewer.m_viewMatrix.get(), self.viewer._proj_matrix.get())

    def window_pos(self, pos):
        return self.viewer.parent.to_window(*pos) if self.viewer.parent is not None else pos

    def viewport(self):
        return tuple(self.viewer._view_cube_gl_origin()) + tuple(self.viewer.size)

    def screen_ray(self, pos, inverse=None):
        viewer = self.viewer
        if viewer.width <= 0 or viewer.height <= 0:
            raise ValueError("Scene viewport is empty")
        pos = self.window_pos(pos)
        ox, oy = viewer._view_cube_gl_origin()
        x, y = (2 * (pos[0] - ox) / viewer.width - 1, 2 * (pos[1] - oy) / viewer.height - 1)
        inverse = inverse if inverse is not None else self._inverse()
        points = []
        for z in (-1, 1):
            point = homogeneous_point(inverse, x, y, z)
            scale = viewer.move_scale_by_positon or 1
            points.append(
                tuple(
                    (point[i] + viewer.lines_center[i]) / scale + viewer.machine_setup.work_offset_mm[i]
                    for i in range(3)
                )
            )
        return points[0], subtract(points[1], points[0])

    def movement(self, group):
        return self.viewer._machine_pose.get(
            "table" if group in ("stock", "workholding", "fixture", "atc") else group, (0, 0, 0)
        )

    def center(self):
        viewer = self.viewer
        selected = self.workspace.object_inspector.selected
        if (
            selected not in ("stock", "workholding")
            or not viewer.machine_visible
            or not viewer.machine_group_visibility.get(selected, True)
        ):
            return None
        bounds = viewer.inspected_component_bounds(selected)
        if bounds is None:
            return None
        point = tuple((a + b) / 2 + shift for a, b, shift in zip(*bounds, self.movement(selected)))
        return selected, point

    def refresh_handle(self, *_):
        self.overlay["projection_mat"] = Window.render_context["projection_mat"]
        center = (
            self.center()
            if self.mode.text.startswith("Move")
            and self.workspace.active_section == "Scene"
            and not self.viewer.disabled
            else None
        )
        self.color.a = 1 if center else 0
        if center:
            viewer = self.viewer
            scale = viewer.move_scale_by_positon or 1
            point = tuple(
                (center[1][i] - viewer.machine_setup.work_offset_mm[i]) * scale - viewer.lines_center[i]
                for i in range(3)
            )
            screen = viewer.m_viewMatrix.project(
                *point,
                viewer.m_viewMatrix,
                viewer._proj_matrix,
                *viewer._view_cube_gl_origin(),
                viewer.width,
                viewer.height,
            )
            if screen is None or not 0 <= screen[2] <= 1:
                self.color.a = 0
                return
            self.handle.circle = (screen[0], screen[1], dp(8))
            if self.gesture is None:
                self.guide.points = []

    def down(self, touch):
        if (
            self.workspace.active_section != "Scene"
            or self.mode.text == "View"
            or getattr(touch, "button", "left") != "left"
        ):
            return False
        ws, viewer = self.workspace, self.viewer
        try:
            if not viewer.machine_visible:
                raise ValueError("Show the machine scene before selecting geometry")
            if self.mode.text == "Pick component":
                self.pick(touch.pos)
                return True
            if ws.app.playing or ws.app.state not in ("Idle", "N/A"):
                raise ValueError("Stop playback before editing the local scene")
            center = self.center()
            if center is None:
                raise ValueError("Select visible stock or a vise before moving its handle")
            self.refresh_handle()
            if (
                self.color.a == 0
                or sum((self.window_pos(touch.pos)[i] - self.handle.circle[i]) ** 2 for i in (0, 1)) > dp(18) ** 2
            ):
                return False
            kind = "stock" if center[0] == "stock" else "workholding"
            profile = getattr(ws, "selected_machine_profile", None) or {}
            if (profile.get("id"), kind) in getattr(ws, "setup_drafts", {}):
                raise ValueError("Review the retained setup draft before starting a new placement gesture")
            inverse = self._inverse()
            origin, direction = self.screen_ray(touch.pos, inverse)
            normal = (0, 0, 1) if self.mode.text == "Move XY" else (direction[0], direction[1], 0)
            start = plane_point(origin, direction, center[1], normal)
            self.gesture = {
                "kind": kind,
                "setup": capture_scene_setup(ws),
                "geometry": viewer._inspection_geometry,
                "profile": profile.get("id"),
                "inverse": inverse,
                "normal": normal,
                "center": center[1],
                "start": start,
                "axis": self.mode.text[-2:].strip(),
                "snap": self.snap.value(),
                "delta": (0, 0, 0),
                "viewport": self.viewport(),
                "screen": self.window_pos(touch.pos),
            }
            self.gesture["view"] = (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
            return True
        except ValueError as exc:
            self.note.text = str(exc)
            return True

    def move(self, touch):
        if self.gesture is None:
            return
        try:
            gesture = self.gesture
            point = plane_point(*self.screen_ray(touch.pos, gesture["inverse"]), gesture["center"], gesture["normal"])
            gesture["delta"] = placement_delta(gesture["start"], point, gesture["axis"], gesture["snap"])
            self.guide.points = [*gesture["screen"], *self.window_pos(touch.pos)]
            self.note.text = (
                "Placement draft Δ XYZ: " + ", ".join(f"{v:g} mm" for v in gesture["delta"]) + " · release to review"
            )
        except ValueError as exc:
            self.gesture["failed"] = True
            self.note.text = str(exc)

    def up(self, touch):
        self.move(touch)
        gesture, self.gesture = self.gesture, None
        self.guide.points = []
        if gesture is None or not any(gesture["delta"]):
            return
        ws, viewer = self.workspace, self.viewer
        profile = getattr(ws, "selected_machine_profile", None) or {}
        if (
            gesture.get("failed")
            or ws.app.playing
            or ws.app.state not in ("Idle", "N/A")
            or capture_scene_setup(ws) != gesture["setup"]
            or viewer._inspection_geometry is not gesture["geometry"]
            or profile.get("id") != gesture["profile"]
            or self.viewport() != gesture["viewport"]
            or (viewer.m_viewMatrix.get(), viewer._proj_matrix.get()) != gesture["view"]
        ):
            self.note.text = "Scene changed during the gesture · placement discarded; try again"
            return
        from carveracontroller.desktop_setup_editor import open_setup_editor

        editor = open_setup_editor(ws, gesture["kind"])
        field = "stock_origin_mm" if gesture["kind"] == "stock" else "workholding_offset_mm"
        for axis in range(3):
            editor.fields[(field, axis)].text = f"{gesture['setup'][field][axis] + gesture['delta'][axis]:.12g} mm"
        self.note.text = "Placement draft ready · Apply saves the local setup; Cancel preserves it"

    def pick(self, pos):
        if self.picking:
            self.note.text = "Picking rendered geometry…"
            return
        viewer = self.viewer
        origin, direction = self.screen_ray(pos)
        geometry = viewer._inspection_geometry
        view = (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
        viewport = self.viewport()
        visibility = dict(viewer.machine_group_visibility)
        components = [
            (key, geometry[group], self.movement(group))
            for key, groups in GEOMETRY_GROUPS.items()
            for group in groups
            if group in geometry and viewer.machine_group_visibility.get(group, True)
        ]
        self.request += 1
        request = self.request
        self.picking = True
        self.note.text = "Picking rendered geometry…"

        def work():
            try:
                result = pick_geometry(origin, direction, components)
            except (ValueError, IndexError, ArithmeticError):
                result = None

            def done(_dt):
                self.picking = False
                if (
                    request != self.request
                    or geometry is not viewer._inspection_geometry
                    or self.mode.text != "Pick component"
                    or self.workspace.active_section != "Scene"
                    or view != (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
                    or viewport != self.viewport()
                    or visibility != viewer.machine_group_visibility
                    or not viewer.machine_visible
                ):
                    return
                if result is None:
                    self.note.text = "No rendered surface at this point"
                    return
                self.workspace.object_inspector.select(result[0], reveal=False)
                self.note.text = "Selected rendered surface · " + result[0]

            Clock.schedule_once(done, 0)

        threading.Thread(target=work, name="scene-surface-pick", daemon=True).start()
