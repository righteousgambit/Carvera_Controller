"""First retained CAD surface/solid contacts and complete nominal machine poses."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction as F
from typing import Literal

from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_surface_clearance import (
    ProgramSolidInterval,
    ProgramSurfaceClearance,
    ProgramSurfaceContact,
    ProgramSurfaceContactGroup,
    SurfaceGap,
    _translation,
    group_member_contact,
)
from carveracontroller.machine.surface_motion import QPoint, SurfaceBudget, qpoint, triangle_interval


@dataclass(frozen=True)
class ContactBodyPose:
    name: str
    translation_mm: QPoint
    rotation: tuple[float, ...]


@dataclass(frozen=True)
class ContactPose:
    segment_index: int
    line: int
    tool: int
    sample: F
    joints_mm: QPoint
    bodies: tuple[ContactBodyPose, ...]


@dataclass(frozen=True)
class CadFirstContact:
    tool: int
    first: str
    second: str
    state: Literal["initial_overlap", "surface_entry", "contained", "separated", "unavailable"]
    segment_index: int | None
    lower: F | None = None
    upper: F | None = None
    pose: ContactPose | None = None
    surface: ProgramSurfaceContact | None = None
    group: ProgramSurfaceContactGroup | None = None
    occupancy: ProgramSolidInterval | None = None
    earliest_proven: bool = False
    reason: str = ""


@dataclass(frozen=True)
class CadFirstContactStudy:
    source_sha256: str
    pairs: tuple[CadFirstContact, ...]
    timeline_rows: int
    original_group_members: int
    surface_counts: tuple[int, int, int]
    qualification: str = (
        "Earliest retained CAD surface/closed-solid contact per ordered tool/body pair, including initial "
        "containment and every geometry gap. Complete source records determine the earliest move/time; identical "
        "exact-interval groups retain all original members. The selected original face pair is independently "
        "rechecked at the original relative chord and outward position/curve allowance. Earlier or same-move "
        "unknown initial occupancy prevents an earliest volume-contact claim. Each pose retains exact rational "
        "XYZ joints and every declared body's nominal rigid placement; display conversion is approximate. "
        "Explicit exclusions and original source/curve coverage still apply. Rotating results remain separate. "
        "Measured registration, manufactured geometry, effective compensation, backend execution, current "
        "physical start and machining approval remain unqualified."
    )


def contact_pose(
    report: ProgramSurfaceClearance,
    tool: int,
    move: int,
    sample: F,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    budget: SurfaceBudget | None = None,
) -> ContactPose:
    """All retained body placements at an exact parameter of the original source move."""
    if type(sample) is not F or not 0 <= sample <= 1 or not 0 <= move < len(report.body_review.segments):
        raise ValueError("Contact pose requires a retained move and exact parameter in [0,1]")
    segment = report.body_review.segments[move]
    if segment.tool_id != str(tool):
        raise ValueError("Contact pose tool differs from its retained source move")
    machine = machine_from_record(report.body_review.records[tool])
    bodies, _ = bodies_from_record(report.body_review.records[tool], machine)
    qs, qe = qpoint(segment.start.tuple), qpoint(segment.end.tuple)
    values = tuple(qs[j] + sample * (qe[j] - qs[j]) for j in range(3))
    joints: QPoint = values[0], values[1], values[2]
    start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
    zero = dict.fromkeys(start, 0.0)
    poses = []
    for body in bodies:
        if budget is not None:
            budget.consume("nodes")
        if cancelled():
            raise InterruptedError("CAD contact pose cancelled; no partial report")
        origin = body_transform(machine, body, zero)
        if any(body_transform(machine, body, values).rotation != origin.rotation for values in (start, end)):
            raise ValueError("CAD contact pose requires the retained translation-only rigid placements")
        a, delta = _translation(machine, body, start, end)
        qa, qd, qo = qpoint(a.tuple), qpoint(delta.tuple), qpoint(origin.translation.tuple)
        values = tuple(qo[j] + qa[j] + sample * qd[j] for j in range(3))
        poses.append(ContactBodyPose(body.name, (values[0], values[1], values[2]), origin.rotation))
    return ContactPose(move, segment.line, tool, sample, joints, tuple(poses))


def locate_cad_first_contacts(
    report: ProgramSurfaceClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda *_: None,
    budget: SurfaceBudget | None = None,
) -> CadFirstContactStudy:
    """Scan complete retained timelines; never pick a convenient pair or omit unknown geometry."""
    row_sets: tuple[
        Sequence[ProgramSurfaceContact | ProgramSurfaceContactGroup | ProgramSolidInterval | SurfaceGap], ...
    ] = (report.contacts, report.groups, report.occupancy, report.gaps)
    total = sum(len(rows) for rows in row_sets)
    if total > 100_000 or len(report.body_review.segments) > 20_000:
        raise ValueError("CAD first-contact complete timeline exceeds shared result budget")
    active = budget or SurfaceBudget()
    prior = active.cancelled
    active.cancelled = lambda: cancelled() or prior()
    pairs: dict[
        tuple[int, str, str],
        list[tuple[str, ProgramSurfaceContact | ProgramSurfaceContactGroup | ProgramSolidInterval | SurfaceGap]],
    ] = {}
    group_members = 0
    seen_groups: set[tuple[int, int, str, str]] = set()
    visited = 0
    try:
        for kind, source_rows in zip(("surface", "group", "solid", "gap"), row_sets):
            for row in source_rows:
                active.consume("nodes")
                if not 0 <= row.segment_index < len(report.body_review.segments):
                    raise ValueError("CAD first-contact record lies outside the retained timeline")
                key = row.tool, row.first, row.second
                pairs.setdefault(key, []).append((kind, row))
                if isinstance(row, ProgramSurfaceContactGroup):
                    identity = id(row.group), *key
                    if identity not in seen_groups:
                        if len(seen_groups) >= 10_000 or group_members + len(row.group.triangle_pairs) > 100_000:
                            raise ValueError("CAD first-contact complete original-member budget exhausted")
                        if not row.group.triangle_pairs:
                            raise ValueError("CAD contact group has no original face members")
                        meshes = report.meshes[row.tool]
                        for face_a, face_b in row.group.triangle_pairs:
                            active.consume("nodes")
                            if not 0 <= face_a < len(meshes[row.first].triangles) or not 0 <= face_b < len(
                                meshes[row.second].triangles
                            ):
                                raise ValueError("CAD contact group contains an invalid original face")
                        group_members += len(row.group.triangle_pairs)
                        seen_groups.add(identity)
                visited += 1
                if visited % 64 == 0 or visited == total:
                    progress(visited, total)
        results = []
        for (tool, first, second), pair_rows in sorted(pairs.items()):
            active.consume("nodes")
            positives: list[
                tuple[int, F, int, ProgramSurfaceContact | ProgramSurfaceContactGroup | ProgramSolidInterval]
            ] = []
            unknown = []
            for kind, value in pair_rows:
                if isinstance(value, ProgramSurfaceContact):
                    positives.append((value.segment_index, value.contact.lower, 0, value))
                elif isinstance(value, ProgramSurfaceContactGroup):
                    positives.append((value.segment_index, value.group.lower, 0, value))
                elif isinstance(value, ProgramSolidInterval) and value.interval.state == "contained":
                    positives.append((value.segment_index, value.interval.lower, 1, value))
                elif isinstance(value, SurfaceGap):
                    unknown.append(value.segment_index)
            if not positives:
                results.append(
                    CadFirstContact(
                        tool,
                        first,
                        second,
                        "unavailable" if unknown else "separated",
                        min(unknown) if unknown else None,
                        earliest_proven=not unknown,
                        reason="Solid/geometry coverage unavailable"
                        if unknown
                        else "Complete retained CAD pair timeline separated",
                    )
                )
                continue
            move, time, _, candidate = min(positives, key=lambda p: p[:3])
            if not 0 <= time <= 1:
                raise ValueError("CAD contact entry lies outside its source move")
            covered = not any(i < move or (i == move and time > 0) for i in unknown)
            surface = occupancy = group = None
            if isinstance(candidate, ProgramSolidInterval):
                occupancy_interval = candidate.interval
                if not occupancy_interval.lower_closed:
                    raise ValueError(
                        "First contained interval has an open lower endpoint; earlier surface evidence required"
                    )
                occupancy = replace(candidate, interval=replace(occupancy_interval, sample=time))
                state: Literal["initial_overlap", "surface_entry", "contained", "separated", "unavailable"] = (
                    "contained"
                )
            else:
                group = candidate if isinstance(candidate, ProgramSurfaceContactGroup) else None
                selected = (
                    group_member_contact(candidate, 0)
                    if isinstance(candidate, ProgramSurfaceContactGroup)
                    else candidate
                )
                segment = report.body_review.segments[move]
                machine = machine_from_record(report.body_review.records[tool])
                bodies, _ = bodies_from_record(report.body_review.records[tool], machine)
                by_name = {b.name: b for b in bodies}
                start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
                a, da = _translation(machine, by_name[first], start, end)
                b, db = _translation(machine, by_name[second], start, end)
                same = (by_name[first].frame, by_name[first].joint_count) == (
                    by_name[second].frame,
                    by_name[second].joint_count,
                )
                bounds = {line: error for line, _command, error in report.body_review.curve_enclosures}
                error = 1e-6 + (0.0 if same else 2 * bounds.get(segment.line, 0.0) * (1 + 1e-7))
                active.consume("pairs")
                original = selected.contact
                meshes = report.meshes[tool]
                expected_interval = triangle_interval(
                    meshes[first].triangles[original.first_triangle],
                    meshes[second].triangles[original.second_triangle],
                    (a - b).tuple,
                    (da - db).tuple,
                    position_error_mm=error,
                )
                if expected_interval != (original.lower, original.upper):
                    raise ValueError("Selected CAD face pair differs from its retained exact interval")
                active.consume("contacts")
                source = F(segment.source_start_ratio) + time * (
                    F(segment.source_end_ratio) - F(segment.source_start_ratio)
                )
                surface = replace(
                    selected,
                    contact=replace(original, lower=time, upper=time),
                    source_lower_ratio=source,
                    source_upper_ratio=source,
                )
                state = "initial_overlap" if time == 0 else "surface_entry"
            results.append(
                CadFirstContact(
                    tool,
                    first,
                    second,
                    state,
                    move,
                    time,
                    time,
                    contact_pose(report, tool, move, time, cancelled=active.cancelled, budget=active),
                    surface,
                    group,
                    occupancy,
                    covered,
                    "Earlier initial solid/geometry coverage unavailable"
                    if not covered
                    else "Nominal declared CAD contact; outward allowance retained",
                )
            )
        progress(total, total)
        if active.cancelled():
            raise InterruptedError("CAD first-contact study cancelled; no partial report")
        return CadFirstContactStudy(
            report.body_review.program_hash,
            tuple(results),
            visited,
            group_members,
            (active.nodes, active.pairs, active.contacts),
        )
    finally:
        active.cancelled = prior
