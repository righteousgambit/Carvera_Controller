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
