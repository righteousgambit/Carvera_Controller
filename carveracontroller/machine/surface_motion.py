"""Continuous triangle-surface contact in exact input-coordinate arithmetic.

Translation only. Surface separation does not establish solid non-containment.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

Point = tuple[float, float, float]
QPoint = tuple[Fraction, Fraction, Fraction]
Triangle = tuple[Point, Point, Point]
Box = tuple[Point, Point]


def qpoint(point: Sequence[float]) -> QPoint:
    if len(point) != 3 or any(type(v) not in (int, float) or abs(v) > 1e6 or not isfinite(v) for v in point):
        raise ValueError("Surface coordinates need three finite numbers within one million mm")
    return Fraction(point[0]), Fraction(point[1]), Fraction(point[2])


def sub(a: QPoint, b: QPoint) -> QPoint:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def cross(a: QPoint, b: QPoint) -> QPoint:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def dot(a: QPoint, b: QPoint) -> Fraction:
    return sum((x * y for x, y in zip(a, b)), Fraction(0))


def slab_interval(
    first: Sequence[QPoint],
    second: Sequence[QPoint],
    shift: QPoint,
    delta: QPoint,
    axes: Sequence[QPoint],
    padding: Fraction = Fraction(0),
) -> tuple[Fraction, Fraction] | None:
    low, high = Fraction(0), Fraction(1)
    for axis in axes:
        if not any(axis):
            continue
        # L1 dominates the Euclidean projection of a position-error ball.
        allowance = padding * sum(abs(v) for v in axis)
        pa, pb = [dot(p, axis) for p in first], [dot(p, axis) for p in second]
        start, speed = dot(shift, axis), dot(delta, axis)
        lower, upper = min(pb) - max(pa) - allowance - start, max(pb) - min(pa) + allowance - start
        if speed == 0:
            if not lower <= 0 <= upper:
                return None
        else:
            a, b = lower / speed, upper / speed
            low, high = max(low, min(a, b)), min(high, max(a, b))
            if low > high:
                return None
    return low, high


def triangle_interval(
    first: Triangle,
    second: Triangle,
    shift: Point = (0, 0, 0),
    delta: Point = (0, 0, 0),
    *,
    position_error_mm: float = 0.0,
) -> tuple[Fraction, Fraction] | None:
    """Closed contact interval for translating triangles, or conservative curve enclosure.

    Exact rational SAT includes face normals, edge cross-products and in-plane
    axes for coplanar triangles. Degenerate triangles remain conservative.
    `position_error_mm` bounds relative displacement, not per-body error.
    """
    if len(first) != 3 or len(second) != 3:
        raise ValueError("Surface contact requires complete triangles")
    a, b = tuple(qpoint(p) for p in first), tuple(qpoint(p) for p in second)
    if (
        type(position_error_mm) not in (int, float)
        or not 0 <= position_error_mm <= 2000
        or not isfinite(position_error_mm)
    ):
        raise ValueError("Relative surface-position error must be from zero to 2000 mm")
    ea = [sub(a[(i + 1) % 3], a[i]) for i in range(3)]
    eb = [sub(b[(i + 1) % 3], b[i]) for i in range(3)]
    na, nb = cross(ea[0], ea[1]), cross(eb[0], eb[1])
    axes = [
        na,
        nb,
        *[cross(u, v) for u in ea for v in eb],
        *[cross(n, e) for n in (na, nb) for e in ea + eb],
        qpoint((1, 0, 0)),
        qpoint((0, 1, 0)),
        qpoint((0, 0, 1)),
    ]
    return slab_interval(a, b, qpoint(shift), qpoint(delta), axes, Fraction(position_error_mm))


@dataclass(frozen=True)
class SurfaceNode:
    bounds: Box
    ids: tuple[int, ...] = ()
    children: tuple[SurfaceNode, ...] = ()


@dataclass(frozen=True, init=False)
class SurfaceMesh:
    triangles: tuple[Triangle, ...]
    root: SurfaceNode

    def __init__(self) -> None:
        raise TypeError("Use SurfaceMesh.create to validate complete geometry")

    @classmethod
    def create(cls, triangles: Sequence[Triangle], *, cancelled: Callable[[], bool] = lambda: False) -> SurfaceMesh:
        if not 1 <= len(triangles) <= 200_000:
            raise ValueError("Surface mesh needs one to 200000 complete triangles")
        detached = []
        boxes = []
        for i, row in enumerate(triangles):
            if i % 64 == 0 and cancelled():
                raise InterruptedError("Surface mesh preparation cancelled")
            if len(row) != 3:
                raise ValueError("Surface mesh has incomplete triangles")
            points = []
            for p in row:
                qpoint(p)
                points.append((float(p[0]), float(p[1]), float(p[2])))
            triangle: Triangle = (points[0], points[1], points[2])
            detached.append(triangle)
            boxes.append(
                (
                    (min(p[0] for p in points), min(p[1] for p in points), min(p[2] for p in points)),
                    (max(p[0] for p in points), max(p[1] for p in points), max(p[2] for p in points)),
                )
            )

        def build(ids: list[int]) -> SurfaceNode:
            if cancelled():
                raise InterruptedError("Surface index preparation cancelled")
            lo = tuple(min(boxes[i][0][a] for i in ids) for a in range(3))
            hi = tuple(max(boxes[i][1][a] for i in ids) for a in range(3))
            bounds: Box = ((lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2]))
            if len(ids) <= 8:
                return SurfaceNode(bounds, tuple(ids))
            axis = max(range(3), key=lambda a: hi[a] - lo[a])
            ordered = sorted(ids, key=lambda i: boxes[i][0][axis] / 2 + boxes[i][1][axis] / 2)
            middle = len(ids) // 2
            return SurfaceNode(bounds, children=(build(ordered[:middle]), build(ordered[middle:])))

        root = build(list(range(len(detached))))
        result = object.__new__(cls)
        object.__setattr__(result, "triangles", tuple(detached))
        object.__setattr__(result, "root", root)
        return result


@dataclass
class SurfaceBudget:
    max_nodes: int = 2_000_000
    max_pairs: int = 100_000
    max_contacts: int = 10_000
    cancelled: Callable[[], bool] = lambda: False
    nodes: int = 0
    pairs: int = 0
    contacts: int = 0

    def __post_init__(self) -> None:
        for value, limit in ((self.max_nodes, 2_000_000), (self.max_pairs, 100_000), (self.max_contacts, 10_000)):
            if type(value) is not int or not 1 <= value <= limit:
                raise ValueError("Surface review budgets exceed the bounded contract")
        for kind in ("nodes", "pairs", "contacts"):
            value = getattr(self, kind)
            if type(value) is not int or not 0 <= value <= getattr(self, "max_" + kind):
                raise ValueError("Surface review counters exceed the bounded contract")

    def consume(self, kind: str) -> None:
        if self.cancelled():
            raise InterruptedError("Surface review cancelled; no partial report")
        value = getattr(self, kind) + 1
        if value > getattr(self, "max_" + kind):
            raise ValueError("Surface review exhausted its shared " + kind + " budget; no partial report")
        setattr(self, kind, value)


@dataclass(frozen=True)
class SurfaceContact:
    first_triangle: int
    second_triangle: int
    lower: Fraction
    upper: Fraction


def mesh_contacts(
    first: SurfaceMesh,
    second: SurfaceMesh,
    shift: Point,
    delta: Point,
    *,
    position_error_mm: float = 0.0,
    budget: SurfaceBudget | None = None,
) -> tuple[SurfaceContact, ...]:
    """All triangle contact intervals; full [0,1] translation, no time sampling."""
    budget = budget or SurfaceBudget()
    # Validate even an immediately culled/empty query through the same contract.
    qs, qd = qpoint(shift), qpoint(delta)
    if (
        type(position_error_mm) not in (int, float)
        or not 0 <= position_error_mm <= 2000
        or not isfinite(position_error_mm)
    ):
        raise ValueError("Relative surface-position error must be from zero to 2000 mm")
    axes = (qpoint((1, 0, 0)), qpoint((0, 1, 0)), qpoint((0, 0, 1)))
    pending = [(first.root, second.root)]
    result = []
    while pending:
        a, b = pending.pop()
        budget.consume("nodes")
        if (
            slab_interval(
                tuple(qpoint(p) for p in a.bounds),
                tuple(qpoint(p) for p in b.bounds),
                qs,
                qd,
                axes,
                Fraction(position_error_mm),
            )
            is None
        ):
            continue
        if a.children:
            pending.extend((child, b) for child in a.children)
        elif b.children:
            pending.extend((a, child) for child in b.children)
        else:
            for i in a.ids:
                for j in b.ids:
                    budget.consume("pairs")
                    interval = triangle_interval(
                        first.triangles[i], second.triangles[j], shift, delta, position_error_mm=position_error_mm
                    )
                    if interval is not None:
                        budget.consume("contacts")
                        result.append(SurfaceContact(i, j, *interval))
    if budget.cancelled():
        raise InterruptedError("Surface review cancelled; no partial report")
    return tuple(sorted(result, key=lambda c: (c.lower, c.upper, c.first_triangle, c.second_triangle)))
