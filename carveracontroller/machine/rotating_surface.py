"""Continuous +Z rotating-cylinder queries against complete prepared triangles.

Each declared cylinder is a filled rotational envelope, not a manufactured flute.
The exact rational feasible prism is projected into the radial plane. Its convex
hull gives the global minimum squared distance over the entire translating move.
No angular/time sampling, tessellated circle or approximate optimization is used.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction as F
from itertools import combinations
from math import isfinite

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.machine.rotating_shape import RotatingShape, shape_contact
from carveracontroller.machine.surface_motion import Box, Point, QPoint, Triangle, cross, dot, qpoint, sub


@dataclass(frozen=True)
class CylinderWitness:
    sample: F
    point: QPoint
    barycentric: tuple[F, F, F]
    radial_distance_squared: F


def dimensions(section: AxialEnvelope, error: float = 0.0) -> tuple[F, F, F]:
    if not isinstance(section, AxialEnvelope) or any(
        type(v) not in (int, float) or not isfinite(v) or abs(v) > 10000
        for v in (section.low_mm, section.high_mm, section.radius_mm)
    ):
        raise ValueError("Rotating section needs finite bounded axial dimensions")
    if type(error) not in (int, float) or not isfinite(error) or not 0 <= error <= 2000:
        raise ValueError("Rotating position allowance must be from zero to 2000 mm")
    padding = F(error)
    # An error cube of halfwidth e lies inside radius 2e in XY and height e.
    # This exact outward guard also contains the previous L1 allowance ball.
    return F(section.low_mm) - padding, F(section.high_mm) + padding, F(section.radius_mm) + 2 * padding


def _solve(rows: Sequence[tuple[QPoint, F]]) -> QPoint | None:
    a, b, c = (row[0] for row in rows)
    determinant = dot(a, cross(b, c))
    if not determinant:
        return None
    bc, ca, ab = cross(b, c), cross(c, a), cross(a, b)
    axes = bc, ca, ab
    values = tuple(sum((rows[j][1] * axes[j][i] for j in range(3)), F(0)) / determinant for i in range(3))
    return values[0], values[1], values[2]


def _orient(a: tuple[F, F], b: tuple[F, F], c: tuple[F, F]) -> F:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _minimum(rows: dict[tuple[F, F], QPoint]) -> tuple[F, QPoint]:
    points = sorted(rows)
    chains: list[list[tuple[F, F]]] = []
    for ordered in (points, list(reversed(points))):
        chain: list[tuple[F, F]] = []
        for p in ordered:
            while len(chain) >= 2 and _orient(chain[-2], chain[-1], p) <= 0:
                chain.pop()
            chain.append(p)
        chains.append(chain)
    hull = chains[0][:-1] + chains[1][:-1] if len(points) > 1 else points
    # If the origin belongs to the hull, recover a feasible rational witness
    # by triangulating it. Convex combinations preserve every original prism
    # inequality and barycentric/time constraint, including lower-dimensional
    # tangencies. Otherwise the nearest point lies on a hull edge.
    for i in range(1, len(hull) - 1):
        a, b, c = hull[0], hull[i], hull[i + 1]
        area = _orient(a, b, c)
        weights = (
            _orient((F(0), F(0)), b, c) / area,
            _orient(a, (F(0), F(0)), c) / area,
            _orient(a, b, (F(0), F(0))) / area,
        )
        if min(weights) >= 0:
            witness = tuple(
                sum((weights[j] * rows[p][axis] for j, p in enumerate((a, b, c))), F(0)) for axis in range(3)
            )
            return F(0), (witness[0], witness[1], witness[2])
    best: tuple[F, QPoint] | None = None
    for a, b in zip(hull, hull[1:] + hull[:1]):
        delta = b[0] - a[0], b[1] - a[1]
        denominator = sum((v * v for v in delta), F(0))
        ratio = (
            max(F(0), min(F(1), -sum((a[j] * delta[j] for j in range(2)), F(0)) / denominator)) if denominator else F(0)
        )
        radial = tuple(a[j] + ratio * delta[j] for j in range(2))
        distance = sum((v * v for v in radial), F(0))
        witness = tuple(rows[a][j] + ratio * (rows[b][j] - rows[a][j]) for j in range(3))
        if best is None or distance < best[0]:
            best = distance, (witness[0], witness[1], witness[2])
    assert best is not None
    return best


def triangle_contact(
    section: AxialEnvelope,
    triangle: Triangle,
    shift: Point = (0, 0, 0),
    delta: Point = (0, 0, 0),
    *,
    position_error_mm: float = 0.0,
    cancelled: Callable[[], bool] = lambda: False,
) -> CylinderWitness | None:
    """Exact whole-chord existence and a witness for the declared padded cylinder.

    The witness is a global radial minimizer subject to complete axial overlap,
    not the first collision time or a surface-of-tool contact. Cutting contact
    is not excluded. Physical flutes and measured registration remain separate.
    """
    if len(triangle) != 3:
        raise ValueError("Rotating surface query requires a complete triangle")
    low, high, radius = dimensions(section, position_error_mm)
    if isinstance(section, RotatingShape):
        hit = shape_contact(section, triangle, shift, delta, position_error_mm, cancelled)
        return CylinderWitness(*hit) if hit is not None else None
    a, b, c = (qpoint(p) for p in triangle)
    start, speed = qpoint(shift), qpoint(delta)
    e, f = sub(b, a), sub(c, a)
    zaxis: QPoint = e[2], f[2], -speed[2]
    constraints = (
        ((F(-1), F(0), F(0)), F(0)),
        ((F(0), F(-1), F(0)), F(0)),
        ((F(1), F(1), F(0)), F(1)),
        ((F(0), F(0), F(-1)), F(0)),
        ((F(0), F(0), F(1)), F(1)),
        (zaxis, high + start[2] - a[2]),
        ((-zaxis[0], -zaxis[1], -zaxis[2]), a[2] - start[2] - low),
    )
    projected: dict[tuple[F, F], QPoint] = {}
    for rows in combinations(constraints, 3):
        if cancelled():
            raise InterruptedError("Rotating surface query cancelled; no partial report")
        p = _solve(rows)
        if p is None or any(dot(normal, p) > bound for normal, bound in constraints):
            continue
        u, v, t = p
        radial = tuple(a[j] + u * e[j] + v * f[j] - start[j] - t * speed[j] for j in range(2))
        projected[(radial[0], radial[1])] = p
    if not projected:
        return None  # The complete axial/time/barycentric prism is empty.
    distance, (u, v, t) = _minimum(projected)
    if distance > radius * radius:
        return None
    point = tuple(a[j] + u * e[j] + v * f[j] for j in range(3))
    return CylinderWitness(t, (point[0], point[1], point[2]), (1 - u - v, u, v), distance)


def box_candidate(section: AxialEnvelope, box: Box, shift: QPoint, delta: QPoint, error: float) -> bool:
    """Exact complete cylinder/node-box rejection, never a contact certificate."""
    low, high, radius = dimensions(section, error)
    lo, hi = F(0), F(1)
    lower, upper = F(box[0][2]) - high - shift[2], F(box[1][2]) - low - shift[2]
    if delta[2]:
        a, b = lower / delta[2], upper / delta[2]
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if lo > hi:
            return False
    elif not lower <= 0 <= upper:
        return False
    breaks = {lo, hi}
    for axis in range(2):
        if delta[axis]:
            for corner in box:
                t = (F(corner[axis]) - shift[axis]) / delta[axis]
                if lo < t < hi:
                    breaks.add(t)
    times = sorted(breaks)

    def distance(t: F) -> F:
        return sum(
            (
                max(F(box[0][j]) - shift[j] - t * delta[j], F(0), shift[j] + t * delta[j] - F(box[1][j])) ** 2
                for j in range(2)
            ),
            F(0),
        )

    if any(distance(t) <= radius * radius for t in times):
        return True
    for a, b in zip(times, times[1:]):
        midpoint = (a + b) / 2
        numerator, denominator = F(0), F(0)
        for j in range(2):
            value = shift[j] + midpoint * delta[j]
            bound = F(box[0][j]) if value < box[0][j] else F(box[1][j]) if value > box[1][j] else None
            if bound is not None:
                numerator += delta[j] * (bound - shift[j])
                denominator += delta[j] ** 2
        if denominator and distance(max(a, min(b, numerator / denominator))) <= radius * radius:
            return True
    return False
