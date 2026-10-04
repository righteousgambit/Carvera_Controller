from dataclasses import replace

from carveracontroller.machine.program_comparison import compare_programs
from carveracontroller.machine.program_preview import inspect_program


def capture(tmp_path, text):
    path = tmp_path / "revision.nc"
    path.write_text(text)
    return inspect_program(path)


def test_same_filename_capture_retains_old_tools_depth_feed_and_frames(tmp_path):
    old = capture(tmp_path, "G21 G90 G54\nT1 M6\nG0 X0 Y0 Z5\nG1 Z-2 F100 S10000 M3\nG1 X10\n")
    new = capture(tmp_path, "G21 G90 G55\nT8 M6\nG0 X0 Y0 Z5\nG1 Z-4 F300 S12000 M3\nG1 X20\n")
    report = compare_programs(old, new)
    assert report.changed and report.baseline_digest == old.digest and report.candidate_digest == new.digest
    assert "Work frames changed" in report.text and "Active tools changed" in report.text
    assert "Six-pocket bank assignments changed" in report.text and "Feed/spindle declarations changed" in report.text
    assert "G54: resolved bounds removed" in report.text and "G55: resolved bounds added" in report.text
    assert old.frame_bounds[0].minimum_mm[2] == -2


def test_depth_change_is_reported_in_frame_millimeters(tmp_path):
    old = capture(tmp_path, "G21 G90 G54\nG0 X0 Y0 Z5\nG1 Z-2 F100\n")
    new = capture(tmp_path, "G21 G90 G54\nG0 X0 Y0 Z5\nG1 Z-4 F100\n")
    text = compare_programs(old, new).text
    assert "G54: resolved bounds changed (mm)" in text
    assert "Z: -2.000…5.000 → -4.000…5.000" in text
    assert "do not prove equivalent execution" in text


def test_same_summary_different_bytes_remains_explicit(tmp_path):
    old = capture(tmp_path, "G21 G90 G54\n(Comment A)\n")
    new = capture(tmp_path, "G21 G90 G54\n(Comment B)\n")
    report = compare_programs(old, new)
    assert report.changed and "other source changes remain unclassified" in report.text
    assert not compare_programs(old, old).changed
    assert "Identical captured bytes" in compare_programs(old, old).text


def test_large_lists_are_bounded_and_complete_captures_remain_intact(tmp_path):
    old = capture(tmp_path, "G21\n")
    new = replace(old, digest="b" * 64, active_tool_ids=tuple(range(100)))
    report = compare_programs(old, new)
    assert "(100 total)" in report.text and "T99" not in report.text
    assert len(new.active_tool_ids) == 100


def test_changed_unresolved_count_does_not_claim_matching_summary(tmp_path):
    old = capture(tmp_path, "G21 G90 G54\nG0 X0 Y0 Z5\n")
    new = replace(old, digest="c" * 64, unresolved_lines=(2, 3))
    text = compare_programs(old, new).text
    assert "Unresolved motion lines: 1 → 2" in text
    assert "Summary fields match" not in text
