"""Preserved positive-weight NURBS and bounded, parameter-matched conversion.

Geometry only. A dialect adapter must supply its actual controls, weights and
knots; this module does not guess G-code semantics or emit controller commands.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from .spline_geometry import Point, SplinePolyline

Homogeneous = tuple[float, float, float, float]


@dataclass(frozen=True)
class NurbsCurve:
    control_points_mm: tuple[Point, ...]
    weights: tuple[float, ...]
    knots: tuple[float, ...]
    degree: int

    @classmethod
    def create(
        cls, controls: Sequence[Sequence[float]], weights: Sequence[float], knots: Sequence[float], degree: int
    ) -> NurbsCurve:
        if type(degree) is not int or not 1 <= degree <= 16 or not degree + 1 <= len(controls) <= 4096:
            raise ValueError("NURBS requires degree 1–16 and degree+1 to 4096 controls")
        points = []
        for point in controls:
            if len(point) != 3 or any(
                type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1e6 for v in point
            ):
                raise ValueError("NURBS controls require three finite coordinates within one million mm")
            points.append((float(point[0]), float(point[1]), float(point[2])))
        if len(weights) != len(points) or any(
            type(w) not in (int, float) or not math.isfinite(w) or w <= 0 for w in weights
        ):
            raise ValueError("NURBS requires one positive finite weight per control")
        if len(knots) != len(points) + degree + 1 or any(
            type(u) not in (int, float) or not math.isfinite(u) for u in knots
        ):
            raise ValueError("NURBS knot count must equal control count + degree + 1")
        u = tuple(float(v) for v in knots)
        if any(a > b for a, b in zip(u, u[1:])) or u[degree] >= u[-degree - 1]:
            raise ValueError("NURBS knots must be ordered with a positive parameter domain")
        if len(set(u[: degree + 1])) != 1 or len(set(u[-degree - 1 :])) != 1:
            raise ValueError("NURBS conversion requires clamped endpoint knots")
        interior = u[degree + 1 : -degree - 1]
        if any(interior.count(v) > degree for v in set(interior)):
            raise ValueError("NURBS interior knots must not introduce discontinuities")
        return cls(tuple(points), tuple(float(w) for w in weights), u, degree)


def _mix(a: Homogeneous, b: Homogeneous, t: float) -> Homogeneous:
    return cast(Homogeneous, tuple((1 - t) * x + t * y for x, y in zip(a, b)))


def _point(h: Homogeneous) -> Point:
    return h[0] / h[3], h[1] / h[3], h[2] / h[3]


def _split(controls: tuple[Homogeneous, ...]) -> tuple[tuple[Homogeneous, ...], tuple[Homogeneous, ...]]:
    rows = [controls]
    while len(rows[-1]) > 1:
        rows.append(tuple(_mix(a, b, 0.5) for a, b in zip(rows[-1], rows[-1][1:])))
    return tuple(row[0] for row in rows), tuple(row[-1] for row in reversed(rows))


def _bound(controls: tuple[Homogeneous, ...]) -> float:
    # N/W - L = (N-WL)/W. Elevate N to degree p+1 and multiply W
    # by the endpoint chord L using Bernstein products. The numerator lies
    # in its coefficient hull; positive W is at least its smallest weight.
    p = len(controls) - 1
    a, b = _point(controls[0]), _point(controls[-1])
    errors = []
    for i in range(1, p + 1):
        t = i / (p + 1)
        errors.append(
            math.hypot(
                *(
                    (1 - t) * (controls[i][j] - controls[i][3] * a[j])
                    + t * (controls[i - 1][j] - controls[i - 1][3] * b[j])
                    for j in range(3)
                )
            )
        )
    return max(errors, default=0.0) / min(h[3] for h in controls)


def tessellate_nurbs(
    curve: NurbsCurve, *, tolerance_mm: float, max_segments: int = 10000, cancelled: Callable[[], bool] = lambda: False
) -> SplinePolyline:
    # Revalidate public dataclass construction as well as factory input.
    curve = NurbsCurve.create(curve.control_points_mm, curve.weights, curve.knots, curve.degree)
    if type(tolerance_mm) not in (int, float) or not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("NURBS tolerance must be positive and finite")
    if type(max_segments) is not int or not 1 <= max_segments <= 100000:
        raise ValueError("NURBS segment budget must be an integer from one to 100000")
    p = curve.degree
    lo, hi = curve.knots[p], curve.knots[-p - 1]
    domain = hi - lo
    if not math.isfinite(domain):
        raise ValueError("NURBS parameter range overflows")
    knots = [(u - lo) / domain for u in curve.knots]
    distinct = sorted(set(knots))
    minimum_spacing = min(b - a for a, b in zip(distinct, distinct[1:]))
    if minimum_spacing < 1e-12:
        raise ValueError("NURBS knot spacing is below the conversion precision limit")
    if len(distinct) - 1 > max_segments:
        raise ValueError("NURBS span count exceeds the segment budget")
    maximum_weight = max(curve.weights)
    weights = [w / maximum_weight for w in curve.weights]
    if min(weights) < 1e-12:
        raise ValueError("NURBS weight ratio exceeds the conversion precision limit")
    scale = max(1.0, *(abs(v) for point in curve.control_points_mm for v in point))
    parameter_condition = max(1.0, abs(lo / domain), abs(hi / domain))
    allowance = 2048 * math.ulp(scale) * len(weights) * (p + 1) * parameter_condition / (min(weights) * minimum_spacing)
    if tolerance_mm <= allowance:
        raise ValueError("NURBS tolerance is below its floating-point allowance")
    controls: list[Homogeneous] = [
        (point[0] * w, point[1] * w, point[2] * w, w) for point, w in zip(curve.control_points_mm, weights)
    ]
    # Insert each interior knot to degree multiplicity (Boehm insertion).
    # The resulting nonzero spans are rational Bezier patches.
    for u in distinct[1:-1]:
        while knots.count(u) < p:
            if cancelled():
                raise InterruptedError("NURBS conversion cancelled")
            k, s = bisect_right(knots, u) - 1, knots.count(u)
            updated = controls[: k - p + 1]
            for i in range(k - p + 1, k - s + 1):
                alpha = (u - knots[i]) / (knots[i + p] - knots[i])
                updated.append(_mix(controls[i - 1], controls[i], alpha))
            updated.extend(controls[k - s :])
            controls = updated
            knots.insert(k + 1, u)
    pending = []
    for k in range(p, len(controls)):
        if knots[k] < knots[k + 1]:
            pending.append((tuple(controls[k - p : k + 1]), knots[k], knots[k + 1], 0))
    if len(pending) > max_segments:
        raise ValueError("NURBS span count exceeds the segment budget")
    pending.reverse()
    points, parameters, maximum = [curve.control_points_mm[0]], [lo], 0.0
    while pending:
        if cancelled():
            raise InterruptedError("NURBS conversion cancelled")
        patch, start, end, depth = pending.pop()
        bound = _bound(patch) + allowance
        if bound <= tolerance_mm:
            parameter = hi if end == 1.0 else lo + end * domain
            if parameter <= parameters[-1]:
                raise ValueError("NURBS output parameters cannot be distinguished at this precision")
            points.append(_point(patch[-1]))
            parameters.append(parameter)
            maximum = max(maximum, bound)
            continue
        if len(points) - 1 + len(pending) + 2 > max_segments:
            raise ValueError("NURBS exceeds the segment budget at the requested tolerance")
        if depth >= 32:
            raise ValueError("NURBS exceeds the subdivision depth at the requested tolerance")
        left, right = _split(patch)
        middle = (start + end) / 2
        pending.extend(((right, middle, end, depth + 1), (left, start, middle, depth + 1)))
    low = tuple(min(point[a] for point in curve.control_points_mm) for a in range(3))
    high = tuple(max(point[a] for point in curve.control_points_mm) for a in range(3))
    return SplinePolyline(
        tuple(points), tuple(parameters), maximum, float(tolerance_mm), (cast(Point, low), cast(Point, high))
    )
