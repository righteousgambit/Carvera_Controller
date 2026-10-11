"""Corner dynamics remain explicit instead of inventing a blended controller path."""

from unittest.mock import Mock

import pytest

from carveracontroller.machine.inverse_time import JointSample, JointVelocityLimit, joint_velocity_transitions


def study(points, fractions, seconds=10, **kwargs):
    return joint_velocity_transitions(
        seconds,
        tuple(JointSample(f, (("A", q),)) for f, q in zip(fractions, points)),
        (JointVelocityLimit("A", "rotary", 100, "declared test limit"),),
        **kwargs,
    )


def test_nonuniform_intervals_preserve_signed_rates_and_reversal_time():
    corners = study([350, 10, 30], [0, 0.2, 1])
    assert len(corners) == 1
    corner = corners[0]
    assert corner.fraction == 0.2 and corner.name == "A" and corner.kind == "rotary"
    assert corner.before_per_second == -170  # no invented +20-degree wrapping
    assert corner.after_per_second == 2.5
    assert corner.velocity_change_per_second == 172.5
    assert corner.reverses


def test_stationary_interval_is_a_stop_and_restart_not_a_direct_reversal():
    corners = study([0, 10, 10, 0], [0, 0.25, 0.5, 1])
    assert [(c.before_per_second, c.after_per_second) for c in corners] == [(4, 0), (0, -2)]
    assert all(not c.reverses for c in corners)


def test_constant_rate_and_two_endpoint_motion_do_not_invent_start_stop():
    assert study([0, 1, 4, 10], [0, 0.1, 0.4, 1]) == ()
    assert study([0, 360], [0, 1]) == ()
    assert study([0, 0, 0], [0, 0.5, 1]) == ()


def test_same_direction_rate_change_remains_visible():
    (corner,) = study([0, 10, 30], [0, 0.5, 1])
    assert (corner.before_per_second, corner.after_per_second) == (2, 4)
    assert not corner.reverses


def test_changed_rate_cancellation_withholds_the_whole_result():
    with pytest.raises(InterruptedError):
        study([0, 10, 0], [0, 0.5, 1], cancelled=lambda: True)


def test_invalid_complete_path_is_rejected_before_cancellation_callback():
    cancel = Mock(return_value=False)
    with pytest.raises(ValueError):
        study([0, 10, 0], [0, 0.5, 0.5], cancelled=cancel)
    cancel.assert_not_called()


def test_output_budget_refuses_a_large_alternating_nine_joint_route():
    limits = tuple(JointVelocityLimit(str(i), "linear", 1, "declared") for i in range(9))
    samples = tuple(JointSample(i / 1200, tuple((str(j), float(i % 2)) for j in range(9))) for i in range(1201))
    with pytest.raises(ValueError, match="10000 velocity changes"):
        joint_velocity_transitions(1, samples, limits)


def test_overflowing_jump_is_rejected_without_a_partial_report():
    with pytest.raises(ValueError, match="velocity change"):
        study([0, 1e308, 0], [0, 0.5, 1], seconds=2)
