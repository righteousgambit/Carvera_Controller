"""Exact nearest point on complete triangles, using conservative hierarchy bounds.

Interior barycentric stationary points and all closed edges exhaust a triangle's
convex quadratic minimum. Distances and pruning use exact rational input values;
only display lengths take a square root. No face or point sampling is used.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction as F
from heapq import heappop, heappush

from carveracontroller.machine.surface_motion import (
    Box,
    Point,
    QPoint,
    SurfaceMesh,
    SurfaceNode,
    Triangle,
    dot,
    qpoint,
    sub,
)


@dataclass
class DistanceBudget:
    max_nodes: int = 2_000_000
    max_triangles: int = 250_000
    cancelled: Callable[[], bool] = lambda: False
    nodes: int = 0
    triangles: int = 0

    def __post_init__(self) -> None:
        for name, maximum in (("nodes", 2_000_000), ("triangles", 250_000)):
            if type(getattr(self, "max_" + name)) is not int or not 1 <= getattr(self, "max_" + name) <= maximum:
                raise ValueError("Nearest-surface work limit exceeds bounded contract")
            if type(getattr(self, name)) is not int or not 0 <= getattr(self, name) <= getattr(self, "max_" + name):
                raise ValueError("Nearest-surface counters must be within shared work limit")

    def consume(self, name: str) -> None:
        if self.cancelled():
            raise InterruptedError("Nearest-surface query cancelled; previous result retained")
        value = getattr(self, name) + 1
        if value > getattr(self, "max_" + name):
            raise ValueError("Nearest-surface query exhausted shared " + name + " budget; no partial witness")
        setattr(self, name, value)


@dataclass(frozen=True)
class NearestSurfacePoint:
    triangle: int
    point: QPoint
    barycentric: QPoint
    distance_squared: F
    feature: str


def closest_triangle(point: QPoint, triangle: Triangle) -> tuple[F, QPoint, QPoint]:
    a, b, c = (qpoint(p) for p in triangle)
    candidates: list[tuple[F, QPoint, QPoint]] = []
    for start, end, at, to in ((a, b, 0, 1), (b, c, 1, 2), (c, a, 2, 0)):
        edge, relative = sub(end, start), sub(point, start)
        denominator = dot(edge, edge)
        t = min(F(1), max(F(0), dot(relative, edge) / denominator)) if denominator else F(0)
        p: QPoint = (start[0] + t * edge[0], start[1] + t * edge[1], start[2] + t * edge[2])
        weights = [F(0), F(0), F(0)]
        weights[at], weights[to] = 1 - t, t
        candidates.append((dot(sub(point, p), sub(point, p)), p, (weights[0], weights[1], weights[2])))
    u, v, relative = sub(b, a), sub(c, a), sub(point, a)
    uu, uv, vv = dot(u, u), dot(u, v), dot(v, v)
    determinant = uu * vv - uv * uv
    if determinant:
        s = (dot(relative, u) * vv - dot(relative, v) * uv) / determinant
        t = (dot(relative, v) * uu - dot(relative, u) * uv) / determinant
        if s >= 0 and t >= 0 and s + t <= 1:
            p = (a[0] + s * u[0] + t * v[0], a[1] + s * u[1] + t * v[1], a[2] + s * u[2] + t * v[2])
            candidates.append((dot(sub(point, p), sub(point, p)), p, (1 - s - t, s, t)))
    return min(candidates, key=lambda row: row[0])


def _box_distance(point: QPoint, box: Box) -> F:
    return sum((max(F(low) - p, F(0), p - F(high)) ** 2 for p, low, high in zip(point, box[0], box[1])), F(0))


def nearest_surface(mesh: SurfaceMesh, point: Point, *, budget: DistanceBudget | None = None) -> NearestSurfacePoint:
    budget = budget or DistanceBudget()
    p = qpoint(point)
    queue: list[tuple[F, int, SurfaceNode]] = [(_box_distance(p, mesh.root.bounds), 0, mesh.root)]
    serial = 0
    best: NearestSurfacePoint | None = None
    while queue:
        lower, _, node = heappop(queue)
        budget.consume("nodes")
        if best is not None and lower > best.distance_squared:
            continue
        for index in node.ids:
            budget.consume("triangles")
            distance, position, weights = closest_triangle(p, mesh.triangles[index])
            feature = {0: "face", 1: "edge", 2: "vertex"}[sum(w == 0 for w in weights)]
            hit = NearestSurfacePoint(index, position, weights, distance, feature)
            if best is None or (distance, index) < (best.distance_squared, best.triangle):
                best = hit
        for child in node.children:
            lower = _box_distance(p, child.bounds)
            if best is None or lower <= best.distance_squared:
                serial += 1
                heappush(queue, (lower, serial, child))
    if budget.cancelled():
        raise InterruptedError("Nearest-surface query cancelled; previous result retained")
    assert best is not None
    return best
