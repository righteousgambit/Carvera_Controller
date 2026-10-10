"""Complete retained-grid extrema against all admitted part-target triangles."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from math import prod, sqrt
from types import MappingProxyType

from carveracontroller.addons.manufacturing_simulation import StockVolume, Vec3
from carveracontroller.machine.stock_target import TargetAnalysis
from carveracontroller.machine.surface_distance import DistanceBudget, NearestSurfacePoint, nearest_surface
from carveracontroller.machine.surface_motion import SurfaceMesh


@dataclass(frozen=True)
class AllowancePeak:
    cell: tuple[int, int, int]
    center_grid_mm: tuple[float, float, float]
    center_program_mm: tuple[float, float, float]
    nearest: NearestSurfacePoint
    signed_center_distance_mm: float
    cell_distance_interval_mm: tuple[float, float]


@dataclass(frozen=True)
class StateAllowance:
    excess_centers: int
    missing_centers: int
    excess_peak: AllowancePeak | None
    missing_peak: AllowancePeak | None


@dataclass(frozen=True)
class AllowanceSummary:
    analysis: TargetAnalysis
    states: Mapping[str, StateAllowance]
    cell_work: int
    center_queries: int
    distance_nodes: int
    distance_faces: int
    half_diagonal_mm: float
    qualification: str = (
        "Complete excess/missing center masks for every retained state; exact nearest distance over all target triangles. "
        "Largest positive excess distance and deepest negative missing-target distance retain original cell/face witnesses. "
        "Cell half diagonal bounds signed distance variation within a cell; these are declared grid estimates, not measured "
        "allowance, actual whole-cell removal, tool reach, finishing paths, machine/fixture/ATC or physical qualification."
    )


class _SummaryDistanceBudget(DistanceBudget):
    """Shared whole-grid query cap; individual inspector's smaller cap is unchanged."""

    def __post_init__(self) -> None:
        for name in ("nodes", "triangles"):
            maximum = getattr(self, "max_" + name)
            used = getattr(self, name)
            if type(maximum) is not int or not 1 <= maximum <= 50_000_000:
                raise ValueError("Summary distance work exceeds complete shared 50M bound")
            if type(used) is not int or not 0 <= used <= maximum:
                raise ValueError("Summary counters must be within their complete work bounds")


def summarize_target_allowance(
    analysis: TargetAnalysis,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int, int], None] = lambda cells, total, queries: None,
    max_cell_work: int = 8_000_000,
    max_nodes: int = 50_000_000,
    max_faces: int = 50_000_000,
) -> AllowanceSummary:
    if type(max_cell_work) is not int or not 1 <= max_cell_work <= 8_000_000:
        raise ValueError("Summary cell-work exceeds complete shared 8M bound")
    budget = _SummaryDistanceBudget(max_nodes=max_nodes, max_triangles=max_faces, cancelled=cancelled)
    target = analysis.target
    grid = StockVolume.from_snapshot(target.target, cancelled=cancelled)
    cells = prod(grid.shape)
    total = cells * len(analysis.fits)
    if not analysis.fits or total > max_cell_work:
        raise ValueError("Complete all-state allowance exceeds shared cell-work budget; no partial summary")
    labels = tuple(analysis.fits)
    masks = tuple(
        (
            StockVolume.from_snapshot(analysis.fits[label].excess, cancelled=cancelled),
            StockVolume.from_snapshot(analysis.fits[label].missing, cancelled=cancelled),
        )
        for label in labels
    )
    for excess, missing in masks:
        if any(
            v.shape != grid.shape
            or v.grid_bounds != grid.grid_bounds
            or v.orientation != grid.orientation
            or v.pivot != grid.pivot
            for v in (excess, missing)
        ):
            raise ValueError("Allowance masks differ from the complete retained target grid")
    counts = [[0, 0] for _ in labels]
    peaks: list[list[AllowancePeak | None]] = [[None, None] for _ in labels]
    half = sqrt(sum(v * v for v in grid.cell_size.tuple)) / 2
    mesh: SurfaceMesh | None = None
    translation = Vec3(*target.translation_mm)
    queries = 0
    nx, ny, _ = grid.shape
    for index in range(cells):
        if index % 64 == 0:
            if cancelled():
                raise InterruptedError("Allowance summary cancelled; no partial result")
            progress(index * len(labels), total, queries)
        categories = []
        for row, (excess, missing) in enumerate(masks):
            extra, lost = excess._occupied[index], missing._occupied[index]
            if extra and lost:
                raise ValueError("Excess and missing masks overlap; no partial summary")
            if extra or lost:
                category = 0 if extra else 1
                if bool(grid._occupied[index]) != bool(lost):
                    raise ValueError("Allowance mask disagrees with retained target membership")
                counts[row][category] += 1
                categories.append((row, category))
        if not categories:
            continue
        if mesh is None:
            mesh = SurfaceMesh.create(
                target.solid.mesh.triangles_mm, cancelled=cancelled, index_method="surface-area-v2"
            )
        cell = index % nx, (index // nx) % ny, index // (nx * ny)
        center = grid.grid_center(*cell)
        hit = nearest_surface(mesh, (center - translation).tuple, budget=budget)
        queries += 1
        sign = -1 if grid._occupied[index] else 1
        signed = sqrt(float(hit.distance_squared)) * sign
        peak = AllowancePeak(cell, center.tuple, grid.center(*cell).tuple, hit, signed, (signed - half, signed + half))
        for row, category in categories:
            prior = peaks[row][category]
            # Row-major traversal and strict greater-than retain the earliest
            # cell on equal squared-distance ties. No display-rounded ordering.
            if prior is None or hit.distance_squared > prior.nearest.distance_squared:
                peaks[row][category] = peak
    if cancelled():
        raise InterruptedError("Allowance summary cancelled; no partial result")
    progress(total, total, queries)
    states = {
        label: StateAllowance(counts[row][0], counts[row][1], peaks[row][0], peaks[row][1])
        for row, label in enumerate(labels)
    }
    return AllowanceSummary(analysis, MappingProxyType(states), total, queries, budget.nodes, budget.triangles, half)
