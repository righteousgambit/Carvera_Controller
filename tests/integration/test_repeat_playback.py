import time
from unittest.mock import Mock

import pytest

from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan
from carveracontroller.machine.repeat_playback import prepare_repeat_playback

from .conftest import load_gcode_file, pump_frames


def test_loaded_path_and_cutter_share_declared_frames_and_restore(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    text = "G21 G90 G94 G17 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z-1 F100\nG1 X3\nG0 Z2\nG55\nG0 X0 Y0\nG1 Z-1\nG1 X3"
    path = tmp_path / "repeat-path.cnc"
    path.write_text(text)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.app, "selected_local_filename", str(path))
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "playback-test"})
    load_gcode_file(kivy_app, str(path))
    program = ProgramOperations.from_text(text)
    monkeypatch.setattr(ws.operation_panel, "program", program)
    original_rows = tuple(viewer.raw_positions)
    original_setup = viewer.machine_setup
    original_mode = viewer.pose_mode
    plan = RepeatPartPlan.grid(1, 2, (10, 0, 0), (0, 0, 0), (0, 0, -2), (4, 4, 2))
    panel = ws.repeat_parts_panel
    try:
        panel.show_plan(plan, "playback-test")
        panel.preview()
        viewer.set_machine_visible(True)
        panel.prepare_playback()
        deadline = time.monotonic() + 10
        while panel.calculating and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel.calculating
        assert viewer.declared_playback is not None, panel.simulation_note.text
        assert viewer.loaded_program_hash == program.file_hash
        assert tuple(viewer.raw_positions[-3:]) == (13, 0, -1)
        viewer.display_count = viewer.get_total_distance()
        viewer._scene_dirty = True
        viewer._on_frame_tick(0)
        assert viewer._preview_program_point == pytest.approx((13, 0, -1))
        machine_point = tuple(
            viewer._preview_program_point[a] + viewer.machine_setup.work_offset_mm[a] for a in range(3)
        )
        assert machine_point == pytest.approx((13, 0, -1))
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        assert tuple(viewer.raw_positions[-3:]) == (3, 0, -1)
        viewer.display_count = viewer.get_total_distance()
        viewer._scene_dirty = True
        viewer._on_frame_tick(0)
        assert viewer._preview_program_point == pytest.approx((3, 0, -1))
        assert viewer.loaded_program_hash == program.file_hash
        scale = viewer.move_scale_by_positon
        expected_pointer = tuple(
            viewer._preview_program_point[a] * scale
            - viewer.lines_center[a]
            + (viewer._machine_pose["table"][1] * scale if a == 1 else 0)
            for a in range(3)
        )
        assert tuple(viewer.pointermesh["offset"]) == pytest.approx(expected_pointer)
        assert viewer.set_operation_highlight(program.file_hash, 8, 10)
        assert viewer.linemesh["operation_selected"] == 1
        # Historical scene switching returns both declared playback and the file baseline.
        from carveracontroller.desktop_historical_scene import capture_scene, publish_scene

        previous = capture_scene(viewer)
        publish_scene(viewer, {"declared_playback": None})
        assert tuple(viewer.raw_positions) == original_rows
        publish_scene(viewer, previous)
        assert tuple(viewer.raw_positions[-3:]) == (3, 0, -1)
        panel.restore_playback()
        assert viewer.declared_playback is None
        assert tuple(viewer.raw_positions) == original_rows
        assert viewer.loaded_program_hash == program.file_hash
        with pytest.raises(ValueError, match="currently loaded"):
            viewer.set_declared_playback(prepare_repeat_playback(ProgramOperations.from_text(text + "\nM5"), plan))
        send.assert_not_called()
    finally:
        viewer.restore_file_playback()
        viewer.clear_repeat_stock()
        viewer.machine_setup = original_setup
        ws.set_pose_mode(original_mode)
        panel.plan = None
        panel.owner = None
        if viewer.machine_visible:
            viewer._build_machine_scene()
