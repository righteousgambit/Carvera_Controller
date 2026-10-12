"""Read-only correspondence coverage and per-point reprojection review."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from carveracontroller.machine.camera_registration import CameraRegistration, RegistrationObservation

Pixel = tuple[float, float]


def parse_correspondences(text: str, size: tuple[int, int]) -> tuple[RegistrationObservation, ...]:
    observations: list[RegistrationObservation] = []
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        if len(observations) >= 128:
            raise ValueError("At most 128 correspondences")
        try:
            values = [float(value) for value in line.replace(",", " ").split()]
        except ValueError as exc:
            raise ValueError(f"Line {number}: enter numeric X Y Z U V") from exc
        if len(values) != 5 or not all(math.isfinite(value) for value in values):
            raise ValueError(f"Line {number}: enter five finite X Y Z U V values")
        if not 0 <= values[3] < size[0] or not 0 <= values[4] < size[1]:
            raise ValueError(f"Line {number}: pixels must lie inside the frozen image")
        observations.append(RegistrationObservation((values[0], values[1], values[2]), (values[3], values[4])))
    return tuple(observations)


def pixel_hull(observations: Sequence[RegistrationObservation]) -> tuple[tuple[float, float], ...]:
    points = sorted({point.pixel for point in observations})
    if len(points) < 3:
        return tuple(points)

    def cross(a: Pixel, b: Pixel, c: Pixel) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def chain(values: Iterable[Pixel]) -> list[Pixel]:
        result: list[Pixel] = []
        for point in values:
            while len(result) >= 2 and cross(result[-2], result[-1], point) <= 0:
                result.pop()
            result.append(point)
        return result

    return tuple(chain(points)[:-1] + chain(reversed(points))[:-1])


@dataclass(frozen=True)
class CoverageReview:
    hull: tuple[tuple[float, float], ...]
    image_fraction: float
    z_range_mm: tuple[float, float] | None
    residuals_px: tuple[float, ...]


def review_coverage(
    observations: Sequence[RegistrationObservation],
    size: tuple[int, int],
    registration: CameraRegistration | None = None,
) -> CoverageReview:
    if not 1 <= size[0] <= 32768 or not 1 <= size[1] <= 32768 or len(observations) > 128:
        raise ValueError("Invalid bounded reference geometry")
    if any(not 0 <= point.pixel[0] < size[0] or not 0 <= point.pixel[1] < size[1] for point in observations):
        raise ValueError("Pixels must lie inside the reference image")
    if registration and (registration.intrinsics.width, registration.intrinsics.height) != size:
        raise ValueError("Registration and reference image sizes differ")
    hull = pixel_hull(observations)
    area = abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(hull, hull[1:] + hull[:1]))) / 2
    heights = [point.world_mm[2] for point in observations]
    residuals = (
        tuple(math.dist(registration.project(point.world_mm), point.pixel) for point in observations)
        if registration
        else ()
    )
    if not all(math.isfinite(value) for value in residuals):
        raise ValueError("Reprojection residuals must be finite")
    return CoverageReview(
        hull, area / (size[0] * size[1]), (min(heights), max(heights)) if heights else None, residuals
    )


@dataclass(frozen=True)
class HeldOutReview:
    residuals_px: tuple[float, ...]
    rms_px: float
    maximum_px: float
    limit_px: float | None
    within_limit: bool | None
    coverage: CoverageReview


def review_held_out(
    fitting: Sequence[RegistrationObservation],
    checks: Sequence[RegistrationObservation],
    size: tuple[int, int],
    registration: CameraRegistration,
    limit_px: float | None = None,
) -> HeldOutReview:
    """Evaluate new image correspondences without changing or refitting the model.

    Disjoint entered coordinates are necessary, but cannot establish measurement
    independence, reference accuracy, lens validity or physical registration.
    """
    if not fitting or len(fitting) > 128 or not checks or len(checks) > 128:
        raise ValueError("Enter 1–128 fitting and held-out correspondences")
    if limit_px is not None and (
        isinstance(limit_px, bool) or not math.isfinite(limit_px) or not 0 < limit_px <= 32768
    ):
        raise ValueError("Image error limit must be finite and positive, at most 32768 pixels")
    if any(not all(math.isfinite(value) for value in (*point.world_mm, *point.pixel)) for point in (*fitting, *checks)):
        raise ValueError("Correspondence coordinates must be finite")
    review_coverage(fitting, size)
    seen_world = [point.world_mm for point in fitting]
    seen_pixel = [point.pixel for point in fitting]
    for point in checks:
        if any(math.dist(point.world_mm, previous) <= 1e-6 for previous in seen_world) or any(
            math.dist(point.pixel, previous) <= 1e-6 for previous in seen_pixel
        ):
            raise ValueError("Held-out points must differ from fitting points and from each other in XYZ and pixels")
        seen_world.append(point.world_mm)
        seen_pixel.append(point.pixel)
    coverage = review_coverage(checks, size, registration)
    errors = coverage.residuals_px
    maximum = max(errors)
    return HeldOutReview(
        errors,
        math.sqrt(sum(error * error for error in errors) / len(errors)),
        maximum,
        limit_px,
        maximum <= limit_px if limit_px is not None else None,
        coverage,
    )
