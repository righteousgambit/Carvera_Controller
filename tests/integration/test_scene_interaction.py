from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.graphics.transformation import Matrix

from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.machine.scene_interaction import plane_point
from tests.integration import test_setup_editor
from tests.integration.conftest import pump_frames
from tests.integration.test_setup_editor import apply_editor


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    yield from test_setup_editor.setup_workspace.__wrapped__(kivy_app, tmp_path, monkeypatch)


def test_atc_marker_projects_into_actual_viewport_and_tracks_visibility(setup_workspace, monkeypatch):
    from kivy.core.window import Window

    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    ws, send = setup_workspace
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "disabled", False)
    ws.select("Scene")
    viewer.set_machine_visible(True)
    viewer.configure_machine((-180, -120, -110), (30, 20, 10), (0, 0, 0))
    viewer.restore_default_view()
    pump_frames(5)
    monkeypatch.setattr(viewer, "machine_profile", MachineProfile(profile_data()))
    monkeypatch.setattr(
        ws,
        "slot_inventory_panel",
        SimpleNamespace(overlay_rows=lambda: tuple((number, (-165, -110, -100)) for number in range(6))),
    )
    monkeypatch.setitem(viewer.machine_group_visibility, "atc", True)
    interaction.refresh_handle()
    pump_frames(3)
    interaction.refresh_handle()
    marker = interaction.slot_overlay.markers[0]
    assert marker[0].a == 1 and marker[3] == 0
    screen = interaction.project(
        viewer.machine_profile.configured_atc_target((-165, -110, -100), viewer._machine_pose["table"])
    )
    assert marker[1].circle[:2] == pytest.approx(screen[:2])
    captions = []
    for target in interaction.slot_overlay.markers:
        assert target[0].a == 1
        assert target[1].circle[:2] == pytest.approx(screen[:2])
        assert target[4].points[:2] == pytest.approx(screen[:2])
        captions.append((target[2].pos[1], target[2].pos[1] + target[2].size[1]))
    ordered = sorted(captions)
    assert all(a[1] < b[0] for a, b in zip(ordered, ordered[1:]))
    Window.screenshot(name="/tmp/carvera-atc-scene-target.png")
    monkeypatch.setitem(viewer.machine_group_visibility, "atc", False)
    interaction.refresh_handle()
    assert marker[0].a == 0
    send.assert_not_called()


def test_visibility_readback_does_not_rebuild_or_save_the_scene(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    # Restore injected failures before the shared fixture restores real geometry.
    with monkeypatch.context() as scoped:
        viewer = ws.machine.gcode_viewer
        check = ws.component_checks["stock"]
        scoped.setitem(viewer.machine_group_visibility, "stock", not check.active)
        rebuild = Mock(wraps=viewer._build_machine_scene)
        scoped.setattr(viewer, "_build_machine_scene", rebuild)
        ws.refresh(0)
        assert check.active == viewer.machine_group_visibility["stock"]
        rebuild.assert_not_called()
        assert not ws.scene_setup_store.path.exists()
        viewer.set_machine_group_visible("stock", check.active)
        rebuild.assert_not_called()
        scene = Mock(side_effect=AssertionError("Fit should use the rendered geometry bounds"))
        scoped.setattr(viewer, "_machine_scene", scene)
        viewer._fit_machine_view()
        scene.assert_not_called()
        scoped.setattr(viewer, "_inspection_bounds", {})
        viewer._fit_machine_view()
        import math

        assert math.isfinite(viewer.m_distance)
        assert all(math.isfinite(value) for value in (viewer.m_xLookAt, viewer.m_yLookAt, viewer.m_zLookAt))
        send.assert_not_called()


@pytest.mark.parametrize("perspective", [False, True])
def test_projection_ray_roundtrip_in_machine_coordinates(setup_workspace, monkeypatch, perspective):
    ws, send = setup_workspace
    interaction = ws.scene_interaction
    viewer = interaction.viewer
    monkeypatch.setattr(viewer, "m_viewMatrix", Matrix().look_at(0, -20, 20, 0, 0, 0, 0, 0, 1))
    projection = Matrix()
    projection.view_clip(-2, 2, -1, 1, 1, 100, perspective)
    monkeypatch.setattr(viewer, "_proj_matrix", projection)
    monkeypatch.setattr(viewer, "move_scale_by_positon", 0.5)
    monkeypatch.setattr(viewer, "lines_center", (1, 2, 3))
    rendered = (1, 0, 0)
    offset = viewer.machine_setup.work_offset_mm
    target = tuple((rendered[i] + viewer.lines_center[i]) / 0.5 + offset[i] for i in range(3))
    screen = viewer.m_viewMatrix.project(
        *rendered, viewer.m_viewMatrix, projection, *viewer._view_cube_gl_origin(), viewer.width, viewer.height
    )
    origin, direction = interaction.screen_ray(viewer.parent.to_widget(*screen[:2]))
    assert plane_point(origin, direction, target, (0, 0, 1)) == pytest.approx(target, abs=1e-5)
    send.assert_not_called()


def begin_drag(ws, monkeypatch):
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    ws.active_section = "Scene"
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "machine_visible", True)
    interaction.mode.text = "Move XY"
    monkeypatch.setattr(interaction, "center", lambda: ("stock", (0, 0, 0)))
    monkeypatch.setattr(interaction, "refresh_handle", lambda *args: None)
    monkeypatch.setattr(interaction, "window_pos", lambda pos: pos)
    interaction.color.a = 1
    interaction.handle.circle = (10, 10, 8)
    monkeypatch.setattr(interaction, "screen_ray", lambda pos, inverse=None: ((pos[0], pos[1], 10), (0, 0, -1)))
    touch = SimpleNamespace(pos=(10, 10), button="left")
    assert interaction.down(touch)
    assert interaction.gesture is not None
    touch.pos = (12, 13)
    return interaction, touch


