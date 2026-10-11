"""Immutable multi-view lens measurements and bounded, image-bound exchange."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from carveracontroller.machine.camera_calibration_file import CalibrationReference
from carveracontroller.machine.camera_registration import CameraIntrinsics, RegistrationObservation

MAX_STUDY_BYTES = 48 * 1024 * 1024
MAX_CAPTURE_BYTES = 96 * 1024 * 1024


@dataclass(frozen=True)
class LensCapture:
    reference: CalibrationReference
    observations: tuple[RegistrationObservation, ...]

    @property
    def image_sha256(self) -> str:
        return hashlib.sha256(self.reference.frame.jpeg).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference.to_dict(),
            "observations": [point.to_dict() for point in self.observations],
        }


@dataclass(frozen=True)
class CameraLensStudy:
    prior: CameraIntrinsics
    captures: tuple[LensCapture, ...]
    fit_distortion: bool = True

    def __post_init__(self) -> None:
        if not 1 <= len(self.captures) <= 12 or type(self.fit_distortion) is not bool:
            raise ValueError("A lens study retains 1 to 12 views; fitting needs at least 3")
        source = self.captures[0].reference.source_sha256
        generation = self.captures[0].reference.camera_generation
        hashes: set[str] = set()
        retained = 0
        for capture in self.captures:
            reference = capture.reference
            frame = reference.frame
            if frame.size != (self.prior.width, self.prior.height):
                raise ValueError("Lens study image sizes differ")
            if reference.source_sha256 != source or reference.camera_generation != generation:
                raise ValueError("Lens study views must share a camera source and generation")
            if not frame.jpeg or len(frame.pixels) != frame.size[0] * frame.size[1] * 3:
                raise ValueError("Lens study needs an exact JPEG and decoded RGB image")
            retained += len(frame.jpeg) + len(frame.pixels)
            if retained > MAX_CAPTURE_BYTES:
                raise ValueError("Lens study retained images exceed 96 MB")
            digest = capture.image_sha256
            if digest in hashes:
                raise ValueError("This image is already in the lens study; capture a different board view")
            hashes.add(digest)
            if not 8 <= len(capture.observations) <= 100:
                raise ValueError("Each lens view needs 8 to 100 measured correspondences")
            for point in capture.observations:
                if not all(math.isfinite(v) for v in (*point.world_mm, *point.pixel)):
                    raise ValueError("Lens study points must be finite")
                if not 0 <= point.pixel[0] < frame.size[0] or not 0 <= point.pixel[1] < frame.size[1]:
                    raise ValueError("Lens study pixels are outside the reference image")

    @property
    def source_sha256(self) -> str:
        return self.captures[0].reference.source_sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": 1,
            "prior": self.prior.to_dict(),
            "fit_distortion": self.fit_distortion,
            "captures": [capture.to_dict() for capture in self.captures],
            "physical_qualification": "unqualified",
            "fit_policy": "Refit imported measurements; no cached result is applied",
        }


def _record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Invalid lens study record")
    return value


def _numbers(value: object, count: int) -> tuple[float, ...]:
    if not isinstance(value, (tuple, list)) or len(value) != count:
        raise ValueError("Invalid lens study numeric fields")
    if any(type(v) not in (int, float) for v in value):
        raise ValueError("Lens study numbers cannot be coerced")
    try:
        result = tuple(float(v) for v in value)
    except OverflowError as exc:
        raise ValueError("Lens study numbers exceed finite range") from exc
    if not all(math.isfinite(v) for v in result):
        raise ValueError("Lens study numbers must be finite")
    return result


def _size(value: object) -> tuple[int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("Invalid lens image dimensions")
    if any(type(v) is not int or not 1 <= v <= 4096 for v in value):
        raise ValueError("Invalid lens image dimensions")
    return value[0], value[1]


def decode_lens_study(value: object) -> CameraLensStudy:
    data = _record(value)
    if type(data.get("schema")) is not int or data["schema"] != 1:
        raise ValueError("Unsupported lens study schema")
    raw_prior = _record(data["prior"])
    width, height = _size([raw_prior["width"], raw_prior["height"]])
    fx, fy, cx, cy = _numbers([raw_prior[k] for k in ("fx", "fy", "cx", "cy")], 4)
    k1, k2, p1, p2, k3 = _numbers(raw_prior["distortion"], 5)
    prior = CameraIntrinsics(width, height, fx, fy, cx, cy, (k1, k2, p1, p2, k3))
    raw_captures = data["captures"]
    if not isinstance(raw_captures, list) or not 1 <= len(raw_captures) <= 12:
        raise ValueError("A lens study retains 1 to 12 views")
    captures = []
    retained = 0
    for raw in raw_captures:
        record = _record(raw)
        reference_data = _record(record["reference"])
        size = _size(reference_data["size"])
        # Check the declared allocation before decoding. Reference decoding also
        # verifies actual JPEG dimensions, so a smaller forged size is rejected.
        retained += size[0] * size[1] * 3
        if retained > MAX_CAPTURE_BYTES:
            raise ValueError("Lens study retained images exceed 96 MB")
        reference = CalibrationReference.from_dict(reference_data)
        retained += len(reference.frame.jpeg)
        if retained > MAX_CAPTURE_BYTES:
            raise ValueError("Lens study retained images exceed 96 MB")
        raw_points = record["observations"]
        if not isinstance(raw_points, list) or not 8 <= len(raw_points) <= 100:
            raise ValueError("Each lens view needs 8 to 100 measured correspondences")
        points = []
        for raw_point in raw_points:
            point = _record(raw_point)
            x, y, z = _numbers(point["world_mm"], 3)
            u, v = _numbers(point["pixel"], 2)
            points.append(RegistrationObservation((x, y, z), (u, v)))
        captures.append(LensCapture(reference, tuple(points)))
    return CameraLensStudy(prior, tuple(captures), data["fit_distortion"])


def read_lens_study(path: str | os.PathLike[str]) -> CameraLensStudy:
    with Path(path).open("rb") as source:
        raw = source.read(MAX_STUDY_BYTES + 1)
    if len(raw) > MAX_STUDY_BYTES:
        raise ValueError("Lens study file exceeds 48 MB")
    return decode_lens_study(json.loads(raw))


def write_lens_study(path: str | os.PathLike[str], study: CameraLensStudy) -> str:
    data = study.to_dict()
    decode_lens_study(data)
    raw = json.dumps(data, indent=2, allow_nan=False).encode()
    if len(raw) > MAX_STUDY_BYTES:
        raise ValueError("Lens study file exceeds 48 MB")
    with Path(path).open("xb") as destination:
        destination.write(raw)
        destination.flush()
        os.fsync(destination.fileno())
    with Path(path).open("rb") as saved:
        if saved.read(len(raw) + 1) != raw:
            raise OSError("Lens study readback mismatch")
    return hashlib.sha256(raw).hexdigest()
