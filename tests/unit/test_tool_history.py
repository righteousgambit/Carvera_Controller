"""Tests for per-tool TLO and usage history."""

import pytest

from carveracontroller.machine.tool_history import (
    GOOD_DELTA_MM,
    SUSPECT_DELTA_MM,
    TloReport,
    ToolCondition,
    ToolHistory,
    parse_tlo_report,
)

# Exactly as the firmware prints it (ATCHandler.cpp:2181-2197).
_REPORT = """------------------ Measurements--------------------
TLO value from measurement 1: -21.482
TLO value from measurement 2: -21.479
TLO value from measurement 3: -21.491
------------------ Results------------------------------
Using TLO value from measurement 3: -21.491
Max delta: 0.012
Lowest cutting edge: 3, Highest cutting edge: 2
-----------------------------------------------------------""".splitlines()


# ------------------------------------------------------------------ parsing


def test_parses_a_real_calibration_report():
    report = parse_tlo_report(_REPORT, timestamp=0.0)

    assert report.measurements == (-21.482, -21.479, -21.491)
    assert report.max_delta == pytest.approx(0.012)
    assert report.applied == pytest.approx(-21.491)


def test_the_using_line_is_not_counted_as_a_measurement():
    """It repeats the 'from measurement N' wording and would double-count."""
    assert len(parse_tlo_report(_REPORT, timestamp=0.0).measurements) == 3


def test_output_without_measurements_yields_nothing():
    """A single-shot calibration prints no repeat block."""
    assert parse_tlo_report(["Tool length calibrated", "ok"], timestamp=0.0) is None


def test_max_delta_is_derived_when_the_machine_did_not_print_it():
    lines = [
        "TLO value from measurement 1: -10.000",
        "TLO value from measurement 2: -10.040",
    ]
    assert parse_tlo_report(lines, timestamp=0.0).max_delta == pytest.approx(0.040)


def test_surrounding_noise_is_ignored():
    noisy = ["ok", "<Idle|MPos:0,0,0>", *_REPORT, "ok"]
    assert parse_tlo_report(noisy, timestamp=0.0).max_delta == pytest.approx(0.012)


# ---------------------------------------------------------------- condition


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (0.004, ToolCondition.GOOD),
        (GOOD_DELTA_MM - 0.0001, ToolCondition.GOOD),
        (GOOD_DELTA_MM, ToolCondition.WATCH),
        (0.020, ToolCondition.WATCH),
        (SUSPECT_DELTA_MM, ToolCondition.SUSPECT),
        (0.120, ToolCondition.SUSPECT),
    ],
)
def test_condition_thresholds(delta, expected):
    report = TloReport(measurements=(-1.0, -1.0), max_delta=delta)
    assert report.condition is expected


def test_a_tool_with_no_history_is_unknown():
    assert ToolHistory().record(1).condition is ToolCondition.UNKNOWN


# ------------------------------------------------------------------ history


def test_records_are_created_on_first_reference():
    history = ToolHistory()
    record = history.record(3)

    assert record.tool_number == 3
    assert history.tools() == [record]


def test_delta_trend_needs_two_calibrations():
    history = ToolHistory()
    history.add_report(1, TloReport((-1.0,), max_delta=0.005))
    assert history.record(1).delta_trend is None

    history.add_report(1, TloReport((-1.0,), max_delta=0.021))
    assert history.record(1).delta_trend == pytest.approx(0.016)


def test_a_worsening_tool_is_flagged():
    """The point of keeping history: the trend, not one measurement."""
    history = ToolHistory()
    history.add_report(2, TloReport((-1.0,), max_delta=0.004))
    history.add_report(2, TloReport((-1.0,), max_delta=0.045))

    record = history.record(2)
    assert record.condition is ToolCondition.SUSPECT
    assert record.delta_trend > 0
    assert record in history.needing_attention()


def test_cutting_time_accumulates_and_ignores_negative_input():
    history = ToolHistory()
    history.add_cutting_time(1, 120.0)
    history.add_cutting_time(1, 30.0)
    history.add_cutting_time(1, -500.0)

    assert history.record(1).cutting_seconds == pytest.approx(150.0)


def test_life_fraction_and_exhaustion():
    history = ToolHistory()
    record = history.record(1)
    record.life_limit_seconds = 3600.0

    history.add_cutting_time(1, 1800.0)
    assert record.life_used == pytest.approx(0.5)
    assert not record.life_exhausted

    history.add_cutting_time(1, 1800.0)
    assert record.life_exhausted
    assert record in history.needing_attention()


def test_life_is_unlimited_without_a_configured_limit():
    history = ToolHistory()
    history.add_cutting_time(1, 99999.0)

    assert history.record(1).life_used is None
    assert not history.record(1).life_exhausted


def test_a_healthy_tool_needs_no_attention():
    history = ToolHistory()
    history.add_report(1, TloReport((-1.0,), max_delta=0.003))

    assert history.needing_attention() == []


# ---------------------------------------------------------------- storage


def test_json_round_trip_preserves_everything():
    history = ToolHistory()
    history.add_report(1, TloReport((-21.482, -21.479), max_delta=0.012, applied=-21.479, timestamp=99.0))
    history.add_cutting_time(1, 640.0)
    history.record(1).life_limit_seconds = 7200.0
    history.record(1).label = "1/4in 3F carbide"

    restored = ToolHistory.from_json(history.to_json())
    record = restored.record(1)

    assert record.cutting_seconds == pytest.approx(640.0)
    assert record.life_limit_seconds == pytest.approx(7200.0)
    assert record.label == "1/4in 3F carbide"
    assert record.latest.measurements == (-21.482, -21.479)
    assert record.latest.applied == pytest.approx(-21.479)
    assert record.latest.timestamp == pytest.approx(99.0)


def test_tools_are_returned_in_number_order():
    history = ToolHistory()
    for n in (5, 1, 3):
        history.record(n)

    assert [r.tool_number for r in history.tools()] == [1, 3, 5]


@pytest.mark.parametrize("text", ["", "   ", "not json", '{"tools": "wrong type"}', "[]"])
def test_unreadable_history_loads_empty_rather_than_raising(text):
    """Losing the record is an inconvenience; refusing to start is not."""
    assert ToolHistory.from_json(text).tools() == []
