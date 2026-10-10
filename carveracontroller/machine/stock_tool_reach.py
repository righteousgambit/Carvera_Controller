"""Complete retained excess-cell / candidate-tool +Z access comparisons.

Target chords use every retained triangle and closed-solid containment. Stock
uses the selected state's complete grid without removing material. This is
declared fixed-axis access evidence, not a generated finishing path.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from math import isclose, isfinite, prod
from types import MappingProxyType
from typing import cast

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import CollisionContact, ToolGeometry
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, TriangleSolid
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.rotating_shape import cutting_sections
from carveracontroller.machine.rotating_surface import box_candidate, triangle_contact
from carveracontroller.machine.stock_allowance import ApproachContact
from carveracontroller.machine.stock_target import TargetAnalysis
from carveracontroller.machine.surface_motion import SurfaceMesh, Triangle, qpoint, sub

Cell = tuple[int, int, int]


@dataclass(frozen=True)
class ReachContainment:
    component: str
    point_program_mm: tuple[float, float, float]
    classification: str


@dataclass(frozen=True)
class ReachQuery:
    cell: Cell
    tool: int
    start_program_mm: tuple[float, float, float]
    end_program_mm: tuple[float, float, float]
    target_contacts: tuple[ApproachContact, ...]
    containment: tuple[ReachContainment, ...]
    declaration_gaps: tuple[str, ...]
    model_notes: tuple[str, ...]


@dataclass(frozen=True)
class ReachOutcome:
    query: ReachQuery
    stock_contacts: tuple[CollisionContact, ...]
    limiting_components: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ToolReachStudy:
    analysis: TargetAnalysis
    tools: tuple[int, ...]
    clearance_mm: float
    states: Mapping[str, Mapping[int, tuple[ReachOutcome, ...]]]
    unique_queries: int
    logical_outcomes: int
    cell_work: int
    target_nodes: int
    target_faces: int
    solid_counts: tuple[int, int, int, int]
    contact_records: int
    qualification: str = (
        "Every excess-stock center in every retained state is reviewed for every selected retained tool. "
        "Fixed program +Z insertion begins above declared stock and target, with complete transformed target-face "
        "chord contacts and closed-solid containment; remaining-stock noncutting contacts are conservative grid estimates. "
        "Contact witnesses are feasible poses, not certified first-entry times. No-contact outcomes apply only to declared "
        "target/stock/tool coverage; missing holder/assembly declarations remain explicit. No material is removed. "
        "Machine/fixture/ATC travel, changed tool-length joint poses, compensation, cutting forces, finite flute motion, "
        "physical registration and generated finishing/approach paths remain separate checks."
    )


def review_tool_reach(
    analysis: TargetAnalysis,
    tools: Sequence[int] | None = None,
    *,
    clearance_mm: float = 1,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[str, int, int], None] = lambda phase, done, total: None,
    max_cell_work: int = 50_000_000,
    max_outcomes: int = 50_000,
    max_nodes: int = 2_000_000,
    max_faces: int = 250_000,
    max_contacts: int = 100_000,
    solid_budget: SolidBudget | None = None,
) -> ToolReachStudy:
    evolution = cast(StockEvolution, analysis.target.bindings[1])
    selected = tuple(sorted(evolution.inputs.tools)) if tools is None else tuple(tools)
    if (
        not selected
        or len(selected) > 64
        or any(type(n) is not int or n not in evolution.inputs.tools for n in selected)
        or len(set(selected)) != len(selected)
        or type(clearance_mm) not in (int, float)
        or not isfinite(clearance_mm)
        or not 0.001 <= clearance_mm <= 100
    ):
        raise ValueError("Choose unique retained tools and finite0.001..100 mm insertion clearance")
    for value, maximum in (
        (max_cell_work, 50_000_000),
        (max_outcomes, 50_000),
        (max_nodes, 2_000_000),
        (max_faces, 250_000),
        (max_contacts, 100_000),
    ):
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError("Tool access exceeds complete shared work/storage bounds")
    budget = solid_budget or SolidBudget(cancelled=cancelled)
    prior_cancel = budget.cancelled
    budget.cancelled = lambda: cancelled() or bool(prior_cancel and prior_cancel())
    try:
        return _review(
            analysis,
            selected,
            clearance_mm,
            cancelled,
            progress,
            max_cell_work,
            max_outcomes,
            max_nodes,
            max_faces,
            max_contacts,
            budget,
        )
    finally:
        budget.cancelled = prior_cancel


def _review(
    analysis: TargetAnalysis,
    tools: tuple[int, ...],
    clearance: float,
    cancelled: Callable[[], bool],
    progress: Callable[[str, int, int], None],
    max_cell_work: int,
    max_outcomes: int,
    max_nodes: int,
    max_faces: int,
    max_contacts: int,
    budget: SolidBudget,
) -> ToolReachStudy:
    target = analysis.target
    evolution = cast(StockEvolution, target.bindings[1])
    grid = StockVolume.from_snapshot(target.target, cancelled=cancelled)
    size = prod(grid.shape)
    cell_work = size * len(analysis.fits)
    if not analysis.fits or cell_work > max_cell_work:
        raise ValueError("Tool access exhausted complete mask cell-work budget")
    stocks, selected_cells = {}, {}
    total = 0
    progress("Reconstruct complete retained masks", 0, cell_work)
    for row, (label, fit) in enumerate(analysis.fits.items()):
        extra, missing = (StockVolume.from_snapshot(s, cancelled=cancelled) for s in (fit.excess, fit.missing))
        if any(
            v.shape != grid.shape
            or v.grid_bounds != grid.grid_bounds
            or v.orientation != grid.orientation
            or v.pivot != grid.pivot
            for v in (extra, missing)
        ):
            raise ValueError("Tool access masks differ from retained target grid")
        stock = grid.clone(cancelled=cancelled)
        indices = []
        count = 0
        for index, (wanted, excess, lost) in enumerate(zip(grid._occupied, extra._occupied, missing._occupied)):
            if index % 128 == 0:
                if cancelled():
                    raise InterruptedError("Tool access cancelled; no partial study")
                progress("Reconstruct complete retained masks", row * size + index, size * len(analysis.fits))
            if (excess and (wanted or lost)) or (lost and not wanted):
                raise ValueError("Tool access masks overlap or disagree with target membership")
            has = excess or (wanted and not lost)
            stock._occupied[index] = int(has)
            count += has
            if excess:
                indices.append(index)
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
            raise ValueError("Tool access material volumes differ from complete masks")
        stocks[label], selected_cells[label] = stock, tuple(indices)
        total += len(indices) * len(tools)
    if total > max_outcomes:
        raise ValueError("Tool access exhausted complete outcome budget; no sampled study")
    sections = {
        n: cutting_sections(evolution.inputs.tools[n])
        + tuple(
            s
            for s in SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), evolution.inputs.tools[n]).sections()
            if s.component != "cutter"
        )
        for n in tools
    }
    cell_work += sum(
        size * len(selected_cells[label]) * sum(sum(s.component != "cutter" for s in sections[n]) for n in tools)
        for label in selected_cells
    )
    if cell_work > max_cell_work:
        raise ValueError("Tool access exhausted complete stock-query cell-work budget")
    mesh = None
    solid = None
    if total:
        progress("Prepare complete placed target", 0, len(target.solid.mesh.triangles_mm))
        translation = Vec3(*target.translation_mm)
        placed: list[Triangle] = []
        for index, triangle in enumerate(target.solid.mesh.triangles_mm):
            if index % 64 == 0 and cancelled():
                raise InterruptedError("Tool access target placement cancelled")
            p = [grid.program_point(Vec3(*v) + translation).tuple for v in triangle]
            placed.append((p[0], p[1], p[2]))
        mesh = SurfaceMesh.create(placed, cancelled=cancelled, index_method="surface-area-v2")
        solid = TriangleSolid.validate(placed, budget=budget)
    cache: dict[tuple[int, int], ReachQuery] = {}
    states: dict[str, Mapping[int, tuple[ReachOutcome, ...]]] = {}
    nodes = faces = contacts = done = 0
    nx, ny, _ = grid.shape
    for label, cell_indices in selected_cells.items():
        rows = {}
        for tool in tools:
            outcomes = []
            geometry: ToolGeometry = evolution.inputs.tools[tool]
            gaps = geometry.clearance_notes + (
                () if any(s.component == "holder" for s in sections[tool]) else ("No holder geometry declared",)
            )
            for index in cell_indices:
                if cancelled():
                    raise InterruptedError("Tool access cancelled; no partial study")
                progress(f"Review {label} / T{tool}", done, total)
                key = index, tool
                query = cache.get(key)
                if query is None:
                    assert mesh is not None and solid is not None
                    cell = index % nx, (index // nx) % ny, index // (nx * ny)
                    end = grid.center(*cell)
                    start = Vec3(end.x, end.y, max(grid.bounds.maximum.z, mesh.root.bounds[1][2]) + clearance)
                    found, contained = [], []
                    shift, delta = qpoint(start.tuple), qpoint((end - start).tuple)
                    for section in sections[tool]:
                        before = len(found)
                        pending = [mesh.root]
                        while pending:
                            if cancelled():
                                raise InterruptedError("Tool access target chord cancelled")
                            node = pending.pop()
                            nodes += 1
                            if nodes > max_nodes:
                                raise ValueError("Tool access exhausted shared target node budget")
                            if not box_candidate(section, node.bounds, shift, delta, 0.000001):
                                continue
                            pending.extend(node.children)
                            for face in node.ids:
                                faces += 1
                                if faces > max_faces:
                                    raise ValueError("Tool access exhausted shared target face budget")
                                hit = triangle_contact(
                                    section,
                                    mesh.triangles[face],
                                    start.tuple,
                                    (end - start).tuple,
                                    position_error_mm=0.000001,
                                    cancelled=cancelled,
                                )
                                if hit is not None:
                                    found.append(ApproachContact(section.component, face, hit))
                        # With a complete face-free connected chord, one axial
                        # interior point distinguishes wholly-contained bodies.
                        if len(found) == before:
                            point = start + Vec3(0, 0, (section.low_mm + section.high_mm) / 2)
                            classification = solid.classify(point.tuple, budget=budget)
                            if classification != "outside":
                                contained.append(ReachContainment(section.component, point.tuple, classification))
                    contacts += len(found) + len(contained)
                    query = ReachQuery(
                        cell,
                        tool,
                        start.tuple,
                        end.tuple,
                        tuple(found),
                        tuple(contained),
                        gaps,
                        (geometry.stock_model_note,),
                    )
                    cache[key] = query
                found_stock = stocks[label].collision_contacts(
                    SweptTool(Vec3(*query.start_program_mm), Vec3(*query.end_program_mm), geometry),
                    cutting=True,
                    cancelled=cancelled,
                )
                contacts += len(found_stock)
                if contacts > max_contacts:
                    raise ValueError("Tool access exhausted complete contact storage budget")
                components = tuple(
                    sorted(
                        {c.component for c in query.target_contacts + query.containment}
                        | {c.component for c in found_stock}
                    )
                )
                status = (
                    "Target obstacle"
                    if query.target_contacts or query.containment
                    else "Stock body estimate"
                    if found_stock
                    else "Incomplete declaration"
                    if gaps
                    else "No detected target/stock obstacle"
                )
                outcomes.append(ReachOutcome(query, found_stock, components, status))
                done += 1
            rows[tool] = tuple(outcomes)
        states[label] = MappingProxyType(rows)
    if cancelled():
        raise InterruptedError("Tool access cancelled before delivery")
    progress("Complete candidate-tool access", total, total)
    return ToolReachStudy(
        analysis,
        tools,
        clearance,
        MappingProxyType(states),
        len(cache),
        total,
        cell_work,
        nodes,
        faces,
        (budget.nodes, budget.pairs, budget.rays, budget.queries),
        contacts,
    )
