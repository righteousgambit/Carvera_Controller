import pytest

from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.operation_facts import operation_facts
from carveracontroller.machine.program_operations import ProgramOperations


@pytest.mark.parametrize(
    "motion",
    ["G1 X1", "G5 X1 Y0 I0.3333333333 J0 P-0.3333333333 Q0", "G5.1 X1 I0.5 J0", "G5.2 P1\nX0.5 Y0 P1\nX1 Y0 P1\nG5.3"],
)
def test_mm_to_inch_change_preserves_inherited_physical_g94_feed(motion):
    text = "G21 G90 G17 G94 G54 F254\nG0 X0 Y0 Z0\n(Operation: Feed units)\nG20\n" + motion
    program = ProgramOperations.from_text(text, dialect="linuxcnc")
    op = program.operations[-1]
    assert op.estimated_seconds == pytest.approx(6)
    assert program.checkpoints[-1].state.feed == pytest.approx(10)
    assert "254 mm/min" in MoveInspector(program).explain(len(program.lines)).feed_description
    assert operation_facts(program, op).nominal_feed_seconds == pytest.approx(6)


def test_inch_to_mm_change_preserves_feed_and_explicit_f_overrides_after_units():
    prefix = "G20 G90 G17 G94 G54 F10\nG0 X0 Y0 Z0\n(Operation: Feed units)\n"
    for command, feed, seconds in [
        ("G21 G1 X25.4", 254, 6),
        ("G21 G1 X25.4 F508", 508, 3),
        ("F508 G21 G1 X25.4", 508, 3),
    ]:
        program = ProgramOperations.from_text(prefix + command, dialect="linuxcnc")
        assert program.checkpoints[-1].state.feed == feed
        assert program.operations[-1].estimated_seconds == pytest.approx(seconds)


def test_same_units_do_not_rescale_and_unit_round_trip_preserves_feed():
    text = "G21 G90 G17 G94 G54 F254\nG0 X0 Y0 Z0\nG20\nG20\nG21\nG1 X25.4"
    program = ProgramOperations.from_text(text, dialect="linuxcnc")
    assert [c.state.feed for c in program.checkpoints[2:]] == pytest.approx([10, 10, 254, 254])


def test_carvera_dialect_does_not_inherit_unqualified_linuxcnc_unit_semantics():
    program = ProgramOperations.from_text("G21 G90 G17 G94 G54 F254\nG0 X0 Y0 Z0\nG20\nG1 X1")
    assert program.checkpoints[-1].state.feed == 254


def test_switching_into_g94_still_requires_new_feed():
    text = "G21 G90 G17 G93 G54 F2\nG0 X0 Y0 Z0\nG20 G94\nG1 X1"
    program = ProgramOperations.from_text(text, dialect="linuxcnc")
    assert program.checkpoints[-1].state.feed is None


def test_inverse_minutes_are_not_rescaled_as_linear_feed():
    program = ProgramOperations.from_text("G21 G90 G17 G93 G54\nG0 X0 Y0 Z0\nG20 G1 X1 F2", dialect="linuxcnc")
    assert program.checkpoints[-1].state.feed == 2


@pytest.mark.parametrize("first,change", [("G20 F1.7e308", "G21"), ("G21 F1e-323", "G20")])
def test_unrepresentable_inherited_feed_remains_unknown(first, change):
    # The regular source lexer does not accept exponents; use exact decimal text.
    first = first.replace("1.7e308", format(1.7e308, ".0f")).replace("1e-323", format(1e-323, ".324f"))
    program = ProgramOperations.from_text(
        f"{first} G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Units)\n{change}\nG1 X1", dialect="linuxcnc"
    )
    assert program.checkpoints[-1].state.feed is None
    assert program.operations[-1].estimated_seconds is None
    assert any("representable unit range" in w for w in program.operations[-1].warnings)


def test_explicit_feed_skips_unrepresentable_inherited_conversion():
    huge = format(1.7e308, ".0f")
    program = ProgramOperations.from_text(
        f"G20 G90 G17 G94 G54 F{huge}\nG0 X0 Y0 Z0\nG21 G1 X1 F100", dialect="linuxcnc"
    )
    assert program.checkpoints[-1].state.feed == 100
    assert not any("representable unit range" in w for op in program.operations for w in op.warnings)
