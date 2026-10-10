"""Full declared C1 CAD review of one detached retained-stock tool approach."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from types import MappingProxyType
from typing import Any, cast

from carveracontroller.addons.manufacturing_simulation import SimulationSegment, Vec3
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget
from carveracontroller.machine.joint_clearance import bodies_from_record, review_joint_clearance
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance, ProgramBodyContact
from carveracontroller.machine.program_surface_clearance import ProgramSurfaceClearance, refine_program_surfaces
from carveracontroller.machine.stock_allowance import CellAllowance
from carveracontroller.machine.surface_motion import ContactGroupBudget, SurfaceBudget


@dataclass(frozen=True)
class ApproachClearance:
    inspection: CellAllowance
    parent: ProgramSurfaceClearance
    proposal_sha256: str
    machine_start_mm: tuple[float, float, float]
    machine_end_mm: tuple[float, float, float]
    scene: ProgramSurfaceClearance
    replaced_initial_stock: str
    included_bodies: tuple[str, ...]
    qualification: str = (
        "One detached +Z insertion at the declared selected tool-tip coordinates and WCS datum, not motion from the actual current pose. "
        "Complete retained C1 machine/workholding/ATC geometry and selected-tool stickout are reviewed continuously, "
        "including fixed assembly pairs and explicit geometry/solid/holder gaps. Selected initial stock is replaced by "
        "this inspection's target contacts and remaining-stock center-grid noncutting estimate; other stock remains initial. "
        "No automatic tool-exchange motion, controller tool-length/offset reconciliation, actual assembly, backend, forces "
        "or physical registration/clearance is qualified. This proposal is not executable G-code."
    )


def review_stock_approach(
    inspection: CellAllowance,
    report: ProgramSurfaceClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    max_intervals: int = 50_000,
    surface_budget: SurfaceBudget | None = None,
    solid_budget: SolidBudget | None = None,
    group_budget: ContactGroupBudget | None = None,
) -> ApproachClearance:
    def check() -> None:
        if cancelled():
            raise InterruptedError("Full machine approach review cancelled; no partial result")

    check()
    analysis = inspection.analysis
    target = analysis.target
    if any(
        a is not b
        for a, b in zip(target.bindings, (report.body_review, report.stock_evolution, report.rotating_envelopes))
    ):
        raise ValueError("Cell inspection belongs to a different retained machine/stock review")
    approach = inspection.approach
    if approach is None or report.stock_evolution is None:
        raise ValueError("Inspect a reviewed tool approach before full machine review")
    tool = approach.tool
    if tool not in report.body_review.records or tool not in report.meshes:
        raise ValueError("Selected tool has no retained machine record and CAD surfaces")
    original = report.body_review.records[tool]
    original_bytes = encoded(original)
    record = deepcopy(cast(dict[str, Any], original))
    machine = machine_from_record(record)
    links = machine.tool_chain + machine.work_chain
    if (
        tuple(j.name for j in links) != ("X", "Z", "Y")
        or any(j.kind != "linear" for j in links)
        or tuple(j.axis.tuple for j in links) != ((1, 0, 0), (0, 0, 1), (0, -1, 0))
        or len(machine.tool_chain) != 2
    ):
        raise ValueError("Approach needs the retained C1 tool-tip and negative-Y table mapping")
    bodies, exclusions = bodies_from_record(record, machine)
    selected = tuple(b for b in bodies if b.name != target.stock)
    if len(selected) != len(bodies) - 1 or target.stock not in report.stock_evolution.inputs.stocks:
        raise ValueError("Selected initial stock must be explicitly replaced by its retained inspection")
    # Only the selected initial stock declaration is replaced. All machine,
    # fixture/vise/ATC bodies, other stocks and explicit exclusions remain.
    record["collision_bodies"] = [row for row in record["collision_bodies"] if row["name"] != target.stock]
    record["collision_exclusions"] = [pair for pair in record["collision_exclusions"] if target.stock not in pair]
    selected, exclusions = bodies_from_record(record, machine)
    offset = Vec3(*report.stock_evolution.inputs.stocks[target.stock][0])
    start, end = Vec3(*approach.start) + offset, Vec3(*approach.end) + offset
    states = [dict(zip(("X", "Y", "Z"), p.tuple)) for p in (start, end)]
    broad = review_joint_clearance(
        machine, states, selected, exclusions, max_intervals=max_intervals, cancelled=cancelled
    )
    proposal = {
        "kind": "retained-cell-tool-insertion",
        "parent_program": report.body_review.program_hash,
        "target": target.source_sha256,
        "stock": target.stock,
        "state": inspection.label,
        "state_fit": {
            "excess": dict(analysis.fits[inspection.label].excess),
            "missing": dict(analysis.fits[inspection.label].missing),
        },
        "target_translation_mm": target.translation_mm,
        "selected_move": analysis.segment_index,
        "cell": inspection.cell,
        "tool": tool,
        "machine_start": start.tuple,
        "machine_end": end.tuple,
        "parent_record_sha256": sha256(original_bytes).hexdigest(),
    }
    digest = sha256(encoded(proposal)).hexdigest()
    segment = SimulationSegment(start, end, str(tool), False, line=1)
    contacts = tuple(ProgramBodyContact(0, 1, tool, c.lower_fraction, c.upper_fraction, c) for c in broad.contacts)
    origin = record["scene_source"]
    body = ProgramBodyClearance(
        digest,
        1,
        1,
        (segment,),
        MappingProxyType({tool: record}),
        ((tool, str(origin["scene_digest"])),),
        contacts,
        (),
        (),
        (),
        broad.tested_pairs,
        broad.intervals,
        broad.tolerance_mm,
        broad.status,
    )
    meshes = MappingProxyType(
        {tool: MappingProxyType({name: mesh for name, mesh in report.meshes[tool].items() if name != target.stock})}
    )
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
            group_budget=groups,
            grouped=True,
            rotating_envelopes={tool: report.rotating_envelopes[tool]},
        )
    finally:
        for value, prior in callbacks:
            value.cancelled = prior
    check()
    if any("budget" in gap.reason.lower() or "exhaust" in gap.reason.lower() for gap in scene.gaps):
        raise ValueError("Full machine approach exhausted a shared budget; no partial result")
    if encoded(original) != original_bytes:
        raise ValueError("Retained machine declaration changed during approach review; result withheld")
    return ApproachClearance(
        inspection, report, digest, start.tuple, end.tuple, scene, target.stock, tuple(b.name for b in selected)
    )
