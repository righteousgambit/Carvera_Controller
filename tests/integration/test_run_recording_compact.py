import io
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, JpegImagePlugin, PngImagePlugin  # Register only the formats used by these scenarios.

from carveracontroller.desktop_run_recording import RunRecordingPanel
from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [650, 1200])
def test_packet_details_do_not_displace_primary_recording_controls(tmp_path, width):
    record = RunRecording()
    record.capture_status("Idle", {"MPos": [1, 2, 3], "C": [0, 4, 0, 1], "T": [1, 50.48], "S": [0, 12000]}, 10, 1000, 1)
    workspace = SimpleNamespace(
        machine=SimpleNamespace(controller=SimpleNamespace(run_recording=record), gcode_viewer=Mock()),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=width)
    panel.refresh()
    pump_frames(5)
    before = panel.height
    panel.load(RecordingReplay(record.export_bytes()))
    pump_frames(5)
    assert "reported Idle" in panel.observation.text
    assert "Reported T1" in panel.observation.text and "Actual RPM report 0" in panel.observation.text
    assert "12000" not in panel.observation.text  # Commanded RPM is not actual RPM.
    assert "Spindle report: 0, 12000" in panel.details.text
    assert not panel.packet_section.expanded
    assert panel.height - before < 100
    assert panel.details.parent is panel.packet_section.content
    rendered = panel.export_as_image().texture
    assert "PNG" in Image.SAVE and PngImagePlugin is not None
    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(
        tmp_path / f"recording-compact-{width}.png", format="PNG"
    )
    panel.packet_section.set_expanded(True)
    pump_frames(5)
    assert panel.height > before + 100
    panel.packet_section.set_expanded(False)
    pump_frames(5)
    assert "Spindle report: 0, 12000" in panel.details.text
    record.capture_status("Hold", {"MPos": [4, 2, 3]}, 20, 1010, 1)
    panel.load(RecordingReplay(record.export_bytes()))
    pump_frames(5)
    assert "Tool unknown" in panel.observation.text and "RPM unknown" in panel.observation.text
    panel.step(1 - panel.cursor.value)
    assert "motion unknown" in panel.observation.text
    panel.return_live()
    assert "Latest received state: Hold" in panel.observation.text


@pytest.mark.parametrize("width", [320, 1200])
def test_camera_flush_timeout_keeps_owned_writer_and_controls_until_drain(tmp_path, monkeypatch, width):
    import threading

    from tests.unit.test_camera_run import frame

    send = Mock()
    workspace = SimpleNamespace(
        machine=SimpleNamespace(
            controller=SimpleNamespace(run_recording=RunRecording(), executeCommand=send), gcode_viewer=Mock()
        ),
        camera_client=SimpleNamespace(set_frame_observer=Mock()),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=width)
    writer = CameraRunWriter(tmp_path, workspace.machine.controller.run_recording.session_id)
    panel.camera_writer = writer
    entered, release = threading.Event(), threading.Event()
    persist, close = writer._persist, writer.close

    def held_asset(item, data):
        entered.set()
        assert release.wait(10)
        return persist(item, data)

    # Exercise the actual timeout branch promptly without altering production's
    # five-second deadline or making the fixture depend on slow disk behavior.
    monkeypatch.setattr(writer, "_persist", held_asset)
    monkeypatch.setattr(writer, "close", lambda: close(timeout=0.01))
    try:
        assert writer.submit(frame(1, 10), 0)
        assert entered.wait(2)
        worker = writer.thread
        panel.stop_camera()
        deadline = time.monotonic() + 5
        while panel.busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel.busy and "retain the existing worker" in panel.notice.text
        panel.refresh()
        assert panel.camera_writer is writer and writer.thread is worker and worker.is_alive()
        assert "flushing" in panel.camera_note.text and "retaining existing writer" in panel.camera_note.text
        assert "flushing" in panel.camera_section.toggle.text
        assert panel.camera_start_action.disabled and panel.camera_stop_action.disabled
        assert panel.start_action.disabled and panel.setup_start_action.disabled
        panel.start_camera()  # An attempted restart cannot replace the worker.
        assert panel.camera_writer is writer
        workspace.camera_client.set_frame_observer.assert_called_once_with(None)
        release.set()
        close()  # Wait on the original writer; no retry or second worker.
        panel.refresh()
        assert "saved" in panel.camera_note.text and "1 written" in panel.camera_note.text
        assert not panel.camera_start_action.disabled and not panel.start_action.disabled
        assert panel.camera_stop_action.disabled
        assert CameraRunReplay(writer.folder).footer["written"] == 1
        send.assert_not_called()
    finally:
        release.set()
        close()


