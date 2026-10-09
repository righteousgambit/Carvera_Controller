import time
from copy import deepcopy
from unittest.mock import Mock

import pytest
from kivy.graphics import Mesh

from carveracontroller.machine.repeat_parts import RepeatPartStore

from .conftest import pump_frames


def wait_plan_io(panel):
    deadline = time.monotonic() + 5
    while panel.io_busy and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel.io_busy


@pytest.mark.parametrize("operation", ("calculation", "exchange", "playback"))
def test_unexpected_array_worker_failure_releases_controls_and_retains_scene(kivy_app, monkeypatch, operation):
    import carveracontroller.desktop_repeat_parts as repeat_ui
    from carveracontroller.desktop_historical_scene import capture_scene, publish_scene
    from carveracontroller.machine.program_operations import ProgramOperations
    from carveracontroller.machine.repeat_parts import RepeatPartPlan
    from tests.unit.test_repeat_simulation import TEXT

    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.repeat_parts_panel, ws.machine.gcode_viewer
    previous = capture_scene(viewer)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "worker-failure"})
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws, "machine_profile_loading", False)
    declared = RepeatPartPlan.grid(1, 2, (10, 0, 0), (0, 0, 0), (0, 0, -2), (4, 4, 2))
    program = ProgramOperations.from_text(TEXT)
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "loaded_program_hash", program.file_hash)
    monkeypatch.setattr(panel, "plan", None)
    monkeypatch.setattr(panel, "owner", None)
    monkeypatch.setattr(panel, "result", None)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic worker defect")

    try:
        panel.show_plan(declared, "worker-failure")
        panel.preview()
        before = viewer.machine_setup
        retained = viewer.repeat_rest_geometries
        if operation == "calculation":
            monkeypatch.setattr(repeat_ui, "simulate_repeat_parts", fail)
            monkeypatch.setattr(repeat_ui, "verify_assets", lambda *a, **kw: None)
            panel.simulate()
        elif operation == "exchange":
            monkeypatch.setattr(repeat_ui, "load_repeat_result", fail)
            panel.exchange_result("unused.cvstocks", False)
        else:
            monkeypatch.setattr(repeat_ui, "prepare_repeat_playback", fail)
            panel.prepare_playback()
        deadline = time.monotonic() + 20
        while panel.calculating and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel.calculating
        assert not panel.calculate_action.disabled and panel.cancel_action.disabled
        status = panel.artifact_status if operation == "exchange" else panel.simulation_note
        assert "synthetic worker defect" in status.text
        assert viewer.machine_setup is before
        assert viewer.repeat_rest_geometries is retained
        send.assert_not_called()
    finally:
        publish_scene(viewer, previous)


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
        wait_plan_io(panel)
        stored = panel.store.load("repeat-test")
        panel.plan = None
        panel.restore()
        wait_plan_io(panel)
        assert panel.plan == stored
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        wait_plan_io(panel)
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
        wait_plan_io(panel)
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
        assert panel.page == "Results"
        archive = tmp_path / "parts.cvstocks"
        monkeypatch.setattr(ws, "choose_profile_file", lambda callback, **kwargs: callback(str(archive)))
        panel.save_result()
        deadline = time.monotonic() + 20
        while panel.calculating and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert archive.exists(), panel.artifact_status.text
        assert "Saved all rest stocks" in panel.artifact_status.text
        saved_geometries = dict(panel.result.geometries)
        monkeypatch.setattr(ws, "choose_asset_file", lambda callback, **kwargs: callback(str(archive)))
        panel.choice.text = panel.choice.values[0]
        panel.preview()
        wait_plan_io(panel)
        panel.load_result()
        deadline = time.monotonic() + 20
        while panel.calculating and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert "Loaded all rest stocks" in panel.artifact_status.text
        assert panel.result.geometries == saved_geometries
        import threading

        import carveracontroller.desktop_repeat_parts as repeat_ui

        restored = panel.result
        with monkeypatch.context() as scoped:
            for action in ("cancel", "change context"):
                started, release = threading.Event(), threading.Event()
                previous_meshes = viewer.repeat_rest_geometries

                def delayed_load(*args, started=started, release=release, **kwargs):
                    started.set()
                    assert release.wait(5)
                    return restored

                scoped.setattr(repeat_ui, "load_repeat_result", delayed_load)
                panel.load_result()
                assert started.wait(2)
                if action == "cancel":
                    panel.cancel_event.set()
                else:
                    panel.resolution.text = "2"
                release.set()
                deadline = time.monotonic() + 5
                while panel.calculating and time.monotonic() < deadline:
                    pump_frames(1, sleep=0.01)
                assert not panel.calculating
                assert "displayed results retained" in panel.artifact_status.text
                assert viewer.repeat_rest_geometries is previous_meshes
                panel.resolution.text = "1"
        retained = viewer.repeat_rest_geometries
        panel.resolution.text = "2"
        panel.load_result()
        deadline = time.monotonic() + 20
        while panel.calculating and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert "does not match" in panel.artifact_status.text
        assert viewer.repeat_rest_geometries is retained
        panel.resolution.text = "1"
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        wait_plan_io(panel)
        scene = viewer._machine_scene()
        assert scene["stock"] is viewer.repeat_rest_geometries[stored.parts[1].wcs]
        active = scene["stock"]
        panel.choice.text = panel.choice.values[0]
        panel.preview()
        wait_plan_io(panel)
        assert viewer.repeat_rest_geometries is not None
        assert viewer._machine_scene()["stock"] is panel.result.geometries["G54"]
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        wait_plan_io(panel)
        assert viewer._machine_scene()["stock"] is active
        # A completed worker result cannot overwrite changed inputs or late cancellation.
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
        wait_plan_io(panel)
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
        wait_plan_io(panel)
        setup = viewer.machine_setup
        monkeypatch.setattr(ws, "selected_machine_profile", {"id": "other-machine"})
        panel.preview()
        wait_plan_io(panel)
        assert viewer.machine_setup is setup
        assert "currently selected" in panel.note.text
        monkeypatch.setattr(ws, "selected_machine_profile", {"id": "repeat-test"})
        monkeypatch.setattr(ws.app, "playing", True)
        panel.preview()
        wait_plan_io(panel)
        assert viewer.machine_setup is setup
        assert "Stop playback" in panel.note.text
        monkeypatch.setattr(ws.app, "playing", False)
        monkeypatch.setattr(ws.run_recording_panel, "previous_scene", object())
        panel.preview()
        wait_plan_io(panel)
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


