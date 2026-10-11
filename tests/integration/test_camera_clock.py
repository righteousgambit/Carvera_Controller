import time
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from kivy.core.window import Window

from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording
from carveracontroller.machine.webcam import WebcamClient, fetch_frame
from tests.integration.conftest import pump_frames, set_window_viewport
from tests.unit.test_camera_clock import origin


@pytest.mark.parametrize("viewport", [(1040, 800), (1920, 1080)])
def test_live_clock_bounds_and_recorded_status_relative_timing_are_rendered_without_commands(
    kivy_app, monkeypatch, tmp_path, viewport
):
    ws = kivy_app.root.desktop_workspace
    before_size = Window.system_size
    before_section = ws.active_section
    before_camera_section = ws.camera_registration_panel.sections.current
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    with origin(mutation=lambda headers: headers.update({"X-Camera-Frame-Time-Basis": "jpeg-assembled"})) as (
        url,
        _requests,
    ):
        frame = fetch_frame(url, 1)
    client = WebcamClient(url, start=False)
    client.frame = frame
    client.error = ""
    monkeypatch.setattr(ws, "camera_client", client)
    panel = ws.run_recording_panel
    old_replay, old_archive = panel.replay, panel.camera_archive
    try:
        set_window_viewport(*viewport)
        ws.select("Camera")
        ws.camera_registration_panel.select_section("Source")
        ws._refresh_camera()
        pump_frames(6)
        note = ws.camera_clock_note
        assert "server−desktop clock interval" in note.text and "+120." in note.text
        assert "local monotonic" in note.text and "100 ppm" in note.text
        assert "sensor exposure unqualified" in note.text
        assert "JPEG assembled after FFmpeg delivery" in note.text
        assert all("reported frame ≤" in item.text for item in ws.camera_status_labels)
        assert note.texture_size[1] <= note.height
        scroll = ws.camera_registration_panel.sections.get_screen("Source").children[0]
        scroll.scroll_to(note, animate=False)
        pump_frames(6)
        assert note.width <= scroll.width
        assert scroll.height > 0
        snapshot = Window.screenshot(name=str(tmp_path / f"clock-evidence-{viewport[0]}.png"))
        assert snapshot
        record = RunRecording()
        timestamp = frame.received_at + 0.05
        record.capture_status("Idle", {"MPos": [1, 2, 3]}, timestamp, time.time(), 1)
        replay = RecordingReplay(record.export_bytes())
        writer = CameraRunWriter(tmp_path / "camera", replay.payload["session_id"])
        try:
            assert writer.submit(frame, 0)
            assert writer.submit(replace(frame, sequence=2, received_at=timestamp + 0.1), 0)
        finally:
            writer.close()
        archive = CameraRunReplay(writer.folder)
        panel.replay = replay
        panel.camera_archive = archive
        panel.show_recorded_camera()
        panel._seek_camera(replay.payload["events"][0])
        deadline = time.monotonic() + 10
        while panel._camera_decode_busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel._camera_decode_busy
        assert panel.recorded_camera_frame.clock == frame.clock
        assert "relative to selected status receipt" in panel.camera_replay_status
        assert "100 ppm" in panel.camera_replay_status
        assert "JPEG assembled after FFmpeg delivery" in panel.camera_replay_status
        assert "unqualified" in panel.camera_replay_status
        assert panel.replay is replay and panel.camera_archive is archive
        send.assert_not_called()
    finally:
        panel.show_live_camera()
        panel.replay, panel.camera_archive = old_replay, old_archive
        ws.camera_registration_panel.select_section(before_camera_section)
        ws.select(before_section)
        Window.system_size = before_size
        pump_frames(4)
