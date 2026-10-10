"""Exact fixed-direction node bounds; partitioning never changes original faces."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from fractions import Fraction

QPoint = tuple[Fraction, Fraction, Fraction]
Projections = tuple[Fraction, ...]
DirectionBounds = tuple[tuple[Fraction, Fraction], ...]
# Coordinate directions retain the original AABB test. Six diagonal axes
# tighten its enclosing polytope. Twelve 2:1 directions have L1 norm three.
# The original allowance scales by each exact norm, never by a rounded normal.
DIRECTIONS = (
    (1, 1, 0),
    (1, -1, 0),
    (1, 0, 1),
    (1, 0, -1),
    (0, 1, 1),
    (0, 1, -1),
    (2, 1, 0),
    (2, -1, 0),
    (1, 2, 0),
    (1, -2, 0),
    (2, 0, 1),
    (2, 0, -1),
    (1, 0, 2),
    (1, 0, -2),
    (0, 2, 1),
    (0, 2, -1),
    (0, 1, 2),
    (0, 1, -2),
)
DIRECTION_NORMS = tuple(sum(abs(v) for v in axis) for axis in DIRECTIONS)


def project(point: QPoint) -> Projections:
    x, y, z = point
    xx, yy, zz = x + x, y + y, z + z
    return (
        x + y,
        x - y,
        x + z,
        x - z,
        y + z,
        y - z,
        xx + y,
        xx - y,
        x + yy,
        x - yy,
        xx + z,
        xx - z,
        x + zz,
        x - zz,
        yy + z,
        yy - z,
        y + zz,
        y - zz,
    )


def point_bounds(points: Iterable[QPoint]) -> DirectionBounds:
    rows = tuple(project(p) for p in points)
    return tuple((min(p[i] for p in rows), max(p[i] for p in rows)) for i in range(len(DIRECTIONS)))


def union_bounds(children: Sequence[DirectionBounds]) -> DirectionBounds:
    return tuple((min(c[i][0] for c in children), max(c[i][1] for c in children)) for i in range(len(DIRECTIONS)))


def overlap_interval(
    first: DirectionBounds,
    second: DirectionBounds,
    shifts: Projections,
    speeds: Projections,
    padding: Fraction,
    interval: tuple[Fraction, Fraction],
) -> tuple[Fraction, Fraction] | None:
    """Intersect complete continuous projection intervals with the AABB interval.

    Exact input dyadics and rational division only. Empty intersection proves
    every enclosed original triangle pair separated, including curve allowance.
    A nonempty intersection is a candidate and proves no contact or clearance.
    """
    low, high = interval
    allowances = 2 * padding, 3 * padding
    for i, norm in enumerate(DIRECTION_NORMS):
        allowance = allowances[norm - 2]
        lower = second[i][0] - first[i][1] - allowance - shifts[i]
        upper = second[i][1] - first[i][0] + allowance - shifts[i]
        speed = speeds[i]
        if speed == 0:
            if not lower <= 0 <= upper:
                return None
        else:
            a, b = lower / speed, upper / speed
            low, high = max(low, min(a, b)), min(high, max(a, b))
            if low > high:
                return None
    return low, high


def box_interval(
    first: Sequence[Sequence[float]],
    second: Sequence[Sequence[float]],
    shift: QPoint,
    delta: QPoint,
    padding: Fraction,
) -> tuple[Fraction, Fraction] | None:
    """Original three coordinate-axis slabs, without general dot products.

    Bounds come only from validated complete SurfaceMesh nodes. Coordinate
    endpoints embed exactly as Fractions; no float subtraction or tolerance is
    used. Work counting and closed interval semantics match the original test.
    """
    low, high = Fraction(0), Fraction(1)
    for i in range(3):
        lower = Fraction(second[0][i]) - Fraction(first[1][i]) - padding - shift[i]
        upper = Fraction(second[1][i]) - Fraction(first[0][i]) + padding - shift[i]
        speed = delta[i]
        if speed == 0:
            if not lower <= 0 <= upper:
                return None
        else:
            a, b = lower / speed, upper / speed
            low, high = max(low, min(a, b)), min(high, max(a, b))
            if low > high:
                return None
    return low, high
