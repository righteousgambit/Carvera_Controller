"""Results scrolling past in the console are captured, not just displayed."""

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.machine.tool_history import ToolHistory
from carveracontroller.machine.usage_counters import UsageCounters

_BORE = [
    "Distance Point 2 X surfaces (Diameter) is: 25.412 and center is stored at variable #151",
    "Distance between 2 Y surfaces (Diameter) is: 25.478 and is stored at variable #152",
    "Center of bore or rectangular pocket found. Ready to Zero X and Y",
    "Center Point is: -150.221 , -90.118 and is stored in MCS as #154,#155",
]

_TLO = [
    "TLO value from measurement 1: -21.482",
    "TLO value from measurement 2: -21.479",
    "TLO value from measurement 3: -21.491",
    "Max delta: 0.012",
]


def test_a_probe_result_is_captured_from_the_stream(kivy_app):
    kivy_app.root.usage_counters = UsageCounters()
    for line in _BORE:
        kivy_app.root._watch_console_line(line)

    result = kivy_app.root.last_probe_result

    assert result is not None
    assert result.ovality == pytest.approx(0.066, abs=1e-9)
    assert kivy_app.root.usage_counters.probe_cycles == 1


def test_a_tlo_report_is_filed_against_the_current_tool(kivy_app):
    kivy_app.root.tool_history = ToolHistory()
    CNC.vars["tool"] = 3
    for line in _TLO:
        kivy_app.root._watch_console_line(line)

    record = kivy_app.root.tool_history.record(3)

    assert record.latest is not None
    assert record.latest.max_delta == pytest.approx(0.012)


def test_a_tlo_report_with_no_tool_selected_is_not_misfiled(kivy_app):
    kivy_app.root.tool_history = ToolHistory()
    CNC.vars["tool"] = -1
    for line in _TLO:
        kivy_app.root._watch_console_line(line)

    assert kivy_app.root.tool_history.tools() == []


def test_watching_never_raises_on_unexpected_input(kivy_app):
    """Watching the log must never disturb the log."""
    for line in ["", "\x00 binary junk", "Max delta: not-a-number"]:
        kivy_app.root._watch_console_line(line)


def test_ordinary_output_is_ignored(kivy_app):
    kivy_app.root.last_probe_result = None
    for line in ["ok", "<Idle|MPos:0,0,0>", "version = 2.2.0c"]:
        kivy_app.root._watch_console_line(line)

    assert kivy_app.root.last_probe_result is None
