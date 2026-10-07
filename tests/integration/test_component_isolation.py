from copy import deepcopy
from unittest.mock import Mock

import pytest

from carveracontroller.addons.machine_simulation.model import Geometry
from carveracontroller.desktop_scene import capture_scene_setup
from carveracontroller.desktop_view_state import capture_view, restore_view
from tests.integration import test_setup_editor
from tests.integration.conftest import pump_frames


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    for ws, send in test_setup_editor.setup_workspace.__wrapped__(kivy_app, tmp_path, monkeypatch):
        viewer = ws.machine.gcode_viewer
        groups = dict(viewer.machine_group_visibility)
        cutter, machine, scope = viewer.cutter_visible, viewer.machine_visible, viewer.machine_view_scope
        view, saved_camera = capture_view(viewer), viewer._machine_camera_saved
        rotary = viewer._machine_has_rotary_motion
        try:
            yield ws, send
        finally:
            viewer._machine_has_rotary_motion = False
            viewer.set_scene_component_visibility(
                groups, cutter_visible=cutter, machine_visible=machine, view_scope=scope
            )
            restore_view(viewer, view)
            viewer._machine_camera_saved = saved_camera
            ws.object_inspector.isolation = None
            ws.object_inspector.restore_visibility_button.disabled = True
            ws.scene_interaction.request += 1
            ws.object_inspector._refresh_visibility_controls()
            viewer._machine_has_rotary_motion = rotary


def rendered_components(viewer, monkeypatch):
    geometry = Geometry()
    geometry.triangle(((0, 0, 0), (2, 0, 0), (0, 2, 0)), (0, 0, 1), (1, 1, 1, 1))
    monkeypatch.setattr(viewer, "_inspection_geometry", dict.fromkeys(viewer.machine_group_visibility, geometry))


@pytest.mark.parametrize("initial_visible", [True, False])
def test_isolate_repeat_restore_retains_visibility_camera_setup_and_sends_no_commands(
    setup_workspace, monkeypatch, initial_visible
):
    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    ws.select("Scene")
    pump_frames(3)
    viewer.set_machine_visible(initial_visible)
    rendered_components(viewer, monkeypatch)
    before = capture_scene_setup(ws)
    before_view = capture_view(viewer)
    saved_camera = viewer._machine_camera_saved
    monkeypatch.setattr(viewer, "_build_machine_scene", Mock())
    monkeypatch.setattr(ws.scene_setup_store, "save", Mock())
    inspector.select("stock", reveal=False)
    inspector.isolate()
    assert viewer.machine_visible and not viewer.cutter_visible
    assert [key for key, shown in viewer.machine_group_visibility.items() if shown] == ["stock"]
    assert viewer._build_machine_scene.call_count == 1
    assert ws.scene_scope.text == "Work area"
    assert not inspector.restore_visibility_button.disabled
    assert ws.scene_interaction.surface_selection is None
    assert not ws.scene_interaction.pick_candidates
    inspector.select("fixture", reveal=False)
    inspector.isolate()
    assert [key for key, shown in viewer.machine_group_visibility.items() if shown] == ["fixture"]
    assert viewer._build_machine_scene.call_count == 2
    inspector.restore_visibility()
    assert viewer.machine_visible is initial_visible
    assert capture_scene_setup(ws) == before
    assert capture_view(viewer) == before_view
    assert viewer._machine_camera_saved == saved_camera
    assert inspector.restore_visibility_button.disabled and inspector.isolation is None
    assert "restored" in inspector.status.text
    ws.scene_setup_store.save.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("failure", ["missing", "rotary", "profile"])
