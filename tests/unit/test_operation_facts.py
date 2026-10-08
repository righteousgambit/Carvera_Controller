import pytest

from carveracontroller.machine.operation_facts import format_operation_facts, operation_facts
from carveracontroller.machine.program_operations import ProgramOperations


def test_operation_scope_and_motion_contact_are_distinct():
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Face)\n"
        "S12000 M3\nG1 X10 F100\nG0 Y5\n(Operation: Finish)\nG1 X20 F200"
    )
    facts = operation_facts(program, program.operations[1])
    assert facts.feed_path_mm == 10
    assert facts.rapid_mm == 5
    assert facts.resolved_moves == 2
    assert facts.feeds == (("G94", "G21", 100, 100),)
    assert facts.spindle_range == (12000, 12000)
    assert facts.frames == ("G54",)
    assert "does not establish stock contact" in format_operation_facts(facts)


def test_feed_modes_and_units_remain_separate():
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Mixed)\nG1 X10 F100\nG20 G1 X1 F2\nG93 G1 X2 F3"
    )
    text = format_operation_facts(operation_facts(program, program.operations[-1]))
    assert "100–100 mm/min (G94)" in text
    assert "2–2 in/min (G94)" in text
    assert "3–3 1/min (G93)" in text


def test_unresolved_moves_not_counted_as_zero_length_success():
    program = ProgramOperations.from_text("(Operation: Unknown)\nG1 X10 F100")
    facts = operation_facts(program, program.operations[0])
    assert facts.resolved_moves == 0
    assert facts.unresolved_lines == (2,)
    assert "unknown" in format_operation_facts(facts)


def test_foreign_operation_rejected():
    first = ProgramOperations.from_text("G1 X1")
    second = ProgramOperations.from_text("G1 X2")
    with pytest.raises(ValueError, match="does not belong"):
        operation_facts(first, second.operations[0])


def test_arc_subdivision_counts_source_move_once_and_rapid_feed_is_excluded():
    program = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G94 G54\nG0 X10 Y0 Z0\n(Operation: Arc)\nG3 X0 Y10 I-10 J0 F600\nG0 Z5 F999",
        arc_tolerance_mm=0.001,
    )
    facts = operation_facts(program, program.operations[-1])
    assert facts.resolved_moves == 2
    assert facts.feed_path_mm == pytest.approx(15.708, abs=0.02)
    assert facts.rapid_mm == 5
    assert facts.feeds == (("G94", "G21", 600, 600),)


def test_nominal_timing_and_corner_identify_exact_source_blocks():
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Corners)\nG1 X10 F600\nG1 Y0.1\nG1 X0\nG0 Z5"
    )
    facts = operation_facts(program, program.operations[-1])
    assert facts.timed_feed_lines == 3
    assert facts.nominal_feed_seconds == pytest.approx(2.01)
    assert facts.shortest_feed_block == pytest.approx((5, 0.01))
    assert facts.largest_direction_change == pytest.approx((4, 5, 90))
    text = format_operation_facts(facts)
    assert "line 5 · 10 ms" in text
    assert "lines 4→5 · 90 degrees" in text
    assert "backend timing are unqualified" in text


def test_inverse_time_arc_is_one_block_and_unknown_revolution_feed_is_untimed():
    program = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G54\nG0 X10 Y0 Z0\n(Operation: Modes)\nG93 G3 X0 Y10 I-10 J0 F2\nG95 G1 X5 F0.1"
    )
    facts = operation_facts(program, program.operations[-1])
    assert facts.timed_feed_lines == 1
    assert facts.nominal_feed_seconds == 30
    assert facts.shortest_feed_block == (4, 30)
    assert facts.untimed_feed_lines == (5,)
    arc = ProgramOperations.from_text(
        "G21 G90 G17 G91.1 G54 G94\nG0 X10 Y0 Z0\n(Operation: Arc)\nG3 X0 Y10 I-10 J0 F600"
    )
    assert operation_facts(arc, arc.operations[-1]).largest_direction_change is None


def test_frame_change_and_intervening_nonmotion_line_do_not_form_corners():
    for middle in ("G55", "G4 P1", "M5"):
        program = ProgramOperations.from_text(
            f"G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Separate)\nG1 X10 F600\n{middle}\nG1 Y10"
        )
        assert operation_facts(program, program.operations[-1]).largest_direction_change is None


def test_imperial_nominal_feed_is_converted_without_changing_program_units():
    program = ProgramOperations.from_text("G20 G90 G17 G94 G54\nG0 X0 Y0 Z0\nG1 X1 F2")
    facts = operation_facts(program, program.operations[-1])
    assert facts.nominal_feed_seconds == pytest.approx(30)


def test_inverse_time_cannot_borrow_feed_from_previous_block():
    program = ProgramOperations.from_text("G21 G90 G17 G93 G54\nG0 X0 Y0 Z0\nG1 X10 F2\nG1 Y10")
    facts = operation_facts(program, program.operations[-1])
    assert facts.nominal_feed_seconds == 30
    assert facts.timed_feed_lines == 1
    assert facts.untimed_feed_lines == (4,)
