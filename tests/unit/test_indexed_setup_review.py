"""Fixed indexing must preserve work frames, tip geometry and declared travel."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
from carveracontroller.addons.manufacturing_simulation.kinematics import Joint, MachineKinematics, Transform
from carveracontroller.machine.indexed_setup_review import review_indexed_setup
from carveracontroller.machine.joint_path_review import review_joint_path
from carveracontroller.machine.kinematic_review import example_profile, machine_from_record


@pytest.mark.parametrize("topology", ["Head / head", "Head / table", "Table / table"])
def test_mapping_and_linear_chords_for_rotated_frames_pivots_and_tip(topology):
    record = example_profile(topology)
    for joint in record["tool_chain"] + record["work_chain"]:
        if joint["kind"] == "rotary":
            joint["pivot"] = [12, -7, 18]
    machine = replace(
        machine_from_record(record),
        tool_base=Transform.rotation_about(Vec3(0, 0, 1), 15, Vec3(2, 3, 4)),
        work_base=Transform.rotation_about(Vec3(1, 0, 0), 20, Vec3(-5, 8, 3)),
    )
    fixed = {"B": 35, "C": 200}
    states = [dict(fixed, X=10, Y=-20, Z=35), dict(fixed, X=45, Y=15, Z=-30)]
    targets = [machine.forward(state, 37).tooltip_work for state in states]
    review = review_indexed_setup(machine, fixed, targets, 37)
    assert review is not None
    assert review.fixed_rotary == fixed
    for expected, point in zip(states, review.points):
        assert point.positions == pytest.approx(expected, abs=1e-8)
        assert point.tip_error_mm < 1e-8
        assert min(point.limit_margin.values()) > 0
    route = review_joint_path(machine, [point.positions for point in review.points], 37)
    assert route is not None
    assert route.joint_travel["B"] == route.joint_travel["C"] == 0
    assert route.largest_tip_chord_error_mm < 1e-8
    assert route.largest_axis_step_deg < 1e-5


def test_linear_axes_in_work_chain_and_non_orthogonal_basis():
    machine = MachineKinematics(
        tool_chain=(Joint("B", "rotary", Vec3(0, 1, 0), -100, 100),),
        work_chain=(
            Joint("U", "linear", Vec3(1, 0, 0), -200, 200),
            Joint("V", "linear", Vec3(0.6, 0.8, 0), -200, 200),
            Joint("W", "linear", Vec3(0, 0, 1), -200, 200),
        ),
    )
    state = {"B": 40, "U": 20, "V": -10, "W": 35}
    target = machine.forward(state, 12).tooltip_work
    result = review_indexed_setup(machine, {"B": 40}, [target], 12)
    assert result.points[0].positions == pytest.approx(state)
    assert result.basis_determinant == pytest.approx(-0.8)


@pytest.mark.parametrize("fixed", [{}, {"B": 30}, {"B": 30, "C": 0, "X": 0}, {"B": True, "C": 0}, {"B": 121, "C": 0}])
def test_exact_rotary_state_and_numeric_limits(fixed):
    machine = machine_from_record(example_profile("Head / head"))
    with pytest.raises(ValueError):
        review_indexed_setup(machine, fixed, [Vec3(0, 0, 0)], 5)


def test_unreachable_second_point_rejects_whole_route():
    machine = machine_from_record(example_profile("Head / head"))
    with pytest.raises(ValueError, match="Work point 2 exceeds declared travel"):
        review_indexed_setup(machine, {"B": 0, "C": 0}, [Vec3(0, 0, 0), Vec3(250, 0, 0)], 5)


def test_dependent_linear_axes_rejected_before_mapping():
    machine = machine_from_record(example_profile("Head / head"))
    joints = list(machine.tool_chain)
    joints[1] = replace(joints[1], axis=joints[0].axis)
    with pytest.raises(ValueError, match="dependent"):
        review_indexed_setup(replace(machine, tool_chain=tuple(joints)), {"B": 30, "C": 0}, [Vec3(0, 0, 0)], 5)


@pytest.mark.parametrize(
    "targets,length",
    [([], 5), ([Vec3(0, 0, 0)] * 9, 5), ([Vec3(0, 0, 0)], -1), ([Vec3(0, 0, 0)], True), (["0 0 0"], 5)],
)
def test_input_bounds_before_forward_work(targets, length):
    machine = Mock(wraps=machine_from_record(example_profile("Head / head")))
    machine.tool_chain = machine._mock_wraps.tool_chain
    machine.work_chain = machine._mock_wraps.work_chain
    with pytest.raises(ValueError):
        review_indexed_setup(machine, {"B": 30, "C": 0}, targets, length)
    machine.forward.assert_not_called()


def test_cancellation_discards_even_a_fully_calculated_result():
    machine = machine_from_record(example_profile("Head / head"))
    calls = [0]

    def cancelled():
        calls[0] += 1
        return calls[0] >= 6

    assert review_indexed_setup(machine, {"B": 30, "C": 0}, [Vec3(0, 0, 0)], 5, cancelled=cancelled) is None
