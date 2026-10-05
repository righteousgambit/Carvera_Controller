"""Bounded calibration exchange retaining the exact image used for correspondences."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from carveracontroller.machine.camera_registration import CameraRegistration, RegistrationObservation
from carveracontroller.machine.webcam import MAX_FRAME_BYTES, CameraFrame

MAX_CALIBRATION_BYTES = 12 * 1024 * 1024


@dataclass(frozen=True)
class CalibrationReference:
    frame: CameraFrame
    source_sha256: str
    camera_generation: int
    connection_generation: int
    machine_mm: tuple | None
    pose_received_at: float | None

    def to_dict(self):
        return {
            "jpeg_base64": base64.b64encode(self.frame.jpeg).decode("ascii"),
            "jpeg_sha256": hashlib.sha256(self.frame.jpeg).hexdigest(),
            "size": list(self.frame.size),
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
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Invalid reference record")
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
        pose = data["machine_mm"]
        if pose is not None and (
            not isinstance(pose, (list, tuple))
            or len(pose) != 3
            or not all(
                isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and abs(v) <= 1000
                for v in pose
            )
        ):
            raise ValueError("Invalid reference machine pose")
        for name in ("camera_generation", "connection_generation", "sequence"):
            if type(data[name]) is not int or data[name] < 0:
                raise ValueError("Invalid reference identity")
        for name in ("captured_at", "received_monotonic_s", "pose_received_monotonic_s"):
            if data[name] is not None and (not math.isfinite(data[name]) or data[name] < 0):
                raise ValueError("Invalid reference timestamp")
        if data["received_monotonic_s"] is None or (pose is None) != (data["pose_received_monotonic_s"] is None):
            raise ValueError("Reference pose or receipt timestamp missing")
        frame = CameraFrame(
            rgb.size, rgb.tobytes(), data["captured_at"], data["received_monotonic_s"], data["sequence"], jpeg
        )
        return cls(
            frame,
            source,
            data["camera_generation"],
            data["connection_generation"],
            tuple(pose) if pose else None,
            data["pose_received_monotonic_s"],
        )


def calibration_data(registration, observations, reference, reference_y=None):
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


def decode_calibration(data):
    if not isinstance(data, dict) or type(data.get("schema")) is not int or data["schema"] not in (1, 2):
        raise ValueError("Unsupported camera calibration schema")
    registration = CameraRegistration.from_dict(data["registration"])
    raw_observations = data.get("observations", [])
    if not isinstance(raw_observations, list) or len(raw_observations) > 128:
        raise ValueError("At most 128 correspondences")
    observations = tuple(RegistrationObservation.from_dict(o) for o in raw_observations)
    if len(observations) > 128:
        raise ValueError("At most 128 correspondences")
    reference = (
        CalibrationReference.from_dict(data["reference"]) if data.get("schema") == 2 and data.get("reference") else None
    )
    raw_y = data.get("reference_machine_y_mm")
    reference_y = float(raw_y) if raw_y is not None else None
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


def read_calibration(path):
    with Path(path).open("rb") as source:
        raw = source.read(MAX_CALIBRATION_BYTES + 1)
    if len(raw) > MAX_CALIBRATION_BYTES:
        raise ValueError("Calibration file exceeds 12 MB")
    return decode_calibration(json.loads(raw))


def write_calibration(path, data):
    # Validate before touching the destination. Exclusive creation preserves earlier
    # calibration evidence; interrupted/partial files remain available for diagnosis.
    decode_calibration(data)
    raw = json.dumps(data, indent=2, allow_nan=False).encode()
    if len(raw) > MAX_CALIBRATION_BYTES:
        raise ValueError("Calibration file exceeds 12 MB")
    with Path(path).open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    if Path(path).read_bytes() != raw:
        raise OSError("Calibration readback mismatch")
    return hashlib.sha256(raw).hexdigest()
