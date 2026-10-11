"""Declared or captured-pose route and all-leg target / remaining-stock checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite, prod
from typing import cast

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import CollisionContact
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.rotating_shape import cutting_sections
from carveracontroller.machine.rotating_surface import box_candidate, triangle_contact
from carveracontroller.machine.stock_allowance import ApproachContact, CellAllowance
from carveracontroller.machine.surface_motion import SurfaceMesh, Triangle, qpoint, sub


@dataclass(frozen=True)
class ApproachStart:
    machine_mm: tuple[float, float, float]
    origin: str = "Declared machine XYZ"
    observed: ObservedPose | None = None

    def __post_init__(self) -> None:
        if len(self.machine_mm) != 3 or any(
            type(v) not in (int, float) or not isfinite(v) or abs(v) > 1_000_000 for v in self.machine_mm
        ):
            raise ValueError("Route start needs three finite declared machine coordinates")
        if self.origin not in ("Declared machine XYZ", "Captured Idle status"):
            raise ValueError("Choose a declared start or explicitly captured Idle status")
        if (self.observed is not None) != (self.origin == "Captured Idle status"):
            raise ValueError("Captured route origin must retain its actual status packet")
        if self.observed is not None and self.machine_mm != self.observed.machine_mm:
            raise ValueError("Route start differs from its captured machine packet")


def capture_start(pose: ObservedPose | None, *, connected: bool, tool: int, now: float) -> ApproachStart:
    if not connected or pose is None or not pose.fresh(now) or pose.state != "Idle":
        raise ValueError("Capture requires a connected fresh Idle pose")
    if pose.tool != tool or pose.tool_length_mm is None:
        raise ValueError("Captured spindle tool must match the reviewed tool and report its length offset")
    if pose.rotation_deg != 0 or pose.rotary_deg != 0 or pose.wcs_index is None:
        raise ValueError("Captured C1 approach needs a reported unrotated WCS and rotary zero")
    return ApproachStart(pose.machine_mm, "Captured Idle status", pose)


@dataclass(frozen=True)
class RouteLegMaterial:
    index: int
    label: str
    start_program_mm: tuple[float, float, float]
    end_program_mm: tuple[float, float, float]
    cutting: bool
    target_contacts: tuple[ApproachContact, ...]
    stock_contacts: tuple[CollisionContact, ...]


@dataclass(frozen=True)
class RouteMaterial:
    legs: tuple[RouteLegMaterial, ...]
    nodes: int
    face_queries: int
    declared_cell_work_bound: int
    coverage: tuple[str, ...]
    target_mesh: SurfaceMesh
    qualification: str = (
        "All legs use complete transformed target faces and the selected retained stock-state mask. "
        "Retract/traverse include rapid cutter contacts; only final insertion allows declared cutter engagement with stock. "
        "No material is removed by review. Cell boxes are conservative grid estimates, not physical removal proof. "
        "Captured MPos remains reported-coordinate evidence mapped into declared tool-tip geometry; effective compensation "
        "owners and measured tool registration are not reconciled or certified. No controller commands are generated."
    )


def review_route_material(
    inspection: CellAllowance,
    waypoints_machine_mm: tuple[tuple[float, float, float], ...],
    labels: tuple[str, ...],
    *,
    cancelled: Callable[[], bool],
    max_nodes: int = 2_000_000,
    max_faces: int = 250_000,
    max_cell_work: int = 50_000_000,
) -> RouteMaterial:
    if inspection.approach is None or len(waypoints_machine_mm) != 4 or len(labels) != 3:
        raise ValueError("Material route requires the complete retract, traverse and insertion")
    if any(
        type(value) is not int or not 1 <= value <= limit
        for value, limit in ((max_nodes, 2_000_000), (max_faces, 250_000), (max_cell_work, 50_000_000))
    ):
        raise ValueError("Route material exceeds complete shared work contract")
    target = inspection.analysis.target
    evolution = cast(StockEvolution, target.bindings[1])
    grid = StockVolume.from_snapshot(target.target, cancelled=cancelled)
    fit = inspection.analysis.fits[inspection.label]
    extra = StockVolume.from_snapshot(fit.excess, cancelled=cancelled)
    missing = StockVolume.from_snapshot(fit.missing, cancelled=cancelled)
    stock = grid.clone(cancelled=cancelled)
    geometry = evolution.inputs.tools[inspection.approach.tool]
    sections = cutting_sections(geometry) + tuple(
        s for s in SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), geometry).sections() if s.component != "cutter"
    )
    cell_work = prod(grid.shape) * (1 + 3 * len(sections))
    if cell_work > max_cell_work:
        raise ValueError("Route material exhausted complete cell-work budget; no partial review")
    count = 0
    for at, (wanted, excess, lost) in enumerate(zip(grid._occupied, extra._occupied, missing._occupied)):
        if at % 128 == 0 and cancelled():
            raise InterruptedError("Route material cancelled; no partial review")
        has = excess or (wanted and not lost)
        stock._occupied[at] = int(has)
        count += has
    stock._remaining_count = stock._initial_count = count
    translation = Vec3(*target.translation_mm)
    triangles: list[Triangle] = []
    for at, row in enumerate(target.solid.mesh.triangles_mm):
        if at % 64 == 0 and cancelled():
            raise InterruptedError("Route target placement cancelled")
        p = [grid.program_point(Vec3(*point) + translation).tuple for point in row]
        triangles.append((p[0], p[1], p[2]))
    mesh = SurfaceMesh.create(triangles, cancelled=cancelled, index_method="surface-area-v2")
    offset = Vec3(*evolution.inputs.stocks[target.stock][0])
    points = tuple(Vec3(*point) - offset for point in waypoints_machine_mm)
    legs = []
    nodes = faces = 0
    for index, (start, end, label) in enumerate(zip(points, points[1:], labels)):
        contacts = []
        shift = qpoint(start.tuple)
        delta = sub(qpoint(end.tuple), shift)
        for section in sections:
            pending = [mesh.root]
            while pending:
                if cancelled():
                    raise InterruptedError("Route material cancelled; no partial review")
                node = pending.pop()
                nodes += 1
                if nodes > max_nodes:
                    raise ValueError("Route target exhausted shared node budget; no partial review")
                if not box_candidate(section, node.bounds, shift, delta, 0.000001):
                    continue
                pending.extend(node.children)
                for face in node.ids:
                    faces += 1
                    if faces > max_faces:
                        raise ValueError("Route target exhausted shared face budget; no partial review")
                    hit = triangle_contact(
                        section,
                        mesh.triangles[face],
                        start.tuple,
                        (end - start).tuple,
                        position_error_mm=0.000001,
                        cancelled=cancelled,
                    )
                    if hit is not None:
                        contacts.append(ApproachContact(section.component, face, hit))
        cutting = index == 2
        remaining = stock.collision_contacts(SweptTool(start, end, geometry), cutting=cutting, cancelled=cancelled)
        legs.append(RouteLegMaterial(index, label, start.tuple, end.tuple, cutting, tuple(contacts), remaining))
    if cancelled():
        raise InterruptedError("Route material cancelled; no partial review")
    return RouteMaterial(tuple(legs), nodes, faces, cell_work, inspection.approach.coverage, mesh)
