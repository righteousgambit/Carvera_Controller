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
