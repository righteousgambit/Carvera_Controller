import math

import pytest

from carveracontroller.machine.inverse_time import (
    JointSample,
    JointVelocityLimit,
    analyze_inverse_time,
    joint_velocity_demands,
)
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations

HEADER = "G21 G90 G17 G91.1 G54 G49\nG0 X0 Y0 Z0\n"


def block(text):
    program = ProgramOperations.from_text(HEADER + text, arc_tolerance_mm=0.001)
    return analyze_inverse_time(MoveInspector(program).explain(len(program.lines)))


def test_inverse_time_is_per_block_not_per_arc_chord():
    report = block("G93 G1 X10 F2\nG3 X0 Y10 I-10 J0 F4")
    assert report.seconds == 15
    assert report.sampled_length_mm == pytest.approx(math.pi * 5, rel=0.002)
    assert report.average_path_mm_min == pytest.approx(math.pi * 20, rel=0.002)
    assert report.axis_travel_mm == pytest.approx((10, 10, 0))
    assert not report.issues


def test_inverse_time_is_independent_of_inch_distance_units():
    report = block("G20 G93 G1 X1 F2")
    assert report.seconds == 30
    assert report.sampled_length_mm == pytest.approx(25.4)
    assert report.average_path_mm_min == pytest.approx(50.8)


def test_finite_rate_does_not_overflow_an_unnecessary_sixty_multiplier():
    report = block("G93 G1 X" + "1" + "0" * 307 + " F1")
    assert report.seconds == 60
    assert report.average_path_mm_min == 1e307


@pytest.mark.parametrize("mode", ["G94", "G95"])
def test_feed_mode_transition_does_not_reinterpret_old_inverse_feed(mode):
    program = ProgramOperations.from_text(HEADER + "G93 G1 X10 F2\n" + mode + " G1 X20\nG1 X30 F100")
    inspector = MoveInspector(program)
    assert inspector.explain(4).after.feed is None
    assert inspector.explain(4).feed_description == "Feed unknown"
    assert inspector.explain(5).after.feed == 100


@pytest.mark.parametrize("source", ["G93 G1 X10", "G93 G1 X10 F0", "G93 G1 X10 F-2", "G93 G1 X10 F2 F3"])
def test_invalid_or_missing_per_block_feed_cannot_use_modal_feed(source):
    report = block("G1 X1 F300\n" + source)
    assert report.applicable and report.seconds is None and report.average_path_mm_min is None
    assert report.issues


@pytest.mark.parametrize("source", ["G93 G0 X10 F2", "G93 F2", "G93 G4 P2 F3", "G94 G1 X10 F2"])
def test_rapid_dwell_nonmotion_and_other_feed_modes_are_not_inverse_blocks(source):
    assert not block(source).applicable


def test_comment_feed_and_rotary_geometry_do_not_create_false_demands():
    report = block("G93 G1 X10 (F2) ; F3")
    assert report.seconds is None
    rotary = block("G93 G1 A90 F2")
    assert rotary.seconds == 30
    assert rotary.sampled_length_mm is None and rotary.average_path_mm_min is None
    assert "joint demand unknown" in " ".join(rotary.issues)
    macro = block("G93 G1 X[#1] F2")
    assert macro.seconds is None


def test_supplied_joint_path_checks_rates_without_rotary_shortcut():
    limits = (
        JointVelocityLimit("slide", "linear", 5, "declared fixture machine config"),
        JointVelocityLimit("table", "rotary", 20, "declared fixture machine config"),
    )
    samples = (
        JointSample(0, (("slide", 0), ("table", 350))),
        JointSample(0.5, (("slide", 10), ("table", 180))),
        JointSample(1, (("slide", 11), ("table", 10))),
    )
    demands = joint_velocity_demands(10, samples, limits)
    assert demands[0].maximum_sampled_per_second == 2 and not demands[0].exceeds_limit
    assert demands[1].maximum_sampled_per_second == 34 and demands[1].exceeds_limit
    assert demands[1].kind == "rotary" and demands[1].limit_source == limits[1].source


@pytest.mark.parametrize("seconds", [0, -1, float("inf"), float("nan")])
def test_joint_duration_must_be_finite_positive(seconds):
    with pytest.raises(ValueError):
        joint_velocity_demands(seconds, (), ())


@pytest.mark.parametrize(
    "samples",
    [
        (JointSample(0.1, (("a", 0),)), JointSample(1, (("a", 1),))),
        (JointSample(0, (("a", 0),)), JointSample(0, (("a", 1),)), JointSample(1, (("a", 2),))),
        (JointSample(0, (("a", 0),)), JointSample(1, (("b", 1),))),
        (JointSample(0, (("a", 0),)), JointSample(1, (("a", 1), ("a", 2)))),
        (JointSample(0, (("a", 0),)), JointSample(1, (("a", float("nan")),))),
    ],
)
def test_incomplete_or_invalid_joint_paths_are_refused(samples):
    with pytest.raises(ValueError):
        joint_velocity_demands(1, samples, (JointVelocityLimit("a", "rotary", 10, "declared test profile"),))
