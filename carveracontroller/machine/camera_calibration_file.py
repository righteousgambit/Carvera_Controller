"""Bounded calibration exchange retaining the exact image used for correspondences."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, TypedDict, cast

from PIL import Image

from carveracontroller.machine.camera_registration import CameraRegistration, RegistrationObservation
from carveracontroller.machine.webcam import MAX_FRAME_BYTES, CameraFrame

MAX_CALIBRATION_BYTES = 12 * 1024 * 1024

Vec3 = tuple[float, float, float]


class ReferenceData(TypedDict):
    jpeg_base64: str
    jpeg_sha256: str
    size: list[int]
    captured_at: float | None
    received_monotonic_s: float
    sequence: int
    source_sha256: str
    camera_generation: int
    connection_generation: int
    machine_mm: Vec3 | None
    pose_received_monotonic_s: float | None
    timing_qualification: str


class CalibrationData(TypedDict):
    schema: int
    registration: dict[str, Any]
    observations: list[dict[str, Any]]
    reference: ReferenceData | None
    reference_machine_y_mm: float | None
    physical_qualification: str


DecodedCalibration = tuple[
    CameraRegistration, tuple[RegistrationObservation, ...], Optional["CalibrationReference"], Optional[float]
]


def _record(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("Invalid " + label + " record")
    # Values remain untrusted until each field is validated below.
    return value


def _number(value: object, label: str) -> float:
    if type(value) not in (int, float):
        raise ValueError("Invalid " + label)
    try:
        result = float(cast("int | float", value))
    except OverflowError as exc:
        raise ValueError("Invalid " + label) from exc
    if not math.isfinite(result):
        raise ValueError("Invalid " + label)
    return result


def _timestamp(value: object) -> float | None:
    if value is None:
        return None
    result = _number(value, "reference timestamp")
    if result < 0:
        raise ValueError("Invalid reference timestamp")
    return result


def _identity(value: object) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("Invalid reference identity")
    return value


@dataclass(frozen=True)
class CalibrationReference:
    frame: CameraFrame
    source_sha256: str
    camera_generation: int
    connection_generation: int
    machine_mm: Vec3 | None
    pose_received_at: float | None

    def to_dict(self) -> ReferenceData:
        return {
            "jpeg_base64": base64.b64encode(self.frame.jpeg).decode("ascii"),
            "jpeg_sha256": hashlib.sha256(self.frame.jpeg).hexdigest(),
            "size": [self.frame.size[0], self.frame.size[1]],
            "captured_at": self.frame.captured_at,
            "received_monotonic_s": self.frame.received_at,
            "sequence": self.frame.sequence,
            "source_sha256": self.source_sha256,
            "camera_generation": self.camera_generation,
            "connection_generation": self.connection_generation,
            "machine_mm": self.machine_mm,
            "pose_received_monotonic_s": self.pose_received_at,
            "timing_qualification": "Server capture and local pose receipt; exposure synchronization unqualified",
        }

    @classmethod
    def from_dict(cls, value: object) -> CalibrationReference:
        data = _record(value, "reference")
        encoded = data["jpeg_base64"]
        if not isinstance(encoded, str) or len(encoded) > (MAX_FRAME_BYTES + 2) // 3 * 4:
            raise ValueError("Reference image exceeds limit")
        jpeg = base64.b64decode(encoded, validate=True)
        if not jpeg or len(jpeg) > MAX_FRAME_BYTES or hashlib.sha256(jpeg).hexdigest() != data["jpeg_sha256"]:
            raise ValueError("Reference JPEG hash mismatch")
        try:
            with Image.open(io.BytesIO(jpeg)) as image:
                if image.format != "JPEG" or not 1 <= image.width <= 4096 or not 1 <= image.height <= 4096:
                    raise ValueError("Unsupported reference image")
                if list(image.size) != data["size"]:
                    raise ValueError("Reference image dimensions mismatch")
                rgb = image.convert("RGB")
        except Image.DecompressionBombError as exc:
            raise ValueError("Reference image exceeds decoded dimension limit") from exc
        source = data["source_sha256"]
        if not isinstance(source, str) or len(source) != 64 or any(c not in "0123456789abcdef" for c in source):
            raise ValueError("Invalid camera source fingerprint")
        raw_pose = data["machine_mm"]
        pose: Vec3 | None = None
        if raw_pose is not None:
            if not isinstance(raw_pose, (list, tuple)) or len(raw_pose) != 3:
                raise ValueError("Invalid reference machine pose")
            pose = (
                _number(raw_pose[0], "reference machine pose"),
                _number(raw_pose[1], "reference machine pose"),
                _number(raw_pose[2], "reference machine pose"),
            )
            if any(abs(v) > 1000 for v in pose):
                raise ValueError("Invalid reference machine pose")
        camera_generation = _identity(data["camera_generation"])
        connection_generation = _identity(data["connection_generation"])
        sequence = _identity(data["sequence"])
        captured_at = _timestamp(data["captured_at"])
        received_at = _timestamp(data["received_monotonic_s"])
        pose_received_at = _timestamp(data["pose_received_monotonic_s"])
        if received_at is None or (pose is None) != (pose_received_at is None):
            raise ValueError("Reference pose or receipt timestamp missing")
        frame = CameraFrame(rgb.size, rgb.tobytes(), captured_at, received_at, sequence, jpeg)
        return cls(frame, source, camera_generation, connection_generation, pose, pose_received_at)


def calibration_data(
    registration: CameraRegistration,
    observations: Sequence[RegistrationObservation],
    reference: CalibrationReference | None,
    reference_y: float | None = None,
) -> CalibrationData:
    if len(observations) > 128:
        raise ValueError("At most 128 correspondences")
    if reference is not None and reference.frame.size != (
        registration.intrinsics.width,
        registration.intrinsics.height,
    ):
        raise ValueError("Registration and reference dimensions differ")
    return {
        "schema": 2,
        "registration": registration.to_dict(),
        "observations": [o.to_dict() for o in observations],
        "reference": reference.to_dict() if reference else None,
        "reference_machine_y_mm": reference.machine_mm[1] if reference and reference.machine_mm else reference_y,
        "physical_qualification": "unqualified",
    }


def decode_calibration(value: object) -> DecodedCalibration:
    data = _record(value, "calibration")
    if type(data.get("schema")) is not int or data["schema"] not in (1, 2):
        raise ValueError("Unsupported camera calibration schema")
    registration = CameraRegistration.from_dict(_record(data["registration"], "registration"))
    raw_observations = data.get("observations", [])
    if not isinstance(raw_observations, list) or len(raw_observations) > 128:
        raise ValueError("At most 128 correspondences")
    observations = tuple(RegistrationObservation.from_dict(_record(o, "correspondence")) for o in raw_observations)
    if len(observations) > 128:
        raise ValueError("At most 128 correspondences")
    reference = (
        CalibrationReference.from_dict(data["reference"])
        if data["schema"] == 2 and data.get("reference") is not None
        else None
    )
    raw_y = data.get("reference_machine_y_mm")
    reference_y = _number(raw_y, "table position") if raw_y is not None else None
    if reference_y is not None and (not math.isfinite(reference_y) or abs(reference_y) > 1000):
        raise ValueError("Invalid table position")
    if reference:
        if any(
            not 0 <= o.pixel[0] < reference.frame.size[0] or not 0 <= o.pixel[1] < reference.frame.size[1]
            for o in observations
        ):
            raise ValueError("Correspondence pixels outside reference image")
        if reference.frame.size != (registration.intrinsics.width, registration.intrinsics.height):
            raise ValueError("Registration and reference dimensions differ")
        expected_y = reference.machine_mm[1] if reference.machine_mm else None
        if reference_y != expected_y:
            raise ValueError("Reference table pose mismatch")
    return registration, observations, reference, reference_y


def read_calibration(path: str | os.PathLike[str]) -> DecodedCalibration:
    with Path(path).open("rb") as source:
        raw = source.read(MAX_CALIBRATION_BYTES + 1)
    if len(raw) > MAX_CALIBRATION_BYTES:
        raise ValueError("Calibration file exceeds 12 MB")
    return decode_calibration(json.loads(raw))


def encode_calibration(data: object) -> bytes:
    decode_calibration(data)
    raw = json.dumps(data, indent=2, allow_nan=False).encode()
    if len(raw) > MAX_CALIBRATION_BYTES:
        raise ValueError("Calibration file exceeds 12 MB")
    return raw


def write_calibration(path: str | os.PathLike[str], data: object) -> str:
    # Validate before touching the destination. Exclusive creation preserves earlier
    # calibration evidence; interrupted/partial files remain available for diagnosis.
    raw = encode_calibration(data)
    with Path(path).open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    with Path(path).open("rb") as saved:
        readback = saved.read(len(raw) + 1)
    if readback != raw:
        raise OSError("Calibration readback mismatch")
    return hashlib.sha256(raw).hexdigest()
