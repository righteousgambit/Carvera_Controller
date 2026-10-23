"""Detached buffers preserve the legacy parser and chunk contract."""

import hashlib

import pytest

from carveracontroller.CNC import CNC, detect_document_unit, escape_gcode_markup, highlight_gcode_line
from carveracontroller.machine.job_program_validation import PreviewParserInputs
from carveracontroller.machine.program_render_preparation import bridge_program_colors, prepare_legacy_program

INPUTS = PreviewParserInputs(-3.0, 0.0, False, 0.1)


@pytest.mark.parametrize(
    "text",
    [
        "G21 G90\nT1 M6\nG0 X2 Y3 Z4\nG1 X5 F100\nT2 M6\nG1 Y6\n",
        "G20 G90\nG0 X1 Y2 Z3\nG1 X2 F5\n",
        "G90\nG0 X1 Y0\nG2 X0 Y1 I-1 J0 F100\n",
        "G90\nG0 X1 Y1 Z5\nG81 X2 Y2 Z-2 R2 F100\nX3\nG80\n",
        "G0 X1 A30\nG1 X2 A90 F100\n",
        "(only comment)\n",
        "",
        "M118 [message]\nG1 X1 F100\n",
    ],
)
@pytest.mark.parametrize("chunk", [1, 2, 10000])
def test_streamed_rows_and_end_state_match_legacy(text, chunk):
    lines = text.splitlines(keepends=True)
    globals_before = dict(CNC.vars)
    actual = []
    result = prepare_legacy_program(
        lines, INPUTS, consume=lambda rows, end: actual.append(([r.copy() for r in rows], end)), chunk_lines=chunk
    )
    parser = CNC(variables={"clearance_z": -3.0, "wcoz": 0.0})
    parser.inch, parser.accuracy = False, 0.1
    expected = []
    for number, line in enumerate(lines, 1):
        parser.parseLine(line, number)
        if number % chunk == 0 or number == len(lines):
            expected.append(([r.copy() for r in parser.coordinates], number == len(lines)))
            parser.coordinates = []
    if not lines:
        expected.append(([], True))
    assert actual == expected
    assert result.vertex_count == sum(len(rows) for rows, _ in expected)
    assert result.source_hash == hashlib.sha256(text.encode()).hexdigest()
    assert result.lines == tuple(lines)
    assert result.has_4axis == parser.has_4axis
    assert CNC.vars == globals_before
    for key, value in result.parser_state.items():
        assert value == vars(parser)[key]
    assert not {"vars", "coordinates", "_preview_cancelled"}.intersection(result.parser_state)
    with pytest.raises(TypeError):
        result.margins["xmin"] = 10


def test_tool_metadata_and_color_bridge():
    lines = ["T1 M6\n", "G0 X1\n", "T2 M6\n", "G1 X2 F100\n"]
    result = prepare_legacy_program(lines, INPUTS, consume=lambda *_: None)
    assert result.upcoming_tool == 1 and result.used_tools == (1, 2)
    assert result.tool_change_markers == ((1, "T1"), (3, "T2"))
    rows = [[1, 2, 3, 0, 0, 2, 1, 100], [2, 2, 3, 0, 1, 4, 2, 100]]
    before = [r.copy() for r in rows]
    bridged = bridge_program_colors(rows)
    assert bridged == [rows[0], [2, 2, 3, 0, 0, 4, 2, 100], rows[1]]
    assert rows == before


def test_work_budget_and_cancellation_do_not_publish_partial_result():
    with pytest.raises(ValueError, match="budget"):
        prepare_legacy_program(["G0 X1\n", "G1 X2\n"], INPUTS, consume=lambda *_: None, point_budget=1)
    with pytest.raises(InterruptedError):
        prepare_legacy_program(["G1 X1\n"], INPUTS, consume=lambda *_: None, cancelled=lambda: True)
    with pytest.raises(ValueError, match="positive"):
        prepare_legacy_program([], INPUTS, consume=lambda *_: None, chunk_lines=0)


def test_unmatched_comment_display_is_escaped_and_unit_detection_is_cancellable():
    text = "G21 " + "(" * 20000 + "[unsafe]"
    assert highlight_gcode_line(text) == escape_gcode_markup(text)
    assert detect_document_unit([text]) == "mm"
    with pytest.raises(InterruptedError):
        detect_document_unit(["G20\n"], cancelled=lambda: True)
