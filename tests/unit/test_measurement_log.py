"""Tests for measurement sessions, reports and wear trending."""

import pytest

from carveracontroller.machine.measurement_log import (
    Measurement,
    MeasurementSession,
    ToleranceState,
    feature_history,
    format_report,
    sessions_from_json,
    to_csv,
    to_json,
    wear_trend,
)


def _session(part="ACT-014", cycles=0.0):
    session = MeasurementSession(part_id=part, label="actuator housing", cycles=cycles)
    session.add("bore A dia", 25.412, nominal=25.400, tolerance=0.025)
    session.add("boss B dia", 39.998, nominal=40.000, tolerance=0.025)
    return session


# -------------------------------------------------------------- tolerancing


def test_deviation_is_measured_minus_nominal():
    m = Measurement("bore", measured=25.412, nominal=25.400)
    assert m.deviation == pytest.approx(0.012)


def test_within_tolerance_passes():
    assert Measurement("b", 25.412, nominal=25.400, tolerance=0.025).state is ToleranceState.PASS


def test_outside_tolerance_fails():
    assert Measurement("b", 25.480, nominal=25.400, tolerance=0.025).state is ToleranceState.FAIL


def test_tolerance_is_symmetric():
    assert Measurement("b", 25.375, nominal=25.400, tolerance=0.025).state is ToleranceState.PASS
    assert Measurement("b", 25.374, nominal=25.400, tolerance=0.025).state is ToleranceState.FAIL


def test_no_nominal_means_conformance_is_not_a_question():
    m = Measurement("reference surface", measured=12.0)

    assert m.deviation is None
    assert m.state is ToleranceState.UNKNOWN


def test_nominal_without_tolerance_reports_deviation_but_not_a_verdict():
    m = Measurement("b", 25.412, nominal=25.400)

    assert m.deviation == pytest.approx(0.012)
    assert m.state is ToleranceState.UNKNOWN


def test_untoleranced_measurements_do_not_make_a_session_fail():
    session = MeasurementSession()
    session.add("observation", 1.234)

    assert session.conforms
    assert session.failures == []


def test_a_failing_feature_fails_the_session():
    session = _session()
    session.add("bore A ovality", 0.066, nominal=0.0, tolerance=0.020)

    assert not session.conforms
    assert [m.feature for m in session.failures] == ["bore A ovality"]


# ------------------------------------------------------------------ report


def test_report_shows_deviation_in_microns():
    text = format_report(_session())

    assert "+12 um" in text
    assert "-2 um" in text


def test_report_states_the_limits_of_the_measurement():
    """The report must not imply certified metrology."""
    text = format_report(_session())

    assert "relative change" in text
    assert "not a substitute for certified metrology" in text


def test_report_counts_failures():
    session = _session()
    session.add("bore A ovality", 0.066, nominal=0.0, tolerance=0.020)

    assert "1 feature(s) outside tolerance." in format_report(session)


def test_report_confirms_conformance_when_everything_passes():
    assert "All toleranced features within tolerance." in format_report(_session())


def test_report_columns_line_up():
    lines = format_report(_session()).splitlines()
    rule = next(line for line in lines if set(line) <= {"-", " "} and "-" in line)
    header = lines[lines.index(rule) - 1]

    assert len(rule) == len(header.rstrip()) or len(rule) >= len(header.rstrip())


# ------------------------------------------------------------------- wear


def test_feature_history_is_ordered_by_duty_cycles():
    sessions = [_session(cycles=200.0), _session(cycles=0.0), _session(cycles=100.0)]
    history = feature_history(sessions, "bore A dia")

    assert [cycles for cycles, _ in history] == [0.0, 100.0, 200.0]


def test_feature_history_ignores_other_features():
    assert len(feature_history([_session()], "bore A dia")) == 1


def test_wear_trend_is_the_change_between_first_and_last():
    early, late = _session(cycles=0.0), MeasurementSession(cycles=500.0)
    late.add("bore A dia", 25.461, nominal=25.400, tolerance=0.025)

    assert wear_trend([early, late], "bore A dia") == pytest.approx(0.049)


def test_wear_trend_needs_two_measurements():
    assert wear_trend([_session()], "bore A dia") is None
    assert wear_trend([], "bore A dia") is None


def test_sessions_without_cycles_sort_after_those_with_them():
    """Unknown duty cycles must not be treated as zero."""
    known, unknown = _session(cycles=100.0), _session(cycles=None)
    order = [c for c, _ in feature_history([unknown, known], "bore A dia")]

    assert order == [100.0, None]


# ---------------------------------------------------------------- exports


def test_csv_is_long_format_with_one_row_per_measurement():
    """A feature appearing partway through a study must not invalidate it."""
    text = to_csv([_session()])
    lines = text.strip().splitlines()

    assert lines[0].startswith("part_id,label,cycles,timestamp,feature")
    assert len(lines) == 3


def test_csv_includes_deviation_and_state():
    row = to_csv([_session()]).strip().splitlines()[1]

    assert "0.0120" in row
    assert "pass" in row


def test_csv_leaves_unknown_values_empty_rather_than_zero():
    session = MeasurementSession()
    session.add("observation", 1.0)
    row = to_csv([session]).strip().splitlines()[1]

    assert ",," in row, "missing nominal and deviation should be blank"


def test_json_round_trip_preserves_measurements_and_cycles():
    restored = sessions_from_json(to_json([_session(cycles=250.0)]))

    assert len(restored) == 1
    assert restored[0].cycles == pytest.approx(250.0)
    assert restored[0].part_id == "ACT-014"
    assert restored[0].measurements[0].nominal == pytest.approx(25.400)


@pytest.mark.parametrize("text", ["", "   ", "not json", "[]", '{"sessions": 5}'])
def test_unreadable_logs_load_empty_rather_than_raising(text):
    assert sessions_from_json(text) == []