def test_camera_persistence_error_is_incomplete_in_workbench(tmp_path, monkeypatch):
    from tests.unit.test_camera_run import frame

    workspace = SimpleNamespace(
        machine=SimpleNamespace(controller=SimpleNamespace(run_recording=RunRecording()), gcode_viewer=Mock()),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace)
    writer = CameraRunWriter(tmp_path, workspace.machine.controller.run_recording.session_id)
    panel.camera_writer = writer

    def failed_asset(_item, _data):
        raise OSError("private disk details")

    monkeypatch.setattr(writer, "_persist", failed_asset)
    assert writer.submit(frame(1, 10), 0)
    writer.close()
    panel.refresh()
    assert "incomplete" in panel.camera_note.text and "1 missing" in panel.camera_note.text
    assert "saved" not in panel.camera_note.text and "private" not in panel.camera_note.text
    assert not panel.camera_start_action.disabled and panel.camera_stop_action.disabled


@pytest.mark.parametrize("width", [320, 1200])
def test_camera_observation_actions_seek_and_decode_without_machine_commands(tmp_path, monkeypatch, width):
    record = RunRecording()
    for stamp in (10, 10.5, 11.5, 12, 16):
        record.capture_status("Idle", {}, stamp, stamp + 1000, 1)
    send = Mock()
    workspace = SimpleNamespace(
        machine=SimpleNamespace(
            controller=SimpleNamespace(run_recording=record, executeCommand=send), gcode_viewer=Mock()
        ),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=width)
    encoded = io.BytesIO()
    assert JpegImagePlugin is not None
    Image.new("RGB", (4, 3), (20, 40, 60)).save(encoded, format="JPEG")
    writer = CameraRunWriter(tmp_path, record.session_id)
    try:
        for sequence, stamp in enumerate((10.1, 11.1, 12.1)):
            writer.submit(
                SimpleNamespace(
                    size=(4, 3), jpeg=encoded.getvalue(), received_at=stamp, captured_at=stamp + 1000, sequence=sequence
                ),
                0,
            )
    finally:
        writer.close()
    panel.load(RecordingReplay(record.export_bytes()))
    archive = CameraRunReplay(writer.folder)
    reads = []
    read_frame = archive.read_frame

    def observed_read(receipt):
        reads.append(receipt["attempt"])
        return read_frame(receipt)

    monkeypatch.setattr(archive, "read_frame", observed_read)
    panel._camera_loaded(archive, record.session_id)

    def decoded():
        deadline = time.monotonic() + 5
        while (panel.busy or panel._camera_decode_busy) and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel.busy and not panel._camera_decode_busy and panel.recorded_camera_frame is not None

    panel.camera_first_observation.dispatch("on_release")
    decoded()
    assert panel.cursor.value == 1 and panel.recorded_camera_frame.received_at == 10.1
    assert reads == [1]  # One navigation action performs one asset read/decode.
    panel.camera_previous_observation.dispatch("on_release")
    decoded()
    assert panel.cursor.value == 1 and "No earlier" in panel.notice.text
    panel.camera_next_observation.dispatch("on_release")
    decoded()
    assert panel.cursor.value == 2 and panel.recorded_camera_frame.received_at == 11.1
    panel.camera_next_observation.dispatch("on_release")
    decoded()
    assert panel.cursor.value == 2 and "No later" in panel.notice.text
    panel.camera_previous_observation.dispatch("on_release")
    decoded()
    assert panel.cursor.value == 1 and panel.recorded_camera_frame.received_at == 10.1
    panel.camera_last_observation.dispatch("on_release")
    decoded()
    assert panel.cursor.value == 3 and panel.recorded_camera_frame.received_at == 11.1
    assert "exposure timing" in panel.notice.text
    panel.busy = True
    panel.seek_camera_observation()
    assert panel.cursor.value == 3
    panel.busy = False
    now = [100.0]
    monkeypatch.setattr("carveracontroller.desktop_run_recording.time", SimpleNamespace(monotonic=lambda: now[0]))
    panel.cursor.value = 1
    decoded()
    panel.toggle_playback()
    now[0] = 101.5
    panel._advance_playback(0)
    decoded()
    assert panel.cursor.value == 3 and panel.recorded_camera_frame.received_at == 11.1
    now[0] = 102.0
    panel._advance_playback(0)
    pump_frames(3)
    assert panel._playback_missing and panel.recorded_camera_frame is None
    assert panel._desired_camera is None and "motion unknown" in panel.observation.text
    panel.pause_playback()
    panel.show_live_camera()
    assert not panel.camera_replay_enabled
    send.assert_not_called()


