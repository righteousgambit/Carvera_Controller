"""Transition diagnostics must follow the entered route, not shortcut endpoints."""

from unittest.mock import Mock

import pytest

from carveracontroller.machine import joint_path_review as paths
from carveracontroller.machine.kinematic_review import example_profile, machine_from_record


def machine_and_state(topology="Head / head"):
    machine = machine_from_record(example_profile(topology))
    return machine, {j.name: 0.0 for j in machine.tool_chain + machine.work_chain}


def test_good_endpoints_can_cross_a_dependent_posture():
    machine, state = machine_and_state()
    result = paths.review_joint_path(machine, [dict(state, B=-30), dict(state, B=30)], 5)
    assert len(result.samples) == 31
    assert result.samples[0].rank == result.samples[-1].rank == (5, 5)
    assert 15 in result.singular_indices
    assert result.samples[15].positions["B"] == 0
    assert result.samples[15].rank == (4, 5)
    assert result.largest_tip_chord_error_mm > 0.6
    assert result.joint_travel["B"] == 60


def test_full_rotary_turn_is_not_replaced_by_nearest_equivalent():
    machine, state = machine_and_state()
    result = paths.review_joint_path(machine, [dict(state, B=30), dict(state, B=30, C=360)], 10, rotary_step_deg=30)
    assert len(result.samples) == 13
    assert result.joint_travel["C"] == 360
    assert result.samples[6].positions["C"] == 180
    assert result.samples[-1].positions["C"] == 360
    assert result.largest_tip_chord_error_mm > 9.9
    assert result.largest_axis_step_deg > 14


@pytest.mark.parametrize("topology", ["Head / head", "Head / table", "Table / table"])
def test_each_sample_is_the_declared_forward_pose_and_respects_spacing(topology):
    machine, state = machine_and_state(topology)
    start = dict(state, B=15, C=-10, X=-5)
    middle = dict(state, B=20, C=10, X=10)
    end = dict(state, B=25, C=25, X=20)
    result = paths.review_joint_path(machine, [start, middle, end], 7, linear_step_mm=1, rotary_step_deg=3)
    assert result.samples[0].positions == start
    assert result.samples[-1].positions == end
    assert sum(sample.positions == middle for sample in result.samples) == 1
    for sample in result.samples:
        pose = machine.forward(sample.positions, 7)
        assert sample.tip_mm == pose.tooltip_work
        assert sample.axis == pose.axis_in_work
        assert min(sample.limit_margin.values()) >= 0
    for first, second in zip(result.samples, result.samples[1:]):
        for joint in machine.tool_chain + machine.work_chain:
            bound = 1 if joint.kind == "linear" else 3
            assert abs(second.positions[joint.name] - first.positions[joint.name]) <= bound + 1e-9


def test_every_waypoint_and_total_budget_validate_before_rank_work(monkeypatch):
    machine, state = machine_and_state()
    rank = Mock()
    monkeypatch.setattr(paths, "local_rank", rank)
    for points, kwargs in (
        ([state, dict(state, B=130)], {}),
        ([state, dict(state, C=720)], {"rotary_step_deg": 0.001}),
        ([state, dict(state, X=1)], {"linear_step_mm": 1e-320}),
        ([state, dict(state, X=100), state], {"linear_step_mm": 0.08}),
    ):
        with pytest.raises(ValueError):
            paths.review_joint_path(machine, points, 5, **kwargs)
    rank.assert_not_called()


@pytest.mark.parametrize(
    "kwargs",
    [{"tool_length_mm": -1}, {"linear_step_mm": 0}, {"rotary_step_deg": True}, {"rotary_step_deg": float("nan")}],
)
def test_invalid_review_parameters(kwargs):
    machine, state = machine_and_state()
    with pytest.raises(ValueError):
        paths.review_joint_path(machine, [state, state], **dict({"tool_length_mm": 5}, **kwargs))


def test_cancellation_discards_a_partial_path(monkeypatch):
    machine, state = machine_and_state()
    original = paths.local_rank
    count = 0

    def rank(*args):
        nonlocal count
        count += 1
        return original(*args)

    monkeypatch.setattr(paths, "local_rank", rank)
    assert paths.review_joint_path(machine, [state, dict(state, B=30)], 5, cancelled=lambda: count >= 3) is None
    assert count == 3


def test_stationary_route_has_two_samples_and_zero_travel():
    machine, state = machine_and_state()
    result = paths.review_joint_path(machine, [state, state], 0)
    assert len(result.samples) == 2
    assert all(travel == 0 for travel in result.joint_travel.values())
    assert result.largest_tip_step_mm == result.largest_axis_step_deg == result.largest_tip_chord_error_mm == 0
