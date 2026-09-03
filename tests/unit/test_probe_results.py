"""Tests for parsing probing cycle output."""

import pytest

from carveracontroller.machine.probe_results import (
    ProbeResultKind,
    format_probe_result,
    parse_probe_result,
)

# Exactly as ZProbe.cpp prints them.
_BORE = """Distance Point 2 X surfaces (Diameter) is: 25.412 and center is stored at variable #151
Distance between 2 Y surfaces (Diameter) is: 25.478 and is stored at variable #152
Center of bore or rectangular pocket found. Ready to Zero X and Y
Center Point is: -150.221 , -90.118 and is stored in MCS as #154,#155""".splitlines()

# Note "Betweeen" -- three E's. That typo is upstream and only in the boss cycle.
_BOSS = """Distance Betweeen 2 X surfaces (Diameter) is: 40.002 and is stored at variable #151
Distance Betweeen 2 Y surfaces (Diameter) is: 39.998 and is stored at variable #152
Center of Boss or Rectangular Block found. Ready to Zero X and Y
Center Point is: -100.500 , -60.250 and is stored in MCS as #154,#155""".splitlines()

_CORNER = ["Corner found. X coordinate stored in #154 as MCS -181.223 , Y coordinate in #155 as MCS -121.887 "]

_ANGLE = [
    "Probing 2 points to find an angle",
    "Measurement 1: Angle from X Axis is: 1.204 degrees or 0.021 radians",
    "Average angle from X Axis is: 1.187 degrees or 0.021 radians and is stored in radians at variable #153",
]


def test_bore_is_parsed():
    result = parse_probe_result(_BORE)

    assert result.kind is ProbeResultKind.BORE
    assert result.x_diameter == pytest.approx(25.412)
    assert result.y_diameter == pytest.approx(25.478)
    assert result.centre_x == pytest.approx(-150.221)
    assert result.centre_y == pytest.approx(-90.118)


def test_boss_is_parsed_despite_the_upstream_typo():
    """The boss cycle prints "Betweeen". Matching it is not optional."""
    result = parse_probe_result(_BOSS)

    assert result.kind is ProbeResultKind.BOSS
    assert result.x_diameter == pytest.approx(40.002)
    assert result.y_diameter == pytest.approx(39.998)


def test_corner_is_parsed():
    result = parse_probe_result(_CORNER)

    assert result.kind is ProbeResultKind.CORNER
    assert result.corner_x == pytest.approx(-181.223)
    assert result.corner_y == pytest.approx(-121.887)


def test_angle_is_parsed_from_the_average_not_a_single_measurement():
    result = parse_probe_result(_ANGLE)

    assert result.kind is ProbeResultKind.ANGLE
    assert result.angle_degrees == pytest.approx(1.187)
    assert result.angle_reference == "X"


def test_angle_is_taken_in_degrees():
    """The firmware claims #153 holds radians; the value it prints and stores
    is degrees. Parsing the degrees figure avoids the question entirely."""
    result = parse_probe_result(_ANGLE)
    assert result.angle_degrees > 1.0


def test_probe_failure_is_reported_rather_than_parsed_as_a_measurement():
    result = parse_probe_result(["ERROR: Probe fail: first point not found"])

    assert result.kind is ProbeResultKind.FAILURE
    assert "first point" in result.error


def test_failure_wins_over_partial_output():
    lines = [*_BORE, "ERROR: Probe fail: second point not found"]
    assert parse_probe_result(lines).kind is ProbeResultKind.FAILURE


def test_unrelated_output_parses_to_nothing():
    assert parse_probe_result(["ok", "<Idle|MPos:0,0,0>", "Distance moved: 5.000"]) is None


def test_ovality_is_the_difference_between_axes():
    """The wear signature: a bore going out of round reports it in microns."""
    result = parse_probe_result(_BORE)

    assert result.ovality == pytest.approx(0.066, abs=1e-9)
    assert result.mean_diameter == pytest.approx(25.445)


def test_ovality_is_unavailable_when_only_one_axis_was_probed():
    single = ["Distance Point 2 X surfaces (Diameter) is: 25.412 and center is stored at variable #151"]
    result = parse_probe_result(single)

    assert result.x_diameter == pytest.approx(25.412)
    assert result.ovality is None
    assert result.mean_diameter == pytest.approx(25.412)


def test_ovality_is_never_negative():
    result = parse_probe_result(_BOSS)
    assert result.ovality == pytest.approx(0.004, abs=1e-9)


def test_formatting_shows_ovality_in_microns():
    text = format_probe_result(parse_probe_result(_BORE))

    assert "Ovality" in text
    assert "66 um" in text


def test_formatting_a_failure_returns_the_error():
    result = parse_probe_result(["ERROR: Probe fail: first point not found"])
    assert "first point" in format_probe_result(result)


def test_formatting_aligns_the_value_column():
    import re

    lines = format_probe_result(parse_probe_result(_BORE)).splitlines()
    # Where the value begins, i.e. the first non-space after the padding.
    starts = {re.search(r"\s\s+(\S)", line).start(1) for line in lines}

    assert len(starts) == 1, f"values should start in one column, got {starts}"