def test_drag_creates_reviewed_draft_without_changing_scene_then_apply_persists(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    configure = Mock(wraps=interaction.viewer.configure_machine)
    monkeypatch.setattr(interaction.viewer, "configure_machine", configure)
    interaction.move(touch)
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    configure.assert_not_called()
    interaction.up(touch)
    editor = ws.setup_editor
    assert editor.fields["stock_origin_mm", 0].value() == before["stock_origin_mm"][0] + 2
    assert editor.fields["stock_origin_mm", 1].value() == before["stock_origin_mm"][1] + 3
    assert capture_scene_setup(ws) == before
    assert apply_editor(editor)
    assert ws.scene_setup_store.get("editor-machine") == capture_scene_setup(ws)
    send.assert_not_called()


@pytest.mark.parametrize("change", ["profile", "camera", "state", "viewport"])
def test_changed_context_discards_gesture(setup_workspace, monkeypatch, change):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.move(touch)
    if change == "profile":
        ws.selected_machine_profile = {"id": "different"}
    elif change == "camera":
        monkeypatch.setattr(interaction.viewer, "m_viewMatrix", Matrix().translate(1, 0, 0))
    elif change == "state":
        ws.app.state = "Run"
    else:
        monkeypatch.setattr(interaction.viewer, "width", interaction.viewer.width + 1)
    interaction.up(touch)
    assert interaction.gesture is None
    assert "discarded" in interaction.note.text
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    send.assert_not_called()


def test_cancel_placement_and_default_view(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.up(touch)
    ws.setup_editor.cancel()
    pump_frames(10, sleep=0.03)
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    interaction.mode.text = "View"
    assert not interaction.down(touch)
    send.assert_not_called()


def test_retained_draft_is_not_overwritten_by_drag(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.gesture = None
    ws.setup_drafts[("editor-machine", "stock")] = {"sentinel": "operator draft"}
    touch.pos = (10, 10)
    assert interaction.down(touch)
    assert interaction.gesture is None
    assert ws.setup_drafts[("editor-machine", "stock")] == {"sentinel": "operator draft"}
    assert "retained" in interaction.note.text
    send.assert_not_called()


def test_invalid_drag_point_discards_entire_gesture(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    interaction, touch = begin_drag(ws, monkeypatch)
    interaction.move(touch)
    monkeypatch.setattr(interaction, "screen_ray", Mock(side_effect=ValueError("invalid ray")))
    interaction.up(touch)
    assert interaction.gesture is None
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    assert "discarded" in interaction.note.text
    send.assert_not_called()


@pytest.mark.parametrize("stale", [False, True, "cutaway", "explosion"])
def test_surface_pick_delivers_only_current_view(setup_workspace, monkeypatch, stale):
    ws, send = setup_workspace
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    from carveracontroller import desktop_scene_interaction as module
    from carveracontroller.addons.machine_simulation.model import Geometry

    geometry = Geometry()
    geometry.triangle(((0, 0, 0), (2, 0, 0), (0, 2, 0)), (0, 0, 1), (1, 1, 1, 1))
    monkeypatch.setattr(viewer, "_inspection_geometry", {"stock": geometry})
    monkeypatch.setattr(viewer, "_machine_pose", {**viewer._machine_pose, "table": (0, 0, 0)})
    monkeypatch.setattr(viewer, "machine_visible", True)
    monkeypatch.setattr(viewer, "machine_group_visibility", {**viewer.machine_group_visibility, "stock": True})
    monkeypatch.setattr(interaction, "screen_ray", lambda pos: ((0.5, 0.5, 10), (0, 0, -20)))
    ws.active_section = "Scene"
    interaction.mode.text = "Pick component"
    selected = Mock()
    monkeypatch.setattr(ws.object_inspector, "select", selected)
    # Execute worker deterministically, leaving delivery on the actual UI Clock.
    monkeypatch.setattr(module.threading, "Thread", lambda **kwargs: SimpleNamespace(start=kwargs["target"]))
    interaction.pick((10, 10))
    if stale == "cutaway":
        from carveracontroller.machine.section_view import SectionClip

        monkeypatch.setattr(viewer, "component_cutaways", {"stock": SectionClip(2, -1)})
    elif stale == "explosion":
        monkeypatch.setattr(viewer, "explosion_mm", viewer.explosion_mm)
        viewer.set_pose_mode("Preview")
        viewer.set_explosion(25)
    elif stale:
        monkeypatch.setattr(viewer, "m_viewMatrix", Matrix().translate(3, 0, 0))
    pump_frames(3)
    if stale:
        selected.assert_not_called()
    else:
        selected.assert_called_once_with("stock", reveal=False)
        monkeypatch.setattr(ws.object_inspector, "selected", "stock")
        hit = interaction.selected_surface()
        assert hit.component_point_mm == pytest.approx((0.5, 0.5, 0))
        assert hit.normal == pytest.approx((0, 0, 1))
        assert "not a measured datum" in interaction.note.text
        from carveracontroller.desktop_surface_measurement import SurfaceMeasurementReview

        review = SurfaceMeasurementReview(interaction)
        assert review.plan.contact_center_mm == pytest.approx((0.5, 0.5, 1))
        assert "Expected ball center" in review.result.text
        review.direction.text = "X+"
        assert review.plan is None
        assert "Approach must move into" in review.result.text
        review.direction.text = "Z−"
        review.fields["tip"].text = "0.125 in"
        assert review.plan.tip_radius_mm == pytest.approx(1.5875)
        review.open()
        pump_frames(5)
        from kivy.core.window import Window

        Window.screenshot(name="/tmp/carvera-surface-measurement-review.png")
        monkeypatch.setattr(viewer, "disabled", False)
        monkeypatch.setattr(interaction, "project", lambda p: (100 + p[0] * 2, 200 + p[1] * 2, 0.5))
        review.preview()
        assert interaction.measurement_preview[0].tip_radius_mm == pytest.approx(1.5875)
        assert interaction.measurement_color.a == 1
        assert interaction.measurement_line.points == pytest.approx([101, 201] * 3)
        assert all(color.a == 1 for color, _, _ in interaction.measurement_markers)
        from kivy.metrics import dp

        for _, marker, radius in interaction.measurement_markers:
            assert marker.pos == pytest.approx((101 - dp(radius), 201 - dp(radius)))
            assert marker.size == pytest.approx((dp(radius * 2), dp(radius * 2)))
        assert "amber contact center" in interaction.measurement_note.text
        assert not interaction.clear_measurement_button.disabled
        interaction.clear_measurement_button.trigger_action(0)
        pump_frames(2)
        assert interaction.measurement_preview is None
        assert interaction.clear_measurement_button.disabled
        assert not interaction.measurement_note.text
        assert all(color.a == 0 for color, _, _ in interaction.measurement_markers)
        interaction.preview_measurement(review.plan)
        viewer.machine_group_visibility["stock"] = False
        interaction.refresh_measurement_preview()
        assert interaction.measurement_color.a == 0
        assert all(color.a == 0 for color, _, _ in interaction.measurement_markers)
        viewer.machine_group_visibility["stock"] = True
        from carveracontroller.machine.section_view import SectionClip

        viewer.set_component_cutaway("stock", SectionClip(2, -1))
        assert interaction.selected_surface() is None
        interaction.refresh_measurement_preview()
        assert interaction.measurement_preview is None
        assert all(color.a == 0 for color, _, _ in interaction.measurement_markers)
        viewer.set_component_cutaway("stock", None)
        interaction.preview_measurement(review.plan)
        viewer._machine_pose = {**viewer._machine_pose, "table": (0, 1, 0)}
        assert interaction.selected_surface() is None
        interaction.refresh_measurement_preview()
        assert interaction.measurement_preview is None
        assert not interaction.measurement_line.points
        assert interaction.clear_measurement_button.disabled
        assert not interaction.measurement_note.text
        review.refresh()
        assert review.plan is None
        assert "changed" in review.result.text
        # Resizing may rebuild geometry; do not reuse the old nominal reference.
        review.open()
        original_size = Window.system_size
        try:
            Window.size = (560, 700)
            pump_frames(5)
            review.refresh()
            assert review.plan is None
            for field in review.fields.values():
                assert field.width <= review.popup.width
            Window.screenshot(name="/tmp/carvera-surface-measurement-narrow.png")
        finally:
            review.close()
            Window.size = original_size
            pump_frames(3)
    assert not interaction.picking
    send.assert_not_called()


def test_real_stock_handle_render_and_task_visibility(setup_workspace, monkeypatch):
    from kivy.core.window import Window

    ws, send = setup_workspace
    interaction, viewer = ws.scene_interaction, ws.machine.gcode_viewer
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "disabled", False)
    ws.select("Scene")
    ws.object_inspector.select("stock", reveal=False)
    viewer.set_machine_visible(True)
    viewer.configure_machine((-180, -120, -110), (30, 20, 10), (0, 0, 0))
    interaction.mode.text = "Move XY"
    viewer.restore_default_view()
    pump_frames(5)
    interaction.refresh_handle()
    assert interaction.center() is not None
    assert interaction.color.a == 1
    x, y = interaction.handle.circle[:2]
    local = viewer.parent.to_widget(x, y)
    assert viewer.collide_point(*local)
    Window.screenshot(name="/tmp/carvera-scene-handle.png")
    before = capture_scene_setup(ws)
    touch = SimpleNamespace(pos=local, button="left")
    assert interaction.down(touch)
    assert interaction.gesture is not None
    touch.pos = viewer.parent.to_widget(x + 25, y + 15)
    interaction.up(touch)
    assert ws.setup_editor is not None
    assert capture_scene_setup(ws) == before
    ws.setup_editor.cancel()
    pump_frames(10, sleep=0.03)
    ws.select("Job")
    interaction.refresh_handle()
    assert interaction.color.a == 0
    send.assert_not_called()


def prepare_vise_rotation(ws, monkeypatch):
    from carveracontroller.addons.machine_simulation.model import Geometry
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    geometry = Geometry()
    geometry.box((150, 100, 40), (210, 140, 60), (1, 1, 1, 1))
    data = profile_data()
    data["components"].append({"group": "workholding", "vertices": geometry.vertices})
    data["workholding"] = {"pivot_mm": (180, 120, 40)}
    viewer, interaction = ws.machine.gcode_viewer, ws.scene_interaction
    monkeypatch.setattr(viewer, "machine_component_profiles", {"workholding": MachineProfile(data)})
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "disabled", False)
    ws.select("Scene")
    viewer.set_machine_visible(True)
    viewer.configure_machine((-180, -120, -110), (30, 20, 10))
    viewer.configure_workholding((10, 15, 5), 20, 0)
    ws.object_inspector.select("workholding", reveal=False)
    interaction.mode.text = "Rotate vise Z"
    pump_frames(5)
    interaction.refresh_handle()
    return interaction


@pytest.mark.parametrize("apply", [False, True])
def test_real_vise_rotation_ring_creates_reviewed_persistent_angle(setup_workspace, monkeypatch, apply):
    import math

    from kivy.core.window import Window

    ws, send = setup_workspace
    interaction = prepare_vise_rotation(ws, monkeypatch)
    viewer = interaction.viewer
    before = capture_scene_setup(ws)
    pivot = interaction.center()[1]
    assert pivot == pytest.approx(tuple(a + b for a, b in zip((-170, -105, -95), viewer._machine_pose["table"])))
    assert len(interaction.ring.points) == 130
    x, y = interaction.ring.points[:2]
    touch = SimpleNamespace(pos=viewer.parent.to_widget(x, y), button="left")
    assert interaction.down(touch)
    assert interaction.gesture is not None
    start = interaction.gesture["start"]
    radius = math.hypot(start[0] - pivot[0], start[1] - pivot[1])
    angle = math.atan2(start[1] - pivot[1], start[0] - pivot[0]) + math.radians(32)
    target = interaction.project((pivot[0] + radius * math.cos(angle), pivot[1] + radius * math.sin(angle), pivot[2]))
    touch.pos = viewer.parent.to_widget(*target[:2])
    interaction.move(touch)
    assert interaction.gesture["delta"][2] == 30
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    Window.screenshot(name="/tmp/carvera-vise-rotation.png")
    interaction.up(touch)
    editor = ws.setup_editor
    assert editor.fields["workholding_rotation_deg", None].value() == 50
    assert capture_scene_setup(ws) == before
    if apply:
        assert apply_editor(editor)
        after = capture_scene_setup(ws)
        assert after["workholding_rotation_deg"] == 50
        assert after["workholding_offset_mm"] == before["workholding_offset_mm"]
        assert ws.scene_setup_store.get("editor-machine") == after
    else:
        editor.cancel()
        pump_frames(10, sleep=0.03)
        assert capture_scene_setup(ws) == before
        assert not ws.scene_setup_store.path.exists()
    send.assert_not_called()


def test_rotation_requires_vise_and_preserves_existing_draft(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    interaction = prepare_vise_rotation(ws, monkeypatch)
    ws.object_inspector.select("stock", reveal=False)
    assert interaction.center() is None
    touch = SimpleNamespace(pos=(10, 10), button="left")
    assert interaction.down(touch)
    assert "vise" in interaction.note.text
    assert interaction.gesture is None
    ws.object_inspector.select("workholding", reveal=False)
    interaction.refresh_handle()
    ws.setup_drafts[("editor-machine", "workholding")] = {"sentinel": "existing draft"}
    touch.pos = interaction.viewer.parent.to_widget(*interaction.ring.points[:2])
    assert interaction.down(touch)
    assert interaction.gesture is None
    assert "retained" in interaction.note.text
    assert ws.setup_drafts[("editor-machine", "workholding")] == {"sentinel": "existing draft"}
    send.assert_not_called()


@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("scene_visible", [False, True])
@pytest.mark.parametrize("exploded", [False, True])
def test_pick_actual_displayed_cutter_and_reject_changed_mesh(
    setup_workspace, monkeypatch, stale, scene_visible, exploded
):
    from carveracontroller import desktop_scene_interaction as module
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
    from carveracontroller.machine.scene_interaction import render_tool_snapshot

    ws, send = setup_workspace
    viewer, interaction = ws.machine.gcode_viewer, ws.scene_interaction
    saved_tools, saved_override = dict(viewer.library_tool_table_mm), viewer.preview_tool_override
    saved_visibility = dict(viewer.machine_group_visibility)
    saved_machine_visible, saved_cutter_visible = viewer.machine_visible, viewer.cutter_visible
    try:
        monkeypatch.setattr(ws.app, "playing", False)
        monkeypatch.setattr(ws.app, "state", "Idle")
        ws.select("Scene")
        viewer.set_machine_visible(True)
        viewer.configure_machine((-180, -120, -110), (30, 20, 10))
        for group in list(viewer.machine_group_visibility):
            viewer.set_machine_group_visible(group, False)
        tool = ToolDefinition(7, ToolType.FLAT_END_MILL, diameter=6, shank_diameter=6, length=30, flute_length=15)
        viewer.load_tool_profiles({7: tool}, replace=True)
        ws.enter_preview()
        viewer.select_preview_tool(7)
        viewer.set_cutter_visible(True)
        viewer.set_machine_visible(scene_visible)
        interaction.mode.text = "Pick component"
        viewer._update_static_cutter()
        viewer.set_explosion(25 if exploded else 0)
        pump_frames(4)
        snapshot = viewer.inspection_cutter_snapshot()
        assert snapshot is not None
        ws.object_inspector.select("cutter", reveal=False)
        interaction.frame_selected()
        pump_frames(10, sleep=0.01)
        assert "Framed" in interaction.note.text
        snapshot = viewer.inspection_cutter_snapshot()
        geometry = render_tool_snapshot(snapshot)
        bounds = [geometry.vertices[i::10] for i in range(3)]
        shift = viewer.explosion_offset("cutter")
        center = tuple((min(values) + max(values)) / 2 + shift[i] for i, values in enumerate(bounds))
        screen = interaction.project(center)
        origin_x, origin_y, width, height = interaction.viewport()
        for index in set(geometry.indices):
            point = geometry.vertices[index * 10 : index * 10 + 3]
            projected = interaction.project(tuple(point[i] + shift[i] for i in range(3)))
            assert projected is not None
            assert origin_x <= projected[0] <= origin_x + width
            assert origin_y <= projected[1] <= origin_y + height
        selected = Mock()
        monkeypatch.setattr(ws.object_inspector, "select", selected)
        monkeypatch.setattr(module.threading, "Thread", lambda **kwargs: SimpleNamespace(start=kwargs["target"]))
        interaction.pick(viewer.parent.to_widget(*screen[:2]))
        if stale:
            replacement = ToolDefinition(
                7, ToolType.FLAT_END_MILL, diameter=12, shank_diameter=12, length=30, flute_length=15
            )
            viewer.load_tool_profiles({7: replacement}, replace=True)
        pump_frames(3)
        if stale:
            selected.assert_not_called()
        else:
            selected.assert_called_once_with("cutter", reveal=False)
        viewer.set_cutter_visible(False)
        assert viewer.inspection_cutter_snapshot() is None
        send.assert_not_called()
    finally:
        viewer.set_explosion(0)
        viewer.load_tool_profiles(saved_tools, replace=True)
        viewer.select_preview_tool(saved_override)
        viewer.set_cutter_visible(saved_cutter_visible)
        for group, visible in saved_visibility.items():
            viewer.set_machine_group_visible(group, visible)
        viewer.set_machine_visible(saved_machine_visible)


@pytest.mark.parametrize("change", ["camera", "task"])
def test_async_component_framing_rejects_context_changes(setup_workspace, monkeypatch, change):
    from carveracontroller import desktop_scene_interaction as module

    ws, send = setup_workspace
    viewer, interaction = ws.machine.gcode_viewer, ws.scene_interaction
    ws.select("Scene")
    viewer.set_machine_visible(True)
    viewer.configure_machine((-180, -120, -110), (30, 20, 10))
    viewer.set_machine_group_visible("stock", True)
    ws.object_inspector.select("stock", reveal=False)
    pending = []
    monkeypatch.setattr(
        module.threading, "Thread", lambda **kwargs: SimpleNamespace(start=lambda: pending.append(kwargs["target"]))
    )
    interaction.frame_selected()
    assert len(pending) == 1
    if change == "camera":
        viewer.m_xLookAt += 3
        viewer.update_view()
    else:
        ws.select("Position")
    after = viewer.m_viewMatrix.get()
    pending.pop()()
    pump_frames(3)
    assert viewer.m_viewMatrix.get() == after
    if change == "camera":
        assert "changed while framing" in interaction.note.text
    else:
        assert ws.active_section == "Position"
    send.assert_not_called()


@pytest.mark.parametrize("active", [3, None])
def test_cutter_inspector_describes_displayed_not_pending_tool(setup_workspace, monkeypatch, active):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {
            3: ToolDefinition(3, ToolType.FLAT_END_MILL, diameter=4, length=20, flute_length=10),
            7: ToolDefinition(7, ToolType.FLAT_END_MILL, diameter=6, length=30, flute_length=15),
        },
    )
    monkeypatch.setattr(viewer, "_active_tool_number", active)
    monkeypatch.setattr(viewer, "_tool_number_at_index", lambda _index: 7)
    monkeypatch.setattr(viewer, "pose_mode", "Preview")
    ws.object_inspector.select("cutter", reveal=False)
    facts = ws.object_inspector.facts.text
    assert "Requested T7" in facts
    assert "Displayed preview T7" not in facts
    if active is None:
        assert "Displayed cutter identity unavailable" in facts
    else:
        assert "Displayed preview T3" in facts
        assert "Diameter 4 mm" in facts
    send.assert_not_called()


@pytest.mark.parametrize("apply", [False, True])
def test_stock_rotation_ring_reviews_angle_about_declared_center(setup_workspace, monkeypatch, apply):
    import math

    from kivy.core.window import Window

    ws, send = setup_workspace
    viewer, interaction = ws.machine.gcode_viewer, ws.scene_interaction
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(viewer, "disabled", False)
    ws.select("Scene")
    viewer.set_machine_visible(True)
    viewer.set_machine_group_visible("stock", True)
    viewer.configure_machine((-180, -120, -110), (40, 20, 10), (-20, -10, 0), stock_rotation_deg=20)
    ws.object_inspector.select("stock", reveal=False)
    interaction.mode.text = "Rotate stock Z"
    pump_frames(5)
    interaction.refresh_handle()
    before = capture_scene_setup(ws)
    pivot = interaction.center()[1]
    assert pivot == pytest.approx(tuple(a + b for a, b in zip((-180, -120, -105), viewer._machine_pose["table"])))
    assert len(interaction.ring.points) == 130
    touch = SimpleNamespace(pos=viewer.parent.to_widget(*interaction.ring.points[:2]), button="left")
    assert interaction.down(touch)
    start = interaction.gesture["start"]
    radius = math.hypot(start[0] - pivot[0], start[1] - pivot[1])
    angle = math.atan2(start[1] - pivot[1], start[0] - pivot[0]) + math.radians(32)
    target = interaction.project((pivot[0] + radius * math.cos(angle), pivot[1] + radius * math.sin(angle), pivot[2]))
    touch.pos = viewer.parent.to_widget(*target[:2])
    interaction.move(touch)
    assert interaction.gesture["delta"][2] == 30
    assert capture_scene_setup(ws) == before
    Window.screenshot(name="/tmp/carvera-stock-rotation-ring.png")
    interaction.up(touch)
    editor = ws.setup_editor
    assert editor.fields["stock_rotation_deg", None].value() == 50
    assert capture_scene_setup(ws) == before
    if apply:
        assert apply_editor(editor)
        after = capture_scene_setup(ws)
        assert after["stock_rotation_deg"] == 50
        assert after["stock_origin_mm"] == before["stock_origin_mm"]
        assert after["stock_size_mm"] == before["stock_size_mm"]
        assert after["work_offset_mm"] == before["work_offset_mm"]
        assert ws.scene_setup_store.get("editor-machine") == after
    else:
        editor.cancel()
        pump_frames(10, sleep=0.03)
        assert capture_scene_setup(ws) == before
        assert not ws.scene_setup_store.path.exists()
    send.assert_not_called()


def test_stock_rotation_pivot_ignores_asymmetric_rest_geometry(setup_workspace, monkeypatch):
    from carveracontroller.addons.machine_simulation.model import Geometry

    ws, send = setup_workspace
    viewer, interaction = ws.machine.gcode_viewer, ws.scene_interaction
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws.app, "state", "Idle")
    ws.select("Scene")
    viewer.set_machine_visible(True)
    viewer.set_machine_group_visible("stock", True)
    viewer.configure_machine((-180, -120, -110), (40, 20, 10), (-20, -10, 0), stock_rotation_deg=20)
    residual = Geometry()
    residual.box((-20, -10, 0), (-10, -5, 5), (1, 1, 1, 1))
    viewer.set_rest_stock_geometry(residual)
    ws.object_inspector.select("stock", reveal=False)
    interaction.mode.text = "Rotate stock Z"
    pump_frames(3)
    expected = tuple(a + b for a, b in zip((-180, -120, -105), viewer._machine_pose["table"]))
    assert interaction.center()[1] == pytest.approx(expected)
    ws.setup_drafts[("editor-machine", "stock")] = {"sentinel": "retained stock draft"}
    interaction.refresh_handle()
    touch = SimpleNamespace(pos=viewer.parent.to_widget(*interaction.ring.points[:2]), button="left")
    assert interaction.down(touch)
    assert interaction.gesture is None
    assert "retained" in interaction.note.text
    assert ws.setup_drafts[("editor-machine", "stock")]["sentinel"] == "retained stock draft"
    send.assert_not_called()