@pytest.mark.parametrize("width", [320, 1200])
def test_receipt_position_readout_advances_between_packets_and_keeps_gap_visible(monkeypatch, tmp_path, width):
    record = RunRecording()
    for stamp in (10, 11, 16):
        record.capture_status("Idle", {}, stamp, stamp + 1000, 1)
    send = Mock()
    workspace = SimpleNamespace(
        machine=SimpleNamespace(
            controller=SimpleNamespace(run_recording=record, executeCommand=send), gcode_viewer=Mock()
        ),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=width)
    panel.load(RecordingReplay(record.export_bytes()))
    panel.cursor.value = 1
    now = [100.0]
    monkeypatch.setattr("carveracontroller.desktop_run_recording.time", SimpleNamespace(monotonic=lambda: now[0]))
    panel.toggle_playback()
    now[0] = 101.5
    panel._advance_playback(0)
    pump_frames(3)
    assert "Receipt +2.50 / 6.00 s" in panel.receipt_position.text
    assert "event 2/4" in panel.receipt_position.text
    assert "Next gap at +6.00 s" in panel.receipt_position.text
    assert panel._playback_missing
    assert panel.receipt_position.parent is panel
    assert panel.receipt_position.texture_size[1] <= panel.receipt_position.height
    assert panel.cursor.y >= panel.receipt_position.top
    assert panel.receipt_position.y >= panel.cursor_hint.top
    rendered = panel.export_as_image().texture
    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(tmp_path / f"receipt-position-{width}.png")
    now[0] = 106.0
    panel._advance_playback(0)
    assert not panel.playback.running
    assert "Receipt +6.00 / 6.00 s" in panel.receipt_position.text
    panel.step(1)
    assert "event 4/4" in panel.receipt_position.text
    assert "No later evidence boundary" in panel.receipt_position.text
    panel.return_live()
    assert panel.receipt_position.text == "Receipt timeline · live buffer"
    send.assert_not_called()


def test_replay_transport_precedes_timeline_and_keyboard_help():
    record = RunRecording()
    workspace = SimpleNamespace(
        machine=SimpleNamespace(controller=SimpleNamespace(run_recording=record), gcode_viewer=Mock()),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=320)
    panel.refresh()
    pump_frames(6)
    transport = panel.playback_action.parent
    assert transport.parent is panel
    assert transport.y >= panel.navigation_actions[0].parent.top
    assert panel.receipt_position.y >= panel.playback_note.top
    assert panel.playback_note.y >= panel.cursor_hint.top
    assert transport.height >= panel.playback_action.height


