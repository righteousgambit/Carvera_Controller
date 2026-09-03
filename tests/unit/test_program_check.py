"""Tests for static G-code checks against machine limits."""

import os

import pytest

from carveracontroller.machine.program_check import (
    MachineLimits,
    Severity,
    check_program,
)

_HEADER = ["G90 G94", "G17", "G21", "S12000 M3"]


def _codes(issues):
    return {i.code for i in issues}


def _check(body, header=True):
    lines = (_HEADER if header else []) + body
    return check_program(lines)


# ---------------------------------------------------------------- no noise


def test_a_real_program_produces_no_issues():
    """Guards against false positives, which are worse than misses here."""
    path = os.path.join(os.path.dirname(__file__), "..", "resources", "Face 4x4 stock.cnc")
    with open(path) as handle:
        issues = check_program(handle.read().splitlines())

    assert issues == []


def test_s_word_belonging_to_another_mcode_is_not_a_spindle_speed():
    """`M851 S100` sets that M-code's parameter, not 100 RPM."""
    issues = _check(["M851 S100", "M220 S50"])

    assert "rpm-too-low" not in _codes(issues)


# ---------------------------------------------------------------- spindle


def test_rpm_above_machine_maximum_is_an_error():
    issues = _check(["S18000 M3", "G1 X10 F500"])

    assert "rpm-too-high" in _codes(issues)
    assert any(i.severity is Severity.ERROR for i in issues if i.code == "rpm-too-high")


def test_rpm_below_machine_minimum_warns():
    issues = _check(["S400 M3", "G1 X10 F500"])
    assert "rpm-too-low" in _codes(issues)


def test_cutting_with_the_spindle_stopped_is_an_error():
    issues = check_program(["G90", "G21", "G17", "G1 X10 F500"])
    assert "cutting-without-spindle" in _codes(issues)


def test_spindle_stopped_mid_program_is_caught():
    issues = _check(["G1 X10 F500", "M5", "G1 X20 F500"])

    offenders = [i for i in issues if i.code == "cutting-without-spindle"]
    assert len(offenders) == 1
    assert offenders[0].line_number == 7


def test_rapid_moves_do_not_need_the_spindle():
    issues = check_program(["G90", "G21", "G17", "G0 X10 Y10"])
    assert "cutting-without-spindle" not in _codes(issues)


# ------------------------------------------------------------------ feeds


def test_feed_beyond_the_xy_axis_maximum_is_an_error():
    issues = _check(["G1 X50 F4000"])

    assert "feed-too-high" in _codes(issues)
    assert "3000" in next(i.message for i in issues if i.code == "feed-too-high")


def test_z_only_moves_are_held_to_the_lower_z_limit():
    """Z tops out at 2000 mm/min, so 2500 is legal in XY but not in Z."""
    assert "feed-too-high" not in _codes(_check(["G1 X50 F2500"]))
    assert "feed-too-high" in _codes(_check(["G1 Z-5 F2500"]))


def test_feed_is_modal_across_lines():
    """F persists, so the following moves inherit the bad feed and are counted."""
    issues = _check(["G1 X10 F4000", "X20", "X30"])

    feed = [i for i in issues if i.code == "feed-too-high"]
    assert len(feed) == 1
    assert feed[0].occurrences == 3


def test_rapids_are_not_feed_checked():
    issues = _check(["G0 X50 Y50"])
    assert "feed-too-high" not in _codes(issues)


def test_inch_feeds_are_converted_before_comparison():
    """F200 in/min is 5080 mm/min, well past the axis limit."""
    issues = check_program(["G90", "G20", "G17", "S12000 M3", "G1 X5 F200"])
    assert "feed-too-high" in _codes(issues)


# --------------------------------------------------------------- firmware


def test_inch_mode_is_reported_as_an_error():
    """G20 is documented as broken in firmware, not merely unusual."""
    issues = check_program(["G90", "G20", "G17", "S12000 M3", "G1 X1 F100"])

    inch = [i for i in issues if i.code == "inch-mode"]
    assert inch and inch[0].severity is Severity.ERROR


