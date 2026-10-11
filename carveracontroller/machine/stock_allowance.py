"""Nearest-target cell allowance and complete target-only +Z insertion review."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite, sqrt
from typing import cast

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import CollisionContact
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.rotating_shape import cutting_sections
from carveracontroller.machine.rotating_surface import CylinderWitness, box_candidate, triangle_contact
from carveracontroller.machine.stock_target import TargetAnalysis
from carveracontroller.machine.surface_distance import DistanceBudget, NearestSurfacePoint, nearest_surface
from carveracontroller.machine.surface_motion import SurfaceMesh, Triangle, qpoint, sub


@dataclass(frozen=True)
class ApproachContact:
    component: str
    triangle: int
    witness: CylinderWitness


@dataclass(frozen=True)
class CellApproach:
    tool: int
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    target_contacts: tuple[ApproachContact, ...]
    stock_contacts: tuple[CollisionContact, ...]
    nodes: int
    face_queries: int
    coverage: tuple[str, ...]
    qualification: str = (
        "One straight +Z-tool insertion from above all declared stock, stopping at this cell center. "
        "Complete transformed target triangles with continuous declared rotating envelopes; all contacts retained. "
        "Remaining-stock noncutting contact is a center-grid estimate. This is not a finishing toolpath. "
        "Holder/assembly declaration gaps, changed-length joint poses, machine/fixture/ATC/force/physical checks remain separate."
    )


@dataclass(frozen=True)
class CellAllowance:
    analysis: TargetAnalysis
    label: str
    cell: tuple[int, int, int]
    category: str
    center_grid_mm: tuple[float, float, float]
    center_program_mm: tuple[float, float, float]
    nearest: NearestSurfacePoint
    signed_distance_mm: float
    cell_distance_interval_mm: tuple[float, float]
    half_diagonal_mm: float
    approach: CellApproach | None
    distance_nodes: int
    distance_faces: int
    qualification: str = (
        "Exact nearest triangle point for the stored finite coordinates and grid center; signed display length. "
        "Positive outside the target; negative inside. Face-interior distance is normal to that triangle; "
        "edge/vertex witnesses have no unique face normal. Cell distance interval uses its half diagonal, "
        "not a measured allowance or manufactured geometry certificate. Physical registration and resolution remain explicit."
    )


def inspect_target_cell(
    analysis: TargetAnalysis,
    label: str,
    cell: tuple[int, int, int],
    *,
    tool: int | None = None,
    approach_clearance_mm: float = 1,
    cancelled: Callable[[], bool] = lambda: False,
    distance_budget: DistanceBudget | None = None,
    max_nodes: int = 2_000_000,
    max_faces: int = 250_000,
) -> CellAllowance:
    if label not in analysis.fits or len(cell) != 3 or any(type(v) is not int for v in cell):
        raise ValueError("Choose a retained stock state and three integer cell indices")
    target = analysis.target
    evolution = cast(StockEvolution, target.bindings[1])
    if tool is not None and (type(tool) is not int or tool not in evolution.inputs.tools):
        raise ValueError("Choose a tool retained in this target review")
    if (
        type(approach_clearance_mm) not in (int, float)
        or not isfinite(approach_clearance_mm)
        or not 0.001 <= approach_clearance_mm <= 100
    ):
        raise ValueError("Approach clearance must be finite 0.001..100 mm")
    if (
        type(max_nodes) is not int
        or not 1 <= max_nodes <= 2_000_000
        or type(max_faces) is not int
        or not 1 <= max_faces <= 250_000
    ):
        raise ValueError("Cell approach exceeds complete shared work bounds")
    grid = StockVolume.from_snapshot(target.target, cancelled=cancelled)
    if any(not 0 <= index < size for index, size in zip(cell, grid.shape)):
        raise ValueError("Cell indices must be inside the complete retained grid")
    center = grid.grid_center(*cell)
    source_point = center - Vec3(*target.translation_mm)
    mesh = SurfaceMesh.create(target.solid.mesh.triangles_mm, cancelled=cancelled, index_method="surface-area-v2")
    budget = distance_budget or DistanceBudget(cancelled=cancelled)
    if distance_budget is not None:
        prior = distance_budget.cancelled
        budget.cancelled = lambda: cancelled() or prior()
    try:
        nearest = nearest_surface(mesh, source_point.tuple, budget=budget)
    finally:
        if distance_budget is not None:
            budget.cancelled = prior
    fit = analysis.fits[label]
    excess = StockVolume.from_snapshot(fit.excess, cancelled=cancelled)
    missing = StockVolume.from_snapshot(fit.missing, cancelled=cancelled)
    want = grid.occupied(*cell)
    category = (
        "excess stock"
        if excess.occupied(*cell)
        else "missing target"
        if missing.occupied(*cell)
        else "retained target"
        if want
        else "empty outside target"
    )
    distance = sqrt(float(nearest.distance_squared)) * (-1 if want else 1)
    half = sqrt(sum(v * v for v in grid.cell_size.tuple)) / 2
    approach = None
    if tool is not None:
        # Recreate this variant's complete material mask, without inventing a path.
        stock = grid.clone(cancelled=cancelled)
        count = 0
        for at, (wanted, extra, lost) in enumerate(zip(grid._occupied, excess._occupied, missing._occupied)):
            if at % 128 == 0 and cancelled():
                raise InterruptedError("Cell approach cancelled; previous result retained")
            has = extra or (wanted and not lost)
            stock._occupied[at] = int(has)
            count += has
        stock._remaining_count = stock._initial_count = count
        end = grid.center(*cell)
        start = Vec3(end.x, end.y, grid.bounds.maximum.z + approach_clearance_mm)
        geometry = evolution.inputs.tools[tool]
        sweep = SweptTool(start, end, geometry)
        sections = cutting_sections(geometry) + tuple(s for s in sweep.sections() if s.component != "cutter")
        # Target mesh is in source coordinates; transform every face with the
        # exact same declared grid pose used by stock cells, before +Z review.
        placed: list[Triangle] = []
        translation = Vec3(*target.translation_mm)
        for at, row in enumerate(mesh.triangles):
            if at % 64 == 0 and cancelled():
                raise InterruptedError("Cell approach cancelled; previous result retained")
            points = [grid.program_point(Vec3(*p) + translation).tuple for p in row]
            placed.append((points[0], points[1], points[2]))
        placed_mesh = SurfaceMesh.create(placed, cancelled=cancelled, index_method="surface-area-v2")
        contacts = []
        nodes = faces = 0
        shift, delta = qpoint(start.tuple), sub(qpoint(end.tuple), qpoint(start.tuple))
        for section in sections:
            pending = [placed_mesh.root]
            while pending:
                if cancelled():
                    raise InterruptedError("Cell approach cancelled; previous result retained")
                node = pending.pop()
                nodes += 1
                if nodes > max_nodes:
                    raise ValueError("Cell approach exhausted complete shared node budget; no partial review")
                if not box_candidate(section, node.bounds, shift, delta, 0.000001):
                    continue
                pending.extend(node.children)
                for index in node.ids:
                    faces += 1
                    if faces > max_faces:
                        raise ValueError("Cell approach exhausted complete shared face budget; no partial review")
                    hit = triangle_contact(
                        section,
                        placed_mesh.triangles[index],
                        start.tuple,
                        (end - start).tuple,
                        position_error_mm=0.000001,
                        cancelled=cancelled,
                    )
                    if hit is not None:
                        contacts.append(ApproachContact(section.component, index, hit))
        stock_contacts = stock.collision_contacts(sweep, cutting=True, cancelled=cancelled)
        notes = list(geometry.clearance_notes)
        if not any(section.component == "holder" for section in sections):
            notes.append("No holder geometry declared")
        approach = CellApproach(
            tool, start.tuple, end.tuple, tuple(contacts), stock_contacts, nodes, faces, tuple(notes)
        )
    if cancelled():
        raise InterruptedError("Cell allowance cancelled; previous result retained")
    return CellAllowance(
        analysis,
        label,
        cell,
        category,
        center.tuple,
        grid.center(*cell).tuple,
        nearest,
        distance,
        (distance - half, distance + half),
        half,
        approach,
        budget.nodes,
        budget.triangles,
    )
