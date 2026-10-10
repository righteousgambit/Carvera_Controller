"""Full nonzero route, independent material contacts and captured-pose boundaries."""

from dataclasses import replace

import pytest

from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.stock_allowance import inspect_target_cell
from carveracontroller.machine.stock_approach_clearance import review_stock_approach
from carveracontroller.machine.stock_approach_path import ApproachStart, capture_start, review_route_material
from tests.unit.test_stock_allowance import example


def test_complete_retract_traverse_insertion_and_rapid_stock(tmp_path):
    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    # Start inside occupied stock, then retract and traverse to another cell.
    offset = report.stock_evolution.inputs.stocks[analysis.target.stock][0]
    origin = ApproachStart(tuple(a + b for a, b in zip((0.25, 0.25, 0.25), offset)))
    result = review_stock_approach(cell, report, route_start=origin)
    assert result.leg_labels == ("Retract", "Traverse", "Insertion")
    assert result.waypoints_mm[0] == origin.machine_mm
    assert all(a != b for a, b in zip(result.waypoints_mm, result.waypoints_mm[1:]))
    assert len(result.scene.body_review.segments) == 3
    assert [r.cutting for r in result.material.legs] == [False, False, True]
    assert any(c.component == "cutter" for c in result.material.legs[0].stock_contacts)
    assert all(c.component != "cutter" for c in result.material.legs[-1].stock_contacts)
    assert result.material.legs[-1].target_contacts
    assert len(result.material.target_mesh.triangles) == 12
    assert result.scene.rigid_reused_pairs > 0
    assert "not executable" in result.qualification
    assert result.start_evidence is origin


@pytest.mark.parametrize("failure", ["nodes", "faces", "cells", "cancel"])
def test_all_leg_material_refuses_incomplete_work(tmp_path, failure):
    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    route = review_stock_approach(cell, report, route_start=ApproachStart((-9.0, -5.0, -8.0)))
    kwargs = {"cancelled": lambda: failure == "cancel"}
    if failure == "nodes":
        kwargs["max_nodes"] = 1
    if failure == "faces":
        kwargs["max_faces"] = 1
    if failure == "cells":
        kwargs["max_cell_work"] = 1
    with pytest.raises((ValueError, InterruptedError)):
        review_route_material(cell, route.waypoints_mm, route.leg_labels, **kwargs)


@pytest.mark.parametrize(
    "failure", ["disconnect", "stale", "future", "state", "tool", "length", "wcs", "rotation", "rotary"]
)
def test_capture_requires_same_fresh_idle_packet(failure):
    pose = ObservedPose(10, "Idle", (-9.0, -5.0, -8.0), (0.0, 0.0, 2.0), 2, 30.0, 0.0, 0, 0.0)
    now = 10.2
    connected = True
    if failure == "disconnect":
        connected = False
    if failure == "stale":
        now = 11
    if failure == "future":
        now = 9
    if failure == "state":
        pose = replace(pose, state="Run")
    if failure == "tool":
        pose = replace(pose, tool=1)
    if failure == "length":
        pose = replace(pose, tool_length_mm=None)
    if failure == "wcs":
        pose = replace(pose, wcs_index=None)
    if failure == "rotation":
        pose = replace(pose, rotation_deg=1)
    if failure == "rotary":
        pose = replace(pose, rotary_deg=1)
    with pytest.raises(ValueError):
        capture_start(pose, connected=connected, tool=2, now=now)


def test_captured_metadata_is_bound_and_not_reconciled(tmp_path):
    report, analysis = example(tmp_path)
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    pose = ObservedPose(10, "Idle", (-9.0, -5.0, -8.0), (0.0, 0.0, 2.0), 2, 30.0, 0.0, 0, 0.0)
    first = capture_start(pose, connected=True, tool=2, now=10.1)
    result = review_stock_approach(cell, report, route_start=first)
    second = capture_start(replace(pose, tool_length_mm=31), connected=True, tool=2, now=10.1)
    changed = review_stock_approach(cell, report, route_start=second)
    assert result.start_evidence.observed is pose
    assert result.proposal_sha256 != changed.proposal_sha256
    assert "not reconciled" in result.qualification
    with pytest.raises(ValueError):
        ApproachStart((-1, -2, -3), "Captured Idle status", pose)
