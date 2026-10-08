"""Tests for the G-code helpers exposed by the CNC module."""

from carveracontroller.CNC import CNC, detect_document_unit, unit_scale_to_mm


class TestDocumentUnit:
    def test_detects_g21_as_mm(self):
        assert detect_document_unit(["G90 G94\n", "G17\n", "G21\n", "G0 X0\n"]) == "mm"

    def test_detects_g20_as_inches(self):
        assert detect_document_unit(["G90\n", "G20\n", "G0 X1\n"]) == "in"

    def test_defaults_to_mm_when_absent(self):
        assert detect_document_unit(["G90 G94\n", "G0 X10\n"]) == "mm"

    def test_ignores_unit_command_inside_paren_comment(self):
        assert detect_document_unit(["(G20 inches)\n", "G21\n", "G0 X0\n"]) == "mm"

    def test_ignores_unit_command_inside_semicolon_comment(self):
        assert detect_document_unit(["; G20\n", "G21\n"]) == "mm"

    def test_accepts_lowercase_and_leading_zeros(self):
        assert detect_document_unit(["g020\n"]) == "in"
        assert detect_document_unit(["g021\n"]) == "mm"

    def test_unit_scale_to_mm(self):
        assert unit_scale_to_mm("mm") == 1.0
        assert unit_scale_to_mm("in") == 25.4
        assert unit_scale_to_mm("unknown") == 1.0


def test_controller_has_connection_address_before_connecting():
    """`updateStatus` and the camera probe read this before any connection.

    It was previously set only in `open()`, so touching it while disconnected
    raised AttributeError inside `updateStatus`'s bare `except`, silently
    abandoning everything after the camera probe — including the spindle,
    tool and coordinate panels.
    """
    from carveracontroller.Controller import Controller

    controller = Controller(CNC(), lambda _line: None, False)

    assert controller.connection_address is None


def test_document_margins_follow_cutting_path_without_including_origin():
    cnc = CNC()
    cnc.parseLine("G0 X10 Y20 Z5", 1)
    assert cnc.getMargins() == (0.0, 0.0, 0.0, 0.0)
    cnc.parseLine("S12000 G1 X12 Y24 F125.5", 2)
    assert cnc.getMargins() == (10.25, 20.5, 12.0, 24.0)
    assert cnc.feed == 125.5
    assert all(len(row) == 8 for row in cnc.coordinates)
    cnc.init()
    assert cnc.getMargins() == (0.0, 0.0, 0.0, 0.0)


def test_document_margins_preserve_negative_only_geometry():
    cnc = CNC()
    cnc.pathMargins([(-12.0, -24.0, 0.0, 0.0), (-10.0, -20.0, 0.0, 0.0)])
    assert cnc.getMargins() == (-12.0, -24.0, -10.0, -20.0)


def test_gcode_word_formatter_uses_precision_and_normalizes_zero():
    cnc = CNC()
    assert cnc.fmt("X", 12.345678) == "X12.3457"
    assert cnc.fmt("Y", 12.0) == "Y12"
    assert cnc.fmt("Z", -0.00001) == "Z0"
    assert cnc.fmt("F", 100.0, 0) == "F100"
    assert cnc.fmt("A", 1.234, 2) == "A1.23"


def test_gcode_word_formatter_rejects_nonfinite_and_invalid_precision():
    import pytest

    cnc = CNC()
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError, match="finite"):
            cnc.fmt("X", value)
    with pytest.raises(ValueError, match="precision"):
        cnc.fmt("X", 1.0, -1)
