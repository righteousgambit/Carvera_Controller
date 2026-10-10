"""Earliest declared rotating contact per pair, using complete exact prefixes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction as F
from typing import Literal

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, TriangleSolid
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_surface_clearance import (
    ProgramRotatingResult,
    ProgramSurfaceClearance,
    _translation,
)
from carveracontroller.machine.rotating_pair import RotatingSectionReview, review_rotating_pair
from carveracontroller.machine.surface_motion import Point, SurfaceBudget, SurfaceMesh


@dataclass(frozen=True)
class FirstContact:
    tool: int
    first: str
    second: str
    state: Literal["initial_overlap", "bounded_contact", "separated", "unavailable"]
    segment_index: int | None
    lower: F | None = None
    upper: F | None = None
    witness: ProgramRotatingResult | None = None
    earliest_proven: bool = False
    reason: str = ""


@dataclass(frozen=True)
class FirstContactStudy:
    source_sha256: str
    pairs: tuple[FirstContact, ...]
    prefix_queries: int
    surface_counts: tuple[int, int, int]
    solid_counts: tuple[int, int, int, int]
    geometry_gaps: int
    qualification: str = (
        "First declared rotating contact per ordered body pair across the complete retained timeline. "
        "Exact whole-prefix existence queries bound entry time; no pose or angle sampling. Initial boundary "
        "contact and closed-solid containment are retained. Each bracket uses the original outward position/curve "
        "allowance and complete declared sections; shaped assembly pairs use enclosing cylinders. Earlier unavailable "
        "solid records prevent an earliest claim. Nonrotating CAD contacts remain in the parent report. "
        "Explicit exclusions, missing holders, manufactured flutes, physical registration, backend execution "
        "and machining approval remain outside this study."
    )


def locate_first_contacts(
    report: ProgramSurfaceClearance,
    *,
    resolution_bits: int = 20,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda *_: None,
    surface_budget: SurfaceBudget | None = None,
    solid_budget: SolidBudget | None = None,
) -> FirstContactStudy:
    """Refine the first positive move for every retained rotating pair, or refuse whole delivery.

    A complete parent review proves earlier separated moves. Within the first positive
    move, prefix(lo) is separated and a contact witness supplies hi. Initial containment
    is tested before refining boundary contact, including solids fully enclosing a tool.
    """
    if type(resolution_bits) is not int or not 1 <= resolution_bits <= 30:
        raise ValueError("First-contact precision must be from 1 to 30 bits")
    if len(report.rotating) > 100_000 or len(report.body_review.segments) > 20_000:
        raise ValueError("First-contact complete timeline exceeds review budget")
    surface = surface_budget or SurfaceBudget()
    solid = solid_budget or SolidBudget()
    callbacks = ((surface, surface.cancelled), (solid, solid.cancelled))
    queries = 0
    cache: dict[int, TriangleSolid | str] = {}
    grouped: dict[tuple[int, str, str], list[ProgramRotatingResult]] = {}
    for row in report.rotating:
        if cancelled():
            raise InterruptedError("First-contact study cancelled; no partial report")
        if not 0 <= row.segment_index < len(report.body_review.segments):
            raise ValueError("First-contact row lies outside the complete source timeline")
        grouped.setdefault((row.tool, row.first, row.second), []).append(row)
    results = []

    def combined(prior: Callable[[], bool] | None) -> Callable[[], bool]:
        return lambda: cancelled() or bool(prior and prior())

    for budget, prior in callbacks:
        budget.cancelled = combined(prior)
    try:
        for index, ((tool, first, second), rows) in enumerate(sorted(grouped.items())):
            progress(index, len(grouped))
            if cancelled():
                raise InterruptedError("First-contact study cancelled; no partial report")
            positive = [r for r in rows if r.result.state in ("possible_contact", "contained")]
            unknown = [r.segment_index for r in rows if r.result.state == "unavailable"]
            unknown.extend(
                g.segment_index for g in report.gaps if g.tool == tool and {g.first, g.second} == {first, second}
            )
            if not positive:
                results.append(
                    FirstContact(
                        tool,
                        first,
                        second,
                        "unavailable" if unknown else "separated",
                        min(unknown) if unknown else None,
                        earliest_proven=not unknown,
                        reason="Earlier solid/geometry coverage unavailable"
                        if unknown
                        else "Complete retained pair timeline separated",
                    )
                )
                continue
            candidate = min(positive, key=lambda r: r.segment_index)
            move = candidate.segment_index
            segment = report.body_review.segments[move]
            machine = machine_from_record(report.body_review.records[tool])
            bodies, _ = bodies_from_record(report.body_review.records[tool], machine)
            by_name = {b.name: b for b in bodies}
            start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
            a, da = _translation(machine, by_name[first], start, end)
            b, db = _translation(machine, by_name[second], start, end)
            zero = dict.fromkeys(start, 0.0)
            shift = a - b + body_transform(machine, by_name[first], zero).translation
            sections = report.rotating_envelopes[tool]
            if second in sections:
                shift = shift - body_transform(machine, by_name[second], zero).translation
            same = (by_name[first].frame, by_name[first].joint_count) == (
                by_name[second].frame,
                by_name[second].joint_count,
            )
            bounds = {line: bound for line, _command, bound in report.body_review.curve_enclosures}
            error = 1e-6 + (0.0 if same else 2 * bounds.get(segment.line, 0.0) * (1 + 1e-7))
            selected_mesh = report.meshes[tool].get(second)

            def prefix(
                time: F,
                selected_sections: tuple[AxialEnvelope, ...] = sections[first],
                selected_shift: Point = shift.tuple,
                selected_delta: Point = (da - db).tuple,
                mesh: SurfaceMesh | None = selected_mesh,
                other_sections: tuple[AxialEnvelope, ...] = sections.get(second, ()),
                allowance: float = error,
            ) -> tuple[RotatingSectionReview, ...]:
                nonlocal queries
                queries += 1
                return review_rotating_pair(
                    selected_sections,
                    selected_shift,
                    selected_delta,
                    mesh=mesh,
                    other_sections=other_sections,
                    position_error_mm=allowance,
                    surface_budget=surface,
                    solid_budget=solid,
                    cache=cache,
                    directional_bounds=True,
                    upper_time=time,
                )

            def witness(
                row: RotatingSectionReview,
                source: ProgramRotatingResult = candidate,
                lower: F = F(segment.source_start_ratio),
                span: F = F(segment.source_end_ratio) - F(segment.source_start_ratio),
            ) -> ProgramRotatingResult:
                return replace(source, result=row, source_sample_ratio=lower + span * row.sample)

            at_start = prefix(F(0))
            starting = next((r for r in at_start if r.state in ("possible_contact", "contained")), None)
            prior_gap = any(i < move for i in unknown)
            if starting is not None:
                results.append(
                    FirstContact(
                        tool,
                        first,
                        second,
                        "initial_overlap",
                        move,
                        F(0),
                        F(0),
                        witness(starting),
                        not prior_gap,
                        "Earlier coverage unavailable" if prior_gap else starting.reason,
                    )
                )
                continue
            if any(r.state == "unavailable" for r in at_start):
                results.append(
                    FirstContact(
                        tool,
                        first,
                        second,
                        "unavailable",
                        move,
                        witness=candidate,
                        reason="Initial solid occupancy unavailable; earliest volume contact cannot be established",
                    )
                )
                continue
            lo, hi = F(0), candidate.result.sample
            selected = candidate
            if not 0 < hi <= 1:
                raise ValueError("Positive rotating witness must follow the separated initial pose")
            while hi - lo > F(1, 2**resolution_bits):
                mid = (lo + hi) / 2
                tested = prefix(mid)
                hits = [r for r in tested if r.state in ("possible_contact", "contained")]
                if hits:
                    hit = min(hits, key=lambda r: r.sample)
                    if not lo < hit.sample <= mid:
                        raise ValueError("Prefix witness contradicts separated lower prefix")
                    hi, selected = hit.sample, witness(hit)
                elif any(r.state == "unavailable" for r in tested):
                    raise ValueError("Prefix solid coverage unavailable; complete first-contact study withheld")
                else:
                    lo = mid
            results.append(
                FirstContact(
                    tool,
                    first,
                    second,
                    "bounded_contact",
                    move,
                    lo,
                    hi,
                    selected,
                    not prior_gap,
                    "Earlier coverage unavailable" if prior_gap else selected.result.reason,
                )
            )
        progress(len(grouped), len(grouped))
        if cancelled():
            raise InterruptedError("First-contact study cancelled; no partial report")
        return FirstContactStudy(
            report.body_review.program_hash,
            tuple(results),
            queries,
            (surface.nodes, surface.pairs, surface.contacts),
            (solid.nodes, solid.pairs, solid.rays, solid.queries),
            len(report.gaps),
        )
    finally:
        for budget, prior in callbacks:
            budget.cancelled = prior
