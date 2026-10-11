from math import inf

import pytest

from carveracontroller.machine.telemetry_quality import TelemetryQuality


def test_arrival_timing_and_gaps_are_not_claimed_as_firmware_or_transport_latency():
    quality = TelemetryQuality()
    for t, rpm in ((1, 12000), (1.2, 11950), (1.4, 11850), (2.4, 11850)):
        quality.record(t, rpm=rpm, pwm_available=True)
    result = quality.snapshot(2.5)
    assert result["arrival_age_s"] == pytest.approx(0.1)
    assert result["p95_interval_s"] == pytest.approx(1)
    assert result["gap_count"] == 1
    assert result["estimated_unobserved_poll_slots"] == 4
    assert result["rpm_observed_minimum_change"] == 50
    assert result["state"] == "irregular"
    assert result["firmware_sample_age_s"] is None
    assert result["one_way_transport_delay_s"] is None
    assert result["command_response_latency_s"] is None


def test_incomplete_status_packets_count_without_reusing_previous_spindle_signal():
    quality = TelemetryQuality()
    quality.record(1, rpm=12000, pwm_available=True)
    quality.record(1.2, missing=("S", "F"))
    result = quality.snapshot(1.3)
    assert result["complete_packets"] == 1 and result["window_packets"] == 2
    assert result["pwm_packets"] == 1
    assert result["latest_missing"] == ["S", "F"]
    assert result["state"] == "incomplete"
    assert quality.export(1.3)["arrivals"][-1]["rpm"] is None


def test_invalid_or_regressed_timestamps_do_not_refresh_arrival_age():
    quality = TelemetryQuality()
    quality.record(2)
    quality.record(1)
    quality.record(inf)
    quality.record(2)
    result = quality.snapshot(3)
    assert result["rejected_timestamps"] == 3
    assert result["arrival_age_s"] == 1
    assert result["state"] == "stale"
    assert quality.snapshot(1)["state"] == "clock invalid"
    assert quality.snapshot(inf)["arrival_age_s"] is None


def test_window_evicts_old_gaps_and_never_reports_static_rpm_as_sensor_resolution():
    quality = TelemetryQuality(capacity=3)
    for t in (0, 1, 1.2, 1.4):
        quality.record(t, rpm=12000)
    result = quality.snapshot(1.4)
    assert result["gap_count"] == 0
    assert result["window_packets"] == 3 and result["total_packets"] == 4
    assert result["mean_interval_s"] == pytest.approx(0.2)
    assert result["rpm_observed_minimum_change"] is None


def test_invalid_signal_does_not_contribute_rpm_resolution_or_complete_coverage():
    quality = TelemetryQuality()
    quality.record(1, rpm=12000)
    quality.record(1.2, rpm=11999, valid=False)
    result = quality.snapshot(1.2)
    assert result["invalid_packets"] == 1 and result["complete_packets"] == 1
    assert result["rpm_observed_minimum_change"] is None
    assert result["state"] == "incomplete"


@pytest.mark.parametrize("settings", [{"stale_after": inf}, {"expected_interval": 0}, {"capacity": True}])
def test_invalid_window_parameters_are_rejected(settings):
    with pytest.raises(ValueError):
        TelemetryQuality(**settings)


@pytest.mark.parametrize("timestamp", ["1.2", True, None, -1, 1e308, 10**1000])
def test_malformed_arrival_does_not_refresh_the_quality_window(timestamp):
    quality = TelemetryQuality()
    quality.record(1, rpm=12000)
    quality.record(timestamp, rpm=12000)
    result = quality.snapshot(1.5)
    assert result["window_packets"] == 1 and result["rejected_timestamps"] == 1
    assert result["arrival_age_s"] == 0.5


@pytest.mark.parametrize("rpm", ["12000", True, float("nan"), 10**1000])
def test_malformed_rpm_cannot_enter_quality_exports(rpm):
    import json

    quality = TelemetryQuality()
    quality.record(1, rpm=rpm, valid=False)
    result = quality.export(1.1)
    assert result["arrivals"][0]["rpm"] is None
    json.dumps(result, allow_nan=False)
