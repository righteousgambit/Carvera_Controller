"""Distance bounds for a fixed-axis translating cylinder and a convex box.

The translation segment plus cylinder is convex. Minkowski support planes give
lower bounds; convex combinations of support pairs give upper witnesses. The
simplex search never samples motion time, and preserves an unresolved interval
when its numerical budget is exhausted. This does not handle changing axes.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import isfinite, sqrt

from .geometry import AABB, AxialEnvelope, SweptTool

Point = tuple[float, float, float]


def _dot(a: Point, b: Point) -> float:
    return sum(x * y for x, y in zip(a, b))


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


@dataclass(frozen=True)
class _Support:
    point: Point
    fraction: float


def _solve(matrix: list[list[float]], values: list[float]) -> list[float] | None:
    """Small scaled-pivot Gram solve; dependent simplices use their faces."""
    n = len(values)
    rows = [list(row) + [value] for row, value in zip(matrix, values)]
    scale = max((abs(v) for row in matrix for v in row), default=0)
    if not scale:
        return None
    for column in range(n):
        pivot = max(range(column, n), key=lambda i: abs(rows[i][column]))
        if abs(rows[pivot][column]) <= scale * 1e-14:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [v / divisor for v in rows[column]]
        for i in range(n):
            if i != column:
                factor = rows[i][column]
                rows[i] = [a - factor * b for a, b in zip(rows[i], rows[column])]
    return [row[-1] for row in rows]


def _closest(vertices: list[_Support]) -> tuple[Point, float, list[_Support]]:
    """Enumerate all independent simplex faces, retaining a feasible witness."""
    best_squared = float("inf")
    best_point: Point = (0, 0, 0)
    best_fraction = 0.0
    best_vertices: list[_Support] = []
    for count in range(1, min(4, len(vertices)) + 1):
        for indices in combinations(range(len(vertices)), count):
            face = [vertices[i] for i in indices]
            origin = face[0].point
            if count == 1:
                weights = [1.0]
            else:
                edges = [_sub(v.point, origin) for v in face[1:]]
                solved = _solve([[_dot(a, b) for b in edges] for a in edges], [-_dot(e, origin) for e in edges])
                if solved is None:
                    continue
                weights = [1 - sum(solved), *solved]
                if min(weights) < 0:
                    continue
            coordinates = [sum(v.point[i] * w for v, w in zip(face, weights)) for i in range(3)]
            point: Point = (coordinates[0], coordinates[1], coordinates[2])
            squared = _dot(point, point)
            if squared < best_squared:
                best_squared, best_point = squared, point
                best_fraction = sum(v.fraction * w for v, w in zip(face, weights))
                best_vertices = [v for v, w in zip(face, weights) if w > 0]
    return best_point, max(0.0, min(1.0, best_fraction)), best_vertices


def cylinder_box_clearance(
    sweep: SweptTool, section: AxialEnvelope, obstacle: AABB, tolerance_mm: float, *, max_evaluations: int = 128
) -> tuple[float, float, float, str, int]:
    """Return a support-plane lower bound and feasible upper witness.

    The witness fraction locates a modeled distance witness, not a contact or
    machine event. Coordinates are shifted/scaled before simplex arithmetic.
    A small outward numerical guard widens both interval ends.
    """
    if isinstance(tolerance_mm, bool) or not isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("Clearance tolerance must be finite and positive")
    if isinstance(max_evaluations, bool) or not isinstance(max_evaluations, int) or not 2 <= max_evaluations <= 128:
        raise ValueError("Convex clearance needs 2–128 support evaluations")
    coordinates = (
        *sweep.start.tuple,
        *sweep.end.tuple,
        *obstacle.minimum.tuple,
        *obstacle.maximum.tuple,
        section.high_mm,
        section.radius_mm,
    )
    if any(abs(v) > 1e9 for v in coordinates):
        raise ValueError("Convex clearance coordinates exceed the bounded millimetre domain")
    axis_raw = (sweep.axis.x, sweep.axis.y, sweep.axis.z)
    length = sqrt(_dot(axis_raw, axis_raw))
    axis: Point = (axis_raw[0] / length, axis_raw[1] / length, axis_raw[2] / length)
    least = min(range(3), key=lambda i: abs(axis[i]))
    basis = [0.0, 0.0, 0.0]
    basis[least] = 1.0
    cross: Point = (
        axis[1] * basis[2] - axis[2] * basis[1],
        axis[2] * basis[0] - axis[0] * basis[2],
        axis[0] * basis[1] - axis[1] * basis[0],
    )
    cross_length = sqrt(_dot(cross, cross))
    u: Point = (cross[0] / cross_length, cross[1] / cross_length, cross[2] / cross_length)
    v: Point = (axis[1] * u[2] - axis[2] * u[1], axis[2] * u[0] - axis[0] * u[2], axis[0] * u[1] - axis[1] * u[0])
    start = (sweep.start.x, sweep.start.y, sweep.start.z)
    end = (sweep.end.x, sweep.end.y, sweep.end.z)
    movement = _sub(end, start)
    low = _sub((obstacle.minimum.x, obstacle.minimum.y, obstacle.minimum.z), start)
    high = _sub((obstacle.maximum.x, obstacle.maximum.y, obstacle.maximum.z), start)
    scale = max(1.0, section.high_mm, section.radius_mm, *(abs(v) for p in (movement, low, high) for v in p))
    guard = scale * 1e-10

    def support(direction: Point) -> _Support:
        axial = _dot(direction, axis)
        height = section.high_mm if axial >= 0 else section.low_mm
        du, dv = _dot(direction, u), _dot(direction, v)
        radial_length = sqrt(du * du + dv * dv)
        direction_length = sqrt(_dot(direction, direction))
        radial_scale = section.radius_mm / radial_length if radial_length > 1e-14 * direction_length else 0.0
        radial: Point = (du * u[0] + dv * v[0], du * u[1] + dv * v[1], du * u[2] + dv * v[2])
        fraction = 1.0 if _dot(direction, movement) > 0 else 0.0
        coordinates = [
            (
                fraction * movement[i]
                + height * axis[i]
                + radial_scale * radial[i]
                - (low[i] if direction[i] >= 0 else high[i])
            )
            / scale
            for i in range(3)
        ]
        return _Support((coordinates[0], coordinates[1], coordinates[2]), fraction)

    vertices = [support((1, 0, 0))]
    lower = 0.0
    for evaluations in range(1, max_evaluations):
        closest, fraction, vertices = _closest(vertices)
        distance = sqrt(_dot(closest, closest))
        upper = distance * scale + guard
        if distance <= guard / scale:
            return (
                0.0,
                upper,
                fraction,
                "Continuous fixed-axis convex envelope; contact/near-contact interval",
                evaluations,
            )
        direction: Point = (-closest[0], -closest[1], -closest[2])
        vertex = support(direction)
        lower = max(lower, max(0.0, _dot(closest, vertex.point) / distance * scale - guard))
        if upper - lower <= tolerance_mm:
            return (
                lower,
                upper,
                fraction,
                "Continuous fixed-axis convex envelope; support-plane distance bounds",
                evaluations + 1,
            )
        if vertex in vertices or evaluations + 1 == max_evaluations:
            return (
                lower,
                upper,
                fraction,
                "Continuous fixed-axis convex envelope; unresolved numerical interval",
                evaluations + 1,
            )
        vertices.append(vertex)
    raise AssertionError("Convex clearance budget must be positive")
