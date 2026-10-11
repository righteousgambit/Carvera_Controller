"""Retained complete C1 geometry, coordinate placement and bounded approach review."""

from copy import deepcopy
from dataclasses import replace
from types import MappingProxyType

import pytest

from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.stock_allowance import inspect_target_cell
from carveracontroller.machine.stock_approach_clearance import review_stock_approach
from carveracontroller.machine.surface_motion import SurfaceBudget
from tests.unit.test_stock_allowance import example


def test_full_scene_retains_bodies_and_selected_tool_placement(tmp_path):
    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    before = encoded(report.body_review.records[2])
    result = review_stock_approach(cell, report)
    offset = report.stock_evolution.inputs.stocks[analysis.target.stock][0]
    assert result.machine_start_mm == tuple(a + b for a, b in zip(cell.approach.start, offset))
    assert result.machine_end_mm == tuple(a + b for a, b in zip(cell.approach.end, offset))
    original = {r["name"] for r in report.body_review.records[2]["collision_bodies"]}
    assert set(result.included_bodies) == original - {analysis.target.stock}
    assert any(n.startswith("fixture") for n in result.included_bodies)
    assert any(n.startswith("atc") for n in result.included_bodies)
    assert result.scene.body_review.tested_pairs > 0 and result.scene.refined_pairs > 0
    assert result.scene.contact_mode == "groups" and result.scene.rotating
    assert encoded(report.body_review.records[2]) == before
    assert result.inspection is cell and result.parent is report
    assert "not executable" in result.qualification
    assert analysis.target.stock not in result.scene.meshes[2]


@pytest.mark.parametrize("change", ["review", "distance_only", "tool", "stock", "bounds", "budget", "cancel"])
def test_refuse_invalid_binding_or_partial_candidate(tmp_path, change):
    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    kwargs = {}
    if change == "review":
        report = replace(report, body_review=replace(report.body_review))
    elif change == "distance_only":
        cell = replace(cell, approach=None)
    elif change == "tool":
        report = replace(report, meshes={})
    elif change == "stock":
        records = deepcopy(dict(report.body_review.records))
        records[2]["collision_bodies"] = [
            b for b in records[2]["collision_bodies"] if b["name"] != analysis.target.stock
        ]
        # Retained binding is the same object: the declaration itself was altered.
        report.body_review.records[2]["collision_bodies"] = records[2]["collision_bodies"]
    elif change == "bounds":
        cell = replace(cell, approach=replace(cell.approach, start=(1000, 0, 3)))
    elif change == "budget":
        kwargs["max_intervals"] = 1
    elif change == "cancel":
        kwargs["cancelled"] = lambda: True
    with pytest.raises((ValueError, InterruptedError)):
        review_stock_approach(cell, report, **kwargs)


def test_changed_stickout_uses_its_own_retained_spindle_mesh(tmp_path):
    report, analysis = example(tmp_path, short=True)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    result = review_stock_approach(cell, report)
    spindle = next(n for n in result.scene.meshes[2] if n.startswith("spindle"))
    assert result.scene.meshes[2][spindle] is report.meshes[2][spindle]
    assert result.scene.body_review.records[2]["scene_source"]["tool_number"] == 2
    assert "controller tool-length/offset reconciliation" in result.qualification


def test_external_budget_callbacks_restored_and_honored(tmp_path):
    from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget
    from carveracontroller.machine.surface_motion import ContactGroupBudget

    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    budgets = SurfaceBudget(), SolidBudget(), ContactGroupBudget()
    prior = tuple(b.cancelled for b in budgets)
    review_stock_approach(cell, report, surface_budget=budgets[0], solid_budget=budgets[1], group_budget=budgets[2])
    assert tuple(b.cancelled for b in budgets) == prior
    budgets[0].cancelled = lambda: True
    callback = budgets[0].cancelled
    with pytest.raises(InterruptedError):
        review_stock_approach(cell, report, surface_budget=budgets[0])
    assert budgets[0].cancelled is callback


def test_placement_and_continuation_masks_change_proposal_identity(tmp_path):
    report, analysis = example(tmp_path)
    first = review_stock_approach(inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2), report)
    changed = replace(analysis, target=replace(analysis.target, translation_mm=(0.1, 0, 0)))
    second = review_stock_approach(inspect_target_cell(changed, "Initial stock", (1, 1, 0), tool=2), report)
    assert first.proposal_sha256 != second.proposal_sha256


def test_full_chord_retains_obstacle_contact_between_endpoints(tmp_path):
    from carveracontroller.machine.surface_motion import SurfaceMesh
    from tests.unit.test_stock_solid import box

    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2, approach_clearance_mm=6)
    offset = report.stock_evolution.inputs.stocks[analysis.target.stock][0]
    from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
    from carveracontroller.machine.kinematic_review import machine_from_record

    machine = machine_from_record(report.body_review.records[2])
    bodies, _ = bodies_from_record(report.body_review.records[2], machine)
    cutter = next(b for b in bodies if "cutter" in b.name)
    joints = dict(zip(("X", "Y", "Z"), (a + b for a, b in zip(cell.approach.end, offset))))
    x, y, z = body_transform(machine, cutter, joints).translation.tuple
    # Thin world obstacle is crossed by the tip in the middle of its insertion.
    lo, hi = (x - 0.1, y - 0.1, z + 5.5), (x + 0.1, y + 0.1, z + 5.6)
    obstacle = {
        "name": "Thin insertion obstacle",
        "frame": "world",
        "joint_count": 0,
        "minimum_mm": lo,
        "maximum_mm": hi,
    }
    report.body_review.records[2]["collision_bodies"].append(obstacle)
    meshes = {tool: dict(rows) for tool, rows in report.meshes.items()}
    meshes[2][obstacle["name"]] = SurfaceMesh.create(box(lo, hi))
    report = replace(report, meshes=MappingProxyType(meshes))
    result = review_stock_approach(cell, report)
    crossed = [
        r
        for r in result.scene.rotating
        if r.second == obstacle["name"] and r.first == cutter.name and r.result.state == "possible_contact"
    ]
    assert crossed and any(0 < r.result.sample < 1 for r in crossed)
    assert all(r.result.witness_triangle is not None for r in crossed)
    assert obstacle["name"] in result.included_bodies

    for endpoint in (cell.approach.start, cell.approach.end):
        at_endpoint = replace(cell, approach=replace(cell.approach, start=endpoint, end=endpoint))
        endpoint_scene = review_stock_approach(at_endpoint, report).scene
        assert not any(
            r.first == cutter.name and r.second == obstacle["name"] and r.result.state == "possible_contact"
            for r in endpoint_scene.rotating
        )