def test_restore_synchronizes_array_and_custom_editor(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.repeat_parts import RepeatPartPlan

    ws = kivy_app.root.desktop_workspace
    panel = ws.repeat_parts_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "editor-test"})
    monkeypatch.setattr(panel, "store", RepeatPartStore(tmp_path / "parts.json"))
    plan = RepeatPartPlan.grid(2, 2, (-50, 60, 0), (-100, -150, -80), (0, 0, -10), (40, 40, 10), "G55")
    panel.store.save("editor-test", plan)
    panel.restore()
    wait_plan_io(panel)
    assert panel.plan == plan
    assert (panel.rows.text, panel.columns.text, panel.first_wcs.text) == ("2", "2", "G55")
    assert float(panel.pitch_x.text) == -50
    panel.choice.text = panel.choice.values[1]
    panel.part_name.text = "Bracket"
    panel.part_size.text = "20, 30, 10"
    panel.apply_part()
    custom = panel.plan
    assert custom.parts[1].name == "Bracket"
    assert custom.parts[0] == plan.parts[0]
    assert all(control.disabled for control in panel.layout_controls)
    panel.generate()
    assert panel.plan is custom
    assert "Start a new array draft" in panel.note.text
    panel.part_wcs.text = "G55"
    panel.apply_part()
    assert panel.plan is custom
    assert "distinct work" in panel.note.text
    panel.discard_part_draft()
    assert panel.part_wcs.text == "G56"
    panel.save()
    wait_plan_io(panel)
    assert panel.store.load("editor-test") == custom
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "another-machine"})
    panel.refresh_frame_review()
    assert panel.part_editor.disabled
    assert panel.part_offset.text == ""
    send.assert_not_called()


