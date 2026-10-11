from dataclasses import replace

import pytest

from carveracontroller.machine.program_operations import ProgramOperations


def program():
    return ProgramOperations.from_text(
        "G21 G90 G17 G94\nG0 X0 Y0 Z5\nG1 X1 F100\nT2 M6\nG1 X2\nT7 M6\nG1 X3\nG1 X4\nT2 M6\nG1 X5\nT9 M6\n"
    )


def test_index_matches_resolved_motion_for_every_inclusive_range():
    loaded = program()
    assert loaded.motion_tool_ids() == frozenset({None, 2, 7})
    assert 9 not in loaded.motion_tool_ids()  # A tool change alone is not motion.
    for start in (None, *range(0, len(loaded.lines) + 2)):
        for end in (None, *range(0, len(loaded.lines) + 2)):
            expected = frozenset(
                segment.tool_id
                for segment in loaded.motion_segments
                if (start is None or segment.line_number >= start) and (end is None or segment.line_number <= end)
            )
            assert loaded.motion_tool_ids(start, end) == expected


def test_replacing_motion_rebuilds_index_and_detaches_mutable_input():
    loaded = program()
    original = loaded.motion_segments
    incoming = [replace(original[-1], tool_id=5), replace(original[0], tool_id=3)]
    loaded.motion_segments = incoming
    assert loaded.motion_tool_ids() == frozenset({3, 5})
    incoming.clear()
    assert len(loaded.motion_segments) == 2
    assert loaded.motion_tool_ids(original[-1].line_number, original[-1].line_number) == frozenset({5})
    loaded.motion_segments = ()
    assert loaded.motion_tool_ids() == loaded.motion_tool_ids(1, 10) == frozenset()


def test_queries_do_not_read_motion_sequence(monkeypatch):
    loaded = program()
    monkeypatch.setattr(
        ProgramOperations, "motion_segments", property(lambda _: pytest.fail("UI query scanned motion"))
    )
    assert loaded.motion_tool_ids() == frozenset({None, 2, 7})
    assert loaded.motion_tool_ids(6, 8) == frozenset({7})
