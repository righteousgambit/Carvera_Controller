"""CAM header replay and conservative tool-identity/geometry boundaries."""

import pytest

from carveracontroller.addons.tool_visualization.extractor import extract_tool_table
from carveracontroller.addons.tool_visualization.parsers.base import MAX_HEADER_LINES, ToolTableParser
from carveracontroller.addons.tool_visualization.parsers.freecad_makera import FreeCADMakeraParser
from carveracontroller.addons.tool_visualization.parsers.makera_studio import MakeraStudioParser


@pytest.mark.parametrize(
    "header",
    [
        "(T3  End mill  D=6 - flat end mill)",
        "(@FC|TOOL|number=3|name=FreeCAD|type=Endmill|diameter=6)",
        ";@MKR|TOOL|number=3|name=Makera|type=Flat End|diameter=6",
    ],
)
def test_one_pass_program_recognizes_each_cam_without_consuming_motion_body(header):
    def program():
        yield "(Header)"
        yield header
        yield "G0 X0"
        raise AssertionError("Metadata extraction consumed the motion body")

    table = extract_tool_table(program())
    assert list(table) == [3] and table[3].diameter == 6


def test_header_scan_does_not_read_past_its_line_budget():
    pulled = []

    def oversized_header():
        for i in range(MAX_HEADER_LINES + 1):
            pulled.append(i)
            yield "(Comment)"

    assert extract_tool_table(oversized_header()) == {}
    assert len(pulled) == MAX_HEADER_LINES
    assert list(ToolTableParser.iter_header_lines(iter(["(Comment)"]), max_lines=0)) == []


@pytest.mark.parametrize(
    ("parser", "template"),
    [
        (FreeCADMakeraParser(), "(@FC|TOOL|number={number}|type=Endmill|diameter={diameter})"),
        (MakeraStudioParser(), ";@MKR|TOOL|number={number}|type=Flat End|diameter={diameter}"),
    ],
)
@pytest.mark.parametrize("number", ["nan", "inf", "1e309", "1.5", "-1", "1.0000000000000000000001"])
def test_invalid_identity_does_not_replace_a_valid_tool_or_discard_other_tools(parser, template, number):
    table = parser.parse(
        [
            template.format(number=number, diameter="99"),
            template.format(number="1", diameter="6"),
            template.format(number="2", diameter="3"),
            "G0 X0",
        ]
    )
    assert set(table) == {1, 2} and table[1].diameter == 6 and table[2].diameter == 3


@pytest.mark.parametrize(
    ("parser", "template"),
    [
        (FreeCADMakeraParser(), "(@FC|TOOL|number={number}|type=Endmill|diameter={diameter})"),
        (MakeraStudioParser(), ";@MKR|TOOL|number={number}|type=Flat End|diameter={diameter}"),
    ],
)
def test_integer_identity_is_not_rounded_through_binary_float(parser, template):
    table = parser.parse([template.format(number="9007199254740993", diameter="6")])
    assert list(table) == [9007199254740993]


@pytest.mark.parametrize("dimension", ["nan", "inf", "-inf", "1e309"])
@pytest.mark.parametrize(
    ("parser", "line"),
    [
        (FreeCADMakeraParser(), "(@FC|TOOL|number=1|type=Endmill|diameter={value}|shankdiameter={value})"),
        (MakeraStudioParser(), ";@MKR|TOOL|number=1|type=Flat End|diameter={value}|handlediameter={value}"),
    ],
)
def test_nonfinite_geometry_stays_unknown_instead_of_entering_simulation(parser, line, dimension):
    tool = parser.parse([line.format(value=dimension)])[1]
    assert tool.diameter is None and tool.shank_diameter is None


def test_failed_parser_cannot_consume_header_needed_by_next_parser(monkeypatch):
    from carveracontroller.addons.tool_visualization import extractor
    from carveracontroller.addons.tool_visualization.parsers.fusion360_makera import Fusion360MakeraParser

    class FailedParser(ToolTableParser):
        name = "synthetic failure"

        def parse(self, lines):
            list(lines)
            raise ValueError("synthetic parser failure")

    monkeypatch.setattr(extractor, "TOOL_TABLE_PARSERS", [FailedParser(), Fusion360MakeraParser()])
    table = extractor.extract_tool_table(iter(["(T2  End mill  D=3 - flat end mill)", "G0 X0"]))
    assert list(table) == [2] and table[2].diameter == 3
