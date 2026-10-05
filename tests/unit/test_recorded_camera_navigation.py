from types import SimpleNamespace

import pytest

from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter
from carveracontroller.machine.recorded_camera_navigation import camera_observation_index
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording


def associated_record(tmp_path, generations=(0, 0, 0)):
    record = RunRecording()
    for stamp in (10, 10.5, 11.5, 12, 16):
        record.capture_status("Idle", {}, stamp, stamp + 1000, 1)
    writer = CameraRunWriter(tmp_path, record.session_id)
    try:
        for index, stamp in enumerate((10.1, 11.1, 12.1)):
            writer.submit(
                SimpleNamespace(
                    size=(1, 1),
                    jpeg=b"\xff\xd8receipt metadata\xff\xd9",
                    received_at=stamp,
                    captured_at=stamp + 1000,
                    sequence=index,
                ),
                generations[index],
            )
    finally:
        writer.close()
    return RecordingReplay(record.export_bytes()), CameraRunReplay(writer.folder)


def test_receipt_navigation_skips_status_outside_camera_window_and_performs_no_image_io(tmp_path, monkeypatch):
    replay, camera = associated_record(tmp_path)

    def forbid(*_args, **_kwargs):
        raise AssertionError("Receipt navigation read image assets")

    monkeypatch.setattr(camera, "read_frame", forbid)
    assert camera_observation_index(replay, camera) == 1
    assert camera_observation_index(replay, camera, last=True) == 3
    assert replay.payload["events"][-1]["monotonic_at"] == 16
    with pytest.raises(ValueError, match="another status session"):
        camera_observation_index(RecordingReplay(RunRecording().export_bytes()), camera)


def test_no_camera_overlap_keeps_navigation_unavailable(tmp_path):
    replay, camera = associated_record(tmp_path)
    for event in replay.payload["events"]:
        event["monotonic_at"] += 100
    assert camera_observation_index(replay, camera) is None
    assert camera_observation_index(replay, camera, last=True) is None


def test_camera_source_boundary_is_not_promoted_to_an_observation(tmp_path):
    replay, camera = associated_record(tmp_path, generations=(0, 1, 1))
    assert camera.at(10.5)["frame"] is None
    assert camera_observation_index(replay, camera) == 2
    assert camera_observation_index(replay, camera, last=True) == 3
