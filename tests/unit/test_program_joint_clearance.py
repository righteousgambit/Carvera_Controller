"""Program coverage, tool-specific geometry and conservative failure contracts."""

from dataclasses import replace

import pytest

from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.joint_clearance import bodies_from_record
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource, review_program_clearance
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.scene_joint_clearance import capture_scene_clearance
from tests.unit.test_scene_joint_clearance import scene_viewer


def program(extra="", *, arc=False):
    motion = "G2 X10 Y0 I5 J0" if arc else "G1 X10 F100"
    return ProgramOperations.from_text("G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\n" + motion + "\n" + extra)


def captures(*tools):
    viewer = scene_viewer()
    result = {}
    for number in tools or (1,):
        definition = replace(viewer.library_tool_table_mm[1], number=number, stickout=30 + number)
        viewer.library_tool_table_mm[number] = definition
        result[number] = capture_scene_clearance(
            viewer.machine_profile,
            {},
            viewer.machine_setup,
            (viewer.workholding_offset_mm, viewer.workholding_rotation_deg, viewer.jaw_offset_mm),
            definition,
            number,
            None,
            capture_context(viewer, None, verify_assets=False),
        )
    return result


def review(p=None, **kwargs):
    return review_program_clearance(
        ProgramClearanceSource.capture(p or program()), captures(1, 2), {"G54": (-180, -120, -110)}, **kwargs
    )


def test_full_program_has_explicit_unresolved_entry_and_tool_change_coverage_gaps():
    result = review()
    assert len(result.segments) == 1 and result.segments[0].line == 4
    assert result.uncovered_lines == (3,)
    assert result.tool_change_lines == (2,)
    assert result.curved_lines == ()
    assert result.status != "clear_resolved_polylines"
    assert result.tested_pairs == 45
    assert "physical clearance remain unqualified" in result.qualification


def test_more_than_eight_segments_and_per_tool_stickout_are_all_reviewed():
    p = program("\n".join(f"G1 X{x}" for x in range(11, 21)) + "\nT2 M6\nG1 X21")
    result = review(p)
    assert len(result.segments) == 12
    assert result.tested_pairs == 45 * 12
    assert set(result.records) == {1, 2}
    assert result.scene_digests[0][1] != result.scene_digests[1][1]
    for tool, record in result.records.items():
        bodies, _ = bodies_from_record(record, machine_from_record(record))
        shank = next(b for b in bodies if b.name == f"T{tool} shank")
        assert shank.bounds.maximum.z == 30 + tool
    assert all(c.line == result.segments[c.segment_index].line for c in result.contacts)
    assert all(0 <= c.source_lower_ratio <= c.source_upper_ratio <= 1 for c in result.contacts)


def test_arc_chords_are_reviewed_but_curve_interiors_remain_unqualified():
    result = review(program(arc=True), start_line=4, cover_curves=False)
    assert len(result.segments) > 1 and result.curved_lines == (4,)
    assert result.uncovered_lines == ()
    assert result.tool_change_lines == ()
    for c in result.contacts:
        segment = result.segments[c.segment_index]
        assert segment.source_start_ratio <= c.source_lower_ratio <= c.source_upper_ratio <= segment.source_end_ratio
    assert "curve interiors" in result.qualification


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"max_segments": 1}, "segment budget"),
        ({"max_intervals": 1}, "interval budget"),
        ({"max_contacts": 1}, "contact budget"),
        ({"cancelled": lambda: True}, "cancelled"),
        ({"max_intervals": True}, "budgets"),
        ({"start_line": 0}, "source range"),
    ],
)
def test_limits_and_cancellation_withhold_entire_report(kwargs, message):
    with pytest.raises((ValueError, InterruptedError), match=message):
        review(program("G1 X11"), **kwargs)


def test_missing_datums_tools_and_out_of_travel_are_refused():
    source = ProgramClearanceSource.capture(program())
    for tools, offsets, message in (
        ({}, {"G54": (-180, -120, -110)}, "every program tool"),
        (captures(), {"G55": (0, 0, 0)}, "Missing declared frame"),
        (captures(), {"G54": (0, 0, 0)}, "exceeds nominal"),
    ):
        with pytest.raises(ValueError, match=message):
            review_program_clearance(source, tools, offsets)


def test_named_wcs_offsets_transform_every_segment_without_guessing():
    p = ProgramOperations.from_text(
        "G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X10 F100\nG55\nG1 X11",
        work_offsets={"G54": (-180, -120, -110), "G55": (-200, -100, -100)},
    )
    result = review_program_clearance(
        ProgramClearanceSource.capture(p), captures(), {"G54": (-180, -120, -110), "G55": (-200, -100, -100)}
    )
    assert result.segments[0].start.tuple == (-180, -120, -110)
    assert result.segments[1].start == result.segments[0].end
    assert result.segments[1].end.tuple == (-189, -120, -110)


def test_snapshot_detaches_parser_replacement_and_compensation_is_uncovered():
    p = program("G41 D1\nG1 X11")
    source = ProgramClearanceSource.capture(p)
    p.motion_segments = ()
    result = review_program_clearance(source, captures(), {"G54": (-180, -120, -110)})
    assert len(result.segments) == 1 and 6 in result.uncovered_lines


def test_range_review_does_not_hide_unresolved_motion_inside_selection():
    p = program("G53 G0 Z0\nG0 X0 Y0 Z0\nG1 X1")
    result = review(p, start_line=4)
    assert result.uncovered_lines == (5, 6)
    assert [s.line for s in result.segments] == [4, 7]


def test_repeated_same_tool_change_and_comments_have_correct_gaps():
    result = review(program("(M6)\n; M6\nM06.0\nG1 X11"))
    assert result.tool_change_lines == (2, 7)


def test_offsets_used_to_resolve_wcs_transitions_cannot_be_reinterpreted():
    p = ProgramOperations.from_text(
        "G21 G90 G54\nT1 M6\nG0 X0 Y0 Z0\nG55\nG1 X1",
        work_offsets={"G54": (-180, -120, -110), "G55": (-200, -100, -100)},
    )
    with pytest.raises(ValueError, match="different declared WCS"):
        review_program_clearance(
            ProgramClearanceSource.capture(p), captures(), {"G54": (-180, -120, -110), "G55": (-201, -100, -100)}
        )
