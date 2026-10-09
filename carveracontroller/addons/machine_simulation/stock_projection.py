"""Worker-prepared source-mesh projections for stock placement drawings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Literal

from .model import MachineSetup
from .stock_model import StockModel

DrawingFrame = Literal["stock", "program", "machine", "rotation"]
Point = tuple[float, float, float]


@dataclass(frozen=True)
class Projection:
    # Default Kivy 2D mesh format: XY plus unused texture coordinates. Each
    # adjacent pair is a source edge; batches retain unsigned-short indices.
    batches: tuple[tuple[tuple[float, ...], tuple[int, ...]], ...]
    minimum: tuple[float, float]
    maximum: tuple[float, float]


@dataclass(frozen=True)
class StockProjection:
    views: tuple[Projection, Projection]
    corner: Point
    pivot: Point


def project_stock(
    source: StockModel,
    record: Mapping[str, object],
    frame: DrawingFrame,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> StockProjection:
    """Project all actual mesh edges, including hidden edges; never a silhouette.

    No files or UI objects are accessed. Stock/program frames intentionally omit
    WCS; the stock frame omits placement, and program-corner edits omit rotation.
    Rotation and machine drawings include rotation in both XY and XZ.
    """

    def check() -> None:
        if cancelled is not None and cancelled():
            raise InterruptedError("Stock drawing preparation cancelled")

    def triple(name: str) -> Point:
        value = record[name]
        if not isinstance(value, (tuple, list)) or len(value) != 3:
            raise ValueError("Stock drawing requires three coordinates")
        return float(value[0]), float(value[1]), float(value[2])

    check()
    if frame not in ("stock", "program", "machine", "rotation"):
        raise ValueError("Unsupported stock drawing frame")
    origin = triple("stock_origin_mm") if frame in ("program", "machine") else (0.0, 0.0, 0.0)
    offset = triple("work_offset_mm") if frame == "machine" else (0.0, 0.0, 0.0)
    angle = record.get("stock_rotation_deg", 0)
    if not isinstance(angle, (int, float)) or isinstance(angle, bool):
        raise ValueError("Stock drawing requires a numeric rotation")
    rotation = float(angle) if frame in ("machine", "rotation") else 0.0
    setup = MachineSetup(offset, source.size_mm, origin, False, rotation, source)
    edges: set[tuple[Point, Point]] = set()
    batches: list[list[tuple[float, ...]]] = [[], []]
    buffers: list[list[float]] = [[], []]
    lower = [float("inf")] * 3
    upper = [float("-inf")] * 3

    def place(point: Point) -> Point:
        local = tuple(point[i] - source.minimum_mm[i] + origin[i] for i in range(3))
        return setup.machine_point(setup.stock_point(local))

    for index, triangle in enumerate(source.solid.mesh.triangles_mm):
        if index % 128 == 0:
            check()
        for a, b in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            edge = (a, b) if a <= b else (b, a)
            if edge in edges:
                continue
            edges.add(edge)
            for point in (place(a), place(b)):
                for axis in range(3):
                    lower[axis] = min(lower[axis], point[axis])
                    upper[axis] = max(upper[axis], point[axis])
                for view, vertical in enumerate((1, 2)):
                    buffers[view].extend((point[0], point[vertical], 0, 0))
            if len(buffers[0]) // 4 >= 65534:
                for view in (0, 1):
                    batches[view].append(tuple(buffers[view]))
                    buffers[view] = []
    check()
    for view in (0, 1):
        if buffers[view]:
            batches[view].append(tuple(buffers[view]))
    views = tuple(
        Projection(
            tuple((vertices, tuple(range(len(vertices) // 4))) for vertices in batches[view]),
            (lower[0], lower[vertical]),
            (upper[0], upper[vertical]),
        )
        for view, vertical in enumerate((1, 2))
    )
    corner = setup.machine_point(origin)
    pivot = setup.machine_point(tuple(origin[i] + source.size_mm[i] / 2 for i in range(3)))
    return StockProjection((views[0], views[1]), corner, pivot)
