"""Branch review tests use declared geometry without a controller backend."""

import copy
from unittest.mock import Mock

import pytest

from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
from carveracontroller.addons.manufacturing_simulation.kinematics import inverse_kinematics
from carveracontroller.machine import kinematic_review as review


@pytest.mark.parametrize("topology", ["Head / head", "Head / table", "Table / table"])
def test_declared_topologies_recover_known_pose(topology):
    machine = review.machine_from_record(review.example_profile(topology))
    joints = machine.tool_chain + machine.work_chain
    known = {j.name: 30.0 if j.name in ("B", "C") else 15.0 for j in joints}
    pose = machine.forward(known, 5)
    seed = {j.name: known[j.name] + 2 for j in joints}
    results = review.review_branches(machine, pose.tooltip_work, pose.axis_in_work, [seed, known], 5)
    assert len(results) == 2
    for branch in results:
        assert branch.result.converged
        assert branch.result.tip_error_mm < 0.01
        assert branch.result.axis_error < 0.001
        assert all(margin >= 0 for margin in branch.limit_margin.values())
        assert branch.equivalent_positions is not None


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf"), 10**1000, 1e7])
def test_invalid_geometry_numbers(value):
    record = review.example_profile("Head / head")
    record["tool_chain"][0]["maximum"] = value
    with pytest.raises(ValueError):
        review.machine_from_record(record)


def test_profile_rejects_tcp_claim_duplicate_joint_and_invalid_rotation():
    original = review.example_profile("Head / head")
    mutations = [dict(original, controller_tcp_supported=True), dict(original, schema=True)]
    duplicate = copy.deepcopy(original)
    duplicate["tool_chain"][1]["name"] = "X"
    mutations.append(duplicate)
    mutations.append(dict(original, work_base={"rotation": [0] * 9}))
    for record in mutations:
        with pytest.raises(ValueError):
            review.machine_from_record(record)


def test_all_seeds_validate_before_solver(monkeypatch):
    machine = review.machine_from_record(review.example_profile("Head / head"))
    valid = {j.name: 0.0 for j in machine.tool_chain}
    solve = Mock()
    monkeypatch.setattr(review, "inverse_kinematics", solve)
    with pytest.raises(ValueError):
        review.review_branches(machine, Vec3(0, 0, 0), Vec3(0, 0, 1), [valid, dict(valid, B=121)], 5)
    solve.assert_not_called()


def test_rank_detects_rotary_singularity_and_stays_within_limits():
    machine = review.machine_from_record(review.example_profile("Head / head"))
    seed = {j.name: 0.0 for j in machine.tool_chain}
    assert review.local_rank(machine, seed, 5) == (4, 5)
    assert review.local_rank(machine, dict(seed, B=30), 5) == (5, 5)
    assert review.local_rank(machine, {j.name: j.maximum for j in machine.tool_chain}, 5) == (5, 5)


def test_cancelled_solver_does_not_publish_partial_branches():
    machine = review.machine_from_record(review.example_profile("Head / head"))
    seed = {j.name: 0.0 for j in machine.tool_chain}
    result = inverse_kinematics(machine, Vec3(100, 20, 30), seed, cancelled=lambda: True)
    assert result.reason == "cancelled"
    assert result.iterations == 0
    assert review.review_branches(machine, Vec3(10, 20, 30), Vec3(0, 0, 1), [seed], 5, cancelled=lambda: True) == ()


@pytest.mark.parametrize(
    "kwargs", [{"tolerance_mm": float("nan")}, {"axis_tolerance": float("inf")}, {"max_iterations": True}]
)
def test_invalid_solver_bounds(kwargs):
    machine = review.machine_from_record(review.example_profile("Head / head"))
    seed = {j.name: 0.0 for j in machine.tool_chain}
    with pytest.raises(ValueError):
        inverse_kinematics(machine, Vec3(0, 0, 0), seed, **kwargs)


@pytest.mark.parametrize("extra", [{"name": float("nan")}, {"metadata": float("nan")}, {"name": "x" * 121}])
def test_unbounded_or_unknown_metadata_rejected(extra):
    with pytest.raises(ValueError):
        review.machine_from_record(dict(review.example_profile("Head / head"), **extra))


def test_cancel_between_branches_discards_successful_partial_result(monkeypatch):
    machine = review.machine_from_record(review.example_profile("Head / head"))
    state = {j.name: 0.0 for j in machine.tool_chain}
    pose = machine.forward(state, 5)
    cancelled = False
    real_solve = review.inverse_kinematics

    def solve(*args, **kwargs):
        nonlocal cancelled
        result = real_solve(*args, **kwargs)
        assert result.converged
        cancelled = True
        return result

    monkeypatch.setattr(review, "inverse_kinematics", solve)
    assert (
        review.review_branches(
            machine, pose.tooltip_work, pose.axis_in_work, [state, state], 5, cancelled=lambda: cancelled
        )
        == ()
    )
