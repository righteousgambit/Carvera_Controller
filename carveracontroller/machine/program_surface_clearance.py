"""Whole-range continuous CAD surface refinement with explicit occupancy gaps."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from types import MappingProxyType

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel
from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.addons.manufacturing_simulation.kinematics import MachineKinematics
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, TriangleSolid
from carveracontroller.machine.geometry_changes import asset_problems, verify_context_assets
from carveracontroller.machine.joint_clearance import JointBody, bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import (
    ProgramBodyClearance,
    ProgramClearanceSource,
    review_program_clearance,
)
from carveracontroller.machine.scene_joint_clearance import SceneClearanceCapture, component_points
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceContact, SurfaceMesh, Triangle, qpoint
from carveracontroller.machine.surface_occupancy import OccupancyInterval, review_solid_pair


@dataclass(frozen=True)
class ProgramSurfaceContact:
    segment_index: int
    line: int
    tool: int
    first: str
    second: str
    contact: SurfaceContact
    source_lower_ratio: Fraction
    source_upper_ratio: Fraction


@dataclass(frozen=True)
class SurfaceGap:
    segment_index: int
    line: int
    tool: int
    first: str
    second: str
    reason: str


@dataclass(frozen=True)
class ProgramSolidInterval:
    segment_index: int
    line: int
    tool: int
    first: str
    second: str
    interval: OccupancyInterval
    source_lower_ratio: Fraction
    source_upper_ratio: Fraction


@dataclass(frozen=True)
class ProgramSurfaceClearance:
    body_review: ProgramBodyClearance
    meshes: Mapping[int, Mapping[str, SurfaceMesh]]
    contacts: tuple[ProgramSurfaceContact, ...]
    gaps: tuple[SurfaceGap, ...]
    refined_pairs: int
    nodes: int
    triangle_pairs: int
    triangles: int
    occupancy: tuple[ProgramSolidInterval, ...] = ()
    solid_counts: tuple[int, int, int, int] = (0, 0, 0, 0)
    qualification: str = (
        "Continuous imported triangle surfaces at nominal C1 registration. No time sampling or face decimation. "
        "A 0.000001 mm outward numerical allowance precedes exact rational projection tests. Closed-solid containment/separation is classified only between possible surface contacts after complete mesh admission; unavailable solids retain explicit gaps. Rotating cutter/shank/holder clearance retains conservative body envelopes. "
        "Original curve, unresolved-command and ATC coverage still applies. Removed stock, backend execution and physical clearance remain unqualified. "
        "Surface reviews retain prepared triangle declarations and recompute contacts and solid intervals on opening. "
        "Retained scene identities do not independently verify original CAD provenance or measured registration. "
        "Save body review retains the separate body-envelope report only."
    )


def scene_surfaces(
    capture: SceneClearanceCapture,
    record: dict[str, object],
    *,
    max_triangles: int = 250_000,
    cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, SurfaceMesh]:
    return _scene_surfaces(capture, record, max_triangles=max_triangles, cancelled=cancelled)


def _scene_surfaces(
    capture: SceneClearanceCapture,
    record: dict[str, object],
    *,
    max_triangles: int,
    cancelled: Callable[[], bool],
    shared: Mapping[str, SurfaceMesh] | None = None,
) -> dict[str, SurfaceMesh]:
    # Only the program worker supplies shared meshes, after validating every
    # tool has identical selected machine geometry, placement and stock.
    if type(max_triangles) is not int or not 1 <= max_triangles <= 250_000:
        raise ValueError("Surface capture triangle budget must be one to 250000")
    machine = machine_from_record(record)
    bodies, _ = bodies_from_record(record, machine)
    by_name = {body.name: body for body in bodies}
    result = dict(shared or {})
    count = 0
    zero = {joint.name: 0.0 for joint in machine.tool_chain + machine.work_chain}

    def add(name: str, triangles: Sequence[Triangle]) -> None:
        nonlocal count
        if cancelled():
            raise InterruptedError("Scene surface capture cancelled")
        count += len(triangles)
        if count > max_triangles:
            raise ValueError("Scene surfaces exceed shared triangle budget; no faces omitted")
        body = by_name[name]
        transform = body_transform(machine, body, zero)
        transformed = []
        for index, triangle in enumerate(triangles):
            if index % 64 == 0 and cancelled():
                raise InterruptedError("Scene surface capture cancelled")
            points = tuple(transform.apply(Vec3(*p)).tuple for p in triangle)
            transformed.append((points[0], points[1], points[2]))
        result[name] = SurfaceMesh.create(transformed, cancelled=cancelled)

    for group, profile in capture.components.items():
        for index, component in enumerate(profile.components):
            if component["group"] != group:
                continue
            title = str(component.get("assembly", group)).replace("\n", " ")
            name = f"{group} {index + 1} · {title}"[:80]
            if group != "spindle" and name in result:
                continue
            if len(component["vertices"]) // 30 + count > max_triangles:
                raise ValueError("Scene surfaces exceed shared triangle budget; no faces omitted")
            # ToolGeometry.overall_length_mm is the declared exposed stickout.
            assert capture.definition.stickout is not None
            length = capture.definition.stickout
            points = tuple(component_points(capture, group, profile, component, length, cancelled=cancelled))
            add(name, tuple((points[i], points[i + 1], points[i + 2]) for i in range(0, len(points), 3)))
    if capture.repeat_plan is None:
        stock_rows = [] if "stock G54 · Current stock" in result else [("stock G54 · Current stock", capture.setup)]
    else:
        stock_rows = []
        for part in capture.repeat_plan.parts:
            name = f"stock {part.wcs} · {part.name}"[:80]
            if name in result:
                continue
            model = None
            if part.stock_source is not None:
                if (
                    capture.setup.stock_model is not None
                    and capture.setup.stock_model.reference == part.stock_source.reference
                ):
                    model = capture.setup.stock_model
                else:
                    model = StockModel.from_reference(part.stock_source.reference, cancelled=cancelled)
            stock_rows.append(
                (
                    name,
                    MachineSetup(
                        work_offset_mm=part.work_offset_mm,
                        stock_origin_mm=part.stock_origin_mm,
                        stock_size_mm=part.stock_size_mm,
                        stock_model=model,
                        stock_rotation_deg=part.stock_orientation_deg[2],
                        stock_tilt_deg=part.stock_orientation_deg[:2],
                    ),
                )
            )
    for name, setup in stock_rows:
        geometry = (
            setup.stock_model.geometry(setup, (0.7, 0.5, 0.25, 1), cancelled=cancelled)
            if setup.stock_model
            else setup.stock_mesh()
        )
        if len(geometry.indices) % 3 or count + len(geometry.indices) // 3 > max_triangles:
            raise ValueError("Stock surface triangles incomplete or over shared budget")
        triangles = []
        for index in range(0, len(geometry.indices), 3):
            if index % 192 == 0 and cancelled():
                raise InterruptedError("Stock surface capture cancelled")
            points = tuple(
                (geometry.vertices[i * 10], geometry.vertices[i * 10 + 1], geometry.vertices[i * 10 + 2])
                for i in geometry.indices[index : index + 3]
            )
            triangles.append(
                (
                    (points[0][0], points[0][1], points[0][2]),
                    (points[1][0], points[1][1], points[1][2]),
                    (points[2][0], points[2][1], points[2][2]),
                )
            )
        add(name, triangles)
    return result


def _translation(
    machine: MachineKinematics, body: JointBody, start: Mapping[str, float], end: Mapping[str, float]
) -> tuple[Vec3, Vec3]:
    zero = dict.fromkeys(start, 0.0)
    origin = body_transform(machine, body, zero).translation
    a, b = (
        body_transform(machine, body, start).translation - origin,
        body_transform(machine, body, end).translation - origin,
    )
    return a, b - a


def refine_program_surfaces(
    body_review: ProgramBodyClearance,
    meshes: Mapping[int, Mapping[str, SurfaceMesh]],
    *,
    budget: SurfaceBudget | None = None,
    solid_budget: SolidBudget | None = None,
) -> ProgramSurfaceClearance:
    budget = budget or SurfaceBudget()
    solid_budget = solid_budget or SolidBudget(cancelled=budget.cancelled)
    solid_cache: dict[int, TriangleSolid | str] = {}
    occupancy = []
    contacts = []
    gaps = []
    refined = 0
    # Every original broad-phase pair is refined over the COMPLETE chord, not
    # merely its first possible box-contact interval.
    contexts = {}
    for tool, record in body_review.records.items():
        machine = machine_from_record(record)
        links = machine.tool_chain + machine.work_chain
        if (
            tuple(j.name for j in links) != ("X", "Z", "Y")
            or any(j.kind != "linear" for j in links)
            or tuple(j.axis.tuple for j in links) != ((1, 0, 0), (0, 0, 1), (0, -1, 0))
            or len(machine.tool_chain) != 2
        ):
            raise ValueError("Surface review requires the validated C1 linear mapping")
        bodies, _ = bodies_from_record(record, machine)
        contexts[tool] = (machine, {b.name: b for b in bodies})
    bounds = {line: error for line, _command, error in body_review.curve_enclosures}
    seen = set()
    for candidate in body_review.contacts:
        if budget.cancelled():
            raise InterruptedError("Program surface review cancelled; no partial report")
        key = (candidate.segment_index, candidate.contact.first, candidate.contact.second)
        if key in seen:
            continue
        seen.add(key)
        segment = body_review.segments[candidate.segment_index]
        tool = int(segment.tool_id)
        first, second = candidate.contact.first, candidate.contact.second
        surfaces = meshes.get(tool, {})
        if first not in surfaces or second not in surfaces:
            gaps.append(
                SurfaceGap(
                    candidate.segment_index,
                    segment.line,
                    tool,
                    first,
                    second,
                    "envelope_only: rotating assembly or missing surface geometry",
                )
            )
            continue
        machine, body_map = contexts[tool]
        start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
        a, da = _translation(machine, body_map[first], start, end)
        b, db = _translation(machine, body_map[second], start, end)
        same = (body_map[first].frame, body_map[first].joint_count) == (
            body_map[second].frame,
            body_map[second].joint_count,
        )
        # Outward allowance covers float placement/translation roundoff before
        # the rational surface solver. It does not qualify physical registration.
        numeric_guard = 1e-6
        error = numeric_guard + (0.0 if same else 2 * bounds.get(segment.line, 0.0) * (1 + 1e-7))
        pair = review_solid_pair(
            surfaces[first],
            surfaces[second],
            (a - b).tuple,
            (da - db).tuple,
            position_error_mm=error,
            surface_budget=budget,
            budget=solid_budget,
            cache=solid_cache,
        )
        hits = pair.contacts
        lo, span = (
            Fraction(segment.source_start_ratio),
            Fraction(segment.source_end_ratio) - Fraction(segment.source_start_ratio),
        )
        for interval in pair.intervals:
            occupancy.append(
                ProgramSolidInterval(
                    candidate.segment_index,
                    segment.line,
                    tool,
                    first,
                    second,
                    interval,
                    lo + span * interval.lower,
                    lo + span * interval.upper,
                )
            )
        refined += 1
        for hit in hits:
            lo, span = (
                Fraction(segment.source_start_ratio),
                Fraction(segment.source_end_ratio) - Fraction(segment.source_start_ratio),
            )
            contacts.append(
                ProgramSurfaceContact(
                    candidate.segment_index,
                    segment.line,
                    tool,
                    first,
                    second,
                    hit,
                    lo + span * hit.lower,
                    lo + span * hit.upper,
                )
            )
        if pair.gap:
            gaps.append(
                SurfaceGap(
                    candidate.segment_index,
                    segment.line,
                    tool,
                    first,
                    second,
                    "solid_unavailable: " + pair.gap,
                )
            )
    if budget.cancelled():
        raise InterruptedError("Program surface review cancelled; no partial report")
    return ProgramSurfaceClearance(
        body_review,
        MappingProxyType({t: MappingProxyType(dict(m)) for t, m in meshes.items()}),
        tuple(
            sorted(
                contacts,
                key=lambda c: (
                    c.segment_index,
                    c.contact.lower,
                    c.first,
                    c.second,
                    c.contact.first_triangle,
                    c.contact.second_triangle,
                ),
            )
        ),
        tuple(gaps),
        refined,
        budget.nodes,
        budget.pairs,
        sum(len(m.triangles) for m in {id(m): m for rows in meshes.values() for m in rows.values()}.values()),
        tuple(occupancy),
        (solid_budget.nodes, solid_budget.pairs, solid_budget.rays, solid_budget.queries),
    )


def verify_repeat_sources(capture: SceneClearanceCapture, cancelled: Callable[[], bool]) -> None:
    if capture.repeat_plan is None:
        return
    sources = {p.stock_source for p in capture.repeat_plan.parts if p.stock_source is not None}
    for source in sources:
        ref = source.reference
        if asset_digest(ref["source_path"], 24 * 1024 * 1024, cancelled=cancelled) != ref["source_sha256"]:
            raise ValueError("Imported repeat stock bytes changed during surface review")


def review_program_surfaces(
    source: ProgramClearanceSource,
    captures: Mapping[int, SceneClearanceCapture],
    work_offsets: Mapping[str, Sequence[float]],
    *,
    start_line: int = 1,
    end_line: int | None = None,
    tolerance_mm: float = 0.05,
    cancelled: Callable[[], bool] = lambda: False,
    max_triangles: int = 250_000,
    budget: SurfaceBudget | None = None,
) -> ProgramSurfaceClearance:
    if type(max_triangles) is not int or not 1 <= max_triangles <= 250_000:
        raise ValueError("Shared surface triangle budget exceeds contract")
    body_review = review_program_clearance(
        source,
        captures,
        work_offsets,
        start_line=start_line,
        end_line=end_line,
        tolerance_mm=tolerance_mm,
        cancelled=cancelled,
    )
    meshes = {}
    remaining = max_triangles
    shared: dict[str, SurfaceMesh] = {}
    allocated: set[int] = set()
    for tool, record in body_review.records.items():
        verify_repeat_sources(captures[tool], cancelled)
        meshes[tool] = _scene_surfaces(
            captures[tool], record, max_triangles=remaining, cancelled=cancelled, shared=shared
        )
        for mesh in meshes[tool].values():
            if id(mesh) not in allocated:
                remaining -= len(mesh.triangles)
                allocated.add(id(mesh))
        shared = {name: mesh for name, mesh in meshes[tool].items() if not name.startswith("spindle ")}
    active_budget = budget or SurfaceBudget(cancelled=cancelled)
    if budget is not None:
        prior = budget.cancelled
        budget.cancelled = lambda: cancelled() or prior()
    try:
        result = refine_program_surfaces(body_review, meshes, budget=active_budget)
    finally:
        if budget is not None:
            budget.cancelled = prior
    for tool in body_review.records:
        verify_repeat_sources(captures[tool], cancelled)
        problems = asset_problems(verify_context_assets(captures[tool].context, cancelled=cancelled))
        if problems:
            raise ValueError("\n".join(problems))
    if cancelled():
        raise InterruptedError("Program surface review cancelled; no partial report")
    return result


def contact_triangles(report: ProgramSurfaceClearance, contact: ProgramSurfaceContact) -> tuple[Triangle, Triangle]:
    segment = report.body_review.segments[contact.segment_index]
    machine = machine_from_record(report.body_review.records[contact.tool])
    bodies, _ = bodies_from_record(report.body_review.records[contact.tool], machine)
    by_name = {b.name: b for b in bodies}
    start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
    fraction = float((contact.contact.lower + contact.contact.upper) / 2)
    result = []
    for name, index in (
        (contact.first, contact.contact.first_triangle),
        (contact.second, contact.contact.second_triangle),
    ):
        a, d = _translation(machine, by_name[name], start, end)
        shift = a + d.scaled(fraction)
        points = tuple((Vec3(*p) + shift).tuple for p in report.meshes[contact.tool][name].triangles[index])
        result.append((points[0], points[1], points[2]))
    return result[0], result[1]


def occupancy_witness(
    report: ProgramSurfaceClearance, selected: ProgramSolidInterval
) -> tuple[float, float, float] | None:
    interval = selected.interval
    if interval.witness_point is None or interval.contained_side is None:
        return None
    segment = report.body_review.segments[selected.segment_index]
    machine = machine_from_record(report.body_review.records[selected.tool])
    bodies, _ = bodies_from_record(report.body_review.records[selected.tool], machine)
    name = selected.first if interval.contained_side == "first" else selected.second
    body = next(b for b in bodies if b.name == name)
    start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
    a, d = _translation(machine, body, start, end)
    qa, qd = qpoint(a.tuple), qpoint(d.tuple)
    values = tuple(float(interval.witness_point[i] + qa[i] + interval.sample * qd[i]) for i in range(3))
    return values[0], values[1], values[2]
