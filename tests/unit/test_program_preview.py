import hashlib

import pytest

from carveracontroller.machine.program_preview import inspect_program


def test_captured_summary_includes_units_tools_operations_unknown_motion_and_raw_hash(tmp_path):
    path = tmp_path / "part.nc"
    content = b"G20 G90 G17 G94 G54\nT7 M6\nG0 X0 Y0 Z1\n(Operation: Face)\nG1 Z0 F10\nG1 X1\n"
    path.write_bytes(content)
    result = inspect_program(path)
    assert result.units == ("G20",)
    assert result.frames == ("G54",)
    assert result.tool_ids == (7,)
    assert "Face" in result.operation_names
    assert result.digest == hashlib.sha256(content).hexdigest()
    assert result.unresolved_lines == (3,)
    assert result.segments[-1].end_mm == (25.4, 0, 0)


def test_quick_inspection_rejects_prefix_summaries_and_invalid_encoding(tmp_path):
    path = tmp_path / "part.nc"
    path.write_bytes(b"G21\n" * 10)
    with pytest.raises(ValueError, match="limit"):
        inspect_program(path, byte_limit=10)
    with pytest.raises(ValueError, match="limit"):
        inspect_program(path, line_limit=2)
    path.write_bytes(b"G21\xff")
    with pytest.raises(UnicodeError):
        inspect_program(path)


def test_multiple_frames_remain_distinct_and_pending_tools_are_declared(tmp_path):
    path = tmp_path / "part.nc"
    path.write_text("G21 G90 G17 G94 G54\nT2\nG0 X0 Y0 Z1\nG1 X1 F100\nG55\nT9 M6\nG1 X2\n")
    result = inspect_program(path)
    assert result.frames == ("G54", "G55")
    assert result.tool_ids == (2, 9)
    assert result.active_tool_ids == (9,)
    assert result.six_pocket_banks[0].slots == ((1, 9),)


def test_captured_bank_plan_preserves_ordered_reuse_and_preselection(tmp_path):
    path = tmp_path / "banks.nc"
    path.write_text("G21\n" + "\n".join(f"T{tool} M6" for tool in (1, 2, 3, 4, 5, 6, 7, 1)) + "\nT99\n")
    result = inspect_program(path)
    assert result.tool_ids == (1, 2, 3, 4, 5, 6, 7, 99)
    assert result.active_tool_ids == (1, 2, 3, 4, 5, 6, 7)
    assert len(result.six_pocket_banks) == 2
    assert result.six_pocket_banks[1].slots == ((1, 7), (2, 1))
    assert result.six_pocket_banks[1].reload_required


def test_frame_bounds_include_analytic_arc_extrema_and_exclude_unknown_approach(tmp_path):
    path = tmp_path / "circle.nc"
    path.write_text("G21 G90 G91.1 G17 G94 G54\nG0 X10 Y0 Z0\nG2 X10 Y0 I-10 J0 F100\n")
    result = inspect_program(path)
    extent = result.frame_bounds[0]
    assert extent.wcs == "G54"
    assert extent.minimum_mm == pytest.approx((-10, -10, 0))
    assert extent.maximum_mm == pytest.approx((10, 10, 0))
    assert extent.resolved_lines == (3,)
    assert result.unresolved_lines == (2,)
    # The polygon thumbnail does not have exact cardinal samples; its extrema
    # must not replace the analytic arc extent used for dimensional inspection.
    assert min(s.end_mm[1] for s in result.segments) > -10


def test_multiple_frame_extents_and_previews_remain_separate_before_sampling(tmp_path):
    path = tmp_path / "frames.nc"
    path.write_text(
        "G21 G90 G54\nG0 X0 Y0 Z0\nG1 X1 F100\nG55\nG0 X100 Y50 Z10\nG1 X101\nG54\nG0 X0 Y0 Z0\n"
        + "\n".join(f"G1 X{i} Y{i % 2}" for i in range(2500))
        + "\nG53 G0 X9000\n"
    )
    result = inspect_program(path)
    extents = {extent.wcs: extent for extent in result.frame_bounds}
    previews = dict(result.frame_previews)
    assert extents["G54"].maximum_mm == (2499, 1, 0)
    assert extents["G55"].minimum_mm == (100, 50, 10)
    assert extents["G55"].maximum_mm == (101, 50, 10)
    assert len(previews["G54"]) <= 2001
    assert len(previews["G55"]) == 1
    assert all(segment.wcs == "G55" for segment in previews["G55"])
    assert result.line_count in result.unresolved_lines


def test_unresolved_only_program_does_not_invent_bounds(tmp_path):
    path = tmp_path / "unknown.nc"
    path.write_text("G21 G90 G54\nG0 X8 Y9 Z10\nG1 X[#1]\n")
    result = inspect_program(path)
    assert not result.frame_bounds and not result.frame_previews
