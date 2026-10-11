from types import SimpleNamespace

import pytest

from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter
from carveracontroller.machine.recorded_camera_navigation import (
    adjacent_camera_observation_index,
    camera_observation_index,
)
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


def test_adjacent_images_skip_repeated_associations_without_reading_assets(tmp_path, monkeypatch):
    replay, camera = associated_record(tmp_path)
    monkeypatch.setattr(camera, "read_frame", lambda *_: pytest.fail("Image I/O during metadata navigation"))
    assert adjacent_camera_observation_index(replay, camera, 1) == 2
    # Statuses 2 and 3 share one image; no later associated distinct image exists.
    assert adjacent_camera_observation_index(replay, camera, 2) is None
    assert adjacent_camera_observation_index(replay, camera, 3, previous=True) == 1
    assert adjacent_camera_observation_index(replay, camera, 1, previous=True) is None
    # All JPEG assets are identical: frame receipt identity, not JPEG hash, matters.
    assert len({frame["sha256"] for frame in camera.frames}) == 1


def test_adjacent_images_recover_from_outside_window_and_source_boundary(tmp_path):
    replay, camera = associated_record(tmp_path, generations=(0, 1, 1))
    assert camera.at(10.5)["frame"] is None
    assert adjacent_camera_observation_index(replay, camera, 0) == 2
    assert adjacent_camera_observation_index(replay, camera, 1) == 2
    assert adjacent_camera_observation_index(replay, camera, 4, previous=True) == 3
    assert adjacent_camera_observation_index(replay, camera, 2, previous=True) is None


@pytest.mark.parametrize("current", [-1, 999999, True, 1.5, "1"])
def test_adjacent_images_reject_invalid_selection(tmp_path, current):
    replay, camera = associated_record(tmp_path)
    with pytest.raises(ValueError, match="outside the recording"):
        adjacent_camera_observation_index(replay, camera, current)


def test_adjacent_images_reject_other_session_and_absent_overlap(tmp_path):
    replay, camera = associated_record(tmp_path)
    with pytest.raises(ValueError, match="another status session"):
        adjacent_camera_observation_index(RecordingReplay(RunRecording().export_bytes()), camera, 0)
    for event in replay.payload["events"]:
        event["monotonic_at"] += 100
    assert adjacent_camera_observation_index(replay, camera, 1) is None
    assert adjacent_camera_observation_index(replay, camera, 1, previous=True) is None


def test_adjacent_images_skip_explicit_telemetry_gap(tmp_path):
    replay, camera = associated_record(tmp_path)
    gap = next(index for index, event in enumerate(replay.payload["events"]) if event["kind"] == "gap")
    assert adjacent_camera_observation_index(replay, camera, gap, previous=True) == 3
    assert adjacent_camera_observation_index(replay, camera, gap) is None
    assert replay.payload["events"][gap]["kind"] == "gap"
