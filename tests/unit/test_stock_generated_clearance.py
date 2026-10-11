"""Complete nominal generated machine path, material identity and shared bounds."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.stock_generated_clearance import review_generated_finish
from carveracontroller.machine.stock_generated_finish import generate_stock_finish
from carveracontroller.machine.surface_motion import ContactGroupBudget, SurfaceBudget, SurfaceMesh
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_solid import box


def prepared(tmp_path):
    report, analysis = example(tmp_path)
    return report, generate_stock_finish(analysis, 2)


def test_all_moves_machine_coordinates_workholding_and_material_states_retained(tmp_path):
    parent, plan = prepared(tmp_path)
    before = encoded(parent.body_review.records[2])
    phases = []
    result = review_generated_finish(plan, parent, progress=lambda *p: phases.append(p))
    assert result.plan is plan and result.parent is parent
    assert len(result.scene.body_review.segments) == len(plan.moves) > 3
    for i, (segment, move) in enumerate(zip(result.scene.body_review.segments, plan.moves)):
        assert segment.line == i + 1 and segment.cutting == move.cutting and segment.tool_id == "2"
        assert segment.start.tuple == tuple(a + b for a, b in zip(move.start, plan.stock_offset_mm))
        assert segment.end.tuple == tuple(a + b for a, b in zip(move.end, plan.stock_offset_mm))
    assert result.scene.rigid_reused_pairs > 0
    assert set(result.included_bodies) == {r["name"] for r in parent.body_review.records[2]["collision_bodies"]} - {
        plan.analysis.target.stock
    }
    assert any(n.startswith("fixture") for n in result.included_bodies)
    assert any(n.startswith("atc") for n in result.included_bodies)
    assert plan.analysis.target.stock not in result.scene.meshes[2]
    assert len(result.plan.states) == 4 and all(s.newly_missing_mm3 == 0 for s in result.plan.states.values())
    assert result.scene.body_review.tested_pairs > len(plan.moves)
    assert encoded(parent.body_review.records[2]) == before
    assert phases[-1] == ("Complete generated machine review", len(plan.moves), len(plan.moves))


@pytest.mark.parametrize("change", ["move", "material", "offset", "tool", "parent"])
def test_forged_or_different_context_never_uses_stale_material_evidence(tmp_path, change):
    parent, plan = prepared(tmp_path)
    if change == "move":
        plan = replace(plan, moves=(replace(plan.moves[0], end=(0, 0, 0)),) + plan.moves[1:])
    elif change == "material":
        states = dict(plan.states)
        label = next(iter(states))
        states[label] = replace(states[label], removed_mm3=100)
        plan = replace(plan, states=MappingProxyType(states))
    elif change == "offset":
        plan = replace(plan, stock_offset_mm=(1, 2, 3))
    elif change == "tool":
        plan = replace(plan, tool=1)
    else:
        parent = replace(parent, body_review=replace(parent.body_review))
    with pytest.raises(ValueError):
        review_generated_finish(plan, parent)


def test_exact_shared_thresholds_refuse_whole_operation_and_restore_external_callbacks(tmp_path):
    parent, plan = prepared(tmp_path)
    result = review_generated_finish(plan, parent)
    scene = result.scene
    count = sum(len(getattr(scene, f)) for f in ("contacts", "groups", "occupancy", "rotating", "gaps"))
    exact = {
        "max_intervals": scene.body_review.intervals,
        "max_tested_pairs": scene.body_review.tested_pairs,
        "max_shared_rows": count,
    }
    assert review_generated_finish(plan, parent, **exact).proposal_sha256 == result.proposal_sha256
    for name, value in exact.items():
        with pytest.raises(ValueError, match="budget"):
            review_generated_finish(plan, parent, **{name: value - 1})
    budgets = SurfaceBudget(), SolidBudget(), ContactGroupBudget()
    callbacks = tuple(b.cancelled for b in budgets)
    review_generated_finish(plan, parent, surface_budget=budgets[0], solid_budget=budgets[1], group_budget=budgets[2])
    assert tuple(b.cancelled for b in budgets) == callbacks
    budgets[0].cancelled = lambda: True
    callback = budgets[0].cancelled
    with pytest.raises(InterruptedError):
        review_generated_finish(plan, parent, surface_budget=budgets[0])
    assert budgets[0].cancelled is callback


def test_mid_review_context_change_refuses_complete_delivery(tmp_path):
    parent, plan = prepared(tmp_path)

    def progress(phase, done, total):
        if phase == "Complete moving-machine CAD/solids" and done == total:
            parent.body_review.records[2]["scene_source"]["scene_digest"] = "changed"

    with pytest.raises(ValueError, match="context changed"):
        review_generated_finish(plan, parent, progress=progress)


def test_mid_chord_obstacle_is_retained_and_source_linked(tmp_path):
    parent, plan = prepared(tmp_path)
    cut = next((i, m) for i, m in enumerate(plan.moves) if m.kind == "Raster cut")
    i, move = cut
    midpoint = tuple((a + b) / 2 + c for a, b, c in zip(move.start, move.end, plan.stock_offset_mm))
    # The retained zero tool-frame translation is part of its declaration.
    from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
    from carveracontroller.machine.kinematic_review import machine_from_record

    machine = machine_from_record(parent.body_review.records[2])
    bodies, _ = bodies_from_record(parent.body_review.records[2], machine)
    cutter = next(b for b in bodies if b.name == "T2 cutter")
    point = body_transform(machine, cutter, dict(zip(("X", "Y", "Z"), midpoint))).translation.tuple
    point = point[0], point[1] + 0.45, point[2]
    # Entire thin box is outside the radius-.5 cutter at both endpoints;
    # an interior portion of the horizontal chord reaches it.
    from math import hypot, sqrt

    for endpoint in (move.start, move.end):
        joints = dict(zip(("X", "Y", "Z"), (a + b for a, b in zip(endpoint, plan.stock_offset_mm))))
        center = body_transform(machine, cutter, joints).translation.tuple
        assert hypot(center[0] - point[0], center[1] - point[1]) > 0.5 + sqrt(2) * 0.03
    lo, hi = tuple(v - 0.03 for v in point), tuple(v + 0.03 for v in point)
    name = "Thin attachment obstacle"
    parent.body_review.records[2]["collision_bodies"].append(
        {"name": name, "frame": "world", "joint_count": 0, "minimum_mm": lo, "maximum_mm": hi}
    )
    rows = {n: dict(m) for n, m in parent.meshes.items()}
    rows[2][name] = SurfaceMesh.create(box(lo, hi))
    parent = replace(parent, meshes=rows)
    result = review_generated_finish(plan, parent)
    assert any(r.segment_index == i and r.second == name for r in result.scene.rotating)
    assert name in result.included_bodies


@pytest.mark.parametrize(
    "phase",
    [
        "Replay Initial stock",
        "Retain complete generated machine context",
        "Complete moving-machine bounding pairs",
        "Complete moving-machine CAD/solids",
    ],
)
def test_cancel_at_each_full_review_stage_withholds_partial_result(tmp_path, phase):
    parent, plan = prepared(tmp_path)
    active = [False]

    def progress(name, *_):
        if name == phase:
            active[0] = True

    with pytest.raises(InterruptedError):
        review_generated_finish(plan, parent, progress=progress, cancelled=lambda: active[0])