@pytest.mark.parametrize("width, columns", [(320, 2), (1200, 4)])
def test_camera_image_navigation_reflows_inside_expanded_section(tmp_path, width, columns):
    workspace = SimpleNamespace(
        machine=SimpleNamespace(controller=SimpleNamespace(run_recording=RunRecording()), gcode_viewer=Mock()),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=width)
    panel.camera_section.set_expanded(True)
    pump_frames(8)
    actions = (
        panel.camera_first_observation,
        panel.camera_previous_observation,
        panel.camera_next_observation,
        panel.camera_last_observation,
    )
    grid = actions[0].parent
    assert grid.cols == columns, (grid.width, grid.min_width, grid.spacing)
    for action in actions:
        assert action.parent is grid
        assert panel.x <= action.x and action.right <= panel.right
        assert action.texture_size[0] <= action.width
        assert action.height >= 32
    rendered = panel.export_as_image().texture
    Image.frombytes("RGBA", rendered.size, rendered.pixels).save(
        tmp_path / f"camera-image-navigation-{width}.png", format="PNG"
    )


@pytest.mark.parametrize("change", ["cursor", "archive", "replay", "live_camera", "return_live"])
def test_late_camera_navigation_cannot_replace_changed_selection(tmp_path, monkeypatch, change):
    import threading

    from carveracontroller.machine import recorded_camera_navigation

    record = RunRecording()
    for stamp in (10, 11):
        record.capture_status("Idle", {}, stamp, stamp + 1000, 1)
    send = Mock()
    workspace = SimpleNamespace(
        machine=SimpleNamespace(
            controller=SimpleNamespace(run_recording=record, executeCommand=send), gcode_viewer=Mock()
        ),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=650)
    panel.load(RecordingReplay(record.export_bytes()))
    panel.camera_archive = SimpleNamespace(header={"recording_session_id": record.session_id})
    started, release = threading.Event(), threading.Event()

    def blocked(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return 0

    monkeypatch.setattr(recorded_camera_navigation, "adjacent_camera_observation_index", blocked)
    try:
        panel.seek_camera_observation(previous=True)
        assert started.wait(2) and panel.busy
        # The UI thread continues to process ordinary Kivy frames during the search.
        pump_frames(3)
        if change == "cursor":
            panel.cursor.value = 0
        elif change == "archive":
            panel.camera_archive = SimpleNamespace(header={"recording_session_id": record.session_id})
        elif change == "replay":
            panel.load(RecordingReplay(record.export_bytes()))
        elif change == "live_camera":
            panel.show_live_camera()
        else:
            panel.return_live()
        expected = (panel.replay, panel.camera_archive, panel.cursor.value, panel.camera_replay_enabled)
        release.set()
        deadline = time.monotonic() + 5
        while panel.busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel.busy
        assert (panel.replay, panel.camera_archive, panel.cursor.value, panel.camera_replay_enabled) == expected
        assert panel.recorded_camera_frame is None and not panel._camera_decode_busy
        assert "navigation withheld" in panel.notice.text
        send.assert_not_called()
    finally:
        release.set()


def test_recording_worker_start_failure_releases_controls_without_work_or_commands(monkeypatch):
    import threading

    record = RunRecording()
    record.capture_status("Idle", {}, 10, 1010, 1)
    send = Mock()
    workspace = SimpleNamespace(
        machine=SimpleNamespace(
            controller=SimpleNamespace(run_recording=record, executeCommand=send), gcode_viewer=Mock()
        ),
        camera_texture=Mock(),
        _refresh_camera=Mock(),
    )
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=650)
    panel.load(RecordingReplay(record.export_bytes()))
    replay, cursor = panel.replay, panel.cursor.value
    work, done = Mock(), Mock()

    def start_failure():
        raise RuntimeError("cannot start a new thread; private diagnostic must not be displayed")

    monkeypatch.setattr(threading, "Thread", lambda **kwargs: SimpleNamespace(start=start_failure))
    panel._worker(work, done)
    assert not panel.busy and not panel.playback_action.disabled
    assert panel.replay is replay and panel.cursor.value == cursor
    assert "could not start" in panel.notice.text
    assert "private diagnostic" not in panel.notice.text
    work.assert_not_called()
    done.assert_not_called()
    send.assert_not_called()
