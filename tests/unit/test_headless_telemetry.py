import pytest

from carveracontroller.headless.telemetry import parse_diagnostics, parse_status


def test_community_fields_preserve_missing_rotary_axes_and_explicit_units():
    status = parse_status("<Idle|MPos:1,2,3,45|WPos:0,0,1|C:1,4,1,1|F:2,3,100|T:1,50.48>")
    assert status["machine_position"] == {"x": 25.4, "y": 50.8, "z": 76.19999999999999, "a": 45, "b": None}
    assert status["work_position"]["a"] is None
    assert status["spindle_rpm"] is None
    assert status["tool_offset_reported"] == 50.48
    assert status["is_playing"] is None


def test_community_diagnostic_inputs_are_not_confused_with_tool_calibration():
    data = parse_diagnostics("{G:1|E:0,0,0,0,0,1,1,0|P:1,0|I:0|A:0,1}")
    assert data["cover_input"] is True
    assert data["probe_triggered"] is True
    assert data["setter_triggered"] is False
    assert data["stop_input"] is False
    assert data["tool_sensor_input"] is True
    assert "tool_calibrated" not in data
    assert data["air_on"] is None


def test_unknown_units_never_manufacture_mm_coordinates():
    status = parse_status("<FutureState|MPos:1,2,3>")
    assert status["state"] == "Unknown"
    assert status["machine_position"]["x"] is None
    assert status["linear_units"] is None


@pytest.mark.parametrize("text", ["{P:0,0|P:1,1}", "{I:nan}", "{E:inf}", "{G:1", "{I:0:1}"])
def test_invalid_diagnostics_are_rejected(text):
    with pytest.raises(ValueError):
        parse_diagnostics(text)


def test_non_boolean_input_stays_unknown():
    assert parse_diagnostics("{I:2|P:-1,0}")["stop_input"] is None
