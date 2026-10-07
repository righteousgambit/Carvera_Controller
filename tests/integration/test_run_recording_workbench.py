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
    original_size = Window.system_size
    ws.select("Job")
    ws.program_tasks.choose("Run record")
    try:
        panel.load(RecordingReplay(record.export_bytes()))
        pump_frames(5)

        assert ws.program_tasks.tabs.cols == 5
        panel.export_to_png("/tmp/carvera-run-recording-wide.png")
        Window.system_size = (700, 900)
        pump_frames(8)
        assert panel.details.height > 0 and panel.cursor.width > 0
        assert all(
            action.width > 0
            for action in (panel.freeze_action, panel.live_action, panel.export_action, panel.import_action)
        )
        panel.export_to_png("/tmp/carvera-run-recording-narrow.png")
        compact_height = panel.height
        original_archive = panel.replay
        for section in (panel.files_section, panel.scene_section, panel.camera_section):
            section.set_expanded(True)
        pump_frames(8)
        assert panel.height > compact_height
        assert panel.camera_start_action.width >= 100
        assert panel.camera_section.height >= panel.camera_section.content.height
        assert panel.details.parent is panel.packet_section.content and panel.cursor.parent is panel
        assert panel.observation.parent is panel and not panel.packet_section.expanded
        panel.export_to_png("/tmp/carvera-run-recording-expanded-narrow.png")
        for section in (panel.files_section, panel.scene_section, panel.camera_section):
            section.set_expanded(False)
        pump_frames(8)
        assert panel.height < compact_height + 1
        assert panel.replay is original_archive
        assert all(
            section.content.parent is None
            for section in (panel.files_section, panel.scene_section, panel.camera_section)
        )
        panel.load(RecordingReplay(RunRecording().export_bytes()))
        assert panel.cursor.disabled and "No events" in panel.details.text and "Idle" not in panel.details.text
        assert "No events" in panel.observation.text and "Idle" not in panel.observation.text
    finally:
        Window.system_size = original_size
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
        assert "recording live" in panel.camera_section.toggle.text
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


