"""Geometry-derived layered +Z flat-mill raster and complete stock comparison.

An exact clipped-triangle upper envelope over a continuous rectangular swept
footprint conservatively contains the circular cutter. This is an explicit
top-envelope strategy, not an arbitrary surface-normal finishing algorithm.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from fractions import Fraction as F
from math import ceil, isclose, isfinite, nextafter, prod
from types import MappingProxyType
from typing import Any, cast

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import CollisionContact
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, TriangleSolid
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.rotating_surface import box_candidate, triangle_contact
from carveracontroller.machine.stock_allowance import ApproachContact
from carveracontroller.machine.stock_target import TargetAnalysis, TargetFit
from carveracontroller.machine.stock_tool_reach import ReachContainment
from carveracontroller.machine.surface_motion import Point, QPoint, SurfaceMesh, Triangle, qpoint, sub

Rectangle = tuple[F, F, F, F]
Vertex = tuple[QPoint, QPoint]


@dataclass(frozen=True)
class HeightWitness:
    triangle: int
    point: QPoint
    barycentric: QPoint


@dataclass(frozen=True)
class FinishPatch:
    row: int
    column: int
    rectangle: Rectangle
    start_xy: tuple[float, float]
    end_xy: tuple[float, float]
    witness: HeightWitness | None
    tip_z_mm: float | None


@dataclass(frozen=True)
class GeneratedMove:
    patch: int
    layer: int
    kind: str
    start: Point
    end: Point
    cutting: bool


@dataclass(frozen=True)
class GeneratedContact:
    move: int
    contact: CollisionContact


@dataclass(frozen=True)
class GeneratedTargetContact:
    move: int
    contact: ApproachContact | ReachContainment


@dataclass(frozen=True)
class GeneratedStockState:
    before: TargetFit
    after: TargetFit
    final: Mapping[str, Any]
    removed_mm3: float
    newly_missing_mm3: float
    contacts: tuple[GeneratedContact, ...]


@dataclass(frozen=True)
class GeneratedFinish:
    analysis: TargetAnalysis
    tool: int
    stock_offset_mm: Point
    stepover_mm: float
    patch_length_mm: float
    allowance_mm: float
    stepdown_mm: float
    clearance_mm: float
    clearance_z_mm: float
    patches: tuple[FinishPatch, ...]
    moves: tuple[GeneratedMove, ...]
    states: Mapping[str, GeneratedStockState]
    target_contacts: tuple[GeneratedTargetContact, ...]
    declaration_gaps: tuple[str, ...]
    target_nodes: int
    target_faces: int
    cell_work: int
    solid_counts: tuple[int, int, int, int]
    numerical_margin_mm: float = 0.000001
    qualification: str = (
        "Geometry-derived fixed +Z flat-mill top-envelope raster in the rotated stock frame before its retained work offset. "
        "Adding stock_offset_mm gives declared machine-frame intended tip coordinates; effective controller compensation "
        "and physical registration remain separate. Exact triangle clipping over every "
        "continuous square-expanded horizontal patch bounds the circular cutter footprint; this can leave extra "
        "material at slopes, corners, vertical walls, cavities and overhangs. Explicit stepover, patch length, axial "
        "allowance and layer depth describe this strategy, not certified normal allowance or surface tolerance. "
        "Every patch retracts to above complete declared stock/target before transfer. Entries are cutting plunges, "
        "whose tool suitability, feed, spindle, chip load, forces and process parameters remain unqualified. "
        "All retained stock states are independently replayed; contacts are recorded before each move and stock "
        "removal/target differences classify cell centers, not whole cells. Noncutting contacts do not silently "
        "suppress simulation. Missing holder/assembly declarations remain unknown. No live start, controller "
        "compensation, machine/fixture/ATC clearance, manufactured geometry, execution or G-code is supplied."
    )


@dataclass
class HeightBudget:
    max_nodes: int = 2_000_000
    max_faces: int = 250_000
    nodes: int = 0
    faces: int = 0

    def __post_init__(self) -> None:
        for value, used, maximum in ((self.max_nodes, self.nodes, 2_000_000), (self.max_faces, self.faces, 250_000)):
            if type(value) is not int or not 1 <= value <= maximum or type(used) is not int or not 0 <= used <= value:
                raise ValueError("Generated finish exceeds complete target work bounds")


def _clip(polygon: list[Vertex], axis: int, bound: F, lower: bool) -> list[Vertex]:
    result: list[Vertex] = []
    if not polygon:
        return result
    prior = polygon[-1]
    prior_in = prior[0][axis] >= bound if lower else prior[0][axis] <= bound
    for current in polygon:
        inside = current[0][axis] >= bound if lower else current[0][axis] <= bound
        if inside != prior_in:
            ratio = (bound - prior[0][axis]) / (current[0][axis] - prior[0][axis])
            point = tuple(a + ratio * (b - a) for a, b in zip(prior[0], current[0]))
            bary = tuple(a + ratio * (b - a) for a, b in zip(prior[1], current[1]))
            result.append((cast(QPoint, point), cast(QPoint, bary)))
        if inside:
            result.append(current)
        prior, prior_in = current, inside
    return result


def upper_surface(
    mesh: SurfaceMesh,
    rectangle: Rectangle,
    budget: HeightBudget,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> HeightWitness | None:
    """Exact maximum Z on every original triangle intersecting the XY rectangle.

    Vertical projected faces remain in the polygon; no ray sampling or convex hull
    substitution is involved. Shared hierarchy/face work refuses the whole caller.
    """
    if len(rectangle) != 4 or any(not isinstance(v, F) for v in rectangle):
        raise ValueError("Surface footprint needs four exact rational bounds")
    left, bottom, right, top = rectangle
    if left > right or bottom > top:
        raise ValueError("Surface footprint bounds must be ordered")
    found = None
    pending = [mesh.root]
    while pending:
        if cancelled():
            raise InterruptedError("Generated finish surface review cancelled; no partial plan")
        node = pending.pop()
        budget.nodes += 1
        if budget.nodes > budget.max_nodes:
            raise ValueError("Generated finish exhausted complete target node budget")
        low, high = node.bounds
        if F(high[0]) < left or F(low[0]) > right or F(high[1]) < bottom or F(low[1]) > top:
            continue
        if found is not None and F(high[2]) < found.point[2]:
            continue
        pending.extend(node.children)
        for index in node.ids:
            budget.faces += 1
            if budget.faces > budget.max_faces:
                raise ValueError("Generated finish exhausted complete target face budget")
            polygon = [
                (qpoint(p), cast(QPoint, tuple(F(int(a == i)) for a in range(3))))
                for i, p in enumerate(mesh.triangles[index])
            ]
            for axis, bound, lower in ((0, left, True), (0, right, False), (1, bottom, True), (1, top, False)):
                polygon = _clip(polygon, axis, bound, lower)
            for point, bary in polygon:
                if (
                    found is None
                    or point[2] > found.point[2]
                    or (
                        point[2] == found.point[2]
                        and (index, point, bary) < (found.triangle, found.point, found.barycentric)
                    )
                ):
                    found = HeightWitness(index, point, bary)
    return found


def _state_stock(
    analysis: TargetAnalysis, label: str, grid: StockVolume, cancelled: Callable[[], bool]
) -> tuple[StockVolume, int]:
    fit = analysis.fits[label]
    extra, missing = (StockVolume.from_snapshot(s, cancelled=cancelled) for s in (fit.excess, fit.missing))
    if any(
        (v.shape, v.grid_bounds, v.orientation, v.pivot) != (grid.shape, grid.grid_bounds, grid.orientation, grid.pivot)
        for v in (extra, missing)
    ):
        raise ValueError("Generated finish masks differ from retained target grid")
    stock = grid.clone(cancelled=cancelled)
    count = lost_count = 0
    for index, (wanted, excess, lost) in enumerate(zip(grid._occupied, extra._occupied, missing._occupied)):
        if index % 128 == 0 and cancelled():
            raise InterruptedError("Generated finish mask reconstruction cancelled")
        if (excess and (wanted or lost)) or (lost and not wanted):
            raise ValueError("Generated finish masks overlap or disagree with target")
        has = excess or (wanted and not lost)
        stock._occupied[index] = int(has)
        count += has
        lost_count += lost
    stock._remaining_count = stock._initial_count = count
    if any(
        not isclose(actual, saved, rel_tol=1e-12, abs_tol=1e-8)
        for actual, saved in (
            (count * grid.cell_volume_mm3, fit.material_mm3),
            (extra.remaining_volume_mm3, fit.excess_mm3),
            (missing.remaining_volume_mm3, fit.missing_mm3),
            (grid.remaining_volume_mm3 - missing.remaining_volume_mm3, fit.retained_target_mm3),
        )
    ):
        raise ValueError("Generated finish volumes differ from complete masks")
    return stock, lost_count


def _fit(stock: StockVolume, grid: StockVolume, cancelled: Callable[[], bool]) -> tuple[TargetFit, int]:
    extra, missing = grid.clone(cancelled=cancelled), grid.clone(cancelled=cancelled)
    retained = excess_count = missing_count = 0
    for index, (want, has) in enumerate(zip(grid._occupied, stock._occupied)):
        if index % 128 == 0 and cancelled():
            raise InterruptedError("Generated finish target comparison cancelled")
        excess, lost = bool(has and not want), bool(want and not has)
        extra._occupied[index], missing._occupied[index] = int(excess), int(lost)
        excess_count += excess
        missing_count += lost
        retained += want and has
    for volume, count in ((extra, excess_count), (missing, missing_count)):
        volume._remaining_count = volume._initial_count = count
    return TargetFit(
        stock.remaining_volume_mm3,
        retained * grid.cell_volume_mm3,
        extra.remaining_volume_mm3,
        missing.remaining_volume_mm3,
        MappingProxyType(extra.snapshot(cancelled=cancelled)),
        MappingProxyType(missing.snapshot(cancelled=cancelled)),
    ), missing_count


def generate_stock_finish(
    analysis: TargetAnalysis,
    tool: int,
    *,
    stepover_mm: float = 0.5,
    patch_length_mm: float = 1,
    allowance_mm: float = 0.05,
    stepdown_mm: float = 0.25,
    clearance_mm: float = 1,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[str, int, int], None] = lambda phase, done, total: None,
    max_patches: int = 5_000,
    max_moves: int = 20_000,
    max_cell_work: int = 50_000_000,
    max_nodes: int = 2_000_000,
    max_faces: int = 250_000,
    max_contacts: int = 100_000,
) -> GeneratedFinish:
    evolution = cast(StockEvolution, analysis.target.bindings[1])
    if (
        analysis.target.stock not in evolution.inputs.stocks
        or analysis.target.initial != evolution.inputs.stocks[analysis.target.stock][1]
    ):
        raise ValueError("Generated finish stock declaration differs from retained review")
    stock_offset = tuple(float(v) for v in evolution.inputs.stocks[analysis.target.stock][0])
    qpoint(stock_offset)
    if type(tool) is not int or tool not in evolution.inputs.tools:
        raise ValueError("Choose a retained flat-mill tool")
    geometry = evolution.inputs.tools[tool]
    if geometry.shape != "flat":
        raise ValueError("Top-envelope raster currently requires a declared flat mill")
    for value, allowed_low, allowed_high in (
        (stepover_mm, 0.001, geometry.diameter_mm),
        (patch_length_mm, 0.001, 1000),
        (allowance_mm, 0, 100),
        (stepdown_mm, 0.001, geometry.flute_length_mm),
        (clearance_mm, 0.001, 100),
    ):
        if type(value) not in (int, float) or not isfinite(value) or not allowed_low <= value <= allowed_high:
            raise ValueError(
                "Use finite bounded stepover, patch length, axial allowance, flute-contained stepdown and clearance"
            )
    for value, maximum in (
        (max_patches, 5000),
        (max_moves, 20000),
        (max_cell_work, 50_000_000),
        (max_contacts, 100_000),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("Generated finish exceeds complete shared work/storage bounds")
    budget = HeightBudget(max_nodes, max_faces)
    grid = StockVolume.from_snapshot(analysis.target.target, cancelled=cancelled)
    size = prod(grid.shape)
    if not analysis.fits or size * len(analysis.fits) * 2 > max_cell_work:
        raise ValueError("Generated finish exhausted complete mask cell-work budget")
    translation = Vec3(*analysis.target.translation_mm)
    placed: list[Triangle] = []
    progress("Prepare complete placed target", 0, len(analysis.target.solid.mesh.triangles_mm))
    for index, triangle in enumerate(analysis.target.solid.mesh.triangles_mm):
        if index % 64 == 0 and cancelled():
            raise InterruptedError("Generated finish target placement cancelled")
        points = [grid.program_point(Vec3(*p) + translation).tuple for p in triangle]
        placed.append((points[0], points[1], points[2]))
    mesh = SurfaceMesh.create(placed, cancelled=cancelled, index_method="surface-area-v2")
    low, high = mesh.root.bounds
    nx = max(1, ceil((high[0] - low[0]) / patch_length_mm))
    ny = max(1, ceil((high[1] - low[1]) / stepover_mm))
    total = nx * (ny + 1)
    if total > max_patches:
        raise ValueError("Generated finish exhausted complete patch budget; no sampled path")
    radius = F(geometry.diameter_mm) / 2
    top_stock = grid.bounds.maximum.z
    clearance = nextafter(max(top_stock, high[2] + allowance_mm + 0.000001) + clearance_mm, float("inf"))
    patches, moves = [], []
    position = None
    for row in range(ny + 1):
        y = low[1] + (high[1] - low[1]) * row / ny
        columns = range(nx) if row % 2 == 0 else range(nx - 1, -1, -1)
        for column in columns:
            if cancelled():
                raise InterruptedError("Generated finish path cancelled; no partial plan")
            progress("Generate continuous target-envelope patches", len(patches), total)
            a = low[0] + (high[0] - low[0]) * column / nx
            b = low[0] + (high[0] - low[0]) * (column + 1) / nx
            rectangle = (F(a) - radius, F(y) - radius, F(b) + radius, F(y) + radius)
            witness = upper_surface(mesh, rectangle, budget, cancelled=cancelled)
            start, end = ((a, y), (b, y)) if row % 2 == 0 else ((b, y), (a, y))
            z = nextafter(float(witness.point[2] + F(allowance_mm) + F(0.000001)), float("inf")) if witness else None
            patch = len(patches)
            patches.append(FinishPatch(row, column, rectangle, start, end, witness, z))
            if z is None:
                continue
            layers = max(1, ceil(max(0, top_stock - z) / stepdown_mm))
            if len(moves) + layers * 4 > max_moves:
                raise ValueError("Generated finish exhausted complete move budget; no truncated path")
            for layer in range(1, layers + 1):
                level = max(z, top_stock - layer * stepdown_mm)
                at = (start[0], start[1], clearance)
                down, across, up = (start[0], start[1], level), (end[0], end[1], level), (end[0], end[1], clearance)
                moves.extend(
                    (
                        GeneratedMove(patch, layer, "Transfer above stock", position or at, at, False),
                        GeneratedMove(patch, layer, "Cutting plunge", at, down, True),
                        GeneratedMove(patch, layer, "Raster cut", down, across, True),
                        GeneratedMove(patch, layer, "Retract above stock", across, up, False),
                    )
                )
                position = up
    sections = len(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), geometry).sections())
    cell_work = size * len(analysis.fits) * (2 + len(moves) * (sections + 1))
    if cell_work > max_cell_work:
        raise ValueError("Generated finish exhausted complete replay cell-work budget; no partial simulation")
    target_contacts: list[GeneratedTargetContact] = []
    solid_budget = SolidBudget(cancelled=cancelled)
    solid = TriangleSolid.validate(placed, budget=solid_budget)
    for index, move in enumerate(moves):
        progress("Review complete target noncutting bodies", index, len(moves))
        shift, delta = qpoint(move.start), sub(qpoint(move.end), qpoint(move.start))
        for section in SweptTool(Vec3(*move.start), Vec3(*move.end), geometry).sections():
            if section.component == "cutter":
                continue
            before = len(target_contacts)
            pending = [mesh.root]
            while pending:
                if cancelled():
                    raise InterruptedError("Generated finish noncutting review cancelled")
                node = pending.pop()
                budget.nodes += 1
                if budget.nodes > budget.max_nodes:
                    raise ValueError("Generated finish exhausted complete target node budget")
                if not box_candidate(section, node.bounds, shift, delta, 0.000001):
                    continue
                pending.extend(node.children)
                for face in node.ids:
                    budget.faces += 1
                    if budget.faces > budget.max_faces:
                        raise ValueError("Generated finish exhausted complete target face budget")
                    hit = triangle_contact(
                        section,
                        mesh.triangles[face],
                        move.start,
                        (Vec3(*move.end) - Vec3(*move.start)).tuple,
                        position_error_mm=0.000001,
                        cancelled=cancelled,
                    )
                    if hit is not None:
                        target_contacts.append(
                            GeneratedTargetContact(index, ApproachContact(section.component, face, hit))
                        )
                        if len(target_contacts) > max_contacts:
                            raise ValueError("Generated finish exhausted complete contact budget")
            if len(target_contacts) == before:
                point = (move.start[0], move.start[1], move.start[2] + (section.low_mm + section.high_mm) / 2)
                classification = solid.classify(point, budget=solid_budget)
                if classification != "outside":
                    target_contacts.append(
                        GeneratedTargetContact(index, ReachContainment(section.component, point, classification))
                    )
                    if len(target_contacts) > max_contacts:
                        raise ValueError("Generated finish exhausted complete contact budget")
    states = {}
    contacts_count = len(target_contacts)
    for label, fit in analysis.fits.items():
        stock, previously_missing = _state_stock(analysis, label, grid, cancelled)
        contacts = []
        for index, move in enumerate(moves):
            if cancelled():
                raise InterruptedError("Generated finish stock replay cancelled; previous result retained")
            progress(f"Replay {label}", index, len(moves))
            sweep = SweptTool(Vec3(*move.start), Vec3(*move.end), geometry)
            found = stock.collision_contacts(sweep, cutting=move.cutting, cancelled=cancelled)
            contacts.extend(GeneratedContact(index, c) for c in found)
            contacts_count += len(found)
            if contacts_count > max_contacts:
                raise ValueError("Generated finish exhausted complete contact budget")
            if move.cutting:
                stock.subtract(sweep, cancelled=cancelled)
        after, now_missing = _fit(stock, grid, cancelled)
        if now_missing > previously_missing:
            raise ValueError("Generated finish removed retained target centers; entire plan refused")
        states[label] = GeneratedStockState(
            fit,
            after,
            MappingProxyType(stock.snapshot(cancelled=cancelled)),
            fit.material_mm3 - after.material_mm3,
            after.missing_mm3 - fit.missing_mm3,
            tuple(contacts),
        )
    if cancelled():
        raise InterruptedError("Generated finish cancelled before delivery; no partial plan")
    progress("Complete generated finishing comparison", len(moves) * len(states), len(moves) * len(states))
    return GeneratedFinish(
        analysis,
        tool,
        cast(Point, stock_offset),
        stepover_mm,
        patch_length_mm,
        allowance_mm,
        stepdown_mm,
        clearance_mm,
        clearance,
        tuple(patches),
        tuple(moves),
        MappingProxyType(states),
        tuple(target_contacts),
        geometry.clearance_notes
        + (
            ()
            if any(s.component == "holder" for s in SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), geometry).sections())
            else ("No holder geometry declared",)
        ),
        budget.nodes,
        budget.faces,
        cell_work,
        (solid_budget.nodes, solid_budget.pairs, solid_budget.rays, solid_budget.queries),
    )
