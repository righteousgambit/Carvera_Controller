"""Tests for recognising results in console output."""

import pytest

from carveracontroller.machine.console_watcher import (
    MAX_BUFFERED_LINES,
    ConsoleWatcher,
    ResultKind,
)
from carveracontroller.machine.probe_results import ProbeResultKind

_BORE = [
    "Distance Point 2 X surfaces (Diameter) is: 25.412 and center is stored at variable #151",
    "Distance between 2 Y surfaces (Diameter) is: 25.478 and is stored at variable #152",
    "Center of bore or rectangular pocket found. Ready to Zero X and Y",
    "Center Point is: -150.221 , -90.118 and is stored in MCS as #154,#155",
]

_TLO = [
    "------------------ Measurements--------------------",
    "TLO value from measurement 1: -21.482",
    "TLO value from measurement 2: -21.479",
    "TLO value from measurement 3: -21.491",
    "------------------ Results------------------------------",
    "Using TLO value from measurement 3: -21.491",
    "Max delta: 0.012",
]


def _watcher():
    results = {"probe": [], "tlo": []}
    watcher = ConsoleWatcher(
        on_probe_result=results["probe"].append,
        on_tlo_report=results["tlo"].append,
    )
    return watcher, results


def test_a_probe_result_is_emitted_when_the_cycle_completes():
    watcher, results = _watcher()

    for line in _BORE[:-1]:
        assert watcher.feed(line) is None, "emitted before the cycle finished"
    assert watcher.feed(_BORE[-1]) is ResultKind.PROBE

    assert len(results["probe"]) == 1
    assert results["probe"][0].ovality == pytest.approx(0.066, abs=1e-9)


def test_a_tlo_report_is_emitted_on_the_max_delta_line():
    watcher, results = _watcher()

    for line in _TLO[:-1]:
        assert watcher.feed(line) is None
    assert watcher.feed(_TLO[-1]) is ResultKind.TLO

    assert results["tlo"][0].max_delta == pytest.approx(0.012)


def test_unrelated_output_emits_nothing():
    watcher, results = _watcher()

    for line in ["ok", "<Idle|MPos:0,0,0>", "version = 2.2.0c"]:
        assert watcher.feed(line) is None

    assert results["probe"] == []
    assert results["tlo"] == []


def test_a_probe_failure_is_emitted_rather_than_left_buffered():
    watcher, results = _watcher()

    assert watcher.feed("ERROR: Probe fail: first point not found") is ResultKind.PROBE
    assert results["probe"][0].kind is ProbeResultKind.FAILURE


def test_the_buffer_clears_between_cycles():
    """A second cycle must not inherit the first one's numbers."""
    watcher, results = _watcher()

    for line in _BORE:
        watcher.feed(line)
    assert watcher.buffered == 0

    for line in ["Corner found. X coordinate stored in #154 as MCS -1.000 , Y coordinate in #155 as MCS -2.000"]:
        watcher.feed(line)

    assert results["probe"][1].kind is ProbeResultKind.CORNER
    assert results["probe"][1].x_diameter is None


def test_the_buffer_is_bounded():
    """A session left connected for days must not accumulate the whole log."""
    watcher, _ = _watcher()

    for index in range(MAX_BUFFERED_LINES * 3):
        watcher.feed(f"noise {index}")

    assert watcher.buffered <= MAX_BUFFERED_LINES


def test_a_result_still_parses_after_the_buffer_has_rolled():
    watcher, results = _watcher()

    for index in range(MAX_BUFFERED_LINES * 2):
        watcher.feed(f"noise {index}")
    for line in _BORE:
        watcher.feed(line)

    assert len(results["probe"]) == 1


def test_reset_discards_partial_output():
    watcher, results = _watcher()

    for line in _BORE[:-1]:
        watcher.feed(line)
    watcher.reset()
    watcher.feed(_BORE[-1])

    # The terminator alone still carries the centre, but not the diameters.
    assert results["probe"][0].x_diameter is None
    assert results["probe"][0].centre_x == pytest.approx(-150.221)


def test_callbacks_are_optional():
    watcher = ConsoleWatcher()

    assert watcher.feed(_BORE[-1]) is ResultKind.PROBE
