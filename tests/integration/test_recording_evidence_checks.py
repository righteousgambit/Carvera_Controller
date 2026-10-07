from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from carveracontroller.CNC import CNC
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording
from tests.integration.conftest import pump_frames


def recording():
    buffer = RunRecording(gap_seconds=2)
    buffer.capture_status("Run", {"MPos": [1, 2, 3], "C": [0, 0, 0], "T": [1]}, 10, 1000, 1)
    buffer.capture_status("Alarm:1", {"T": [2]}, 11, 1001, 1)
    buffer.capture_status("Disconnected", {}, 14, 1004, 1)
    buffer.capture_status("Run", {"T": [3]}, 15, 1005, 2)
    return RecordingReplay(buffer.export_bytes())


def test_real_recording_ui_reviews_faults_without_changing_live_machine(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    viewer = ws.machine.gcode_viewer
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    live_state = kivy_app.state
    pose = viewer.observed_pose
    live_vars = deepcopy(CNC.vars)
    live_buffer = ws.machine.controller.run_recording
    replay = recording()
    original = replay.export_bytes()
    ws.select("Job")
    ws.program_tasks.show("Run record")
    panel.load(replay)
    panel.review_section.set_expanded(True)
    panel.review_tool.text = "1"
    panel.review_action.dispatch("on_release")
    for index, text in (
        (1, "reported Alarm:1"),
        (2, "Missing telemetry: 3 s"),
        (3, "reported Disconnected"),
        (4, "generation changed"),
    ):
        assert panel.seek_recorded_event(replay, index)
        pump_frames(4)
        assert text in panel.review_details.text
        assert "physical tool identity" in panel.review_details.text
    panel.seek_recorded_event(replay, 1)
    assert "logical T2" in panel.review_details.text and "expectation is T1" in panel.review_details.text
    panel.seek_recorded_event(replay, 3)
    assert "unavailable in this packet" in panel.review_details.text
    assert "logical T2" not in panel.review_details.text
    assert replay.export_bytes() == original
    assert viewer.observed_pose is pose and kivy_app.state == live_state and CNC.vars == live_vars
    assert ws.machine.controller.run_recording is live_buffer
    send.assert_not_called()
    panel.return_live()
    assert panel.review_tool.text == "" and panel.review_action.disabled
    assert "freeze or open" in panel.review_summary.text
    panel.review_section.set_expanded(False)
    ws.program_tasks.show("Operations")


def test_playback_checks_age_without_resetting_review_time_and_preserves_invalid_drafts(kivy_app, monkeypatch):
    import carveracontroller.desktop_run_recording as recording_ui

    panel = kivy_app.root.desktop_workspace.run_recording_panel
    record = RunRecording(gap_seconds=3)
    record.capture_status("Run", {"MPos": [1, 2, 3], "C": [0, 0, 0], "T": [1]}, 10, 1000, 1)
    record.capture_status("Run", {"MPos": [2, 2, 3], "C": [0, 0, 0], "T": [1]}, 12, 1002, 1)
    panel.load(RecordingReplay(record.export_bytes()))
    panel.step(None)
    panel.playback.play(0, 100)
    monkeypatch.setattr(recording_ui, "time", SimpleNamespace(monotonic=lambda: 101))
    panel._advance_playback(0)
    assert "Receipt age 1.000 s" in panel.review_summary.text and "exceeds" in panel.review_details.text
    panel.pause_playback()
    panel.toggle_marker()
    assert "Receipt age 1.000 s" in panel.review_summary.text  # Opening raw evidence never rewinds its clock.
    panel.review_tool.text = "2"
    panel.review_action.dispatch("on_release")
    assert "expectation is T2" in panel.review_details.text
    panel.review_age.text = "nan"
    panel.review_action.dispatch("on_release")
    panel._render_recorded_checks()
    assert "Review inputs" in panel.review_details.text and "last applied checks retained" in panel.review_details.text
    assert panel.review_age.text == "nan" and panel.review_expected_tool == 2 and panel.review_max_age == 0.8
    panel.step(None)  # Same receipt index still explicitly returns to its exact receipt time.
    assert "Receipt age 0.000 s" in panel.review_summary.text
    panel.load(recording())
    assert panel.review_tool.text == "" and panel.review_expected_tool is None
    assert panel.review_age.text == "0.8" and panel.review_input_error is None
    panel.return_live()
    if panel.marker_enabled:
        panel.toggle_marker()
