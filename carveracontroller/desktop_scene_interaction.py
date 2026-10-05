"""Viewport picking and reviewed placement gestures; never moves a machine."""

import math
import threading

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, RenderContext
from kivy.graphics.transformation import Matrix
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.addons.machine_simulation.profile import CAD_OFFSET
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, QuantityField, Surface, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.machine.scene_inspection import GEOMETRY_GROUPS, geometry_bounds
from carveracontroller.machine.scene_interaction import (
    canonical_angle,
    homogeneous_point,
    inverse_projection,
    near_polyline,
    pick_geometry,
    placement_delta,
    plane_point,
    render_tool_snapshot,
    rotation_step,
    snap_angle,
    subtract,
)


class SceneInteraction:
    MODES = ("View", "Pick component", "Move XY", "Move Z", "Rotate stock Z", "Rotate vise Z")

    def __init__(self, workspace, page):
        self.workspace = workspace
        self.viewer = workspace.machine.gcode_viewer
        self.mode = Choice(text="View", values=self.MODES)
        self.snap = QuantityField(text="1 mm", kind="length", minimum=0, maximum=100)
        self.angle_snap = QuantityField(text="15°", kind="angle", minimum=0, maximum=180)
        self.note = content_label(
            "Pick a rendered surface, or drag the selected stock/vise handle to review placement."
        )
        panel = Surface(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None)
        panel.bind(minimum_height=panel.setter("height"))
        heading = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        heading.add_widget(label("Scene interaction", 15, height=32, bold=True))
        heading.add_widget(
            Action("Frame selected", self.frame_selected, size_hint_x=None, width=dp(125), height=dp(32))
        )
        panel.add_widget(heading)
        controls = AdaptiveGrid(max_cols=3, min_width=145, row_height=54, spacing=dp(6))
        controls.add_widget(self.mode)
        controls.add_widget(self.snap)
        controls.add_widget(self.angle_snap)
        panel.add_widget(controls)
        panel.add_widget(content_label("Translation grid / angle snap · 0 disables · local preview coordinates"))
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
            self.ring = Line(points=[], width=1.5)
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
            "Drag the selected rotation ring · release to review angle"
            if self.rotating
            else "Drag the selected stock/vise handle · release to review placement"
            if self.mode.text.startswith("Move")
            else "Click a rendered surface to inspect its component"
            if self.mode.text == "Pick component"
            else "Orbit, pan and zoom the scene"
        )
        if self.mode.text.startswith("Move") or self.rotating:
            self.workspace.enter_preview()
        self.refresh_handle()

    @property
    def rotating(self):
        return self.mode.text in ("Rotate stock Z", "Rotate vise Z")

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
        if self.rotating:
            expected = "stock" if self.mode.text == "Rotate stock Z" else "workholding"
            if selected != expected:
                return None
            if selected == "stock":
                setup = viewer.machine_setup
                if setup.stock_size_mm is None:
                    return None
                pivot = setup.machine_point(
                    tuple(a + b / 2 for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm))
                )
                return selected, tuple(pivot[i] + self.movement(selected)[i] for i in range(3))
            profile = viewer.machine_component_profiles.get("workholding", viewer.machine_profile)
            if profile is None:
                return None
            pivot = profile.workholding.get("pivot_mm", profile.workholding.get("cad_translation_mm", (0, 0, 0)))
            point = tuple(
                pivot[i] + CAD_OFFSET[i] + viewer.workholding_offset_mm[i] + self.movement(selected)[i]
                for i in range(3)
            )
        else:
            point = tuple((a + b) / 2 + shift for a, b, shift in zip(*bounds, self.movement(selected)))
        return selected, point

    def project(self, machine_point):
        viewer = self.viewer
        scale = viewer.move_scale_by_positon or 1
        point = tuple(
            (machine_point[i] - viewer.machine_setup.work_offset_mm[i]) * scale - viewer.lines_center[i]
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
        return screen if screen is not None and 0 <= screen[2] <= 1 else None

    def refresh_handle(self, *_):
        self.overlay["projection_mat"] = Window.render_context["projection_mat"]
        center = (
            self.center()
            if (self.mode.text.startswith("Move") or self.rotating)
            and self.workspace.active_section == "Scene"
            and not self.viewer.disabled
            else None
        )
        self.color.a = 1 if center else 0
        self.ring.points = []
        if center:
            screen = self.project(center[1])
            if screen is None:
                self.color.a = 0
                return
            self.handle.circle = (screen[0], screen[1], 0 if self.rotating else dp(8))
            if self.rotating:
                low, high = self.viewer.inspected_component_bounds(center[0])
                radius = max(10, math.hypot(high[0] - low[0], high[1] - low[1]) * 0.55)
                ring = []
                for n in range(65):
                    angle = 2 * math.pi * n / 64
                    point = (
                        center[1][0] + radius * math.cos(angle),
                        center[1][1] + radius * math.sin(angle),
                        center[1][2],
                    )
                    projected = self.project(point)
                    if projected is None:
                        self.color.a = 0
                        return
                    ring.extend(projected[:2])
                self.ring.points = ring
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
            if not viewer.machine_visible and not (
                self.mode.text == "Pick component" and viewer.inspection_cutter_snapshot() is not None
            ):
                raise ValueError("Show a machine scene or a visible cutter before selecting geometry")
            if self.mode.text == "Pick component":
                self.pick(touch.pos)
                return True
            if ws.app.playing or ws.app.state not in ("Idle", "N/A"):
                raise ValueError("Stop playback before editing the local scene")
            center = self.center()
            if center is None:
                raise ValueError(
                    (
                        "Select visible declared stock to rotate"
                        if self.mode.text == "Rotate stock Z"
                        else "Select a visible vise with CAD geometry to rotate"
                    )
                    if self.rotating
                    else "Select visible stock or a vise before moving its handle"
                )
            self.refresh_handle()
            hit = (
                near_polyline(self.window_pos(touch.pos), self.ring.points, dp(10))
                if self.rotating
                else sum((self.window_pos(touch.pos)[i] - self.handle.circle[i]) ** 2 for i in (0, 1)) <= dp(18) ** 2
            )
            if self.color.a == 0 or not hit:
                return False
            kind = "stock" if center[0] == "stock" else "workholding"
            profile = getattr(ws, "selected_machine_profile", None) or {}
            if (profile.get("id"), kind) in getattr(ws, "setup_drafts", {}):
                raise ValueError("Review the retained setup draft before starting a new placement gesture")
            inverse = self._inverse()
            origin, direction = self.screen_ray(touch.pos, inverse)
            normal = (0, 0, 1) if self.mode.text == "Move XY" or self.rotating else (direction[0], direction[1], 0)
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
                "axis": "rotate" if self.rotating else self.mode.text[-2:].strip(),
                "snap": self.angle_snap.value() if self.rotating else self.snap.value(),
                "previous": start,
                "angle": 0,
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
            if gesture["axis"] == "rotate":
                gesture["angle"] += rotation_step(gesture["previous"], point, gesture["center"])
                gesture["previous"] = point
                gesture["delta"] = (0, 0, snap_angle(gesture["angle"], gesture["snap"]))
                self.note.text = f"Rotation draft: {gesture['delta'][2]:g}° · release to review"
                pivot = self.project(gesture["center"])
                self.guide.points = [*pivot[:2], *self.window_pos(touch.pos)] if pivot else []
            else:
                gesture["delta"] = placement_delta(gesture["start"], point, gesture["axis"], gesture["snap"])
                self.guide.points = [*gesture["screen"], *self.window_pos(touch.pos)]
                self.note.text = (
                    "Placement draft Δ XYZ: "
                    + ", ".join(f"{v:g} mm" for v in gesture["delta"])
                    + " · release to review"
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
        if gesture["axis"] == "rotate":
            field = "stock_rotation_deg" if gesture["kind"] == "stock" else "workholding_rotation_deg"
            angle = canonical_angle(gesture["setup"][field] + gesture["delta"][2])
            editor.fields[(field, None)].text = f"{angle:.12g}°"
        else:
            field = "stock_origin_mm" if gesture["kind"] == "stock" else "workholding_offset_mm"
            for axis in range(3):
                editor.fields[(field, axis)].text = f"{gesture['setup'][field][axis] + gesture['delta'][axis]:.12g} mm"
        self.note.text = "Placement draft ready · Apply saves the local setup; Cancel preserves it"

    def frame_selected(self):
        """Frame actual displayed bounds; cutter processing stays off the UI thread."""
        viewer, ws = self.viewer, self.workspace
        selected = ws.object_inspector.selected
        if self.gesture is not None or viewer.width <= 0 or viewer.height <= 0:
            self.note.text = "Finish the gesture and show the viewport before framing"
            return
        cutter = viewer.inspection_cutter_snapshot() if selected == "cutter" else None
        geometry = viewer._inspection_geometry
        pose = dict(viewer._machine_pose)
        view = (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
        viewport = self.viewport()
        visibility = dict(viewer.machine_group_visibility)
        machine_visible = viewer.machine_visible
        bounds = []
        if machine_visible and selected != "cutter":
            for group in GEOMETRY_GROUPS.get(selected, ()):
                bound = viewer._inspection_bounds.get(group)
                if bound is not None and visibility.get(group, True):
                    movement = self.movement(group)
                    bounds.append(tuple(tuple(point[i] + movement[i] for i in range(3)) for point in bound))
        if cutter is None and not bounds:
            self.note.text = "Show the selected component before framing it"
            return
        self.request += 1
        request = self.request
        self.note.text = "Framing selected component…"

        def work():
            failure = ""
            try:
                candidates = [geometry_bounds(render_tool_snapshot(cutter))] if cutter is not None else bounds
                candidates = [bound for bound in candidates if bound is not None]
                result = (
                    tuple(min(bound[0][i] for bound in candidates) for i in range(3)),
                    tuple(max(bound[1][i] for bound in candidates) for i in range(3)),
                )
            except (ValueError, IndexError, ArithmeticError) as exc:
                failure, result = str(exc), None

            def done(_dt):
                if (
                    request != self.request
                    or self.gesture is not None
                    or ws.active_section != "Scene"
                    or ws.object_inspector.selected != selected
                    or geometry is not viewer._inspection_geometry
                    or pose != viewer._machine_pose
                    or view != (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
                    or viewport != self.viewport()
                    or visibility != viewer.machine_group_visibility
                    or machine_visible != viewer.machine_visible
                    or (selected == "cutter" and cutter != viewer.inspection_cutter_snapshot())
                ):
                    if request == self.request and self.gesture is None and ws.active_section == "Scene":
                        self.note.text = "View changed while framing · try again"
                    return
                if result is None:
                    self.note.text = "Cannot frame selected component · " + failure
                    return
                from carveracontroller.GcodeViewer import DEFAULT_ZOOM, PROJ_NEAR

                low, high = result
                scale = viewer.move_scale_by_positon or 1
                center = tuple((low[i] + high[i]) / 2 for i in range(3))
                radius = math.hypot(*(high[i] - low[i] for i in range(3))) * scale / 2
                tangent = DEFAULT_ZOOM / (2 * PROJ_NEAR) * min(1, viewer.width / max(viewer.height, 1))
                viewer.m_distance = max(2 * PROJ_NEAR, radius * math.sqrt(1 + tangent * tangent) / tangent * 1.12)
                viewer.m_xLookAt, viewer.m_yLookAt, viewer.m_zLookAt = tuple(
                    (center[i] - viewer.machine_setup.work_offset_mm[i]) * scale - viewer.lines_center[i]
                    for i in range(3)
                )
                viewer.m_zoom = viewer._default_zoom_for_projection()
                viewer.m_xPan = viewer.m_yPan = 0
                viewer.update_proj()
                viewer.update_view()
                viewer._scene_dirty = True
                self.note.text = "Framed selected component · " + selected

            Clock.schedule_once(done, 0)

        threading.Thread(target=work, name="scene-component-frame", daemon=True).start()

    def pick(self, pos):
        if self.picking:
            self.note.text = "Picking rendered geometry…"
            return
        viewer = self.viewer
        origin, direction = self.screen_ray(pos)
        geometry = viewer._inspection_geometry
        machine_visible = viewer.machine_visible
        cutter = viewer.inspection_cutter_snapshot()
        view = (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
        viewport = self.viewport()
        visibility = dict(viewer.machine_group_visibility)
        components = [
            (key, geometry[group], self.movement(group))
            for key, groups in GEOMETRY_GROUPS.items()
            for group in groups
            if machine_visible and group in geometry and viewer.machine_group_visibility.get(group, True)
        ]
        self.request += 1
        request = self.request
        self.picking = True
        self.note.text = "Picking rendered geometry…"

        def work():
            try:
                surfaces = components
                if cutter is not None:
                    surfaces = [*components, ("cutter", render_tool_snapshot(cutter), (0, 0, 0))]
                result = pick_geometry(origin, direction, surfaces, max_distance=math.hypot(*direction))
            except (ValueError, IndexError, ArithmeticError):
                result = None

            def done(_dt):
                self.picking = False
                if (
                    request != self.request
                    or geometry is not viewer._inspection_geometry
                    or cutter != viewer.inspection_cutter_snapshot()
                    or self.mode.text != "Pick component"
                    or self.workspace.active_section != "Scene"
                    or view != (viewer.m_viewMatrix.get(), viewer._proj_matrix.get())
                    or viewport != self.viewport()
                    or visibility != viewer.machine_group_visibility
                    or machine_visible != viewer.machine_visible
                ):
                    if (
                        request == self.request
                        and self.mode.text == "Pick component"
                        and self.workspace.active_section == "Scene"
                    ):
                        self.note.text = "View changed while picking · click again"
                    return
                if result is None:
                    self.note.text = "No rendered surface at this point"
                    return
                self.workspace.object_inspector.select(result[0], reveal=False)
                self.note.text = "Selected rendered surface · " + result[0]

            Clock.schedule_once(done, 0)

        threading.Thread(target=work, name="scene-surface-pick", daemon=True).start()
