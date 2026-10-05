import copy
import hashlib
import io
import json
import time

import pytest
from PIL import Image

from carveracontroller.machine.camera_calibration_file import (
    MAX_CALIBRATION_BYTES,
    CalibrationReference,
    calibration_data,
    decode_calibration,
    read_calibration,
    write_calibration,
)
from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    CameraPose,
    CameraRegistration,
    RegistrationObservation,
)
from carveracontroller.machine.webcam import CameraFrame, WebcamClient


def reference():
    buffer = io.BytesIO()
    Image.new("RGB", (24, 18), (30, 90, 120)).save(buffer, format="JPEG")
    jpeg = buffer.getvalue()
    with Image.open(io.BytesIO(jpeg)) as image:
        pixels = image.convert("RGB").tobytes()
    return CalibrationReference(
        CameraFrame((24, 18), pixels, time.time(), time.monotonic(), 7, jpeg),
        "a" * 64,
        3,
        8,
        (0, -100, 0),
        time.monotonic(),
    )


def data():
    registration = CameraRegistration(CameraIntrinsics(24, 18, 20, 20, 12, 9), CameraPose((0, 0, 0), (0, 0, 100)))
    return calibration_data(registration, [RegistrationObservation((0, 0, 0), (12, 9))], reference())


def test_exact_image_pose_and_correspondences_roundtrip_without_overwrite(tmp_path):
    original = data()
    path = tmp_path / "reference.cvcal"
    digest = write_calibration(path, original)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    registration, observations, captured, y = read_calibration(path)
    assert captured.to_dict() == original["reference"]
    assert captured.frame.pixels == reference().frame.pixels
    assert captured.machine_mm == (0, -100, 0) and y == -100
    assert observations[0].pixel == (12, 9)
    assert registration.intrinsics.width == 24
    with pytest.raises(FileExistsError):
        write_calibration(path, original)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("mutation", ["hash", "size", "pose", "table", "source", "timestamp", "sequence", "points"])
def test_corrupt_reference_is_rejected_before_creating_destination(tmp_path, mutation):
    broken = copy.deepcopy(data())
    if mutation == "hash":
        broken["reference"]["jpeg_sha256"] = "0" * 64
    elif mutation == "size":
        broken["reference"]["size"] = [25, 18]
    elif mutation == "pose":
        broken["reference"]["machine_mm"] = [0, float("nan"), 0]
    elif mutation == "table":
        broken["reference_machine_y_mm"] = -99
    elif mutation == "source":
        broken["reference"]["source_sha256"] = "URL with credentials"
    elif mutation == "timestamp":
        broken["reference"]["received_monotonic_s"] = None
    elif mutation == "sequence":
        broken["reference"]["sequence"] = True
    else:
        broken["observations"] *= 129
    path = tmp_path / "invalid.cvcal"
    with pytest.raises((ValueError, TypeError)):
        write_calibration(path, broken)
    assert not path.exists()


def test_legacy_calibration_retains_numbers_without_claiming_image_custody(tmp_path):
    legacy = data()
    legacy["schema"] = 1
    del legacy["reference"]
    path = tmp_path / "legacy.cvcal"
    path.write_text(json.dumps(legacy))
    _, _, captured, y = read_calibration(path)
    assert captured is None and y == -100
    oversized = tmp_path / "oversize.cvcal"
    with oversized.open("wb") as stream:
        stream.truncate(MAX_CALIBRATION_BYTES + 1)
    with pytest.raises(ValueError, match="exceeds"):
        read_calibration(oversized)
    with pytest.raises(ValueError):
        decode_calibration([])


def test_camera_snapshot_binds_generation_without_disclosing_url():
    client = WebcamClient("http://localhost:18091/snapshot.jpg?token=private", start=False)
    client.frame = reference().frame
    enabled, frame, generation, fingerprint = client.calibration_snapshot()
    assert enabled and frame is client.frame and generation == 0
    assert fingerprint == hashlib.sha256(client.url.encode()).hexdigest()
    client.configure("http://localhost:18091/other.jpg")
    assert client.calibration_snapshot()[1] is None
    assert client.calibration_snapshot()[2] == 1
    assert client.calibration_snapshot()[3] != fingerprint


def test_decompression_bomb_becomes_controlled_validation_error(monkeypatch):
    def reject(*_args, **_kwargs):
        raise Image.DecompressionBombError("oversize")
    original = data()
    monkeypatch.setattr("carveracontroller.machine.camera_calibration_file.Image.open", reject)
    with pytest.raises(ValueError, match="dimension limit"):
        decode_calibration(original)
