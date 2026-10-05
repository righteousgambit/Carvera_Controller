from copy import deepcopy
from unittest.mock import Mock

import pytest
from kivy.graphics import Mesh

from carveracontroller.machine.repeat_parts import RepeatPartStore

from .conftest import pump_frames


def test_repeat_part_build_save_restore_preview_and_profile_guard(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.repeat_parts_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "repeat-test"})
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws, "machine_profile_loading", False)
    panel.store = RepeatPartStore(tmp_path / "parts.json")
    viewer = ws.machine.gcode_viewer
    previous_repeat = (viewer.repeat_stock_plan, viewer.repeat_stock_index, viewer.repeat_rest_geometries)
    previous_groups = dict(viewer.machine_group_visibility)
    previous_setup = viewer.machine_setup
    previous_geometry = deepcopy(getattr(ws, "simulation_geometry", None))
    previous_pose_mode = viewer.pose_mode
    previous_pose = viewer._machine_pose
    previous_rest = getattr(viewer, "_rest_stock_geometry", None)
    try:
        ws.select("Setup")
        panel.toggle()
        panel.generate()
        pump_frames(6)
        assert len(panel.plan.parts) == 2
        panel.save()
        stored = panel.store.load("repeat-test")
        panel.plan = None
        panel.restore()
        assert panel.plan == stored
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        pump_frames(6)
        assert viewer.machine_setup.work_offset_mm == stored.parts[1].work_offset_mm
        assert not viewer.machine_setup.alignment_confirmed
        assert "2 declared stocks shown" in panel.note.text
        assert "simulation applies only to the active stock" in panel.note.text
        assert viewer.repeat_stock_plan == stored
        scene = viewer._machine_scene()
        assert scene["repeat_stock"].indices
        from carveracontroller.machine.scene_inspection import geometry_bounds

        assert geometry_bounds(scene["repeat_stock"]) == stored.parts[0].bounds
        assert geometry_bounds(scene["stock"]) == stored.parts[1].bounds
        viewer._build_machine_scene()
        meshes = [child for child in viewer._machine_contexts["repeat_stock"].children if isinstance(child, Mesh)]
        assert {mesh.mode for mesh in meshes} == {"triangles", "lines"}
        scale = viewer.move_scale_by_positon or 1
        points = [tuple(meshes[0].vertices[i : i + 3]) for i in range(0, len(meshes[0].vertices), 10)]
        expected_low = tuple(
            (stored.parts[0].bounds[0][a] - stored.parts[1].work_offset_mm[a]) * scale for a in range(3)
        )
        assert tuple(min(p[a] for p in points) for a in range(3)) == pytest.approx(expected_low)
        viewer._update_machine_uniforms((0, 5, 0))
        assert viewer._machine_contexts["repeat_stock"]["offset"] == viewer._machine_contexts["stock"]["offset"]
        # Computed active rest stock must not replace or subtract nominal copies.
        from carveracontroller.addons.machine_simulation.model import Geometry

        residual = Geometry()
        residual.box((0, 0, -10), (5, 5, 0), (1, 1, 1, 1))
        viewer.set_rest_stock_geometry(residual)
        scene = viewer._machine_scene()
        assert scene["stock"] is viewer._rest_stock_geometry
        assert geometry_bounds(scene["repeat_stock"]) == stored.parts[0].bounds
        assert viewer.inspected_component_geometry("stock") == (scene["stock"],)
        viewer.machine_group_visibility["stock"] = False
        viewer._build_machine_scene()
        assert not viewer._machine_contexts["repeat_stock"].children
        viewer.machine_group_visibility["stock"] = True
        viewer._build_machine_scene()
        assert viewer._machine_contexts["repeat_stock"].children
        active_rest = viewer._rest_stock_geometry
        panel.hide_others()
        assert viewer.repeat_stock_plan is None
        assert viewer._rest_stock_geometry is active_rest
        viewer._build_machine_scene()
        assert not viewer._machine_contexts["repeat_stock"].children
        panel.preview()
        # Invalid array publication leaves the previous setup and array intact.
        setup_before = viewer.machine_setup
        with pytest.raises(ValueError, match="Active stock"):
            viewer.configure_machine(
                work_offset_mm=(1, 2, 3), stock_size_mm=(4, 5, 6), repeat_plan=stored, repeat_index=1
            )
        assert viewer.machine_setup is setup_before
        assert viewer.repeat_stock_plan == stored
        viewer.configure_machine(
            work_offset_mm=stored.parts[1].work_offset_mm,
            stock_origin_mm=stored.parts[1].stock_origin_mm,
            stock_size_mm=stored.parts[1].stock_size_mm,
            alignment_confirmed=True,
            repeat_plan=stored,
            repeat_index=1,
        )
        assert not viewer.machine_setup.alignment_confirmed
        # The array worker uses parsed WCS and publishes each computed rest stock.
        import time

        from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
        from carveracontroller.machine.program_operations import ProgramOperations
        from tests.unit.test_repeat_simulation import TEXT

        monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text(TEXT))
        monkeypatch.setattr(
            viewer,
            "library_tool_table_mm",
            {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, flute_length=2, stickout=3)},
        )
        panel.show_page("Review")
        assert panel.review_body.parent is panel.content and panel.layout_body.parent is None
        panel.simulate()
        assert panel.calculating and panel.calculate_action.disabled
        deadline = time.monotonic() + 20
        while panel.calculating and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel.calculating
        assert panel.result is not None, panel.simulation_note.text
        assert all(report.removed_volume_mm3 > 0 for report in panel.result.reports)
        assert set(viewer.repeat_rest_geometries) == {"G54", "G55"}
        assert "Computed declared-frame" in panel.simulation_note.text
        assert "removed" in panel.summary.text
        assert "collision candidates" in panel.summary.text
        assert "unresolved lines excluded (3)" in panel.simulation_note.text
        scene = viewer._machine_scene()
        assert scene["stock"] is viewer.repeat_rest_geometries[stored.parts[1].wcs]
        active = scene["stock"]
        panel.choice.text = panel.choice.values[0]
        panel.preview()
        assert viewer.repeat_rest_geometries is not None
        assert viewer._machine_scene()["stock"] is panel.result.geometries["G54"]
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        assert viewer._machine_scene()["stock"] is active
        # A completed worker result cannot overwrite changed inputs or late cancellation.
        import threading

        import carveracontroller.desktop_repeat_parts as repeat_ui

        completed = panel.result
        previous_meshes = viewer.repeat_rest_geometries
        with monkeypatch.context() as scoped:
            for action in ("change resolution", "cancel"):
                started, release = threading.Event(), threading.Event()

                def delayed(*args, started=started, release=release, **kwargs):
                    started.set()
                    assert release.wait(5)
                    return completed

                scoped.setattr(repeat_ui, "simulate_repeat_parts", delayed)
                panel.simulate()
                assert started.wait(2)
                if action == "change resolution":
                    panel.resolution.text = "2"
                else:
                    panel.cancel_event.set()
                release.set()
                deadline = time.monotonic() + 5
                while panel.calculating and time.monotonic() < deadline:
                    pump_frames(1, sleep=0.01)
                assert not panel.calculating
                assert viewer.repeat_rest_geometries is previous_meshes
                assert "not applied" in panel.simulation_note.text or "cancelled" in panel.simulation_note.text
                panel.resolution.text = "1"
        panel.hide_others()
        assert viewer._rest_stock_geometry is active
        assert viewer.repeat_rest_geometries is None
        panel.preview()
        # Local archive viewing clears the array, and returning restores it.
        from carveracontroller.desktop_historical_scene import capture_scene, prepare_previous_scene, publish_scene

        previous_array = capture_scene(viewer)
        publish_scene(viewer, {"repeat_stock_plan": None, "repeat_stock_index": None, "repeat_rest_geometries": None})
        assert not viewer._machine_contexts["repeat_stock"].children
        restored_values, restored_geometry = prepare_previous_scene(
            previous_array, {}, 1, viewer.move_scale_by_positon or 1
        )
        publish_scene(viewer, restored_values, restored_geometry)
        assert viewer.repeat_stock_plan == stored
        assert viewer._machine_contexts["repeat_stock"].children
        # An ordinary single-stock setup must remove all array context.
        viewer.configure_machine(stock_size_mm=(5, 5, 5))
        assert viewer.repeat_stock_plan is None
        assert not viewer._machine_contexts["repeat_stock"].children
        panel.preview()
        setup = viewer.machine_setup
        monkeypatch.setattr(ws, "selected_machine_profile", {"id": "other-machine"})
        panel.preview()
        assert viewer.machine_setup is setup
        assert "currently selected" in panel.note.text
        monkeypatch.setattr(ws, "selected_machine_profile", {"id": "repeat-test"})
        monkeypatch.setattr(ws.app, "playing", True)
        panel.preview()
        assert viewer.machine_setup is setup
        assert "Stop playback" in panel.note.text
        monkeypatch.setattr(ws.app, "playing", False)
        monkeypatch.setattr(ws.run_recording_panel, "previous_scene", object())
        panel.preview()
        assert viewer.machine_setup is setup
        assert "recorded setup" in panel.note.text
        monkeypatch.setattr(ws.run_recording_panel, "previous_scene", None)
        panel.pitch_x.text = "75"
        assert panel.plan is None
        assert viewer.repeat_stock_plan is None
        panel.save()
        assert "currently selected" in panel.note.text
        send.assert_not_called()
    finally:
        ws.simulation_geometry = previous_geometry
        viewer.repeat_stock_plan, viewer.repeat_stock_index, viewer.repeat_rest_geometries = previous_repeat
        viewer.machine_group_visibility = previous_groups
        viewer.machine_setup = previous_setup
        viewer._machine_pose = previous_pose
        viewer._rest_stock_geometry = previous_rest
        ws.set_pose_mode(previous_pose_mode)
        panel.plan = None
        panel.owner = None
        if viewer.machine_visible:
            viewer._build_machine_scene()
        if panel.expanded:
            panel.toggle()
