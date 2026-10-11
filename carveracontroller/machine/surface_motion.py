"""Continuous triangle-surface contact in exact input-coordinate arithmetic.

Translation only. Surface separation does not establish solid non-containment.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from fractions import Fraction
from math import isfinite

from carveracontroller.addons.manufacturing_simulation.solid_separation import surface_area_partition
from carveracontroller.machine.surface_directions import (
    DirectionBounds,
    box_interval,
    overlap_interval,
    point_bounds,
    project,
    union_bounds,
)
from carveracontroller.machine.surface_static import static_contact

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
    axes: Iterable[QPoint],
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
    qs, qd = qpoint(shift), qpoint(delta)
    if not any(qd):
        return (Fraction(0), Fraction(1)) if static_contact(a, b, qs, Fraction(position_error_mm)) else None

    def axes() -> Iterable[QPoint]:
        # Intersections of exact closed intervals commute. Test cheap box axes
        # before constructing derived axes, then stop generating on separation.
        yield qpoint((1, 0, 0))
        yield qpoint((0, 1, 0))
        yield qpoint((0, 0, 1))
        ea = [sub(a[(i + 1) % 3], a[i]) for i in range(3)]
        eb = [sub(b[(i + 1) % 3], b[i]) for i in range(3)]
        na, nb = cross(ea[0], ea[1]), cross(eb[0], eb[1])
        yield na
        yield nb
        for u in ea:
            for v in eb:
                yield cross(u, v)
        for n in (na, nb):
            for e in ea + eb:
                yield cross(n, e)

    return slab_interval(a, b, qs, qd, axes(), Fraction(position_error_mm))


@dataclass(frozen=True)
class SurfaceNode:
    bounds: Box
    ids: tuple[int, ...] = ()
    children: tuple[SurfaceNode, ...] = ()
    projections: DirectionBounds = ()


@dataclass(frozen=True, init=False)
class SurfaceMesh:
    triangles: tuple[Triangle, ...]
    root: SurfaceNode
    index_method: str

    def __init__(self) -> None:
        raise TypeError("Use SurfaceMesh.create to validate complete geometry")

    @classmethod
    def create(
        cls,
        triangles: Sequence[Triangle],
        *,
        cancelled: Callable[[], bool] = lambda: False,
        index_method: str = "surface-directions-v3",
    ) -> SurfaceMesh:
        if type(index_method) is not str or index_method not in (
            "median-v1",
            "surface-area-v2",
            "surface-directions-v3",
        ):
            raise ValueError("Unsupported surface index method")
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

        center_points: list[Point] = []
        for i, (low, high) in enumerate(boxes):
            if i % 128 == 0 and cancelled():
                raise InterruptedError("Surface index preparation cancelled")
            center = tuple(low[a] / 2 + high[a] / 2 for a in range(3))
            center_points.append((center[0], center[1], center[2]))

        def build(ids: list[int], depth: int = 0) -> SurfaceNode:
            if cancelled():
                raise InterruptedError("Surface index preparation cancelled")
            lo = tuple(min(boxes[i][0][a] for i in ids) for a in range(3))
            hi = tuple(max(boxes[i][1][a] for i in ids) for a in range(3))
            bounds: Box = ((lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2]))
            if len(ids) <= {"median-v1": 8, "surface-area-v2": 2, "surface-directions-v3": 1}[index_method]:
                projections = (
                    point_bounds(qpoint(p) for i in ids for p in detached[i])
                    if index_method == "surface-directions-v3"
                    else ()
                )
                return SurfaceNode(bounds, tuple(ids), projections=projections)
            # Only partitioning uses floats; conservative boxes and contact
            # predicates retain every original face and exact input arithmetic.
            # Bound heuristic depth; coincident centers use balanced fallback.
            partition = (
                surface_area_partition(ids, boxes, center_points, cancelled)
                if index_method != "median-v1" and depth < 32
                else None
            )
            if partition is None:
                axis = max(range(3), key=lambda a: hi[a] - lo[a])
                ordered = sorted(ids, key=lambda i: center_points[i][axis])
                middle = len(ids) // 2
                partition = ordered[:middle], ordered[middle:]
            children = tuple(build(part, depth + 1) for part in partition)
            projections = (
                union_bounds(tuple(c.projections for c in children)) if index_method == "surface-directions-v3" else ()
            )
            return SurfaceNode(bounds, children=children, projections=projections)

        root = build(list(range(len(detached))))
        result = object.__new__(cls)
        object.__setattr__(result, "triangles", tuple(detached))
        object.__setattr__(result, "root", root)
        object.__setattr__(result, "index_method", index_method)
        return result


class SurfaceBudgetExceeded(ValueError):
    """Whole-operation surface work limit; no partial contact report."""


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
            raise SurfaceBudgetExceeded("Surface review exhausted its shared " + kind + " budget; no partial report")
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
    result = []
    for contact in _contact_candidates(first, second, shift, delta, position_error_mm=position_error_mm, budget=budget):
        budget.consume("contacts")
        result.append(contact)
    return tuple(sorted(result, key=lambda c: (c.lower, c.upper, c.first_triangle, c.second_triangle)))


def _contact_candidates(
    first: SurfaceMesh,
    second: SurfaceMesh,
    shift: Point,
    delta: Point,
    *,
    position_error_mm: float = 0.0,
    budget: SurfaceBudget | None = None,
) -> Iterator[SurfaceContact]:
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
    shifts, speeds = project(qs), project(qd)
    padding = Fraction(position_error_mm)
    pending = [(first.root, second.root)]
    while pending:
        a, b = pending.pop()
        budget.consume("nodes")
        interval = box_interval(a.bounds, b.bounds, qs, qd, padding)
        if interval is None:
            continue
        if (
            a.projections
            and b.projections
            and overlap_interval(a.projections, b.projections, shifts, speeds, padding, interval) is None
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
                        yield SurfaceContact(i, j, *interval)
    if budget.cancelled():
        raise InterruptedError("Surface review cancelled; no partial report")


class ContactGroupBudgetExceeded(ValueError):
    """Complete grouped review exceeded its separate representation bounds."""


@dataclass
class ContactGroupBudget:
    max_groups: int = 10_000
    max_members: int = 100_000
    cancelled: Callable[[], bool] = lambda: False
    groups: int = 0
    members: int = 0

    def __post_init__(self) -> None:
        for value, maximum in ((self.max_groups, 10_000), (self.max_members, 100_000)):
            if type(value) is not int or not 1 <= value <= maximum:
                raise ValueError("Contact-group representation budget exceeds contract")
        for name in ("groups", "members"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= getattr(self, "max_" + name):
                raise ValueError("Contact-group counters exceed contract")

    def consume(self, *, new_group: bool) -> None:
        if self.cancelled():
            raise InterruptedError("Grouped surface review cancelled; no partial report")
        for name, increment in (("members", 1), ("groups", int(new_group))):
            if getattr(self, name) + increment > getattr(self, "max_" + name):
                raise ContactGroupBudgetExceeded(
                    "Grouped surface review exhausted shared " + name + " budget; no partial report"
                )
        self.members += 1
        self.groups += int(new_group)


@dataclass(frozen=True)
class SurfaceContactGroup:
    lower: Fraction
    upper: Fraction
    triangle_pairs: tuple[tuple[int, int], ...]


def mesh_contact_groups(
    first: SurfaceMesh,
    second: SurfaceMesh,
    shift: Point,
    delta: Point,
    *,
    position_error_mm: float = 0.0,
    budget: SurfaceBudget | None = None,
    group_budget: ContactGroupBudget | None = None,
) -> tuple[SurfaceContactGroup, ...]:
    """Group identical exact intervals; retain EVERY contributing original face pair.

    Node/pair work uses the unchanged SurfaceBudget bounds. This separate mode
    limits representation to10000 exact groups and100000 total member pairs;
    the individual-contact API still charges its original10000-contact bound.
    No contact is merged by tolerance, dropped, sampled or excluded.
    """
    budget = budget or SurfaceBudget()
    group_budget = group_budget or ContactGroupBudget(cancelled=budget.cancelled)
    groups: dict[tuple[Fraction, Fraction], list[tuple[int, int]]] = {}
    for hit in _contact_candidates(first, second, shift, delta, position_error_mm=position_error_mm, budget=budget):
        key = hit.lower, hit.upper
        group_budget.consume(new_group=key not in groups)
        groups.setdefault(key, []).append((hit.first_triangle, hit.second_triangle))
    if budget.cancelled() or group_budget.cancelled():
        raise InterruptedError("Grouped surface review cancelled; no partial report")
    return tuple(SurfaceContactGroup(lo, hi, tuple(sorted(pairs))) for (lo, hi), pairs in sorted(groups.items()))