def test_isolation_rejects_missing_geometry_rotary_and_stale_machine_profiles(setup_workspace, monkeypatch, failure):
    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    ws.select("Scene")
    pump_frames(3)
    rendered_components(viewer, monkeypatch)
    inspector.select("stock", reveal=False)
    before = capture_scene_setup(ws)
    if failure == "profile":
        inspector.isolate()
        isolated = capture_scene_setup(ws)
        monkeypatch.setattr(ws, "selected_machine_profile", {"id": "other-machine"})
        inspector.restore_visibility()
        assert capture_scene_setup(ws) == isolated
        assert "profile changed" in inspector.status.text
        assert inspector.isolation is None and inspector.restore_visibility_button.disabled
    else:
        if failure == "missing":
            monkeypatch.setattr(viewer, "_inspection_geometry", {})
        else:
            monkeypatch.setattr(viewer, "_machine_has_rotary_motion", True)
        inspector.isolate()
        assert capture_scene_setup(ws) == before
        assert inspector.isolation is None and inspector.restore_visibility_button.disabled
    send.assert_not_called()


def test_batch_visibility_validates_before_mutation_and_rebuilds_once(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    viewer.set_machine_visible(True)
    before = capture_scene_setup(ws)
    build = Mock()
    monkeypatch.setattr(viewer, "_build_machine_scene", build)
    values = dict(viewer.machine_group_visibility)
    for invalid in ({}, {**values, "unknown": True}, {**values, "stock": 1}):
        with pytest.raises(ValueError):
            viewer.set_scene_component_visibility(
                invalid, cutter_visible=False, machine_visible=True, view_scope="machine"
            )
        assert capture_scene_setup(ws) == before
        build.assert_not_called()
    changed = {key: key in ("fixed", "carriage") for key in values}
    viewer.set_scene_component_visibility(changed, cutter_visible=False, machine_visible=True, view_scope="machine")
    assert build.call_count == 1
    changed["stock"] = True
    assert not viewer.machine_group_visibility["stock"]
    viewer.set_scene_component_visibility(
        dict(viewer.machine_group_visibility), cutter_visible=False, machine_visible=True, view_scope="machine"
    )
    assert build.call_count == 1
    send.assert_not_called()


@pytest.mark.parametrize("component", ["outer", "cutter"])
def test_isolate_outer_groups_and_cutter_with_compact_controls(setup_workspace, monkeypatch, tmp_path, component):
    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    ws.select("Scene")
    pump_frames(3)
    rendered_components(viewer, monkeypatch)
    monkeypatch.setattr(viewer, "_build_machine_scene", Mock())
    monkeypatch.setattr(viewer, "inspection_cutter_snapshot", lambda: {"available": True})
    frame = Mock()
    monkeypatch.setattr(ws.scene_interaction, "frame_selected", frame)
    baseline = capture_scene_setup(ws)
    inspector.select(component, reveal=False)
    inspector.isolate()
    shown = {key for key, visible in viewer.machine_group_visibility.items() if visible}
    assert shown == ({"fixed", "carriage"} if component == "outer" else set())
    assert viewer.cutter_visible == (component == "cutter")
    assert frame.call_count == 0
    pump_frames(3)
    assert frame.call_count == int(component == "cutter")
    inspector.size_hint_x = None
    inspector.width = 360
    pump_frames(4)
    inspector.export_to_png(str(tmp_path / f"isolate-{component}-360.png"))
    assert inspector.isolate_button.width <= 360
    assert inspector.restore_visibility_button.width <= 360
    inspector.size_hint_x = 1
    inspector.restore_visibility()
    assert capture_scene_setup(ws) == baseline
    send.assert_not_called()


@pytest.mark.parametrize("change", ["restore", "selection", "task", "profile"])
def test_pending_cutter_isolation_frame_cannot_override_new_context(setup_workspace, monkeypatch, change):
    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    ws.select("Scene")
    pump_frames(3)
    rendered_components(viewer, monkeypatch)
    monkeypatch.setattr(viewer, "_build_machine_scene", Mock())
    monkeypatch.setattr(viewer, "inspection_cutter_snapshot", lambda: {"available": True})
    frame = Mock()
    monkeypatch.setattr(ws.scene_interaction, "frame_selected", frame)
    inspector.select("cutter", reveal=False)
    inspector.isolate()
    if change == "restore":
        inspector.restore_visibility()
    elif change == "selection":
        inspector.select("stock", reveal=False)
    elif change == "task":
        ws.select("Position")
    else:
        monkeypatch.setattr(inspector, "_machine_identity", lambda: ("changed",))
    pump_frames(3)
    frame.assert_not_called()
    send.assert_not_called()


def test_cutter_isolation_frames_after_pending_projection_update(setup_workspace, monkeypatch):
    from kivy.clock import Clock

    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    ws.select("Scene")
    pump_frames(3)
    rendered_components(viewer, monkeypatch)
    monkeypatch.setattr(viewer, "_build_machine_scene", Mock())
    monkeypatch.setattr(viewer, "inspection_cutter_snapshot", lambda: {"available": True})
    original = viewer.set_scene_component_visibility
    captured = []

    def visibility(*args, **kwargs):
        original(*args, **kwargs)
        Clock.schedule_once(lambda _dt: setattr(viewer, "m_xLookAt", 123), 0)

    monkeypatch.setattr(viewer, "set_scene_component_visibility", visibility)
    monkeypatch.setattr(ws.scene_interaction, "frame_selected", lambda: captured.append(viewer.m_xLookAt))
    inspector.select("cutter", reveal=False)
    inspector.isolate()
    assert captured == []
    pump_frames(3)
    assert captured == [123]
    send.assert_not_called()


def test_actual_cutter_isolation_fits_displayed_mesh_after_projection_settles(setup_workspace, monkeypatch):
    from kivy.clock import Clock

    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
    from carveracontroller.machine.scene_interaction import render_tool_snapshot

    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    saved_tools, saved_override = dict(viewer.library_tool_table_mm), viewer.preview_tool_override
    try:
        monkeypatch.setattr(ws.app, "playing", False)
        monkeypatch.setattr(ws.app, "state", "Idle")
        ws.select("Scene")
        viewer.set_machine_visible(True)
        viewer.load_tool_profiles(
            {
                7: ToolDefinition(
                    7, ToolType.FLAT_END_MILL, diameter=6.35, shank_diameter=6.35, length=76.2, flute_length=25.4
                )
            },
            replace=True,
        )
        ws.enter_preview()
        viewer.select_preview_tool(7)
        viewer.set_cutter_visible(True)
        viewer._update_static_cutter()
        pump_frames(4)
        inspector.select("cutter", reveal=False)
        original = viewer.set_scene_component_visibility

        def visibility(*args, **kwargs):
            original(*args, **kwargs)

            def projection_update(_dt):
                viewer.m_xLookAt += 1
                viewer.update_view()

            Clock.schedule_once(projection_update, 0)

        monkeypatch.setattr(viewer, "set_scene_component_visibility", visibility)
        inspector.isolate()
        for _ in range(100):
            pump_frames(1, sleep=0.01)
            if ws.scene_interaction.note.text.startswith("Framed"):
                break
        assert ws.scene_interaction.note.text == "Framed selected component · cutter"
        geometry = render_tool_snapshot(viewer.inspection_cutter_snapshot())
        points = [ws.scene_interaction.project(geometry.vertices[i * 10 : i * 10 + 3]) for i in set(geometry.indices)]
        x, y, width, height = ws.scene_interaction.viewport()
        assert all(p is not None and x <= p[0] <= x + width and y <= p[1] <= y + height for p in points)
        assert max(p[1] for p in points) - min(p[1] for p in points) > height / 2
        assert viewer.pointermesh["inspection_highlight"] == 1.0
        meshes = tuple(viewer.pointer_mesh_instrs)
        buffers = [(tuple(m.vertices), tuple(m.indices)) for m in meshes]
        viewer.set_inspected_component("stock")
        assert viewer.pointermesh["inspection_highlight"] == 0.0
        assert tuple(viewer.pointer_mesh_instrs) == meshes
        assert [(tuple(m.vertices), tuple(m.indices)) for m in meshes] == buffers
        inspector.restore_visibility()
        send.assert_not_called()
    finally:
        viewer.load_tool_profiles(saved_tools, replace=True)
        viewer.select_preview_tool(saved_override)