def test_part_drafts_survive_navigation_and_apply_atomically(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.repeat_parts import RepeatPartPlan

    ws = kivy_app.root.desktop_workspace
    panel = ws.repeat_parts_panel
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "draft-test"})
    monkeypatch.setattr(panel, "store", RepeatPartStore(tmp_path / "plans.json"))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    plan = RepeatPartPlan.grid(1, 2, (60, 60, 0), (-200, -150, -80), (0, 0, -10), (40, 40, 10))
    panel.show_plan(plan, "draft-test")
    panel.part_wcs.text = "G55"
    panel.part_name.text = "Left bracket"
    panel.choice.text = panel.choice.values[1]
    panel.part_wcs.text = "G54"
    panel.part_name.text = "Right bracket"
    panel.choice.text = panel.choice.values[0]
    assert panel.part_name.text == "Left bracket"
    assert panel.part_wcs.text == "G55"
    assert len(panel.part_drafts) == 2
    assert "2 unapplied" in panel.part_editor.note.text
    assert all(control.disabled for control in panel.layout_controls)
    panel.rows.text = "3"
    assert panel.rows.text == "1" and panel.plan is plan
    assert len(panel.part_drafts) == 2
    panel.save()
    assert not panel.io_busy and not panel.store.path.exists()
    assert "Apply or discard" in panel.note.text
    panel.restore()
    assert not panel.io_busy and len(panel.part_drafts) == 2
    panel.generate()
    assert panel.plan is plan and len(panel.part_drafts) == 2
    panel.new_array()
    assert panel.plan is plan and len(panel.part_drafts) == 2
    panel.apply_part()
    assert panel.plan is plan  # A single frame swap is invalid until the other draft joins it.
    assert len(panel.part_drafts) == 2
    panel.part_size.text = "0, 40, 10"
    panel.apply_all_parts()
    assert panel.plan is plan
    assert len(panel.part_drafts) == 2
    panel.choice.text = panel.choice.values[1]
    panel.choice.text = panel.choice.values[0]
    assert panel.part_size.text == "0, 40, 10"
    panel.part_size.text = "40, 40, 10"
    panel.apply_all_parts()
    applied = panel.plan
    assert [part.wcs for part in applied.parts] == ["G55", "G54"]
    assert [part.name for part in applied.parts] == ["Left bracket", "Right bracket"]
    assert not panel.part_drafts
    assert applied.parts[0].work_offset_mm == plan.parts[0].work_offset_mm
    panel.part_name.text = "Left revised"
    panel.choice.text = panel.choice.values[1]
    panel.part_name.text = "Right pending"
    panel.choice.text = panel.choice.values[0]
    panel.apply_part()
    assert panel.plan.parts[0].name == "Left revised"
    assert len(panel.part_drafts) == 1
    panel.choice.text = panel.choice.values[1]
    assert panel.part_name.text == "Right pending"
    panel.discard_all_parts()
    applied = panel.plan
    panel.choice.text = panel.choice.values[0]
    panel.part_name.text = "Discard me"
    panel.choice.text = panel.choice.values[1]
    panel.part_size.text = "20, 20, 10"
    panel.discard_part_draft()
    assert len(panel.part_drafts) == 1
    panel.discard_all_parts()
    assert not panel.part_drafts
    panel.choice.text = panel.choice.values[0]
    assert panel.part_name.text == "Left revised"
    panel.save()
    wait_plan_io(panel)
    assert panel.store.load("draft-test") == applied
    panel.part_name.text = "Old machine draft"
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "another-machine"})
    panel.refresh_frame_review()
    assert not panel.part_drafts and panel.part_edit_context is None
    assert panel.part_editor.disabled
    send.assert_not_called()


