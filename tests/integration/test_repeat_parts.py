from copy import deepcopy
from unittest.mock import Mock

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
        assert "Only this stock" in panel.note.text
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
        panel.save()
        assert "currently selected" in panel.note.text
        send.assert_not_called()
    finally:
        ws.simulation_geometry = previous_geometry
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