# ------------------------------------------------------------------ tools


def test_tool_outside_the_atc_range_warns():
    issues = _check(["M6 T9"])
    assert "tool-outside-atc" in _codes(issues)


def test_tool_inside_the_atc_range_is_quiet():
    issues = _check(["M6 T4"])
    assert "tool-outside-atc" not in _codes(issues)


def test_atc_slot_count_is_configurable():
    issues = check_program(["G90", "G21", "M6 T4"], MachineLimits(atc_tool_slots=3))
    assert "tool-outside-atc" in _codes(issues)


# ----------------------------------------------------------------- header


def test_missing_units_and_distance_mode_warn():
    issues = check_program(["S12000 M3", "G1 X1 F100"])

    assert "units-not-set" in _codes(issues)
    assert "distance-mode-not-set" in _codes(issues)


def test_arc_before_any_plane_selection_warns():
    issues = check_program(["G90", "G21", "S12000 M3", "G2 X10 Y10 I5 J0 F500"])
    assert "arc-without-plane" in _codes(issues)


# ------------------------------------------------------------- mechanics


def test_comments_are_ignored():
    issues = _check(["(S18000 would be too fast)", "; S18000 as well", "G1 X1 F100"])
    assert "rpm-too-high" not in _codes(issues)


def test_issues_are_returned_in_program_order():
    issues = _check(["S18000 M3", "G1 X1 F9000"])
    assert [i.line_number for i in issues] == sorted(i.line_number for i in issues)


@pytest.mark.parametrize("blank", ["", "   ", "\t", "(only a comment)"])
def test_blank_and_comment_only_lines_raise_nothing(blank):
    """A line with no words must never be attributed an issue."""
    issues = check_program(["G90", "G21", "G17", blank])

    assert [i for i in issues if i.line_number == 4] == []


# ------------------------------------------------------------ laser mode


def test_laser_power_is_not_read_as_spindle_speed():
    """After M321 the machine is in laser mode and S is beam power.

    A real LightBurn program in the examples produced 134,000 bogus
    'rpm-too-low' findings before this was handled.
    """
    issues = check_program(["M321", "G17 G21", "G90", "M3", "G1 X10 S200 F600"])

    assert "rpm-too-low" not in _codes(issues)


def test_laser_cutting_moves_do_not_require_a_spindle():
    issues = check_program(["M321", "G17 G21 G90", "M3", "G1 X10 F600"])
    assert "cutting-without-spindle" not in _codes(issues)


def test_spindle_checks_still_apply_before_laser_mode():
    issues = check_program(["G17 G21 G90", "S18000 M3", "G1 X1 F100", "M321"])
    assert "rpm-too-high" in _codes(issues)


# ------------------------------------------------------- S word ownership


def test_dwell_seconds_are_not_a_spindle_speed():
    """`G4 S1` is a one-second dwell. The probing test program is full of them."""
    issues = _check(["G4 S1", "G1 X1 F100"])

    assert "rpm-too-low" not in _codes(issues)


def test_collet_index_on_a_tool_change_is_not_a_spindle_speed():
    issues = _check(["M6 T1 S5"])
    assert "rpm-too-low" not in _codes(issues)


# ---------------------------------------------------------- deduplication


def test_repeated_findings_collapse_to_one_with_a_count():
    issues = _check(["G1 X10 F4000", "X20", "X30", "X40"])

    feed = [i for i in issues if i.code == "feed-too-high"]
    assert len(feed) == 1
    assert feed[0].occurrences == 4
    assert feed[0].line_number == 5, "reports the first occurrence"


def test_distinct_codes_are_not_collapsed_together():
    issues = _check(["S18000 M3", "G1 X1 F9000"])

    assert {"rpm-too-high", "feed-too-high"} <= _codes(issues)


def test_single_occurrence_reports_a_count_of_one():
    issues = _check(["G1 X10 F4000"])
    assert next(i for i in issues if i.code == "feed-too-high").occurrences == 1
