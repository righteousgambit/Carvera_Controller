"""Whole generated finishing path against retained C1 machine/workholding CAD."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, fields, is_dataclass
from fractions import Fraction
from hashlib import sha256
from types import MappingProxyType
from typing import Any, cast

from carveracontroller.addons.manufacturing_simulation import SimulationSegment, Vec3
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget
from carveracontroller.machine.joint_clearance import bodies_from_record, review_joint_clearance
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_first_contact import FirstContactStudy, locate_first_contacts
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance, ProgramBodyContact
from carveracontroller.machine.program_surface_clearance import ProgramSurfaceClearance, refine_program_surfaces
from carveracontroller.machine.stock_generated_finish import GeneratedFinish, generate_stock_finish
from carveracontroller.machine.surface_motion import ContactGroupBudget, SurfaceBudget


@dataclass(frozen=True)
class GeneratedMachineClearance:
    plan: GeneratedFinish
    parent: ProgramSurfaceClearance
    proposal_sha256: str
    scene: ProgramSurfaceClearance
    replaced_initial_stock: str
    included_bodies: tuple[str, ...]
    qualification: str = (
        "Every complete generated linear move, including zero-length transfers, cutting entries, rasters and retracts, "
        "is reviewed at the retained intended tool-tip coordinates and stock datum. Full declared C1 moving machine, "
        "fixture, vise, ATC and other initial stock bodies remain included with their explicit exclusions. Only the "
        "selected initial stock body is replaced by the regenerated plan's complete target/noncutting and all-state "
        "remaining-stock comparisons. Rigid geometry data may be shared; every move retains its result wrappers. "
        "Contacts and geometry/solid/holder gaps remain evidence to inspect, not machining approval. The declared "
        "above-stock starting pose is synthetic; live approach, tool exchange, effective controller compensation, "
        "manufactured geometry, backend execution and physical clearance remain unqualified. No G-code or motion is supplied."
    )


def locate_generated_first_contacts(
    result: GeneratedMachineClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int, int], None] = lambda *_: None,
    surface_budget: SurfaceBudget | None = None,
    solid_budget: SolidBudget | None = None,
) -> FirstContactStudy:
    """Keep source/material identity bound around a separate first-contact study."""

    def verify() -> None:
        if (
            result.scene.body_review.program_hash != result.proposal_sha256
            or _context(result.plan, result.parent, cancelled) != result.proposal_sha256
        ):
            raise ValueError("Generated path or machine context changed; first-contact study withheld")

    verify()
    study = locate_first_contacts(
        result.scene, cancelled=cancelled, progress=progress, surface_budget=surface_budget, solid_budget=solid_budget
    )
    verify()
    return study


def _record(value: Any) -> Any:
    """Exact recursive records without deepcopying retained mapping proxies."""
    if isinstance(value, Fraction):
        return {"numerator": str(value.numerator), "denominator": str(value.denominator)}
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _record(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, Mapping):
        return {str(k): _record(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_record(v) for v in value]
    return value


def _context(plan: GeneratedFinish, parent: ProgramSurfaceClearance, cancelled: Callable[[], bool]) -> str:
    target = plan.analysis.target
    evolution = parent.stock_evolution
    if evolution is None:
        raise ValueError("Generated path needs retained stock evolution")
    geometry = {}
    for name, mesh in parent.meshes[plan.tool].items():
        digest = sha256()
        for index, triangle in enumerate(mesh.triangles):
            if index % 64 == 0 and cancelled():
                raise InterruptedError("Generated machine context cancelled; no partial result")
            digest.update(encoded(triangle) + b"\n")
        geometry[name] = (len(mesh.triangles), digest.hexdigest())
    payload = {
        "kind": "complete-retained-generated-flat-finish-C1",
        "parent_program": parent.body_review.program_hash,
        "machine": parent.body_review.records[plan.tool],
        "meshes": geometry,
        "rotating": _record(parent.rotating_envelopes[plan.tool]),
        "stocks": _record(evolution.inputs.stocks),
        "tools": _record(evolution.inputs.tools),
        "target": {
            "source": (target.source_sha256, target.source_units),
            "translation_mm": target.translation_mm,
            "triangles": target.solid.mesh.triangles_mm,
            "initial": dict(target.initial),
            "grid": dict(target.target),
            "fits": _record(plan.analysis.fits),
            "move": (plan.analysis.segment_index, plan.analysis.line),
        },
        "plan": {f.name: _record(getattr(plan, f.name)) for f in fields(plan) if f.name != "analysis"},
    }
    raw = encoded(payload)
    if len(raw) > 64 * 1024 * 1024:
        raise ValueError("Generated machine identity exceeds complete 64 MiB budget; no partial result")
    if cancelled():
        raise InterruptedError("Generated machine context cancelled; no partial result")
    return sha256(raw).hexdigest()


def review_generated_finish(
    plan: GeneratedFinish,
    parent: ProgramSurfaceClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[str, int, int], None] = lambda _phase, _done, _total: None,
    max_intervals: int = 50_000,
    max_tested_pairs: int = 250_000,
    max_shared_rows: int = 100_000,
    surface_budget: SurfaceBudget | None = None,
    solid_budget: SolidBudget | None = None,
    group_budget: ContactGroupBudget | None = None,
) -> GeneratedMachineClearance:
    def check() -> None:
        if cancelled():
            raise InterruptedError("Full generated machine review cancelled; no partial result")

    check()
    target = plan.analysis.target
    if any(
        a is not b
        for a, b in zip(target.bindings, (parent.body_review, parent.stock_evolution, parent.rotating_envelopes))
    ):
        raise ValueError("Generated path belongs to a different retained machine/stock review")
    if (
        plan.tool not in parent.body_review.records
        or plan.tool not in parent.meshes
        or plan.tool not in parent.rotating_envelopes
    ):
        raise ValueError("Generated path tool has no retained machine/surface/envelope declarations")
    # Recreate every move, witness, target contact, and all stock-state outcomes.
    # A replaced/forged frozen dataclass cannot carry stale material evidence.
    verified = generate_stock_finish(
        plan.analysis,
        plan.tool,
        cancelled=cancelled,
        progress=progress,
        stepover_mm=plan.stepover_mm,
        patch_length_mm=plan.patch_length_mm,
        allowance_mm=plan.allowance_mm,
        stepdown_mm=plan.stepdown_mm,
        clearance_mm=plan.clearance_mm,
    )
    if verified != plan or not plan.moves:
        raise ValueError("Generated path/material evidence differs from complete regeneration")
    progress("Retain complete generated machine context", 0, 1)
    digest = _context(plan, parent, cancelled)
    progress("Retain complete generated machine context", 1, 1)
    record = deepcopy(cast(dict[str, Any], parent.body_review.records[plan.tool]))
    machine = machine_from_record(record)
    links = machine.tool_chain + machine.work_chain
    if (
        tuple(j.name for j in links) != ("X", "Z", "Y")
        or any(j.kind != "linear" for j in links)
        or tuple(j.axis.tuple for j in links) != ((1, 0, 0), (0, 0, 1), (0, -1, 0))
        or len(machine.tool_chain) != 2
    ):
        raise ValueError("Generated machine review needs the retained C1 tool-tip/negative-Y mapping")
    bodies, _ = bodies_from_record(record, machine)
    if sum(b.name == target.stock for b in bodies) != 1:
        raise ValueError("Selected initial stock must be explicitly replaced by the generated all-state comparison")
    record["collision_bodies"] = [r for r in record["collision_bodies"] if r["name"] != target.stock]
    record["collision_exclusions"] = [p for p in record["collision_exclusions"] if target.stock not in p]
    bodies, exclusions = bodies_from_record(record, machine)
    offset = Vec3(*plan.stock_offset_mm)
    segments = tuple(
        SimulationSegment(Vec3(*m.start) + offset, Vec3(*m.end) + offset, str(plan.tool), m.cutting, line=i + 1)
        for i, m in enumerate(plan.moves)
    )
    if any(a.end != b.start for a, b in zip(segments, segments[1:])):
        raise ValueError("Generated machine path must retain every contiguous move")
    points = (segments[0].start,) + tuple(s.end for s in segments)
    broad = review_joint_clearance(
        machine,
        [dict(zip(("X", "Y", "Z"), p.tuple)) for p in points],
        bodies,
        exclusions,
        cancelled=cancelled,
        max_intervals=max_intervals,
        reuse_rigid_pairs=True,
        body_position_error_mm=1e-6,
        linear_enclosures=True,
        max_tested_pairs=max_tested_pairs,
        progress=lambda done, total: progress("Complete moving-machine bounding pairs", done, total),
    )
    body = ProgramBodyClearance(
        digest,
        1,
        len(segments),
        segments,
        MappingProxyType({plan.tool: record}),
        ((plan.tool, str(record["scene_source"]["scene_digest"])),),
        tuple(
            ProgramBodyContact(c.segment, c.segment + 1, plan.tool, c.lower_fraction, c.upper_fraction, c)
            for c in broad.contacts
        ),
        (),
        (),
        (),
        broad.tested_pairs,
        broad.intervals,
        broad.tolerance_mm,
        broad.status,
        qualification=broad.qualification,
    )
    meshes = {plan.tool: {name: mesh for name, mesh in parent.meshes[plan.tool].items() if name != target.stock}}
    budget = surface_budget or SurfaceBudget(cancelled=cancelled)
    solids = solid_budget or SolidBudget(cancelled=cancelled)
    groups = group_budget or ContactGroupBudget(cancelled=cancelled)
    callbacks = tuple((value, value.cancelled) for value in (budget, solids, groups))

    def combined(prior: Callable[[], bool] | None) -> Callable[[], bool]:
        return lambda: cancelled() or bool(prior and prior())

    for value, prior in callbacks:
        value.cancelled = combined(prior)
    try:
        scene = refine_program_surfaces(
            body,
            meshes,
            budget=budget,
            solid_budget=solids,
            grouped=True,
            group_budget=groups,
            rotating_envelopes={plan.tool: parent.rotating_envelopes[plan.tool]},
            reuse_rigid_pairs=True,
            reuse_complete_chords=True,
            max_shared_rows=max_shared_rows,
            progress=lambda done, total: progress("Complete moving-machine CAD/solids", done, total),
        )
    finally:
        for value, prior in callbacks:
            value.cancelled = prior
    check()
    if digest != _context(plan, parent, cancelled):
        raise ValueError("Retained generated path or machine context changed; complete result withheld")
    progress("Complete generated machine review", len(segments), len(segments))
    return GeneratedMachineClearance(plan, parent, digest, scene, target.stock, tuple(b.name for b in bodies))
