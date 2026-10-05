from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image, PngImagePlugin  # Register only the PNG writer for render evidence.

from carveracontroller.desktop_run_recording import RunRecordingPanel
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
    Image.frombytes("RGBA", rendered.size, rendered.pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(
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
