import pytest

from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.program_operations import ProgramOperations

HEADER = "G21 G90 G17 G91.1 G94 G54 G49\nT17 M6\nS12000 M3\nG0 X0 Y0 Z0\n"


def inspector(text):
    return MoveInspector(ProgramOperations.from_text(text))


def test_source_trace_keeps_modal_before_after_and_arc_subdivisions():
    view = inspector(HEADER + "(Operation: Helix)\nG1 X10 F600\nG3 X0 Y10 Z2 I-10 J0")
    move = view.explain(7)
    assert move.operation.name == "Helix"
    assert move.before.position_mm == (10, 0, 0)
    assert move.after.position_mm == (0, 10, 2)
    assert len(move.segments) > 1
    assert move.segments[0].start_mm == (10, 0, 0)
    assert move.segments[-1].end_mm == (0, 10, 2)
    assert move.feed_description == "G94 · 600 mm/min"
    assert move.program_hash == view.program.file_hash
    assert move.context[-1] == (7, "G3 X0 Y10 Z2 I-10 J0")


def test_comment_does_not_reexecute_modal_move():
    view = inspector(HEADER + "G1 X10 F600\n(comment T17 rapid)")
    move = view.explain(6)
    assert not move.segments and not move.unresolved
    assert view.search("rapid") == ()
    assert view.search("tool:T17") == (4, 5)
    assert view.search("comment") == (6,)


def test_unknown_machine_frame_and_inherited_macro_error_remain_explicit():
    view = inspector(HEADER + "G53 G0 Z0\nG1 X10\n#1=2\nG1 X20")
    assert view.explain(5).unresolved
    assert not view.explain(5).segments
    assert view.explain(6).unresolved
    assert any("Inherited uncertainty" in message for message in view.explain(8).warnings)
    assert view.search("unresolved") == (4, 5, 6, 7, 8)


def test_missing_wcs_is_unregistered_even_if_segments_exist():
    move = inspector(HEADER.replace("G54", "") + "G1 X10 F600").explain(5)
    assert move.segments and move.unresolved
    assert any("unregistered" in message for message in move.warnings)


def test_feed_modes_are_not_confused_and_inches_are_canonical():
    view = inspector(HEADER + "G20 G1 X1 F2\nG95 G1 X2 F0.1\nG93 G1 X3 F4\nG1 X4")
    assert view.explain(5).feed_description == "G94 · 50.8 mm/min"
    assert view.explain(6).feed_description == "G95 · 2.54 mm/rev"
    assert view.explain(7).feed_description == "G93 · 4 inverse minutes"
    assert "missing" in view.explain(8).feed_description


def test_navigation_filters_and_search_limit():
    view = inspector(HEADER + "(Operation: Finish wall)\nG1 X10 F600\nG0 Z1\nG1 X20")
    assert view.adjacent_motion(5, 1) == 6
    assert view.adjacent_motion(6, -1) == 4
    assert view.adjacent_motion(8, 1) is None
    assert view.search("cutting tool:17 finish") == (6, 8)
    assert view.search("rapid tool:T17") == (7,)
    assert view.search("finish", limit=1) == (5,)
    assert view.search("") == ()
    for value in (0, 10, True, 1.1):
        with pytest.raises(ValueError):
            view.explain(value)


def test_g80_cancels_motion_instead_of_reusing_previous_feed_move():
    view = inspector(HEADER + "G1 X10 F600\nG80\nX20\nG1 X30")
    assert view.explain(6).after.motion is None
    assert not view.explain(7).segments
    assert view.explain(7).after.position_mm == (None, None, None)
    assert view.explain(8).unresolved