def test_camera_archive_tracks_timeline_and_restores_live_without_commands(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.camera_run import CameraRunWriter
    from carveracontroller.machine.webcam import CameraFrame
    from tests.unit.test_webcam import jpeg

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    ws.select("Job")
    from carveracontroller.machine.run_recording import selected_context

    program = tmp_path / "recorded.nc"
    program.write_bytes(b"G21\nG90\nG1 X1 F100\n")
    setup = {
        "work_offset_mm": [0, 0, 0],
        "stock_origin_mm": [0, 0, 0],
        "stock_size_mm": [10, 20, 8],
        "alignment_confirmed": False,
    }
    record = RunRecording(context=selected_context(program, setup))
    for stamp in (10.5, 11.5, 15):
        record.capture_status("Idle", {}, stamp, stamp + 1000, 1)
    writer = CameraRunWriter(tmp_path, record.session_id)
    for index, stamp in enumerate((10, 11, 12, 15)):
        writer.submit(CameraFrame((4, 3), bytes(36), 1000 + stamp, stamp, index + 1, jpeg()), 0)
    writer.close()
    live = CameraFrame((4, 3), bytes([20, 40, 60] * 12), time.time(), time.monotonic(), 9000)
    monkeypatch.setattr(ws.camera_client, "frame", live)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.load(RecordingReplay(record.export_bytes()))
    try:
        panel._import_camera(str(writer.folder / "frames.jsonl"))
        wait_for_record(panel)
        assert panel.camera_archive is not None and not panel.camera_archive_action.disabled
        panel.show_recorded_camera()
        assert "viewing archive" in panel.camera_section.toggle.text
        deadline = time.monotonic() + 5
        while panel._camera_decode_busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert panel.recorded_camera_frame.received_at == 15
        assert ws.camera_texture.texture.size == (4, 3)
        assert all("Recorded camera" in label.text for label in ws.camera_status_labels)
        assert ws.camera_client.snapshot()[1] is live
        panel.step(None)
        deadline = time.monotonic() + 5
        while panel._camera_decode_busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert panel.recorded_camera_frame.received_at == 10
        panel.cursor.value = 2  # Explicit status gap clears the archived image.
        assert panel.recorded_camera_frame is None and ws.camera_texture.texture is None
        ws.camera_registration_panel.fit()
        assert "Show live camera" in ws.camera_registration_panel.note.text
        previous = panel.camera_archive
        unrelated = writer.folder / "other.jsonl"
        unrelated.write_text("{}\n")
        panel._import_camera(str(unrelated))
        wait_for_record(panel)
        assert panel.camera_archive is previous and "frames.jsonl manifest" in panel.notice.text
        foreign = CameraRunWriter(tmp_path, RunRecording().session_id)
        foreign.close()
        panel._import_camera(str(foreign.folder / "frames.jsonl"))
        wait_for_record(panel)
        assert panel.camera_archive is previous and "different status session" in panel.notice.text
        monkeypatch.setattr(ws.profile_store, "path", tmp_path / "profiles.json")
        bundle = tmp_path / "portable.cvcamera"
        panel._export_camera_bundle(str(bundle))
        wait_for_record(panel)
        assert bundle.exists() and "saved and verified" in panel.notice.text
        panel._import_camera_bundle(str(bundle))
        wait_for_record(panel)
        assert panel.camera_archive.folder != previous.folder
        assert panel.camera_archive.manifest_digest == previous.manifest_digest
        assert panel.camera_archive.read_frame(panel.camera_archive.frames[0]) == jpeg()
        monkeypatch.setattr(ws.app, "selected_local_filename", str(program))
        full_bundle = tmp_path / "full.cvsession"
        panel._export_full_run(str(full_bundle))
        wait_for_record(panel)
        assert "Full run saved and verified" in panel.notice.text
        panel._import_full_run(str(full_bundle))
        wait_for_record(panel)
        assert panel.included_program.read_bytes() == program.read_bytes()
        assert not panel.included_program_action.disabled
        assert panel.camera_archive.header["recording_session_id"] == record.session_id
        assert ws.app.selected_local_filename == str(program)
        assert "Full run verified" in panel.notice.text
        from carveracontroller.machine.recorded_jobs import export_recorded_job

        no_camera = tmp_path / "no-camera.cvsession"
        export_recorded_job(panel.replay, program, no_camera)
        panel._import_full_run(str(no_camera))
        wait_for_record(panel)
        assert panel.camera_archive is None
        assert "No camera part included" in panel.camera_archive_note.text
        assert "no camera part bundled" in panel.notice.text
        assert "no retained setup assets" in panel.notice.text
        assert "4 retained events" in panel.notice.text
        assert "execution attribution remain unverified" in panel.notice.text
        panel.load(RecordingReplay(RunRecording().export_bytes()))
        assert panel.camera_archive is None and panel.included_program is None
        assert not panel.camera_replay_enabled and panel.included_program_action.disabled
        panel.show_live_camera()
        assert "idle" in panel.camera_section.toggle.text
        assert ws.camera_texture.texture is not None and ws.camera_texture.sequence == live.sequence
        assert ws.camera_client.snapshot()[1] is live
        send.assert_not_called()
    finally:
        panel.return_live()
        panel.camera_archive = None
        ws.program_tasks.choose("Operations")


def test_superseded_camera_decode_cannot_replace_newer_seek(kivy_app, monkeypatch, tmp_path):
    import threading

    from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter
    from carveracontroller.machine.webcam import CameraFrame
    from tests.unit.test_webcam import jpeg

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    record = RunRecording()
    for stamp in (10.5, 11.5):
        record.capture_status("Idle", {}, stamp, stamp + 1000, 1)
    writer = CameraRunWriter(tmp_path, record.session_id)
    for index, stamp in enumerate((10, 11, 12)):
        writer.submit(CameraFrame((4, 3), bytes(36), None, stamp, index + 1, jpeg()), 0)
    writer.close()
    archive = CameraRunReplay(writer.folder)
    gate, started = threading.Event(), threading.Event()
    original = archive.read_frame

    def blocked(frame):
        if frame["received_at"] == 10:
            started.set()
            assert gate.wait(5)
        return original(frame)

    monkeypatch.setattr(archive, "read_frame", blocked)
    panel.load(RecordingReplay(record.export_bytes()))
    panel.camera_archive = archive
    panel.step(None)
    try:
        panel.show_recorded_camera()
        assert started.wait(2)
        panel.cursor.value = 1
        assert panel.recorded_camera_frame is None
        gate.set()
        deadline = time.monotonic() + 5
        while panel._camera_decode_busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert panel.recorded_camera_frame.received_at == 11
    finally:
        gate.set()
        panel.return_live()
        panel.camera_archive = None


def test_start_with_setup_assets_activates_only_after_custody_and_exports_bound_snapshot(
    kivy_app, monkeypatch, tmp_path
):
    from dataclasses import asdict

    from carveracontroller import desktop_job_packages
    from carveracontroller.machine.job_packages import JobPackage, load_package
    from carveracontroller.machine.recorded_jobs import import_recorded_job

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    controller = ws.machine.controller
    previous = controller.run_recording
    program = tmp_path / "selected.nc"
    program.write_bytes(b"G21\nG90\nG1 X1 F100\n")
    monkeypatch.setattr(ws.app, "selected_local_filename", str(program))
    monkeypatch.setattr(ws.profile_store, "path", tmp_path / "profiles.json")
    setup = asdict(ws.machine.gcode_viewer.machine_setup)
    job = JobPackage(
        "Captured",
        b"",
        stock={
            "size_mm": list(setup["stock_size_mm"]) if setup["stock_size_mm"] is not None else None,
            "origin_mm": list(setup["stock_origin_mm"]),
            "work_offset_mm": list(setup["work_offset_mm"]),
            "alignment_confirmed": setup["alignment_confirmed"],
            "rotation_deg": setup["stock_rotation_deg"],
        },
    )
    monkeypatch.setattr(desktop_job_packages, "capture_recording_job", lambda *_: job)
    send = Mock()
    monkeypatch.setattr(controller, "executeCommand", send)
    assert panel.setup_start_action.parent is panel.start_action.parent
    assert panel.setup_start_action.parent is not panel.files_section.content
    assert panel.start_action.text == "Record program status"
    assert panel.setup_start_action.text == "Record program + scene"
    panel.setup_start_action.dispatch("on_release")
    wait_for_record(panel)
    active = controller.run_recording
    assert active is not previous and active.snapshot()["schema"] == 3, panel.notice.text
    assert panel.previous_buffer is previous
    retained = panel.setup_archives[active.session_id]
    assert load_package(retained).package.program == program.read_bytes()
    panel.freeze()
    wait_for_record(panel)
    assert "Setup archive bound" in panel.binding_note.text
    bundle = tmp_path / "with-setup.cvsession"
    panel._export_full_run(str(bundle))
    wait_for_record(panel)
    installed = import_recorded_job(bundle, tmp_path / "readback")
    assert installed.setup_archive.read_bytes() == retained.read_bytes()
    assert "setup assets included" in panel.notice.text
    panel._import_full_run(str(bundle))
    wait_for_record(panel)
    assert "retained setup assets available for review" in panel.notice.text
    assert "historical tools/calibration unavailable" not in panel.notice.text
    assert panel.setup_archives[active.session_id].read_bytes() == retained.read_bytes()
    assert controller.run_recording is active
    bad = JobPackage(
        "Missing asset",
        b"",
        stock=job.stock,
        machine={"cad_path": "missing.json"},
        assets={"missing.json": tmp_path / "missing.json"},
    )
    monkeypatch.setattr(desktop_job_packages, "capture_recording_job", lambda *_: bad)
    panel.start_recording(retain_setup=True)
    wait_for_record(panel)
    assert controller.run_recording is active and panel.previous_buffer is previous
    assert "Recording unavailable" in panel.notice.text
    send.assert_not_called()
    panel.return_live()


def test_receipt_cursor_keyboard_navigation_is_local_and_releases_hidden_focus(kivy_app, monkeypatch):
    from kivy.core.window import Window
    from kivy.uix.modalview import ModalView

    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    record = RunRecording()
    record.capture_status("Run", {"MPos": [1, 2, 3]}, 10, 1000, 1)
    record.capture_status("Hold", {"MPos": [2, 2, 3]}, 15, 1005, 1)
    ws.select("Job")
    ws.program_tasks.choose("Run record")
    panel.load(RecordingReplay(record.export_bytes()))
    pump_frames(5)
    cursor = panel.cursor
    cursor.focus = True
    assert cursor.focus and cursor._get_focus_next("focus_next") is not None

    def key(name):
        code = (0, name)
        assert cursor.keyboard_on_key_down(Window, code, "", [])
        assert cursor.keyboard_on_key_up(Window, code)

    try:
        key("home")
        assert cursor.value == 0
        key("right")
        assert cursor.value == 1 and "Gap" in panel.details.text
        key("end")
        assert cursor.value == 2 and "Hold" in panel.details.text
        key("left")
        assert cursor.value == 1
        key("home")
        key("spacebar")
        assert panel.playback.running
        key("spacebar")
        assert not panel.playback.running
        key("spacebar")
        key("right")
        assert not panel.playback.running and cursor.value == 1
        modal = ModalView()
        modal.open(animation=False)
        pump_frames(2)
        before = cursor.value
        assert not cursor.keyboard_on_key_down(Window, (0, "right"), "", [])
        assert cursor.value == before
        modal.dismiss(animation=False)
        pump_frames(2)
        cursor.focus = True
        ws.program_tasks.choose("Operations")
        pump_frames(2)
        assert not cursor.focus
        assert not cursor.keyboard_on_key_down(Window, (0, "end"), "", [])
        assert cursor.value == before
        send.assert_not_called()
    finally:
        cursor.focus = False
        panel.return_live()
        ws.program_tasks.choose("Operations")


def test_recording_disclosure_reveals_heading_after_tall_content_layout(kivy_app):
    from kivy.core.window import Window
    from kivy.uix.boxlayout import BoxLayout
    from kivy.uix.scrollview import ScrollView
    from kivy.uix.widget import Widget

    from carveracontroller.desktop_run_recording import ReplaySection

    scroll = ScrollView(size_hint=(None, None), size=(350, 240), pos=(10, 10))
    body = BoxLayout(orientation="vertical", size_hint_y=None)
    body.bind(minimum_height=body.setter("height"))
    body.add_widget(Widget(size_hint_y=None, height=500))
    section = ReplaySection("Recorded scene", [Widget(size_hint_y=None, height=650)])
    body.add_widget(section)
    body.add_widget(Widget(size_hint_y=None, height=500))
    scroll.add_widget(body)
    Window.add_widget(scroll)
    try:
        pump_frames(8)
        section.set_expanded(True)
        pump_frames(15)
        heading_y = section.toggle.to_window(section.toggle.x, section.toggle.top)[1]
        viewport_top = scroll.to_window(scroll.x, scroll.top)[1]
        assert viewport_top - 30 <= heading_y <= viewport_top
        section.set_expanded(False)
        scroll.scroll_y = 1
        section.set_expanded(True)
        section.set_expanded(False)
        pump_frames(15)
        assert scroll.scroll_y == 1  # A stale expansion must not pull the operator back.
    finally:
        Window.remove_widget(scroll)


def test_recording_export_dialog_rejects_changed_selection(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    callbacks = []
    monkeypatch.setattr(ws, "choose_profile_file", lambda callback, **kwargs: callbacks.append(callback))
    worker = Mock()
    monkeypatch.setattr(panel, "_worker", worker)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    record = RunRecording()
    first = RecordingReplay(record.export_bytes())
    monkeypatch.setattr(panel, "replay", first)
    panel.export()
    monkeypatch.setattr(panel, "replay", RecordingReplay(record.export_bytes()))
    path = tmp_path / "wrong-selection.cvrun"
    callbacks.pop()(str(path))
    assert "selection changed" in panel.notice.text and not path.exists()
    worker.assert_not_called()
    first_archive = object()
    monkeypatch.setattr(panel, "camera_archive", first_archive)
    panel.export_camera()
    monkeypatch.setattr(panel, "camera_archive", object())
    path = tmp_path / "wrong-selection.cvcamera"
    callbacks.pop()(str(path))
    assert "selection changed" in panel.notice.text and not path.exists()
    worker.assert_not_called()
    send.assert_not_called()


def test_queued_recording_export_keeps_accepted_source(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel = ws.run_recording_panel
    first_record = RunRecording()
    first_record.capture_status("Idle", {}, 1, 1000, 1)
    accepted = RecordingReplay(first_record.export_bytes())
    monkeypatch.setattr(panel, "replay", accepted)
    worker = Mock()
    monkeypatch.setattr(panel, "_worker", worker)
    path = tmp_path / "accepted.cvrun"
    panel._export_to(str(path))
    other_record = RunRecording()
    other_record.capture_status("Alarm:3", {}, 2, 1001, 2)
    monkeypatch.setattr(panel, "replay", RecordingReplay(other_record.export_bytes()))
    saved = worker.call_args.args[0]()
    assert saved == path
    assert RecordingReplay(path.read_bytes()).payload == accepted.payload
