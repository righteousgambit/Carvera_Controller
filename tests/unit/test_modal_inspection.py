from carveracontroller.machine.modal_inspection import modal_facts, modal_notes
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations


def inspect(text, line):
    return MoveInspector(ProgramOperations.from_text(text)).explain(line)


def facts(move):
    return {fact.key: fact for fact in modal_facts(move)}


def test_unknown_initial_state_is_not_filled_from_machine_defaults():
    move = inspect("(setup)\nG21 G90 G17 G91.1 G94 G54 G40 G49", 2)
    rows = facts(move)
    assert all(row.before == "Unknown" for row in rows.values())
    assert rows["units"].after == "G21 · millimeters"
    assert rows["cutter_compensation"].after == "G40 · off"
    assert rows["tool_length_command"].after == "G49 · off"
    assert not rows["feed"].changed and rows["feed"].after == "Unknown"


def test_feed_meaning_changes_even_when_numeric_f_word_does_not():
    text = "G21 G94 F2\nG20\nG95 F0.1\nG93 F4"
    inch = facts(inspect(text, 2))["feed"]
    assert inch.changed and inch.before == "2 mm/min" and inch.after == "2 in/min"
    assert facts(inspect(text, 3))["feed"].after == "0.1 in/rev"
    assert facts(inspect(text, 4))["feed"].after == "4 inverse min"


def test_pending_tool_is_distinct_from_program_tool_and_compensation_table_value():
    move = inspect("T1 M6\nT17 G43 H5", 2)
    rows = facts(move)
    assert rows["tool"].after == "T1" and not rows["tool"].changed
    assert rows["pending_tool"].before == "T1" and rows["pending_tool"].after == "T17"
    assert rows["tool_length_command"].after == "G43 H5"
    assert any("H/D table values" in note for note in modal_notes(move))


def test_cutter_compensation_is_reported_but_never_resolves_an_offset_path():
    text = "G21 G90 G17 G94 G54 G40\nG0 X0 Y0 Z0\nG41 D2 G1 X10 F100\nG40 G1 X20"
    move = inspect(text, 3)
    assert facts(move)["cutter_compensation"].after == "G41 D2 · requested; path unsupported"
    assert move.unresolved and not move.segments
    canceled = inspect(text, 4)
    assert facts(canceled)["cutter_compensation"].after == "G40 · off"
    assert canceled.unresolved and not canceled.segments
    assert any("Interpretation uncertain" in note for note in modal_notes(canceled))


def test_local_offset_and_macro_uncertainty_stay_visible_on_later_lines():
    for command in ("G52 X2", "G92 X2", "#1=2"):
        move = inspect("G21 G90 G54\n" + command + "\nG1 X10 F100", 3)
        assert any("Interpretation uncertain" in note for note in modal_notes(move))
        assert any("Inherited uncertainty" in note for note in modal_notes(move))


def test_combined_coolant_and_spindle_changes_are_explained_without_inference():
    rows = facts(inspect("M7 S12000 M3\nM8\nM5 M9", 2))
    assert rows["coolant"].after == "M7 · mist + M8 · flood"
    assert not rows["spindle"].changed
    rows = facts(inspect("M7 S12000 M3\nM8\nM5 M9", 3))
    assert rows["spindle"].after == "M5 · stopped"
    assert rows["spindle_speed"].after == "12000 RPM" and not rows["spindle_speed"].changed


def test_comment_preserves_all_inherited_modal_fields():
    move = inspect("G21 G90 G17 G91.1 G94 G54 G40 G49 T1 M6 F100\n(comment G41 D5)", 2)
    assert not any(row.changed for row in modal_facts(move))
    assert facts(move)["cutter_compensation"].after == "G40 · off"
