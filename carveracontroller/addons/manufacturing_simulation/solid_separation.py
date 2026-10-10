"""Exact, cheap certificates before full rational triangle intersection.

Binary floats embed into one common integer grid without rounding. A plane or
coplanar edge can prove disjointness, or restrict contact to original shared
vertices/edges. An inconclusive certificate always falls through to the full
intersection calculation; mesh topology remains a separate prerequisite.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .stock_mesh import Point, Triangle, _cancel

IPoint = tuple[int, int, int]


def sub(a: IPoint, b: IPoint) -> IPoint:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def cross(a: IPoint, b: IPoint) -> IPoint:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def dot(a: IPoint, b: IPoint) -> int:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


@dataclass(frozen=True)
class IntegerTriangle:
    points: tuple[IPoint, IPoint, IPoint]
    normal: IPoint


def integer_triangles(
    triangles: Sequence[Triangle], cancelled: Callable[[], bool] | None
) -> tuple[IntegerTriangle, ...]:
    ratios: dict[Point, tuple[tuple[int, int], ...]] = {}
    scale = 1
    for index, triangle in enumerate(triangles):
        if index % 64 == 0:
            _cancel(cancelled)
        for point in triangle:
            if point not in ratios:
                row = tuple(float(v).as_integer_ratio() for v in point)
                scale = max(scale, *(d for _, d in row))
                ratios[point] = row
    points = {}
    for index, (point, row) in enumerate(ratios.items()):
        if index % 64 == 0:
            _cancel(cancelled)
        values = tuple(n * (scale // d) for n, d in row)
        points[point] = (values[0], values[1], values[2])
    result = []
    for index, triangle in enumerate(triangles):
        if index % 64 == 0:
            _cancel(cancelled)
        a, b, c = (points[p] for p in triangle)
        result.append(IntegerTriangle((a, b, c), cross(sub(b, a), sub(c, a))))
    _cancel(cancelled)
    return tuple(result)


def _one_side(values: Sequence[int], points: Sequence[IPoint], shared: set[IPoint]) -> bool:
    return (min(values) >= 0 or max(values) <= 0) and all(p in shared for p, value in zip(points, values) if value == 0)


def boundary_separated(a: IntegerTriangle, b: IntegerTriangle) -> bool:
    """True proves no intersection beyond an original shared boundary."""
    if not any(a.normal) or not any(b.normal):
        return False
    shared = set(a.points).intersection(b.points)
    if len(shared) == 3:
        return False  # Duplicate faces are invalid, never a clear certificate.
    distances = [dot(a.normal, sub(p, a.points[0])) for p in b.points]
    if _one_side(distances, b.points, shared):
        return True
    other = [dot(b.normal, sub(p, b.points[0])) for p in a.points]
    if _one_side(other, a.points, shared):
        return True
    if any(distances):
        return False  # Inconclusive noncoplanar pair: retain the full test.
    # Coplanar triangle edges supply a complete separating-axis family. A weak
    # separating edge is sufficient when its exact line overlap is confined
    # to the original shared boundary.
    drop = max(range(3), key=lambda axis: abs(a.normal[axis]))
    x, y = (axis for axis in range(3) if axis != drop)

    def orient(p: IPoint, q: IPoint, r: IPoint) -> int:
        return (q[x] - p[x]) * (r[y] - p[y]) - (q[y] - p[y]) * (r[x] - p[x])

    for first, second in ((a, b), (b, a)):
        for i in range(3):
            p, q, inside = first.points[i], first.points[(i + 1) % 3], first.points[(i + 2) % 3]
            sign = 1 if orient(p, q, inside) > 0 else -1
            values = [sign * orient(p, q, r) for r in second.points]
            if max(values) > 0:
                continue
            zeros = [r for r, value in zip(second.points, values) if value == 0]
            if not zeros:
                return True
            axis = x if p[x] != q[x] else y
            low = max(min(p[axis], q[axis]), min(r[axis] for r in zeros))
            high = min(max(p[axis], q[axis]), max(r[axis] for r in zeros))
            if low > high:
                return True
            common = [r[axis] for r in shared if orient(p, q, r) == 0]
            if len(common) == 1 and low == high == common[0]:
                return True
            if len(common) == 2 and min(common) <= low <= high <= max(common):
                return True
    return False


def surface_area_partition(
    ids: Sequence[int],
    boxes: Sequence[tuple[Point, Point]],
    centers: Sequence[Point],
    cancelled: Callable[[], bool] | None,
) -> tuple[list[int], list[int]] | None:
    """Twelve-bin SAH partition; only a heuristic, never a geometry predicate."""
    best: tuple[float, int, int, float, float] | None = None

    def area(low: Sequence[float], high: Sequence[float]) -> float:
        x, y, z = (max(0.0, high[i] - low[i]) for i in range(3))
        return x * y + y * z + z * x

    for axis in range(3):
        _cancel(cancelled)
        minimum = min(centers[i][axis] for i in ids)
        extent = max(centers[i][axis] for i in ids) - minimum
        if extent == 0:
            continue
        counts = [0] * 12
        lows = [[float("inf")] * 3 for _ in range(12)]
        highs = [[-float("inf")] * 3 for _ in range(12)]
        for offset, i in enumerate(ids):
            if offset % 128 == 0:
                _cancel(cancelled)
            slot = min(11, int((centers[i][axis] - minimum) / extent * 12))
            counts[slot] += 1
            for a in range(3):
                lows[slot][a] = min(lows[slot][a], boxes[i][0][a])
                highs[slot][a] = max(highs[slot][a], boxes[i][1][a])
        prefix = []
        count = 0
        low, high = [float("inf")] * 3, [-float("inf")] * 3
        for slot in range(12):
            count += counts[slot]
            low = [min(low[a], lows[slot][a]) for a in range(3)]
            high = [max(high[a], highs[slot][a]) for a in range(3)]
            prefix.append((count, area(low, high)))
        count = 0
        low, high = [float("inf")] * 3, [-float("inf")] * 3
        for slot in range(11, 0, -1):
            count += counts[slot]
            low = [min(low[a], lows[slot][a]) for a in range(3)]
            high = [max(high[a], highs[slot][a]) for a in range(3)]
            left_count, left_area = prefix[slot - 1]
            if not left_count or not count:
                continue
            cost = left_count * left_area + count * area(low, high)
            proposal = (cost, axis, slot, minimum, extent)
            if best is None or proposal < best:
                best = proposal
    if best is None:
        return None
    _, axis, threshold, minimum, extent = best
    left, right = [], []
    for offset, i in enumerate(ids):
        if offset % 128 == 0:
            _cancel(cancelled)
        slot = min(11, int((centers[i][axis] - minimum) / extent * 12))
        (left if slot < threshold else right).append(i)
    return (left, right) if left and right else None
