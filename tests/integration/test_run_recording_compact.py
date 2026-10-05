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


def test_camera_observation_actions_seek_and_decode_without_machine_commands(tmp_path):
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
    panel = RunRecordingPanel(workspace, size_hint_x=None, width=1200)
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
    panel._camera_loaded(CameraRunReplay(writer.folder), record.session_id)

    def decoded():
        deadline = time.monotonic() + 5
        while panel._camera_decode_busy and time.monotonic() < deadline:
            pump_frames(1, sleep=0.01)
        assert not panel._camera_decode_busy and panel.recorded_camera_frame is not None

    panel.camera_first_observation.dispatch("on_release")
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
    panel.show_live_camera()
    assert not panel.camera_replay_enabled
    send.assert_not_called()
