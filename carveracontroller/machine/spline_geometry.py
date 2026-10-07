"""Bounded cubic Bezier tessellation with parameter-matched error certificates.

Geometry only: this module neither selects a controller dialect nor emits motion.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

Point = tuple[float, float, float]
Controls = tuple[Point, Point, Point, Point]


@dataclass(frozen=True)
class SplinePolyline:
    points_mm: tuple[Point, ...]
    parameters: tuple[float, ...]
    maximum_error_bound_mm: float
    tolerance_mm: float
    control_hull_bounds_mm: tuple[Point, Point]


def _controls(values: Sequence[Sequence[float]]) -> Controls:
    if len(values) != 4:
        raise ValueError("Cubic spline requires four three-dimensional control points")
    points: list[Point] = []
    for point in values:
        if len(point) != 3 or any(type(value) not in (int, float) for value in point):
            raise ValueError("Spline coordinates require three finite numbers")
        xyz = tuple(float(value) for value in point)
        if any(not math.isfinite(value) or abs(value) > 1_000_000 for value in xyz):
            raise ValueError("Spline coordinates must be finite and within one million mm")
        points.append((xyz[0], xyz[1], xyz[2]))
    return points[0], points[1], points[2], points[3]


def _midpoint(a: Point, b: Point) -> Point:
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2)


def _split(p: Controls) -> tuple[Controls, Controls]:
    a, b, c = _midpoint(p[0], p[1]), _midpoint(p[1], p[2]), _midpoint(p[2], p[3])
    d, e = _midpoint(a, b), _midpoint(b, c)
    middle = _midpoint(d, e)
    return (p[0], a, d, middle), (middle, e, c, p[3])


def _chord_bound(p: Controls) -> float:
    # Elevate the endpoint chord to cubic degree. Its two internal controls
    # occur at 1/3 and 2/3. The curve/chord difference is a Bezier curve whose
    # endpoint controls are zero, so its norm is bounded by the largest
    # internal difference. This is parameter-matched, including reversals.
    return max(
        math.dist(p[i], tuple(p[0][axis] + (p[3][axis] - p[0][axis]) * i / 3 for axis in range(3))) for i in (1, 2)
    )


def tessellate_cubic(
    control_points_mm: Sequence[Sequence[float]],
    *,
    tolerance_mm: float,
    max_segments: int = 10_000,
    cancelled: Callable[[], bool] = lambda: False,
) -> SplinePolyline:
    """Return a complete polyline or refuse; never publish truncated geometry.

    At every returned parameter interval, linear interpolation approximates
    the cubic at the same parameter within the reported conservative bound.
    A floating-point allowance covers bounded dyadic subdivision arithmetic.
    Control-hull bounds enclose the original curve, not just sampled points.
    No tangent, length, dynamics or executed-toolpath accuracy is certified.
    """
    controls = _controls(control_points_mm)
    if type(tolerance_mm) not in (int, float) or not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("Spline tolerance must be positive and finite")
    if type(max_segments) is not int or not 1 <= max_segments <= 100_000:
        raise ValueError("Spline segment budget must be an integer from one to 100000")
    scale = max(1.0, *(abs(value) for point in controls for value in point))
    allowance = 256 * math.ulp(scale)
    if tolerance_mm <= allowance:
        raise ValueError("Spline tolerance is below the floating-point allowance for these coordinates")
    pending: list[tuple[Controls, float, float, int]] = [(controls, 0.0, 1.0, 0)]
    points, parameters = [controls[0]], [0.0]
    maximum = 0.0
    while pending:
        if cancelled():
            raise InterruptedError("Spline tessellation cancelled")
        p, start, end, depth = pending.pop()
        bound = _chord_bound(p) + allowance
        if bound <= tolerance_mm:
            points.append(p[3])
            parameters.append(end)
            maximum = max(maximum, bound)
            continue
        # Splitting increases the minimum final segment count by one. Reserve
        # every pending leaf before subdivision, including the current leaf.
        if len(points) - 1 + len(pending) + 2 > max_segments:
            raise ValueError("Spline exceeds the segment budget at the requested tolerance")
        if depth >= 32:
            raise ValueError("Spline exceeds the subdivision depth at the requested tolerance")
        left, right = _split(p)
        middle = (start + end) / 2
        pending.extend(((right, middle, end, depth + 1), (left, start, middle, depth + 1)))
    lower = tuple(min(point[axis] for point in controls) for axis in range(3))
    upper = tuple(max(point[axis] for point in controls) for axis in range(3))
    return SplinePolyline(
        tuple(points),
        tuple(parameters),
        maximum,
        float(tolerance_mm),
        ((lower[0], lower[1], lower[2]), (upper[0], upper[1], upper[2])),
    )


def linuxcnc_g5_controls(
    start_mm: Point,
    end_mm: Point,
    words: Mapping[str, float],
    *,
    plane: str | None,
    unit_scale: float,
    previous_pq_mm: tuple[float, float] | None = None,
) -> Controls:
    """Resolve documented LinuxCNC G5 offsets; endpoints are already in mm.

    I/J are relative to the start, P/Q to the endpoint irrespective of G90/91.
    Only a preceding cubic in the same series supplies omitted I/J. The caller
    owns series boundaries and endpoint/modal interpretation. This helper does
    not establish that a connected controller supports G5.
    """
    if plane != "G17" or any(axis in words for axis in "ZABCUVW"):
        raise ValueError("LinuxCNC G5 requires G17 and only X/Y axes")
    if "K" in words or "R" in words:
        raise ValueError("LinuxCNC G5 control offsets use I/J/P/Q, not K/R")
    if not {"P", "Q"} <= words.keys():
        raise ValueError("LinuxCNC G5 requires both P and Q on every block")
    if ("I" in words) != ("J" in words):
        raise ValueError("LinuxCNC G5 requires both I and J or neither")
    if type(unit_scale) not in (int, float) or unit_scale not in (1, 25.4):
        raise ValueError("Spline unit scale must be explicit mm or inch")
    for key in ("I", "J", "P", "Q"):
        if key in words and (type(words[key]) not in (int, float) or not math.isfinite(words[key])):
            raise ValueError("Spline control offsets must be finite numbers")
    if "I" in words:
        i, j = words["I"] * unit_scale, words["J"] * unit_scale
    elif previous_pq_mm is not None:
        if len(previous_pq_mm) != 2 or any(
            type(value) not in (int, float) or not math.isfinite(value) for value in previous_pq_mm
        ):
            raise ValueError("Previous spline offsets must be finite mm values")
        i, j = -previous_pq_mm[0], -previous_pq_mm[1]
    else:
        raise ValueError("The first LinuxCNC G5 block requires I and J")
    return _controls(
        (
            start_mm,
            (start_mm[0] + i, start_mm[1] + j, start_mm[2]),
            (end_mm[0] + words["P"] * unit_scale, end_mm[1] + words["Q"] * unit_scale, end_mm[2]),
            end_mm,
        )
    )
