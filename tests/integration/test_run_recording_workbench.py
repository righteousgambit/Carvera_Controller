import time
from unittest.mock import Mock

from carveracontroller.machine.run_recording import RecordingReplay, RunRecording
from tests.integration.conftest import pump_frames


def wait_for_record(panel):
    deadline = time.monotonic() + 10
    while panel.busy and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel.busy


def test_recording_workbench_freeze_seek_export_import_without_commands(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    controller = ws.machine.controller
    record = RunRecording()
    record.capture_status(
        "Run", {"MPos": [1, 2, 3], "C": [0, 4, 0, 1], "S": [11950, 12000], "P": [80, 10, 1]}, 10, 1000, 1
    )
    record.capture_status("Hold", {"MPos": [7, 2, 3]}, 15, 1005, 1)
    monkeypatch.setattr(controller, "run_recording", record)
    send = Mock()
    monkeypatch.setattr(controller, "executeCommand", send)
    ws.select("Job")
    ws.program_tasks.choose("Run record")
    panel = ws.run_recording_panel
    # Heartbeat refresh must not copy the full retained run.
    with monkeypatch.context() as patch:
        patch.setattr(record, "snapshot", Mock(side_effect=AssertionError("full record on heartbeat")))
        panel.refresh()
        assert "3 events" in panel.summary.text
    panel.freeze_action.dispatch("on_release")
    wait_for_record(panel)
    assert panel.replay is not None and "Replay" in panel.summary.text
    assert "Hold" in panel.details.text and "not in this packet" in panel.details.text
    panel.step(None)
    assert "11950" in panel.details.text and "execution unverified" in panel.details.text
    viewer = ws.machine.gcode_viewer
    mode, observed, preview = viewer.pose_mode, viewer.observed_pose, viewer._preview_program_point
    panel.toggle_marker()
    assert viewer.recorded_machine_point == (1, 2, 3)
    assert (viewer.pose_mode, viewer.observed_pose, viewer._preview_program_point) == (mode, observed, preview)
    refresh_marker = Mock(wraps=viewer.set_recorded_machine_point)
    with monkeypatch.context() as patch:
        patch.setattr(viewer, "set_recorded_machine_point", refresh_marker)
        viewer._build_machine_scene()
        refresh_marker.assert_called_once_with((1, 2, 3))
    panel.step(1)
    assert "Gap" in panel.details.text and "motion unknown" in panel.details.text
    assert viewer.recorded_machine_point is None
    path = tmp_path / "record.cvrun"
    panel._export_to(str(path))
    wait_for_record(panel)
    assert "Saved local recording" in panel.notice.text
    assert len(RecordingReplay(path.read_bytes()).payload["events"]) == 3
    original = path.read_bytes()
    panel._export_to(str(path))
    wait_for_record(panel)
    assert "Recording unavailable" in panel.notice.text and path.read_bytes() == original
    panel.live_action.dispatch("on_release")
    assert panel.replay is None and "Live buffer" in panel.summary.text
    panel._import_from(str(path))
    wait_for_record(panel)
    assert panel.replay is not None and "Replay" in panel.summary.text
    bad = tmp_path / "bad.cvrun"
    bad.write_text('{"payload":{},"sha256":"bad"}')
    previous = panel.replay
    panel._import_from(str(bad))
    wait_for_record(panel)
    assert panel.replay is previous and "digest" in panel.notice.text

    # Unexpected artifact failures must release the controls and preserve replay.
    def fail_artifact():
        raise RuntimeError("artifact worker failed")

    panel._worker(fail_artifact, Mock())
    wait_for_record(panel)
    assert panel.replay is previous and "artifact worker failed" in panel.notice.text
    assert not panel.import_action.disabled and not panel.live_action.disabled
    send.assert_not_called()
    panel.return_live()
    assert viewer.recorded_machine_point is None
    panel.toggle_marker()
    ws.program_tasks.choose("Operations")


def test_matching_recorded_program_opens_local_preview_only(kivy_app, monkeypatch, tmp_path):
    from dataclasses import asdict
    from hashlib import sha256

    from carveracontroller.machine.run_recording import selected_context

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    root = ws.machine
    path = tmp_path / "recorded-preview.nc"
    path.write_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z10\nG1 Z0 F100\nG1 X1\n")
    record = RunRecording(context=selected_context(path, asdict(root.gcode_viewer.machine_setup)))
    monkeypatch.setattr(root, "temp_dir", str(tmp_path / "controller-cache"))
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    original_file = ws.app.selected_local_filename
    panel.load(RecordingReplay(record.export_bytes()))
    wrong = tmp_path / "wrong-preview.nc"
    wrong.write_text("G21\n")
    panel._open_program(str(wrong))
    wait_for_record(panel)
    assert ws.app.selected_local_filename == original_file
    assert "do not match" in panel.notice.text
    panel._open_program(str(path))
    wait_for_record(panel)
    expected = sha256(path.read_bytes()).hexdigest()
    deadline = time.monotonic() + 15
    while (
        root.loading_file or ws.operation_panel.program is None or ws.operation_panel.program.file_hash != expected
    ) and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not root.loading_file and ws.operation_panel.program is not None
    assert ws.operation_panel.program.file_hash == expected
    assert not panel.preview_loader.is_alive()
    assert root.gcode_viewer.raw_positions[-3:] == [1, 0, 0]
    assert "preview loaded" in panel.notice.text
    staged = ws.app.selected_local_filename
    assert staged != str(path) and "recorded-programs" in staged
    from pathlib import Path

    assert Path(staged).read_bytes() == path.read_bytes()
    assert not ws.app.selected_remote_filename
    assert root.gcode_viewer.pose_mode == "Preview"
    send.assert_not_called()
    previous_replay = panel.replay
    with monkeypatch.context() as patch:
        patch.setattr(root, "load_gcode_file", Mock(side_effect=RuntimeError("decoder unavailable")))
        panel._open_program(str(path))
        wait_for_record(panel)
    assert panel.replay is previous_replay
    assert "preview failed: decoder unavailable" in panel.notice.text
    assert not panel.program_action.disabled
    send.assert_not_called()
    panel.return_live()
    ws.program_tasks.choose("Operations")


def test_recording_details_reflow_and_empty_archive_clears_old_sample(kivy_app):
    from kivy.core.window import Window

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    record = RunRecording()
    record.capture_status("Idle", {"MPos": [1, 2, 3], "C": [0, 4, 0, 1]}, 10, 1000, 1)
    original_size = Window.size
    ws.select("Job")
    ws.program_tasks.choose("Run record")
    try:
        panel.load(RecordingReplay(record.export_bytes()))
        pump_frames(5)

        assert ws.program_tasks.tabs.cols == 5
        panel.export_to_png("/tmp/carvera-run-recording-wide.png")
        Window.size = (700, 900)
        pump_frames(8)
        assert panel.details.height > 0 and panel.cursor.width > 0
        assert all(
            action.width > 0
            for action in (panel.freeze_action, panel.live_action, panel.export_action, panel.import_action)
        )
        panel.export_to_png("/tmp/carvera-run-recording-narrow.png")
        panel.load(RecordingReplay(RunRecording().export_bytes()))
        assert panel.cursor.disabled and "No events" in panel.details.text and "Idle" not in panel.details.text
    finally:
        Window.size = original_size
        panel.return_live()
        ws.program_tasks.choose("Operations")
        pump_frames(5)


def test_bound_recording_start_preserves_previous_buffer_and_failed_start(kivy_app, monkeypatch, tmp_path):
    from hashlib import sha256

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    controller = ws.machine.controller
    previous = RunRecording()
    previous.capture_status("Idle", {}, 10, 1000, 1)
    monkeypatch.setattr(controller, "run_recording", previous)
    send = Mock()
    monkeypatch.setattr(controller, "executeCommand", send)
    path = tmp_path / "recorded-job.nc"
    path.write_bytes(b"G21\r\nG1 X1\r\n")
    monkeypatch.setattr(ws.app, "selected_local_filename", str(path))
    panel.start_action.dispatch("on_release")
    wait_for_record(panel)
    active = controller.run_recording
    assert active is not previous and panel.previous_buffer is previous
    assert active.snapshot()["context"]["program"]["sha256"] == sha256(path.read_bytes()).hexdigest()
    assert "recorded-job.nc" in panel.binding_note.text
    assert "machine execution" in panel.binding_note.text
    active.capture_status("Run", {}, 11, 1001, 1)
    panel.freeze()
    wait_for_record(panel)
    viewer = ws.machine.gcode_viewer
    setup = viewer.machine_setup
    pose = viewer.observed_pose
    mode = viewer.pose_mode
    viewer.configure_machine(work_offset_mm=(-10, -20, -30))
    panel.restore_setup()
    assert viewer.machine_setup == setup
    assert viewer.observed_pose is pose and viewer.pose_mode == mode
    panel.inspect_previous()
    wait_for_record(panel)
    assert "context" not in panel.replay.payload
    assert panel.replay.payload["events"][0]["data"]["state"] == "Idle"
    monkeypatch.setattr(ws.app, "selected_local_filename", str(tmp_path / "missing.nc"))
    panel.start_recording()
    wait_for_record(panel)
    assert controller.run_recording is active and panel.previous_buffer is previous
    assert "Recording unavailable" in panel.notice.text
    send.assert_not_called()
    panel.return_live()


def test_camera_recording_controls_preserve_session_and_drain_on_stop(kivy_app, monkeypatch, tmp_path):
    from pathlib import Path

    from carveracontroller.machine.camera_run import CameraRunReplay
    from carveracontroller.machine.webcam import CameraFrame
    from tests.unit.test_webcam import jpeg

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    monkeypatch.setattr(ws.profile_store, "path", tmp_path / "profiles.json")
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.start_camera()
    wait_for_record(panel)
    writer = panel.camera_writer
    assert writer is not None and writer.thread.is_alive()
    try:
        assert panel.camera_start_action.disabled and panel.start_action.disabled
        assert not panel.camera_stop_action.disabled
        callback = ws.camera_client.frame_observer
        callback(CameraFrame((4, 3), bytes(36), 1000, 10, 1, jpeg()), 0)
        active = ws.machine.controller.run_recording
        panel.start_recording()
        assert ws.machine.controller.run_recording is active
        assert "Stop the current camera recording" in panel.notice.text
        panel.stop_camera()
        wait_for_record(panel)
        assert ws.camera_client.frame_observer is None and not writer.thread.is_alive()
        assert writer.status()["written"] == 1
        archive = CameraRunReplay(writer.folder)
        assert archive.header["recording_session_id"] == active.session_id
        assert archive.read_frame(archive.frames[0]) == jpeg()
        assert str(writer.folder).startswith(str(tmp_path))
        assert Path(writer.folder / "frames.jsonl").exists()
        assert not panel.camera_start_action.disabled
        send.assert_not_called()
    finally:
        panel.shutdown_camera()
        writer.close()
