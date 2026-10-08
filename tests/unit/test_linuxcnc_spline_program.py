import math

import pytest

from carveracontroller.machine.program_operations import ProgramOperations

HEADER = "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Spline)\n"


def test_documented_cubic_and_chained_controls_keep_native_geometry_and_line_identity():
    text = HEADER + "G5 I0 J3 P0 Q-3 X1 Y1 F100\nG5 P0 Q-3 X2 Y2"
    program = ProgramOperations.from_text(text, dialect="linuxcnc", spline_tolerance_mm=0.001)
    first, second = program.spline_blocks
    assert first.line_number == 4 and second.line_number == 5
    assert first.control_points_mm == ((0, 0, 0), (0, 3, 0), (1, -2, 0), (1, 1, 0))
    assert second.control_points_mm == ((1, 1, 0), (1, 4, 0), (2, -1, 0), (2, 2, 0))
    assert first.maximum_error_bound_mm <= 0.001
    assert len([s for s in program.motion_segments if s.line_number == 4]) == first.segments
    assert all(s.cutting and not s.rapid for s in program.motion_segments if s.line_number >= 4)
    assert program.operations[-1].bounds_mm == ((0, -2, 0), (2, 4, 0))
    assert program.dialect == "linuxcnc" and program.lines == tuple(text.splitlines())
    assert "backend execution unqualified" in " ".join(program.operations[-1].warnings)
    assert not any(line >= 4 for line in program.unresolved_motion_lines)


def test_cubic_point_index_tracks_the_immutable_motion_snapshot():
    program = ProgramOperations.from_text(HEADER + "G5 I0 J3 P0 Q-3 X1 Y1 F100", dialect="linuxcnc")
    points = program.spline_points(4)
    block = program.spline_block(4)
    assert points[0] == block.control_points_mm[0] and points[-1] == block.control_points_mm[-1]
    assert len(points) == block.segments + 1
    assert program.spline_points(2) == () and program.spline_block(2) is None
    assert program.spline_points(4) is points
    program.motion_segments = ()
    assert program.spline_points(4) == () and points[-1] == (1, 1, 0)


def test_default_carvera_analysis_never_silently_accepts_linuxcnc_g5():
    program = ProgramOperations.from_text(HEADER + "G5 I0 J3 P0 Q-3 X1 Y1 F100\nG1 X5")
    assert program.dialect == "carvera" and not program.spline_blocks
    assert {4, 5} <= set(program.unresolved_motion_lines)
    assert not any(segment.line_number >= 4 for segment in program.motion_segments)


def test_inch_offsets_and_incremental_endpoints_are_separate_quantities():
    program = ProgramOperations.from_text(
        "G20 G90 G17 G94 G54\nG0 X1 Y1 Z0\nG91 G5 X1 Y2 I0 J1 P-1 Q0 F10", dialect="linuxcnc"
    )
    controls = program.spline_blocks[0].control_points_mm
    assert controls[0] == pytest.approx((25.4, 25.4, 0))
    assert controls[1] == pytest.approx((25.4, 50.8, 0))
    assert controls[2] == pytest.approx((25.4, 76.2, 0))
    assert controls[3] == pytest.approx((50.8, 76.2, 0))


@pytest.mark.parametrize(
    "block",
    [
        "G5 X1 Y1 P0 Q-3 F100",
        "G5 X1 Y1 I0 P0 Q-3 F100",
        "G5 X1 Y1 I0 J3 P0 F100",
        "G5 X1 Y1 Z0 I0 J3 P0 Q-3 F100",
        "G18 G5 X1 Y1 I0 J3 P0 Q-3 F100",
    ],
)
def test_illegal_g5_blocks_remain_unresolved_and_publish_no_truncated_curve(block):
    program = ProgramOperations.from_text(HEADER + block, dialect="linuxcnc")
    assert 4 in program.unresolved_motion_lines
    assert not program.spline_blocks
    assert not any(segment.line_number == 4 for segment in program.motion_segments)


def test_nonmotion_interruption_cannot_supply_a_previous_cubic_direction():
    program = ProgramOperations.from_text(
        HEADER + "G5 I0 J3 P0 Q-3 X1 Y1 F100\nM5\nG5 P0 Q-3 X2 Y2", dialect="linuxcnc"
    )
    assert len(program.spline_blocks) == 1
    assert 6 in program.unresolved_motion_lines


def test_budget_refusal_preserves_source_and_does_not_create_motion():
    text = HEADER + "G5 I0 J100 P0 Q-100 X100 Y0 F100"
    program = ProgramOperations.from_text(text, dialect="linuxcnc", max_spline_segments=1)
    assert not program.spline_blocks and 4 in program.unresolved_motion_lines
    assert program.lines == tuple(text.splitlines())
    assert any("segment budget" in warning for warning in program.operations[-1].warnings)


def test_spline_length_is_sampled_once_for_nominal_g94_timing():
    program = ProgramOperations.from_text(HEADER + "G5 I1 J0 P-1 Q0 X3 Y0 F60", dialect="linuxcnc")
    assert program.spline_blocks[0].segments == 1
    assert program.operations[-1].estimated_seconds == pytest.approx(3)
    assert math.dist(program.motion_segments[-1].start_mm, program.motion_segments[-1].end_mm) == 3


def test_inverse_time_cubic_is_one_explicitly_timed_block_with_visible_conversion_provenance():
    from carveracontroller.machine.operation_facts import format_operation_facts, operation_facts

    program = ProgramOperations.from_text(HEADER + "G93 G5 I0 J3 P0 Q-3 X1 Y1 F2\nG5 P0 Q-3 X2 Y2", dialect="linuxcnc")
    facts = operation_facts(program, program.operations[-1])
    assert facts.nominal_feed_seconds == 30
    assert facts.timed_feed_lines == 1 and facts.untimed_feed_lines == (5,)
    assert len(facts.spline_conversions) == 2
    text = format_operation_facts(facts)
    assert "Declared analysis dialect · linuxcnc · backend execution unqualified" in text
    assert "Cubic spline line 4" in text and "parameter-matched error bound" in text
    assert "extent uses original control hull" in text


def test_program_wide_segment_budget_reserves_previous_complete_cubics():
    program = ProgramOperations.from_text(
        HEADER + "G5 I1 J0 P-1 Q0 X3 Y0 F60\nG5 I1 J0 P-1 Q0 X6 Y0",
        dialect="linuxcnc",
        max_spline_segments=1,
    )
    assert len(program.spline_blocks) == 1
    assert program.spline_blocks[0].line_number == 4
    assert 5 in program.unresolved_motion_lines
    assert not any(segment.line_number == 5 for segment in program.motion_segments)


def test_program_analysis_cooperatively_cancels_inside_spline_work():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 10

    with pytest.raises(InterruptedError):
        ProgramOperations.from_text(HEADER + "G5 I0 J100 P0 Q-100 X100 Y0 F60", dialect="linuxcnc", cancelled=cancel)
    assert calls == 10


@pytest.mark.parametrize(
    "block",
    [
        "G5 G1 X1 Y1 I0 J3 P0 Q-3 F100",
        "G1 G5 X1 Y1 I0 J3 P0 Q-3 F100",
        "G5 X1 Y1 I0 I2 J3 P0 Q-3 F100",
        "G5 X1 Y1 I0 J3 K1 P0 Q-3 F100",
    ],
)
def test_ambiguous_motion_or_control_words_do_not_invent_a_spline(block):
    program = ProgramOperations.from_text(HEADER + block, dialect="linuxcnc")
    assert 4 in program.unresolved_motion_lines and not program.spline_blocks
