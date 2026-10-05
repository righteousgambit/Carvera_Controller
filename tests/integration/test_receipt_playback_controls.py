from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, PngImagePlugin

from carveracontroller.desktop_run_recording import RunRecordingPanel
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording
from tests.integration.conftest import pump_frames


def panel_with_clock(monkeypatch, samples):
    record = RunRecording()
    for stamp, generation in samples:
        record.capture_status("Idle", {"MPos": [stamp, 2, 3], "C": [0, 0, 0]}, stamp, stamp + 1000, generation)
    send = Mock()
    ws = SimpleNamespace(
        machine=SimpleNamespace(
            controller=SimpleNamespace(run_recording=record, executeCommand=send), gcode_viewer=Mock()
        ),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    now = [100.0]
    monkeypatch.setattr("carveracontroller.desktop_run_recording.time", SimpleNamespace(monotonic=lambda: now[0]))
    panel = RunRecordingPanel(ws, size_hint_x=None, width=650)
    panel.load(RecordingReplay(record.export_bytes()))
    return panel, ws, now, send


def test_play_pause_seek_speed_and_return_live_cancel_clock_without_commands(monkeypatch):
    panel, ws, now, send = panel_with_clock(monkeypatch, [(10, 1), (11, 1), (12, 1)])
    panel.toggle_playback()  # End selection restarts at first retained event.
    assert panel.cursor.value == 0 and panel.playback.running
    assert panel.playback_speed.disabled and "Pause" in panel.playback_action.text
    event = panel._playback_event
    now[0] = 101
    panel._advance_playback(0)
    assert panel.cursor.value == 1 and panel.playback.running
    panel.step(-1)
    assert panel.cursor.value == 0 and not panel.playback.running
    assert panel._playback_event is None and not event.is_triggered
    panel.playback_speed.text = "4× receipts"
    panel.toggle_playback()
    now[0] = 101.5
    panel._advance_playback(0)
    assert panel.cursor.value == 2 and not panel.playback.running
    assert "End" in panel.playback_note.text
    panel.toggle_playback()
    panel.return_live()
    assert panel.playback is None and panel._playback_event is None
    assert panel.cursor.disabled and "Latest received state" in panel.observation.text
    ws.machine.gcode_viewer.set_recorded_machine_point.assert_called_with(None)
    send.assert_not_called()


def test_gap_withholds_camera_and_marker_even_when_visibility_is_toggled(monkeypatch):
    panel, ws, now, send = panel_with_clock(monkeypatch, [(10, 1), (11, 1), (16, 1)])
    panel.cursor.value = 1
    panel.marker_enabled = True
    panel.camera_replay_enabled = True
    panel.toggle_playback()
    now[0] = 101
    panel._advance_playback(0)
    assert panel.playback.running and panel._playback_missing
    assert "motion unknown" in panel.observation.text
    assert panel.recorded_camera_frame is None and panel._desired_camera is None
    ws.machine.gcode_viewer.set_recorded_machine_point.assert_called_with(None)
    panel.toggle_marker()
    panel.toggle_marker()
    assert panel._desired_camera is None and "missing telemetry" in panel.camera_replay_status
    now[0] = 110  # Even a late UI tick must stop before the following same-time packet.
    assert panel._advance_playback(0) is False
    assert panel.cursor.value == 2 and not panel.playback.running
    assert "5 seconds" in panel.details.text and "review this boundary" in panel.playback_note.text
    panel.toggle_playback()
    panel._advance_playback(0)
    assert panel.cursor.value == 3 and not panel._playback_missing
    assert "reported Idle" in panel.observation.text
    send.assert_not_called()


def test_replacement_and_shutdown_cancel_playback_without_changing_live_capture(monkeypatch):
    panel, ws, now, send = panel_with_clock(monkeypatch, [(10, 1), (11, 1), (12, 1)])
    panel.toggle_playback()
    panel.load(RecordingReplay(ws.machine.controller.run_recording.export_bytes()))
    assert not panel.playback.running and panel._playback_event is None
    panel.toggle_playback()
    ws.camera_client = SimpleNamespace(set_frame_observer=Mock())
    panel.shutdown_camera()
    assert not panel.playback.running and panel._playback_event is None
    assert ws.machine.controller.run_recording.summary()["retained_events"] == 3
    send.assert_not_called()


@pytest.mark.parametrize("width, columns", [(320, 1), (1200, 2)])
def test_playback_controls_reflow_and_stay_inside_card(monkeypatch, tmp_path, width, columns):
    panel, ws, now, send = panel_with_clock(monkeypatch, [(10, 1), (11, 1), (12, 1)])
    panel.width = width
    pump_frames(6)
    controls = panel.playback_action.parent
    assert controls.cols == columns
    for item in (panel.playback_action, panel.playback_speed):
        assert panel.x <= item.x and item.right <= panel.right
        assert item.width >= 140
    assert "never executes" in panel.playback_note.text
    for section in (panel.files_section, panel.scene_section, panel.camera_section, panel.packet_section):
        assert section.toggle.texture_size[0] <= section.toggle.width
        assert section.toggle.texture_size[1] < section.toggle.height
        assert section.height >= section.toggle.height
    assert PngImagePlugin is not None and "PNG" in Image.SAVE
    rendered = panel.export_as_image().texture
    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(
        tmp_path / f"receipt-playback-{width}.png", format="PNG"
    )
    send.assert_not_called()