def test_repeat_plan_common_actions_and_save_conflict_status(kivy_app, monkeypatch, tmp_path):
    from dataclasses import replace

    from carveracontroller.machine.repeat_parts import RepeatPartPlan, plan_revision

    ws = kivy_app.root.desktop_workspace
    panel = ws.repeat_parts_panel
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "status-test"})
    monkeypatch.setattr(panel, "store", RepeatPartStore(tmp_path / "plans.json"))
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    plan = RepeatPartPlan.grid(1, 2, (60, 60, 0), (-200, -150, -80), (0, 0, -10), (40, 40, 10))
    panel.show_plan(plan, "status-test")
    assert "not compared with saved file" in panel.persistence_status.text
    for page in ("Layout", "Review", "Results"):
        panel.show_page(page)
        assert panel.plan_toolbar.parent is panel.content
        assert panel.save_plan_action.parent is panel.plan_toolbar
        assert panel.restore_plan_action.parent is panel.plan_toolbar
    panel.save()
    assert "Saving plan in background" in panel.persistence_status.text
    wait_plan_io(panel)
    assert "matches last saved/read plan" in panel.persistence_status.text
    initial_revision = panel.saved_revisions["status-test"]
    external = RepeatPartPlan((replace(plan.parts[0], name="External revision"), plan.parts[1]))
    panel.store.save("status-test", external, initial_revision)
    panel.part_name.text = "Local revision"
    assert "1 pending edit" in panel.persistence_status.text
    assert panel.save_plan_action.disabled and panel.restore_plan_action.disabled
    panel.apply_part()
    assert "reviewed changes not saved" in panel.persistence_status.text
    assert not panel.save_plan_action.disabled and not panel.restore_plan_action.disabled
    current = panel.plan
    panel.save()
    wait_plan_io(panel)
    assert panel.plan is current
    assert panel.saved_revisions["status-test"] == initial_revision
    assert panel.plan_io_receipt["state"] == "failed"
    assert "Last file operation failed" in panel.persistence_status.text
    assert panel.store.load("status-test") == external
    panel.restore()
    assert "Reading saved plan in background" in panel.persistence_status.text
    wait_plan_io(panel)
    assert panel.plan == external
    assert panel.saved_revisions["status-test"] == plan_revision(external)
    assert "matches last saved/read plan" in panel.persistence_status.text
    assert "Last file operation failed" not in panel.persistence_status.text
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "another-machine"})
    panel.refresh_frame_review()
    assert "build or restore" in panel.persistence_status.text
    assert "matches last saved" not in panel.persistence_status.text
    send.assert_not_called()


@pytest.mark.parametrize("angles", [(23, 0, 0), (0, -32, 0), (0, 0, 41)])
def test_repeat_seed_refuses_oriented_scene_without_losing_draft(kivy_app, monkeypatch, angles):
    from dataclasses import replace

    from carveracontroller.desktop_repeat_parts import RepeatPartsPanel

    ws = kivy_app.root.desktop_workspace
    # A fresh editable draft isolates this guard from earlier retained custom plans.
    panel, viewer = RepeatPartsPanel(ws), ws.machine.gcode_viewer
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws, "machine_profile_loading", False)
    monkeypatch.setattr(
        viewer,
        "machine_setup",
        replace(
            viewer.machine_setup, stock_size_mm=(10, 20, 8), stock_rotation_deg=angles[2], stock_tilt_deg=angles[:2]
        ),
    )
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    before = (panel.offset.text, panel.origin.text, panel.stock_size_field.text)
    panel.seed()
    assert "unrotated stock" in panel.note.text
    assert (panel.offset.text, panel.origin.text, panel.stock_size_field.text) == before
    send.assert_not_called()
