import hashlib
import math

import pytest

from carveracontroller.machine.operation_facts import operation_facts
from carveracontroller.machine.program_operations import NurbsSplineBlock, ProgramOperations

HEADER = "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: NURBS)\n"
BLOCK = "G5.2 P1 F100\nX0 Y1 P1\nX2 Y2 P1\nX2 Y0 P1\nX0 Y0 P2\nG5.3"


def study(text=HEADER + BLOCK, **kwargs):
    return ProgramOperations.from_text(text, dialect="linuxcnc", **kwargs)


def test_complete_block_publishes_only_closure_motion_and_indexes_every_source_row():
    text = HEADER + BLOCK + "\nG1 X3 Y0"
    program = study(text, spline_tolerance_mm=0.001)
    block = program.spline_block(4)
    assert isinstance(block, NurbsSplineBlock)
    assert block.line_number == 9 and (block.data.start_line, block.data.end_line) == (4, 9)
    assert all(program.spline_block(line) is block for line in range(4, 10))
    assert all(program.spline_points(line) == program.spline_points(9) for line in range(4, 10))
    assert program.spline_points(9)[0] == program.spline_points(9)[-1] == (0, 0, 0)
    assert block.maximum_error_bound_mm <= 0.001
    assert not any(s.line_number in range(4, 9) for s in program.motion_segments)
    assert all(s.cutting for s in program.motion_segments if s.line_number == 9)
    assert program.checkpoints[7].state.position_mm == (0, 0, 0)
    assert program.checkpoints[8].state.motion is None
    assert program.checkpoints[9].state.position_mm == (3, 0, 0)
    assert not set(range(4, 11)) & set(program.unresolved_motion_lines)
    assert program.file_hash == hashlib.sha256(text.encode()).hexdigest()
    assert program.lines == tuple(text.splitlines())
    assert block.data.source_sha256 == hashlib.sha256(BLOCK.encode()).hexdigest()
    assert program.frame_bounds[-1].maximum_mm == (3, 2, 0)


def test_nominal_time_and_operation_facts_use_one_closure_feed_and_not_each_control_row():
    program = study(HEADER + BLOCK.replace("X2 Y0 P1", "X2 Y0 P1 F200"))
    op = program.operations[-1]
    length = math.fsum(math.dist(s.start_mm, s.end_mm) for s in program.motion_segments if s.line_number == 9)
    assert op.estimated_seconds == pytest.approx(60 * length / 200)
    facts = operation_facts(program, op)
    assert facts.resolved_moves == facts.timed_feed_lines == 1
    assert facts.nominal_feed_seconds == pytest.approx(op.estimated_seconds)
    assert program.checkpoints[-1].state.feed == 200


@pytest.mark.parametrize(
    "plane,words,expected",
    [("G17", "X1 Y2", (26.4, 52.8, 3)), ("G18", "X1 Z2", (26.4, 2, 53.8)), ("G19", "Y1 Z2", (1, 27.4, 53.8))],
)
def test_whole_program_incremental_inch_controls_anchor_to_preblock_position(plane, words, expected):
    text = f"G21 G90 {plane} G94 G54\nG0 X1 Y2 Z3\nG20 G91\nG5.2 P1 F10\n{words} P1\n{words} P2\nG5.3"
    program = study(text)
    block = program.spline_block(5)
    assert block.plane == plane
    assert block.control_points_mm[-1] == pytest.approx(expected)
    assert program.checkpoints[-1].state.position_mm == pytest.approx(expected)
    assert program.checkpoints[-1].state.feed == pytest.approx(10)


@pytest.mark.parametrize(
    "body",
    [
        BLOCK[:-5],
        BLOCK.replace("X0 Y1 P1", "G1 X0 Y1"),
        BLOCK.replace("P2", "P0"),
        BLOCK.replace("X2 Y2", "X#2 Y2"),
        BLOCK.replace("X2 Y0 P1", "G20"),
        BLOCK.replace("G5.3", "G5.3 X1"),
    ],
)
def test_invalid_or_incomplete_blocks_never_publish_data_row_geometry(body):
    program = study(HEADER + body)
    assert not program.spline_blocks
    assert not any(s.line_number >= 4 for s in program.motion_segments)
    assert 4 in program.unresolved_motion_lines
    assert program.operations[-1].bounds_mm is None
    assert program.operations[-1].estimated_seconds is None


