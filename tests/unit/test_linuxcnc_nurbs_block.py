import hashlib

import pytest

from carveracontroller.machine.linuxcnc_nurbs_block import INTERPRETER_REVISION, parse_linuxcnc_nurbs_block
from carveracontroller.machine.nurbs_geometry import tessellate_nurbs


def parse(text, **kwargs):
    return parse_linuxcnc_nurbs_block(
        text,
        start_mm=kwargs.pop("start_mm", (0, 0, 0)),
        plane=kwargs.pop("plane", "G17"),
        unit_scale=kwargs.pop("unit_scale", 1),
        distance=kwargs.pop("distance", "G90"),
        **kwargs,
    )


def test_complete_documented_block_preserves_controls_weights_source_and_version():
    text = "G5.2 P1 L3\nX0 Y1 P1\nX2 Y2 P1\nX2 Y0 P1\nX0 Y0 P2\nG5.3"
    block = parse(text, start_line=10, feed_per_minute_mm=10)
    assert block.curve.control_points_mm == ((0, 0, 0), (0, 1, 0), (2, 2, 0), (2, 0, 0), (0, 0, 0))
    assert block.curve.weights == (1, 1, 1, 1, 2)
    assert block.curve.knots == (0, 0, 0, 1, 2, 3, 3, 3)
    assert block.control_source_lines == (None, 11, 12, 13, 14)
    assert (block.start_line, block.end_line) == (10, 15)
    assert block.source_sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert block.interpreter_revision == INTERPRETER_REVISION
    assert block.final_feed_per_minute_mm == 10
    assert len(tessellate_nurbs(block.curve, tolerance_mm=0.01).points_mm) > 3


@pytest.mark.parametrize(
    ("plane", "words", "expected"),
    [("G17", "X1 Y2", (26.4, 52.8, 3)), ("G18", "X1 Z2", (26.4, 2, 53.8)), ("G19", "Y1 Z2", (1, 27.4, 53.8))],
)
def test_incremental_controls_remain_relative_to_preblock_position(plane, words, expected):
    block = parse(
        f"G5.2 P2\n{words} P1\n{words} P3\nG5.3", start_mm=(1, 2, 3), plane=plane, distance="G91", unit_scale=25.4
    )
    assert block.curve.control_points_mm[1] == pytest.approx(expected)
    assert block.curve.control_points_mm[2] == pytest.approx(expected)
    assert block.curve.weights[0] == 2


def test_opening_axes_use_p_for_new_control_and_later_low_l_does_not_reset_order():
    block = parse("G5.2 X1 Y2 P2 L4\nG5.2 X2 Y3 P3 L2\nX3 Y4 P4\nG5.3")
    assert block.curve.weights == (1, 2, 3, 4)
    assert block.curve.degree == 3
    assert block.control_source_lines == (None, 1, 2, 3)


@pytest.mark.parametrize(
    "text",
    [
        "G5.3",
        "G5.2 P1\nX1 Y2 P1",
        "G5.2 P1\nX1 P1\nG5.3",
        "G5.2 P1\nX1 Y2\nX2 Y3 P1\nG5.3",
        "G5.2 P1\nX1 Y2 P0\nG5.3",
        "G5.2 P1\nX1 Y2 P-1\nG5.3",
        "G5.2 P1\nG1 X1 Y2 P1\nG5.3",
        "G5.2 P1\nG20\nG5.3",
        "G5.2 P1\nX1 Y2 Z3 P1\nG5.3",
        "G5.2 P1\nX1 X2 Y2 P1\nG5.3",
        "G5.2 P1\nX#1 Y2 P1\nG5.3",
        "G5.2 P1\nX1 Y2 P1 M3\nG5.3",
        "G5.2 P1\nX1 Y2 P1\nX2 Y3 P1\nG5.3 X1",
        "G5.2 P1\nX1 Y2 P1\nX2 Y3 P1\nG5.3\nG1 X0",
        "G5.2 P1 L2.5\nX1 Y2 P1\nX2 Y3 P1\nG5.3",
    ],
)
def test_incomplete_ambiguous_or_side_effecting_blocks_are_refused(text):
    with pytest.raises(ValueError):
        parse(text)


def test_comments_line_identity_and_feed_unit_conversion():
    block = parse("(local study)\nG5.2 P1 F10\n;note\nX1 Y2 P1\nX2 Y3 P1\nG5.3\n", unit_scale=25.4, start_line=20)
    assert block.start_line == 21 and block.end_line == 25
    assert block.control_source_lines == (None, 23, 24)
    assert block.final_feed_per_minute_mm == 254
    assert block.curve.control_points_mm[1] == pytest.approx((25.4, 50.8, 0))


def test_feed_unit_conversion_overflow_is_refused():
    with pytest.raises(ValueError, match="feed"):
        parse("G5.2 P1 F1e308\nX1 Y2 P1\nX2 Y3 P1\nG5.3", unit_scale=25.4)


def test_fractional_line_number_is_refused():
    with pytest.raises(ValueError, match="line number"):
        parse("N1.5 G5.2 P1\nX1 Y2 P1\nX2 Y3 P1\nG5.3")
