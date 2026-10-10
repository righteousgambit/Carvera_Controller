"""Whole-range continuous CAD surface refinement with explicit occupancy gaps."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from types import MappingProxyType

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel
from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope, SweptTool
from carveracontroller.addons.manufacturing_simulation.kinematics import MachineKinematics
from carveracontroller.addons.manufacturing_simulation.stock_solid import (
    SolidBudget,
    SolidBudgetExceeded,
    TriangleSolid,
)
from carveracontroller.machine.geometry_changes import asset_problems, verify_context_assets
from carveracontroller.machine.joint_clearance import JointBody, bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import (
    ProgramBodyClearance,
    ProgramClearanceSource,
    review_program_clearance,
)
from carveracontroller.machine.program_stock_evolution import (
    StockEvolution,
    capture_stock_inputs,
    review_stock_evolution,
)
from carveracontroller.machine.rotating_pair import RotatingSectionReview, review_rotating_pair
from carveracontroller.machine.rotating_shape import RotatingShape, cutting_sections
from carveracontroller.machine.rotating_surface import dimensions
from carveracontroller.machine.scene_joint_clearance import SceneClearanceCapture, component_points
from carveracontroller.machine.simulation_preview import simulation_tools
from carveracontroller.machine.surface_motion import (
    ContactGroupBudget,
    ContactGroupBudgetExceeded,
    SurfaceBudget,
    SurfaceBudgetExceeded,
    SurfaceContact,
    SurfaceContactGroup,
    SurfaceMesh,
    Triangle,
    qpoint,
)
from carveracontroller.machine.surface_occupancy import OccupancyInterval, review_solid_pair
from carveracontroller.machine.surface_rigid_reuse import RigidPairReuse


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
class ProgramSurfaceContactGroup:
    segment_index: int
    line: int
    tool: int
    first: str
    second: str
    group: SurfaceContactGroup
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
class ProgramRotatingResult:
    segment_index: int
    line: int
    tool: int
    first: str
    second: str
    result: RotatingSectionReview
    source_sample_ratio: Fraction


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
    groups: tuple[ProgramSurfaceContactGroup, ...] = ()
    contact_mode: str = "triangles"
    group_counts: tuple[int, int] = (0, 0)
    rotating: tuple[ProgramRotatingResult, ...] = ()
    rotating_envelopes: Mapping[int, Mapping[str, tuple[AxialEnvelope, ...]]] = field(
        default_factory=lambda: MappingProxyType({})
    )
    stock_evolution: StockEvolution | None = None
    rigid_reused_pairs: int = 0


def validate_rotating_envelopes(
    records: Mapping[int, dict[str, object]],
    envelopes: Mapping[int, Mapping[str, tuple[AxialEnvelope, ...]]],
) -> None:
    if set(envelopes) != set(records):
        raise ValueError("Rotating declarations must retain every program tool binding")
    for tool, record in records.items():
        machine = machine_from_record(record)
        bodies, _ = bodies_from_record(record, machine)
        by_name = {body.name: body for body in bodies}
        names = {name for name in by_name if name in (f"T{tool} cutter", f"T{tool} shank", f"T{tool} holder")}
        if set(envelopes[tool]) != names:
            raise ValueError("Rotating declarations must retain every declared cutter/shank/holder body")
        for name, sections in envelopes[tool].items():
            body = by_name[name]
            if body.frame != "tool" or body.joint_count != 2 or not 1 <= len(sections) <= 257:
                raise ValueError("Rotating sections require the complete C1 tool-tip frame")
            zero = dict.fromkeys(("X", "Y", "Z"), 0.0)
            if body_transform(machine, body, zero).rotation != (1, 0, 0, 0, 1, 0, 0, 0, 1):
                raise ValueError("Declared rotating cylinders require an unrotated C1 tool frame")
            for section in sections:
                low, high, radius = dimensions(section)
                if (
                    section.component != name.split()[-1]
                    or not isinstance(section.source, str)
                    or len(section.source) > 512
                ):
                    raise ValueError("Rotating section identity differs from its declared body")
                minimum, maximum = body.bounds.minimum.tuple, body.bounds.maximum.tuple
                if any(
                    Fraction(minimum[i]) > -radius or Fraction(maximum[i]) < radius for i in range(2)
                ) or not Fraction(minimum[2]) <= low < high <= Fraction(maximum[2]):
                    raise ValueError("Rotating section lies outside its declared body envelope")


def scene_rotating_envelopes(capture: SceneClearanceCapture) -> dict[str, tuple[AxialEnvelope, ...]]:
    tool = simulation_tools({capture.number: capture.definition}, {str(capture.number)})[str(capture.number)]
    sections = cutting_sections(tool) + tuple(
        s for s in SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool).sections() if s.component != "cutter"
    )
    return {
        f"T{capture.number} {component}": tuple(s for s in sections if s.component == component)
        for component in ("cutter", "shank", "holder")
        if any(s.component == component for s in sections)
    }


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
    grouped: bool = False,
    group_budget: ContactGroupBudget | None = None,
    rotating_envelopes: Mapping[int, Mapping[str, tuple[AxialEnvelope, ...]]] | None = None,
    reuse_rigid_pairs: bool = False,
) -> ProgramSurfaceClearance:
    if type(grouped) is not bool or (not grouped and group_budget is not None):
        raise ValueError("Grouped review needs explicit boolean mode and a compatible representation budget")
    if type(reuse_rigid_pairs) is not bool or (reuse_rigid_pairs and len(body_review.segments) > 3):
        raise ValueError("Rigid sharing supports at most three complete C1 approach legs")
    rigid = RigidPairReuse() if reuse_rigid_pairs else None
    budget = budget or SurfaceBudget()
    active_groups = (group_budget or ContactGroupBudget(cancelled=budget.cancelled)) if grouped else None
    solid_budget = solid_budget or SolidBudget(cancelled=budget.cancelled)
    solid_cache: dict[int, TriangleSolid | str] = {}
    occupancy = []
    contacts = []
    groups = []
    gaps = []
    refined = 0
    rotating = []
    if rotating_envelopes is not None:
        validate_rotating_envelopes(body_review.records, rotating_envelopes)
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
        cylinders = rotating_envelopes.get(tool, {}) if rotating_envelopes is not None else {}
        rotating_first = first in cylinders or second in cylinders
        if (first not in surfaces and first not in cylinders) or (second not in surfaces and second not in cylinders):
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
        # Only a zero relative translation over this complete C1 linear chord
        # is reusable. Exact relative start/allowance and tool bind the key;
        # changing positions, relative motion or tool cannot reuse this query.
        reusable = (da - db).tuple == (0, 0, 0)
        reuse_key = (tool, first, second, (a - b).tuple, error)
        destinations = (contacts, groups, occupancy, rotating, gaps)
        previous_sizes = tuple(len(rows) for rows in destinations)
        if rigid is not None and reusable:
            cached = rigid.get(reuse_key, candidate.segment_index, segment)
            if cached is not None:
                if len(rotating) + len(cached[3]) > 100_000:
                    raise ValueError("Rotating review exceeds complete shared result budget")
                contacts.extend(cached[0])
                groups.extend(cached[1])
                occupancy.extend(cached[2])
                rotating.extend(cached[3])
                gaps.extend(cached[4])
                refined += 1
                continue

        def remember(
            is_rigid: bool = reusable,
            key: tuple[int, str, str, tuple[float, float, float], float] = reuse_key,
            sizes: tuple[int, ...] = previous_sizes,
        ) -> None:
            if rigid is not None and is_rigid:
                rigid.rows[key] = (
                    tuple(contacts[sizes[0] :]),
                    tuple(groups[sizes[1] :]),
                    tuple(occupancy[sizes[2] :]),
                    tuple(rotating[sizes[3] :]),
                    tuple(gaps[sizes[4] :]),
                )

        try:
            if rotating_first:
                cylinder_name, other_name, shift, delta = (
                    (first, second, a - b, da - db) if first in cylinders else (second, first, b - a, db - da)
                )
                zero = dict.fromkeys(start, 0.0)
                shift = shift + body_transform(machine, body_map[cylinder_name], zero).translation
                if other_name in cylinders:
                    shift = shift - body_transform(machine, body_map[other_name], zero).translation
                rows = review_rotating_pair(
                    cylinders[cylinder_name],
                    shift.tuple,
                    delta.tuple,
                    mesh=surfaces.get(other_name),
                    other_sections=cylinders.get(other_name, ()),
                    position_error_mm=error,
                    surface_budget=budget,
                    solid_budget=solid_budget,
                    cache=solid_cache,
                )
                if len(rotating) + len(rows) > 100_000:
                    raise ValueError(
                        f"Rotating review exceeds complete result budget; no partial report · source line {segment.line}"
                    )
                lo, span = (
                    Fraction(segment.source_start_ratio),
                    Fraction(segment.source_end_ratio) - Fraction(segment.source_start_ratio),
                )
                rotating.extend(
                    ProgramRotatingResult(
                        candidate.segment_index,
                        segment.line,
                        tool,
                        cylinder_name,
                        other_name,
                        row,
                        lo + span * row.sample,
                    )
                    for row in rows
                )
                refined += 1
                remember()
                continue
            pair = review_solid_pair(
                surfaces[first],
                surfaces[second],
                (a - b).tuple,
                (da - db).tuple,
                position_error_mm=error,
                surface_budget=budget,
                budget=solid_budget,
                cache=solid_cache,
                group_budget=active_groups,
            )
        except (SurfaceBudgetExceeded, SolidBudgetExceeded, ContactGroupBudgetExceeded) as exc:
            group_work = (
                f"\nGrouped representation: {active_groups.groups} exact intervals · {active_groups.members} triangle pairs"
                if active_groups is not None
                else ""
            )
            raise ValueError(
                f"{exc}\nSource line {segment.line} · T{tool}\n{first} / {second}\n"
                f"Surface work: {budget.nodes} nodes · {budget.pairs} triangle pairs · {budget.contacts} contacts\n"
                f"Solid work: {solid_budget.nodes} steps · {solid_budget.pairs} pairs · {solid_budget.rays} rays · {solid_budget.queries} queries"
                + group_work
            ) from exc
        hits = pair.contacts
        lo, span = (
            Fraction(segment.source_start_ratio),
            Fraction(segment.source_end_ratio) - Fraction(segment.source_start_ratio),
        )
        for group in pair.groups:
            groups.append(
                ProgramSurfaceContactGroup(
                    candidate.segment_index,
                    segment.line,
                    tool,
                    first,
                    second,
                    group,
                    lo + span * group.lower,
                    lo + span * group.upper,
                )
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
        remember()
    if budget.cancelled():
        raise InterruptedError("Program surface review cancelled; no partial report")
    result = ProgramSurfaceClearance(
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
    if rigid is not None:
        result = replace(
            result,
            rigid_reused_pairs=rigid.hits,
            qualification=result.qualification
            + " Operation-local identical zero-relative-motion pairs share exact immutable geometry records; every leg retains its complete source wrappers. Work and group-storage counters count unique computations/data, not repeated logical membership. No relative-moving pair is reused.",
        )
    if rotating_envelopes is not None:
        result = replace(
            result,
            rotating=tuple(rotating),
            rotating_envelopes=MappingProxyType(
                {tool: MappingProxyType(dict(rows)) for tool, rows in rotating_envelopes.items()}
            ),
            qualification=result.qualification
            + " Declared +Z rotating cylinders are reviewed continuously using exact rational radial/axial feasibility, with outward position/curve allowance. One existence witness per section is retained, not first-contact time or exhaustive face membership. Shape bands, flutes, missing holder declarations and physical registration remain unqualified; initial stock is not material already removed.",
        )
    if any(
        isinstance(s, RotatingShape)
        for rows in result.rotating_envelopes.values()
        for sections in rows.values()
        for s in sections
    ):
        result = replace(
            result,
            qualification=result.qualification
            + " Declared spherical caps and increasing conical cutter profiles use exact whole-chord quadratic minima over every feasible axial/barycentric/time face. Rotating assembly pairs retain outer cylinder envelopes; bull corners and thread teeth retain outside-radius cylinders. Profile dimensions and computed cone slopes are nominal declarations, not manufactured flute geometry. Witnesses establish existence only; changing stock remains separate.",
        )
    if active_groups is not None:
        return replace(
            result,
            groups=tuple(
                sorted(groups, key=lambda c: (c.segment_index, c.group.lower, c.group.upper, c.first, c.second))
            ),
            contact_mode="groups",
            group_counts=(active_groups.groups, active_groups.members),
            qualification=result.qualification
            + " Identical exact contact intervals are grouped; every contributing original triangle pair remains retained. Groups do not permit or exclude mounting contact.",
        )
    return result


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
    grouped: bool = False,
    stock_resolution_mm: float | None = None,
) -> ProgramSurfaceClearance:
    if type(max_triangles) is not int or not 1 <= max_triangles <= 250_000:
        raise ValueError("Shared surface triangle budget exceeds contract")
    if stock_resolution_mm is not None and start_line != 1:
        raise ValueError(
            "Ordered stock needs a program review from line 1; selected operations lack preceding material history"
        )
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
        result = refine_program_surfaces(
            body_review,
            meshes,
            budget=active_budget,
            grouped=grouped,
            rotating_envelopes={tool: scene_rotating_envelopes(captures[tool]) for tool in body_review.records},
        )
    finally:
        if budget is not None:
            budget.cancelled = prior
    if stock_resolution_mm is not None:
        result = replace(
            result,
            stock_evolution=review_stock_evolution(
                body_review,
                capture_stock_inputs(
                    {tool: captures[tool] for tool in body_review.records}, stock_resolution_mm, cancelled=cancelled
                ),
                result.rotating_envelopes,
                cancelled=cancelled,
            ),
        )
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


def group_member_contact(group: ProgramSurfaceContactGroup, index: int) -> ProgramSurfaceContact:
    """One original retained pair for inspection; the complete group remains in the report."""
    if type(index) is not int or not 0 <= index < len(group.group.triangle_pairs):
        raise ValueError("Contact-group member must identify an original retained triangle pair")
    first, second = group.group.triangle_pairs[index]
    return ProgramSurfaceContact(
        group.segment_index,
        group.line,
        group.tool,
        group.first,
        group.second,
        SurfaceContact(first, second, group.group.lower, group.group.upper),
        group.source_lower_ratio,
        group.source_upper_ratio,
    )


def rotating_witness(
    report: ProgramSurfaceClearance, row: ProgramRotatingResult
) -> tuple[tuple[Triangle, ...], tuple[float, float, float] | None]:
    """Declared section witness in the other body's moving nominal world frame."""
    selected = row.result
    if selected.witness_point is None:
        return (), None
    segment = report.body_review.segments[row.segment_index]
    machine = machine_from_record(report.body_review.records[row.tool])
    bodies, _ = bodies_from_record(report.body_review.records[row.tool], machine)
    body = next(b for b in bodies if b.name == row.second)
    start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
    a, d = _translation(machine, body, start, end)
    if row.second in report.rotating_envelopes[row.tool]:
        a = a + body_transform(machine, body, dict.fromkeys(start, 0.0)).translation
    qa, qd = qpoint(a.tuple), qpoint(d.tuple)
    shift = tuple(qa[i] + selected.sample * qd[i] for i in range(3))
    values = tuple(float(selected.witness_point[i] + shift[i]) for i in range(3))
    point = values[0], values[1], values[2]
    if selected.witness_triangle is None:
        return (), point
    triangle = report.meshes[row.tool][row.second].triangles[selected.witness_triangle]
    points = tuple(tuple(float(Fraction(p[i]) + shift[i]) for i in range(3)) for p in triangle)
    return (
        (
            (points[0][0], points[0][1], points[0][2]),
            (points[1][0], points[1][1], points[1][2]),
            (points[2][0], points[2][1], points[2][2]),
        ),
        (point, point, point),
    ), point
