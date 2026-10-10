"""Validated stock solids and actual center-sampled initial occupancy.

Triangle intersections and ray crossings use exact rational representations of
the imported finite coordinates. Voxel centers and placement retain the engine's
floating-point millimetre convention. Neither geometry nor occupancy is measured
physical stock; registration and manufacturing qualification are separate.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations
from typing import Literal, Protocol

from .geometry import AABB, Vec3
from .solid_separation import IntegerTriangle, boundary_separated, integer_triangles, surface_area_partition
from .stock import StockVolume
from .stock_mesh import Point, StockMeshInput, Triangle, _cancel, _topology

QPoint = tuple[Fraction, Fraction, Fraction]
QPoint2 = tuple[Fraction, Fraction]
Box = tuple[Point, Point]
Interval = tuple[Fraction, Fraction]


class _MeshGeometry(Protocol):
    @property
    def triangles_mm(self) -> tuple[Triangle, ...]: ...
    @property
    def minimum_mm(self) -> Point: ...
    @property
    def maximum_mm(self) -> Point: ...


@dataclass(frozen=True)
class _SurfaceInput:
    triangles_mm: tuple[Triangle, ...]
    minimum_mm: Point
    maximum_mm: Point


def _sub(a: QPoint, b: QPoint) -> QPoint:
    return a[0] - b[0], a[1] - b[1], a[2] - b[2]


def _cross(a: QPoint, b: QPoint) -> QPoint:
    return a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]


def _dot(a: QPoint, b: QPoint) -> Fraction:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _interpolate(a: QPoint, b: QPoint, t: Fraction) -> QPoint:
    return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t


def _orient(a: QPoint2, b: QPoint2, p: QPoint2) -> Fraction:
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])


def _box(triangle: Triangle) -> Box:
    return (
        (min(p[0] for p in triangle), min(p[1] for p in triangle), min(p[2] for p in triangle)),
        (max(p[0] for p in triangle), max(p[1] for p in triangle), max(p[2] for p in triangle)),
    )


def _overlap(a: Box, b: Box) -> bool:
    return all(a[0][i] <= b[1][i] and b[0][i] <= a[1][i] for i in range(3))


@dataclass
class _Budget:
    max_nodes: int = 2_000_000
    max_pairs: int = 250_000
    max_rays: int = 8_000_000
    cancelled: Callable[[], bool] | None = None
    nodes: int = 0
    pairs: int = 0
    rays: int = 0

    def __post_init__(self) -> None:
        for value in (self.max_nodes, self.max_pairs, self.max_rays):
            if type(value) is not int or value <= 0:
                raise ValueError("Stock geometry work budgets must be positive integers")

    def consume(self, kind: str) -> None:
        value = getattr(self, kind) + 1
        setattr(self, kind, value)
        if value > getattr(self, "max_" + kind):
            raise ValueError("Stock geometry work budget exceeded; simplify the mesh or use a coarser voxel grid")
        if value % 128 == 1:
            _cancel(self.cancelled)


@dataclass(frozen=True)
class _Node:
    bounds: Box
    count: int
    ids: tuple[int, ...] = ()
    children: tuple[_Node, ...] = ()


def _index(boxes: Sequence[Box], cancelled: Callable[[], bool] | None, *, surface_area: bool = False) -> _Node:
    keys = 0
    centers = []
    if surface_area:
        for index, box in enumerate(boxes):
            if index % 128 == 0:
                _cancel(cancelled)
            values = tuple(box[0][a] / 2 + box[1][a] / 2 for a in range(3))
            centers.append((values[0], values[1], values[2]))

    def branch(ids: list[int], depth: int = 0) -> _Node:
        nonlocal keys
        _cancel(cancelled)
        low = tuple(min(boxes[i][0][a] for i in ids) for a in range(3))
        high = tuple(max(boxes[i][1][a] for i in ids) for a in range(3))
        bounds: Box = ((low[0], low[1], low[2]), (high[0], high[1], high[2]))
        # Larger solid-review leaves trade bounded cheap box comparisons for
        # fewer tree visits; every overlapping face still consumes a step.
        # Keep the legacy stock tree and its accounting unchanged.
        if len(ids) <= (16 if surface_area else 8):
            return _Node(bounds, len(ids), tuple(ids))
        if surface_area and depth < 32:
            partition = surface_area_partition(ids, boxes, centers, cancelled)
            if partition is not None:
                left, right = partition
                return _Node(bounds, len(ids), children=(branch(left, depth + 1), branch(right, depth + 1)))
        axis = max(range(3), key=lambda a: high[a] - low[a])

        def key(i: int) -> float:
            nonlocal keys
            keys += 1
            if keys % 128 == 1:
                _cancel(cancelled)
            return boxes[i][0][axis] / 2 + boxes[i][1][axis] / 2

        ordered = sorted(ids, key=key)
        middle = len(ids) // 2
        return _Node(
            bounds, len(ids), children=(branch(ordered[:middle], depth + 1), branch(ordered[middle:], depth + 1))
        )

    return branch(list(range(len(boxes))))


@dataclass(frozen=True)
class _ExactTriangle:
    points: tuple[QPoint, QPoint, QPoint]
    normal: QPoint


def _exact_triangles(mesh: _MeshGeometry, cancelled: Callable[[], bool] | None) -> tuple[_ExactTriangle, ...]:
    vertices: dict[Point, QPoint] = {}
    result = []
    for index, triangle in enumerate(mesh.triangles_mm):
        if index % 128 == 0:
            _cancel(cancelled)
        points = []
        for point in triangle:
            if point not in vertices:
                vertices[point] = Fraction(point[0]), Fraction(point[1]), Fraction(point[2])
            points.append(vertices[point])
        a, b, c = points
        result.append(_ExactTriangle((a, b, c), _cross(_sub(b, a), _sub(c, a))))
    _cancel(cancelled)
    return tuple(result)


def _plane_cut(triangle: _ExactTriangle, plane: _ExactTriangle) -> tuple[QPoint, ...]:
    points = triangle.points
    distances = [_dot(plane.normal, _sub(point, plane.points[0])) for point in points]
    result = {point for point, distance in zip(points, distances) if distance == 0}
    for i, j in ((0, 1), (1, 2), (2, 0)):
        if distances[i] * distances[j] < 0:
            result.add(_interpolate(points[i], points[j], distances[i] / (distances[i] - distances[j])))
    return tuple(result)


def _coplanar_crossing(a: _ExactTriangle, b: _ExactTriangle, shared: set[QPoint]) -> bool:
    drop = max(range(3), key=lambda i: abs(a.normal[i]))
    axes = [i for i in range(3) if i != drop]

    def project(point: QPoint) -> QPoint2:
        return point[axes[0]], point[axes[1]]

    polygon = [project(p) for p in a.points]
    clip = [project(p) for p in b.points]
    sign = 1 if _orient(*clip) > 0 else -1
    for start, end in zip(clip, clip[1:] + clip[:1]):
        if not polygon:
            return False
        output = []
        previous = polygon[-1]
        d0 = _orient(start, end, previous) * sign
        for point in polygon:
            d1 = _orient(start, end, point) * sign
            if (d0 < 0 <= d1) or (d1 < 0 <= d0):
                t = d0 / (d0 - d1)
                output.append((previous[0] + (point[0] - previous[0]) * t, previous[1] + (point[1] - previous[1]) * t))
            if d1 >= 0:
                output.append(point)
            previous, d0 = point, d1
        polygon = output
    if not polygon:
        return False
    common = [project(p) for p in shared]
    if not common:
        return True
    if len(common) == 1:
        return any(p != common[0] for p in polygon)
    if len(common) != 2:
        return True
    p, q = common
    return any(
        _orient(p, q, point) != 0 or any(not min(p[i], q[i]) <= point[i] <= max(p[i], q[i]) for i in (0, 1))
        for point in polygon
    )


def _improper_intersection(a: _ExactTriangle, b: _ExactTriangle) -> bool:
    shared = set(a.points).intersection(b.points)
    line = _cross(a.normal, b.normal)
    if not any(line):
        if _dot(b.normal, _sub(a.points[0], b.points[0])) != 0:
            return False
        return _coplanar_crossing(a, b, shared)
    # Noncoplanar triangles with a shared edge can intersect only on that edge.
    if len(shared) == 2:
        return False
    cut_a, cut_b = _plane_cut(a, b), _plane_cut(b, a)
    if not cut_a or not cut_b:
        return False
    axis = max(range(3), key=lambda i: abs(line[i]))
    low = max(min(p[axis] for p in cut_a), min(p[axis] for p in cut_b))
    high = min(max(p[axis] for p in cut_a), max(p[axis] for p in cut_b))
    if low > high:
        return False
    return not (len(shared) == 1 and low == high == next(iter(shared))[axis])


def _validate_intersections(
    tree: _Node,
    boxes: Sequence[Box],
    triangles: Sequence[_ExactTriangle],
    budget: _Budget,
    fast: Sequence[IntegerTriangle] | None = None,
) -> None:
    pairs: Iterable[tuple[int, int]]
    pending = [(tree, tree)]
    while pending:
        left, right = pending.pop()
        budget.consume("nodes")
        if not _overlap(left.bounds, right.bounds):
            continue
        if left is right:
            if left.children:
                a, b = left.children
                pending.extend(((a, a), (a, b), (b, b)))
                continue
            pairs = combinations(left.ids, 2)
        elif left.children or right.children:
            if left.children and (not right.children or left.count >= right.count):
                pending.extend((child, right) for child in left.children)
            else:
                pending.extend((left, child) for child in right.children)
            continue
        else:
            pairs = ((i, j) for i in left.ids for j in right.ids)
        for i, j in pairs:
            if fast is not None:
                # Keep cheap certificates bounded by the existing shared
                # validation-step limit; reserve pair budget for full tests.
                if not _overlap(boxes[i], boxes[j]):
                    continue
                budget.consume("nodes")
                if boundary_separated(fast[i], fast[j]):
                    continue
            budget.consume("pairs")
            if _overlap(boxes[i], boxes[j]) and _improper_intersection(triangles[i], triangles[j]):
                raise ValueError(
                    f"Stock mesh triangles {i + 1} and {j + 1} intersect or touch outside a shared edge/vertex"
                )
    _cancel(budget.cancelled)


def _shells(mesh: _MeshGeometry, cancelled: Callable[[], bool] | None) -> tuple[tuple[int, ...], ...]:
    parents = list(range(len(mesh.triangles_mm)))

    def root(i: int) -> int:
        while i != parents[i]:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    owners: dict[tuple[Point, Point], int] = {}
    for index, (a, b, c) in enumerate(mesh.triangles_mm):
        if index % 128 == 0:
            _cancel(cancelled)
        for p, q in ((a, b), (b, c), (c, a)):
            edge = (p, q) if p < q else (q, p)
            if edge in owners:
                parents[root(index)] = root(owners[edge])
            else:
                owners[edge] = index
    groups: dict[int, list[int]] = defaultdict(list)
    for index in range(len(parents)):
        if index % 128 == 0:
            _cancel(cancelled)
        groups[root(index)].append(index)
    return tuple(tuple(ids) for ids in groups.values())


def _projected_inside(points: Sequence[QPoint2], query: QPoint2, *, half_open: bool) -> bool:
    a, b, c = points
    if _orient(a, b, c) < 0:
        b, c = c, b
    for p, q in ((a, b), (b, c), (c, a)):
        distance = _orient(p, q, query)
        top_left = q[1] > p[1] or (q[1] == p[1] and q[0] < p[0])
        if distance < 0 or (distance == 0 and half_open and not top_left):
            return False
    return True


def _parallel_boundary(triangle: _ExactTriangle, y: Fraction, z: Fraction) -> Interval | None:
    a = triangle.points[0]
    if triangle.normal[1] * (y - a[1]) + triangle.normal[2] * (z - a[2]) != 0:
        return None
    axis = 1 if len({p[1] for p in triangle.points}) > 1 else 2
    value = y if axis == 1 else z
    distances = [p[axis] - value for p in triangle.points]
    points = {p for p, d in zip(triangle.points, distances) if d == 0}
    for i, j in ((0, 1), (1, 2), (2, 0)):
        if distances[i] * distances[j] < 0:
            points.add(
                _interpolate(triangle.points[i], triangle.points[j], distances[i] / (distances[i] - distances[j]))
            )
    values = [p[0] for p in points if p[1] == y and p[2] == z]
    return (min(values), max(values)) if values else None


def _row(
    tree: _Node,
    triangles: Sequence[_ExactTriangle],
    y: Fraction,
    z: Fraction,
    budget: _Budget,
    exclude: frozenset[int] = frozenset(),
) -> tuple[list[tuple[Fraction, int]], list[Interval]]:
    pending = [tree]
    crossings: list[tuple[Fraction, int]] = []
    boundary: list[Interval] = []
    while pending:
        node = pending.pop()
        budget.consume("nodes")
        if not (node.bounds[0][1] <= y <= node.bounds[1][1] and node.bounds[0][2] <= z <= node.bounds[1][2]):
            continue
        pending.extend(node.children)
        for index in node.ids:
            if index in exclude:
                continue
            budget.consume("rays")
            triangle = triangles[index]
            normal = triangle.normal
            if not normal[0]:
                interval = _parallel_boundary(triangle, y, z)
                if interval is not None:
                    boundary.append(interval)
                continue
            projected = [(p[1], p[2]) for p in triangle.points]
            if not _projected_inside(projected, (y, z), half_open=False):
                continue
            a = triangle.points[0]
            x = a[0] - (normal[1] * (y - a[1]) + normal[2] * (z - a[2])) / normal[0]
            boundary.append((x, x))
            if _projected_inside(projected, (y, z), half_open=True):
                crossings.append((x, 1 if normal[0] > 0 else -1))
    return crossings, boundary


def _material_intervals(crossings: Sequence[tuple[Fraction, int]], boundary: list[Interval]) -> tuple[Interval, ...]:
    weights: dict[Fraction, int] = defaultdict(int)
    for x, sign in crossings:
        weights[x] += sign
    winding = 0
    start = Fraction(0)
    intervals = list(boundary)
    for x, weight in sorted(weights.items()):
        changed = winding - weight
        if abs(changed) > 1:
            raise ValueError("Stock mesh has ambiguous nested-shell winding")
        if winding == 0 and changed:
            start = x
        elif winding and changed == 0:
            intervals.append((start, x))
        winding = changed
    if winding:
        raise ValueError("Stock mesh ray does not close")
    merged: list[Interval] = []
    for low, high in sorted(intervals):
        if merged and low <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(high, merged[-1][1])
        else:
            merged.append((low, high))
    return tuple(merged)


def _validate_geometry(
    mesh: _MeshGeometry, budget: _Budget
) -> tuple[float, _Node, tuple[_ExactTriangle, ...], tuple[tuple[int, ...], ...]]:
    boxes = []
    for index, triangle in enumerate(mesh.triangles_mm):
        if index % 128 == 0:
            _cancel(budget.cancelled)
        boxes.append(_box(triangle))
    tree = _index(boxes, budget.cancelled, surface_area=isinstance(budget, SolidBudget))
    triangles = _exact_triangles(mesh, budget.cancelled)
    if any(not any(triangle.normal) for triangle in triangles):
        raise ValueError("Solid mesh has an exact degenerate face")
    fast = integer_triangles(mesh.triangles_mm, budget.cancelled) if isinstance(budget, SolidBudget) else None
    _validate_intersections(tree, boxes, triangles, budget, fast)
    shells = _shells(mesh, budget.cancelled)
    material_volume = Fraction(0)
    for shell in shells:
        _cancel(budget.cancelled)
        origin = triangles[shell[0]].points[0]
        signed_volume = Fraction(0)
        for count, index in enumerate(shell):
            if count % 128 == 0:
                _cancel(budget.cancelled)
            a, b, c = (_sub(p, origin) for p in triangles[index].points)
            signed_volume += _dot(a, _cross(b, c)) / 6
        if not signed_volume:
            raise ValueError("Stock shell has zero enclosed volume")
        crossings, boundary = _row(tree, triangles, origin[1], origin[2], budget, frozenset(shell))
        if any(low <= origin[0] <= high for low, high in boundary):
            raise ValueError("Stock shells touch at an unresolved boundary")
        outside = sum(sign for x, sign in crossings if x > origin[0])
        inside = outside + (1 if signed_volume > 0 else -1)
        if abs(outside) > 1 or (outside == 0 and abs(inside) != 1) or (outside != 0 and inside != 0):
            raise ValueError("Stock mesh has ambiguous nested-shell winding")
        material_volume += abs(signed_volume) if outside == 0 else -abs(signed_volume)
    volume = float(material_volume)
    if not math.isfinite(volume) or volume <= 0:
        raise ValueError("Stock material volume must be positive and representable")
    _cancel(budget.cancelled)
    return volume, tree, triangles, shells


@dataclass(frozen=True, init=False)
class StockSolid:
    mesh: StockMeshInput
    material_volume_mm3: float
    shell_count: int
    _tree: _Node
    _triangles: tuple[_ExactTriangle, ...]

    def __init__(self) -> None:
        raise TypeError("Use StockSolid.validate for geometric validation")

    @classmethod
    def validate(
        cls,
        mesh: StockMeshInput,
        *,
        cancelled: Callable[[], bool] | None = None,
        max_pairs: int = 250_000,
        max_node_visits: int = 2_000_000,
    ) -> StockSolid:
        if not isinstance(mesh, StockMeshInput):
            raise ValueError("Stock solid requires topology-checked mesh input")
        budget = _Budget(max_nodes=max_node_visits, max_pairs=max_pairs, cancelled=cancelled)
        volume, tree, triangles, shells = _validate_geometry(mesh, budget)
        result = object.__new__(cls)
        for name, value in (
            ("mesh", mesh),
            ("material_volume_mm3", volume),
            ("shell_count", len(shells)),
            ("_tree", tree),
            ("_triangles", triangles),
        ):
            object.__setattr__(result, name, value)
        return result

    def contains(self, point: Point, *, cancelled: Callable[[], bool] | None = None) -> bool:
        if len(point) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point):
            raise ValueError("Stock point needs three finite millimetre coordinates")
        if any(v < low or v > high for v, low, high in zip(point, self.mesh.minimum_mm, self.mesh.maximum_mm)):
            return False
        budget = _Budget(cancelled=cancelled)
        x, y, z = (Fraction(v) for v in point)
        crossings, boundary = _row(self._tree, self._triangles, y, z, budget)
        _cancel(cancelled)
        return any(low <= x <= high for low, high in _material_intervals(crossings, boundary))

    def voxelize_grid(
        self,
        grid: StockVolume,
        *,
        translation_mm: Point = (0, 0, 0),
        max_ray_tests: int = 8_000_000,
        max_node_visits: int = 16_000_000,
        cancelled: Callable[[], bool] | None = None,
    ) -> StockVolume:
        """Classify a complete solid on an existing grid, before its pose transform.

        Grid bounds, shape, cell sizes, pivot and orientation are retained exactly.
        Mesh coordinates plus explicit translation are in this unrotated grid
        frame. No auto-centering, clipping or interpolation between grids occurs.
        """
        if (
            not isinstance(grid, StockVolume)
            or grid.memory_bytes > 2_000_000
            or len(translation_mm) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100_000 for v in translation_mm)
            or type(max_ray_tests) is not int
            or not 1 <= max_ray_tests <= 8_000_000
            or type(max_node_visits) is not int
            or not 1 <= max_node_visits <= 16_000_000
        ):
            raise ValueError("Target classification needs a bounded grid, explicit finite placement and work limits")
        low, high = grid.grid_bounds.minimum.tuple, grid.grid_bounds.maximum.tuple
        if any(
            a + shift < left or b + shift > right
            for a, b, shift, left, right in zip(self.mesh.minimum_mm, self.mesh.maximum_mm, translation_mm, low, high)
        ):
            raise ValueError("Complete target bounds must fit the retained stock grid; target is not clipped")
        _cancel(cancelled)
        result = grid.clone(cancelled=cancelled)
        budget = _Budget(max_nodes=max_node_visits, max_rays=max_ray_tests, cancelled=cancelled)
        nx, ny, nz = grid.shape
        cells = bytearray(len(grid._occupied))
        remaining = 0

        def first_index(value: Fraction, *, after: bool) -> int:
            left, right = 0, nx
            while left < right:
                middle = (left + right) // 2
                center = Fraction(grid.grid_center(middle, 0, 0).x - translation_mm[0])
                if center < value or (after and center == value):
                    left = middle + 1
                else:
                    right = middle
            return left

        for z in range(nz):
            for y in range(ny):
                _cancel(cancelled)
                center = grid.grid_center(0, y, z)
                crossings, boundary = _row(
                    self._tree,
                    self._triangles,
                    Fraction(center.y - translation_mm[1]),
                    Fraction(center.z - translation_mm[2]),
                    budget,
                )
                offset = nx * (y + ny * z)
                for a, b in _material_intervals(crossings, boundary):
                    start, end = first_index(a, after=False), first_index(b, after=True)
                    for chunk in range(start, end, 65536):
                        _cancel(cancelled)
                        count = min(65536, end - chunk)
                        cells[offset + chunk : offset + chunk + count] = b"\x01" * count
                        remaining += count
        _cancel(cancelled)
        result._occupied, result._remaining_count, result._initial_count = cells, remaining, remaining
        return result

    def voxelize(
        self,
        resolution_mm: float,
        *,
        translation_mm: Point = (0, 0, 0),
        rotation_deg: float = 0,
        tilt_deg: tuple[float, float] = (0.0, 0.0),
        pivot: Vec3 | None = None,
        max_voxels: int = 2_000_000,
        max_ray_tests: int = 8_000_000,
        max_node_visits: int = 16_000_000,
        cancelled: Callable[[], bool] | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> ImportedStock:
        translation = Vec3(*translation_mm)
        bounds = AABB(Vec3(*self.mesh.minimum_mm) + translation, Vec3(*self.mesh.maximum_mm) + translation)
        stock = StockVolume(
            bounds,
            resolution_mm,
            max_voxels=max_voxels,
            rotation_deg=rotation_deg,
            tilt_deg=tilt_deg,
            pivot=pivot,
            cancelled=cancelled,
        )
        for axis, size in enumerate(stock.cell_size.tuple):
            magnitude = max(1.0, abs(bounds.minimum.tuple[axis]), abs(bounds.maximum.tuple[axis]))
            if size < 4 * math.ulp(magnitude):
                raise ValueError("Voxel resolution loses position precision at this placement; use a coarser grid")
        budget = _Budget(max_nodes=max_node_visits, max_rays=max_ray_tests, cancelled=cancelled)
        nx, ny, nz = stock.shape
        cells = bytearray(len(stock._occupied))
        remaining = 0

        def first_index(value: Fraction, *, after: bool) -> int:
            low, high = 0, nx
            while low < high:
                middle = (low + high) // 2
                center = Fraction(bounds.minimum.x + (middle + 0.5) * stock.cell_size.x - translation.x)
                if center < value or (after and center == value):
                    low = middle + 1
                else:
                    high = middle
            return low

        for z in range(nz):
            for y in range(ny):
                _cancel(cancelled)
                local_y = Fraction(bounds.minimum.y + (y + 0.5) * stock.cell_size.y - translation.y)
                local_z = Fraction(bounds.minimum.z + (z + 0.5) * stock.cell_size.z - translation.z)
                crossings, boundary = _row(self._tree, self._triangles, local_y, local_z, budget)
                intervals = _material_intervals(crossings, boundary)
                offset = nx * (y + ny * z)
                for a, b in intervals:
                    start, end = first_index(a, after=False), first_index(b, after=True)
                    for chunk in range(start, end, 65536):
                        _cancel(cancelled)
                        count = min(65536, end - chunk)
                        cells[offset + chunk : offset + chunk + count] = b"\x01" * count
                        remaining += count
                if progress:
                    progress(y + ny * z + 1, ny * nz)
        _cancel(cancelled)
        stock._occupied, stock._remaining_count = cells, remaining
        stock._initial_count = remaining
        return ImportedStock(self, stock, translation.tuple)


@dataclass(frozen=True)
class ImportedStock:
    solid: StockSolid
    stock: StockVolume
    translation_mm: Point

    @property
    def identity(self) -> dict[str, object]:
        return {
            "schema": "carvera-imported-stock-identity-v1",
            "source_path": self.solid.mesh.source_path,
            "source_sha256": self.solid.mesh.source_sha256,
            "source_units": self.solid.mesh.source_units,
            "frame": "stock-local mm",
            "qualification": "unqualified source geometry; physical registration unverified",
            "translation_mm": self.translation_mm,
            "rotation_deg": self.stock.rotation_deg,
            "tilt_deg": self.stock.tilt_deg,
            "pivot_mm": self.stock.pivot.tuple,
            "resolution_mm": self.stock.resolution_mm,
            "shape": self.stock.shape,
        }

    def clone(self, *, cancelled: Callable[[], bool] | None = None) -> ImportedStock:
        return ImportedStock(self.solid, self.stock.clone(cancelled=cancelled), self.translation_mm)


class SolidBudgetExceeded(ValueError):
    """A shared solid-operation budget failed; no partial report is admissible."""


@dataclass
class SolidBudget(_Budget):
    """Shared bounded admission and ray work across a complete machine review.

    Nodes count traversal plus cheap integer certificates; pairs count only
    inconclusive candidates needing full rational intersection. Legacy stock
    validation retains its original pair accounting and budgets.
    """

    max_queries: int = 100_000
    queries: int = 0

    def __post_init__(self) -> None:
        for name, maximum in (("nodes", 2_000_000), ("pairs", 250_000), ("rays", 8_000_000), ("queries", 100_000)):
            limit = getattr(self, "max_" + name)
            value = getattr(self, name)
            if type(limit) is not int or not 1 <= limit <= maximum:
                raise ValueError("Solid work budgets exceed the bounded contract")
            if type(value) is not int or not 0 <= value <= limit:
                raise ValueError("Solid work counters exceed the bounded contract")

    def consume(self, kind: str) -> None:
        _cancel(self.cancelled)
        value = getattr(self, kind) + 1
        if value > getattr(self, "max_" + kind):
            raise SolidBudgetExceeded("Solid review exhausted shared " + kind + " budget; no partial report")
        setattr(self, kind, value)


@dataclass(frozen=True, init=False)
class TriangleSolid:
    """Validated immutable triangle occupancy, with no file/source assertion.

    Exact input coordinates, closed manifold topology, proper intersections and
    alternating shell winding are required. No welding or mesh repair occurs.
    """

    mesh: _SurfaceInput
    material_volume_mm3: float
    shell_count: int
    representatives: tuple[tuple[int, Point], ...]
    _tree: _Node
    _triangles: tuple[_ExactTriangle, ...]

    def __init__(self) -> None:
        raise TypeError("Use TriangleSolid.validate for complete geometric admission")

    @classmethod
    def validate(cls, triangles: Sequence[Triangle], *, budget: SolidBudget | None = None) -> TriangleSolid:
        budget = budget or SolidBudget()
        if not 1 <= len(triangles) <= 200_000:
            raise ValueError("Solid mesh needs one to 200000 complete faces")
        detached = []
        for index, triangle in enumerate(triangles):
            if index % 64 == 0:
                _cancel(budget.cancelled)
            if len(triangle) != 3 or any(len(p) != 3 for p in triangle):
                raise ValueError("Solid mesh has incomplete triangles")
            if any(
                type(v) not in (int, float) or abs(v) > 1_000_000 or not math.isfinite(v) for p in triangle for v in p
            ):
                raise ValueError("Solid coordinates need finite values within one million mm")
            points = tuple((float(p[0]), float(p[1]), float(p[2])) for p in triangle)
            detached.append((points[0], points[1], points[2]))
        rows = tuple(detached)
        _topology(rows, budget.cancelled)
        lo = tuple(min(p[a] for row in rows for p in row) for a in range(3))
        hi = tuple(max(p[a] for row in rows for p in row) for a in range(3))
        mesh = _SurfaceInput(rows, (lo[0], lo[1], lo[2]), (hi[0], hi[1], hi[2]))
        volume, tree, exact, shells = _validate_geometry(mesh, budget)
        _cancel(budget.cancelled)
        result = object.__new__(cls)
        for name, value in (
            ("mesh", mesh),
            ("material_volume_mm3", volume),
            ("shell_count", len(shells)),
            ("representatives", tuple((shell[0], rows[shell[0]][0]) for shell in shells)),
            ("_tree", tree),
            ("_triangles", exact),
        ):
            object.__setattr__(result, name, value)
        return result

    def classify(
        self, point: Sequence[Fraction | float], *, budget: SolidBudget | None = None
    ) -> Literal["outside", "inside", "boundary"]:
        budget = budget or SolidBudget()
        budget.consume("queries")
        if len(point) != 3 or any(
            not isinstance(v, (int, float, Fraction))
            or isinstance(v, bool)
            or v < -4_000_000
            or v > 4_000_000
            or not math.isfinite(v)
            for v in point
        ):
            raise ValueError("Solid query needs three bounded finite coordinates")
        x, y, z = (Fraction(v) for v in point)
        if any(v < low or v > high for v, low, high in zip((x, y, z), self.mesh.minimum_mm, self.mesh.maximum_mm)):
            return "outside"
        crossings, boundary = _row(self._tree, self._triangles, y, z, budget)
        _cancel(budget.cancelled)
        if any(low <= x <= high for low, high in boundary):
            return "boundary"
        return (
            "inside" if any(low <= x <= high for low, high in _material_intervals(crossings, boundary)) else "outside"
        )
