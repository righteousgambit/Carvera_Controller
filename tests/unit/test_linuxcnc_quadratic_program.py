import math

import pytest

from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.spline_geometry import linuxcnc_g51_controls, tessellate_cubic

HEADER = "G21 G90 G17 G94 G54\nG0 X-2 Y4 Z0\n(Operation: Quadratic)\n"


def test_documented_parabola_retains_original_controls_and_bounded_midpoint():
    text = HEADER + "G5.1 X2 I2 J-8 F100"
    program = ProgramOperations.from_text(text, dialect="linuxcnc", spline_tolerance_mm=0.001)
    block = program.spline_block(4)
    assert block.source_command == "G5.1"
    assert block.original_control_points_mm == ((-2, 4, 0), (0, -4, 0), (2, 4, 0))
    assert min(math.dist(point, (0, 0, 0)) for point in program.spline_points(4)) <= block.maximum_error_bound_mm
    assert block.maximum_error_bound_mm <= 0.001
    assert program.checkpoints[-1].state.motion == 5.1
    assert program.lines == tuple(text.splitlines())
    assert not any(line >= 4 for line in program.unresolved_motion_lines)
    assert all(segment.cutting for segment in program.motion_segments if segment.line_number == 4)


def test_elevated_quadratic_certificate_bounds_the_original_polynomial():
    controls, original = linuxcnc_g51_controls((0, 0, 0), (10, 0, 0), {"I": -30, "J": 10}, plane="G17", unit_scale=1)
    result = tessellate_cubic(controls, tolerance_mm=0.002)
    for i, (low, high) in enumerate(zip(result.parameters, result.parameters[1:])):
        for fraction in (0, 0.25, 0.5, 0.75, 1):
            t = low + fraction * (high - low)
            exact = tuple(
                (1 - t) ** 2 * original[0][a] + 2 * t * (1 - t) * original[1][a] + t * t * original[2][a]
                for a in range(3)
            )
            chord = tuple(
                result.points_mm[i][a] * (1 - fraction) + result.points_mm[i + 1][a] * fraction for a in range(3)
            )
            assert math.dist(exact, chord) <= result.maximum_error_bound_mm


@pytest.mark.parametrize("offset", ["I2", "J-8"])
def test_independently_optional_offsets_and_modal_quadratic_blocks(offset):
    program = ProgramOperations.from_text(HEADER + f"G5.1 X2 {offset} F100\nX4 {offset}", dialect="linuxcnc")
    assert [block.source_command for block in program.spline_blocks] == ["G5.1", "G5.1"]
    assert not any(line >= 4 for line in program.unresolved_motion_lines)


def test_incremental_inch_endpoints_do_not_change_start_relative_control_offsets():
    program = ProgramOperations.from_text("G20 G90 G17 G94 G54\nG0 X1 Y1 Z0\nG91 G5.1 X1 I0 J1 F10", dialect="linuxcnc")
    block = program.spline_blocks[0]
    for actual, expected in zip(block.original_control_points_mm, ((25.4, 25.4, 0), (25.4, 50.8, 0), (50.8, 25.4, 0))):
        assert actual == pytest.approx(expected)


@pytest.mark.parametrize(
    "command",
    ["G5.1 X2", "G5.1 X2 I0 J0", "G5.1 X2 I2 P1", "G5.1 X2 I2 Z0", "G18 G5.1 X2 I2", "G1 G5.1 X2 I2", "G5.1 X2 I2 I3"],
)
def test_invalid_quadratic_never_publishes_geometry(command):
    program = ProgramOperations.from_text(HEADER + command, dialect="linuxcnc")
    assert not program.spline_blocks
    assert 4 in program.unresolved_motion_lines
    assert not any(segment.line_number == 4 for segment in program.motion_segments)


def test_default_carvera_rejects_quadratic_and_following_unknown_modal_motion():
    program = ProgramOperations.from_text(HEADER + "G5.1 X2 I2 J-8\nG1 X4")
    assert not program.spline_blocks
    assert {4, 5} <= set(program.unresolved_motion_lines)


def test_quadratic_interruption_does_not_supply_cubic_chain_offsets():
    text = HEADER + "G5 I2 J3 P0 Q-3 X2 Y2 F100\nG5.1 X4 I2\nG5 X6 P0 Q-3"
    program = ProgramOperations.from_text(text, dialect="linuxcnc")
    assert [block.source_command for block in program.spline_blocks] == ["G5", "G5.1"]
    assert 6 in program.unresolved_motion_lines


def test_segment_budget_applies_across_both_spline_degrees_without_truncation():
    program = ProgramOperations.from_text(HEADER + "G5.1 X2 I2 J-8 F100", dialect="linuxcnc", max_spline_segments=1)
    assert not program.spline_blocks and 4 in program.unresolved_motion_lines


def test_mixed_cubic_and_quadratic_share_the_whole_program_segment_budget():
    text = "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\nG5 X3 I1 J0 P-1 Q0 F100\nG5.1 X4 I1 J1"
    program = ProgramOperations.from_text(text, dialect="linuxcnc", max_spline_segments=1)
    assert [block.source_command for block in program.spline_blocks] == ["G5"]
    assert program.spline_blocks[0].segments == 1
    assert 4 in program.unresolved_motion_lines
    assert not any(segment.line_number == 4 for segment in program.motion_segments)


def test_quadratic_inverse_time_is_per_block_and_never_per_converted_segment():
    program = ProgramOperations.from_text(
        HEADER + "G93 G5.1 X2 I2 J-8 F2", dialect="linuxcnc", spline_tolerance_mm=0.001
    )
    assert program.spline_blocks[0].segments > 1
    assert program.operations[-1].estimated_seconds == pytest.approx(30)