def test_default_carvera_refuses_entire_block_and_following_unknown_position():
    program = ProgramOperations.from_text(HEADER + BLOCK + "\nG1 X3")
    assert not program.spline_blocks
    assert not any(s.line_number >= 4 for s in program.motion_segments)
    assert set(range(4, 11)) <= set(program.unresolved_motion_lines)


def test_nurbs_and_polynomial_splines_share_budget_without_publishing_prefix():
    text = HEADER + "G5 X3 Y0 I1 J0 P-1 Q0 F100\n" + BLOCK
    program = study(text, max_spline_segments=1)
    assert len(program.spline_blocks) == 1 and program.spline_blocks[0].source_command == "G5"
    assert not any(s.line_number >= 5 for s in program.motion_segments)
    assert set(range(5, 11)) <= set(program.unresolved_motion_lines)


def test_cancellation_during_rational_conversion_propagates_without_returning_partial_analysis():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 12

    with pytest.raises(InterruptedError):
        study(cancelled=cancel)


def test_resume_inside_data_block_is_refused_even_with_complete_external_evidence():
    header = "G21 G90 G17 G94 G54 G49\nT1 M6\nM5 M9\nG0 X0 Y0 Z0\n"
    program = study(header + BLOCK)
    for line in range(5, 11):
        plan = program.recovery_plan(
            line, safe_machine_z=100, verified_machine_position=(0, 0, 50), clearance_verified=True
        )
        assert not plan.ready and not plan.commands
        assert any("NURBS data block" in warning for warning in plan.warnings)


@pytest.mark.parametrize("mode", ["G93", "G95"])
def test_unimplemented_feed_modes_are_explicitly_unresolved(mode):
    program = study(HEADER.replace("G94", mode) + BLOCK)
    assert not program.spline_blocks and 4 in program.unresolved_motion_lines
    assert any("explicit G94" in w for w in program.operations[-1].warnings)


def test_feed_updates_are_preserved_on_each_data_row_before_closure():
    program = study(HEADER + BLOCK.replace("X2 Y0 P1", "X2 Y0 P1 F200"))
    assert [program.checkpoints[n - 1].state.feed for n in range(4, 10)] == [100, 100, 100, 200, 200, 200]
    assert program.spline_block(9).data.feed_source_updates == ((4, 100), (7, 200))


def test_declared_work_offset_translates_operation_bounds_but_not_control_geometry():
    program = study(work_offsets={"G54": (10, 20, 30)})
    block = program.spline_block(9)
    assert block.control_points_mm[0] == (0, 0, 0)
    assert program.operations[-1].bounds_mm == ((10, 20, 30), (12, 22, 30))
    assert program.frame_bounds[-1].minimum_mm == (0, 0, 0)


def test_move_explanation_preserves_span_warning_without_inventing_control_row_motion():
    from carveracontroller.machine.move_inspection import MoveInspector

    inspector = MoveInspector(study())
    row = inspector.explain(5)
    closing = inspector.explain(9)
    assert not row.segments and not row.unresolved
    assert closing.segments and not closing.unresolved
    assert any("backend execution unqualified" in w for w in row.warnings)
    assert any("backend execution unqualified" in w for w in closing.warnings)
    invalid = MoveInspector(study(HEADER + BLOCK.replace("P2", "P0")))
    assert invalid.explain(5).unresolved
    assert any("positive" in w for w in invalid.explain(5).warnings)


def test_finite_tiny_feed_does_not_publish_infinite_nominal_duration():
    program = study(HEADER + BLOCK.replace("F100", "F1e-308"))
    assert program.spline_blocks and program.spline_points(9)
    assert program.operations[-1].estimated_seconds is None
    assert any("finite timing range" in w for w in program.operations[-1].warnings)


def test_crlf_block_digest_uses_original_interior_source_line_endings():
    block = BLOCK.replace("\n", "\r\n")
    text = HEADER.replace("\n", "\r\n") + block + "\r\nG1 X3\r\n"
    program = study(text)
    assert program.spline_block(4).data.source_sha256 == hashlib.sha256(block.encode()).hexdigest()
    assert program.file_hash == hashlib.sha256(text.encode()).hexdigest()
