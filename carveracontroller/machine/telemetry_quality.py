"""Bounded desktop arrival diagnostics, not a claim about firmware sample age."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import ceil, isfinite
from statistics import mean
from typing import TypedDict


def finite_number(value: object) -> bool:
    """Reject booleans, coercion and overflowing integers at the signal boundary."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return isfinite(value)
    except OverflowError:
        return False


def valid_arrival_time(value: object) -> bool:
    # Monotonic desktop seconds, bounded to keep interval arithmetic finite.
    return finite_number(value) and isinstance(value, (int, float)) and 0 <= value <= 1e12


class QualitySnapshot(TypedDict):
    state: str
    arrival_age_s: float | None
    expected_poll_interval_s: float
    stale_after_s: float
    window_packets: int
    window_duration_s: float
    complete_packets: int
    incomplete_packets: int
    invalid_packets: int
    total_packets: int
    rejected_timestamps: int
    mean_interval_s: float | None
    p95_interval_s: float | None
    maximum_interval_s: float | None
    gap_threshold_s: float
    gap_count: int
    estimated_unobserved_poll_slots: int
    latest_missing: list[str]
    pwm_packets: int
    rpm_observed_minimum_change: float | None
    firmware_sample_age_s: None
    one_way_transport_delay_s: None
    command_response_latency_s: None
    timing_source: str
    rpm_resolution_source: str


class ArrivalPayload(TypedDict):
    timestamp: float
    interval: float | None
    missing: tuple[str, ...]
    valid: bool
    rpm: float | None
    pwm_available: bool


class QualityExport(TypedDict):
    quality: QualitySnapshot
    arrivals: list[ArrivalPayload]


@dataclass(frozen=True)
class Arrival:
    timestamp: float
    interval: float | None
    missing: tuple[str, ...]
    valid: bool
    rpm: float | None
    pwm_available: bool


class TelemetryQuality:
    def __init__(self, expected_interval: float = 0.2, stale_after: float = 0.8, capacity: int = 300) -> None:
        if (
            not finite_number(expected_interval)
            or not finite_number(stale_after)
            or not 0 < expected_interval < stale_after
            or not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity < 2
        ):
            raise ValueError("invalid telemetry timing window")
        self.expected_interval = expected_interval
        self.stale_after = stale_after
        self.history: deque[Arrival] = deque(maxlen=capacity)
        self.total_packets = 0
        self.rejected_timestamps = 0

    def record(
        self,
        timestamp: float,
        *,
        missing: tuple[str, ...] = (),
        valid: bool = True,
        rpm: float | None = None,
        pwm_available: bool = False,
    ) -> None:
        self.total_packets += 1
        previous = self.history[-1] if self.history else None
        if not valid_arrival_time(timestamp) or (previous and timestamp <= previous.timestamp):
            self.rejected_timestamps += 1
            return
        self.history.append(
            Arrival(
                timestamp,
                timestamp - previous.timestamp if previous else None,
                tuple(missing),
                bool(valid),
                rpm if finite_number(rpm) else None,
                bool(pwm_available),
            )
        )

    def snapshot(self, now: float | None = None) -> QualitySnapshot:
        packets = list(self.history)
        # The interval entering the retained window belongs to a discarded packet.
        intervals = [p.interval for p in packets[1:] if p.interval is not None]
        latest = packets[-1] if packets else None
        clock_valid = now is None or (valid_arrival_time(now) and (latest is None or now >= latest.timestamp))
        age = now - latest.timestamp if latest and now is not None and clock_valid else None
        gap_threshold = self.expected_interval * 2.5
        gaps = [dt for dt in intervals if dt > gap_threshold]
        complete = sum(not p.missing and p.valid for p in packets)
        rpms = [p.rpm for p in packets if p.rpm is not None and p.valid and not p.missing]
        steps = [abs(b - a) for a, b in zip(rpms, rpms[1:]) if a != b]
        state = (
            "unavailable"
            if not latest
            else "clock invalid"
            if not clock_valid
            else "stale"
            if age is not None and age > self.stale_after
            else "incomplete"
            if latest.missing or not latest.valid
            else "irregular"
            if gaps or self.rejected_timestamps
            else "receiving"
        )
        return {
            "state": state,
            "arrival_age_s": age,
            "expected_poll_interval_s": self.expected_interval,
            "stale_after_s": self.stale_after,
            "window_packets": len(packets),
            "window_duration_s": latest.timestamp - packets[0].timestamp if latest else 0,
            "complete_packets": complete,
            "incomplete_packets": sum(bool(p.missing) for p in packets),
            "invalid_packets": sum(not p.valid for p in packets),
            "total_packets": self.total_packets,
            "rejected_timestamps": self.rejected_timestamps,
            "mean_interval_s": mean(intervals) if intervals else None,
            "p95_interval_s": sorted(intervals)[ceil(len(intervals) * 0.95) - 1] if intervals else None,
            "maximum_interval_s": max(intervals) if intervals else None,
            "gap_threshold_s": gap_threshold,
            "gap_count": len(gaps),
            "estimated_unobserved_poll_slots": sum(max(0, round(dt / self.expected_interval) - 1) for dt in gaps),
            "latest_missing": list(latest.missing) if latest else [],
            "pwm_packets": sum(p.pwm_available for p in packets),
            "rpm_observed_minimum_change": min(steps) if steps else None,
            "firmware_sample_age_s": None,
            "one_way_transport_delay_s": None,
            "command_response_latency_s": None,
            "timing_source": "desktop monotonic receive time",
            "rpm_resolution_source": "minimum observed change; not sensor resolution",
        }

    def export(self, now: float) -> QualityExport:
        return {
            "quality": self.snapshot(now),
            "arrivals": [
                {
                    "timestamp": p.timestamp,
                    "interval": p.interval,
                    "missing": p.missing,
                    "valid": p.valid,
                    "rpm": p.rpm,
                    "pwm_available": p.pwm_available,
                }
                for p in self.history
            ],
        }
