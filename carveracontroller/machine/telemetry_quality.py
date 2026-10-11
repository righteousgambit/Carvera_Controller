"""Bounded desktop arrival diagnostics, not a claim about firmware sample age."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from math import ceil, isfinite
from statistics import mean
from typing import Any, cast


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
            type(expected_interval) not in (int, float)
            or type(stale_after) not in (int, float)
            or not isfinite(expected_interval)
            or not isfinite(stale_after)
            or not 0 < expected_interval < stale_after
            or not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or not 2 <= capacity <= 10000
        ):
            raise ValueError("invalid telemetry timing window")
        self.expected_interval = expected_interval
        self.stale_after = stale_after
        self.history: deque[Arrival] = deque(maxlen=capacity)
        self.total_packets = 0
        self.rejected_timestamps = 0
        self.source_latest: dict[str, int] | None = None
        self.source_gaps = 0
        self.source_resets = 0
        self.source_regressions = 0
        self.source_duplicates = 0
        self.source_state = "unavailable"
        self.source_current_packet = False

    def record_source(self, source: Mapping[str, int]) -> str:
        """Firmware clock is independent of host clock; no transport-delay estimate."""
        required = {
            "version",
            "boot_id",
            "boot_id_valid",
            "sequence",
            "tick_us",
            "tick_wraps",
            "valid_mask",
            "position_source",
            "feed_source",
        }
        if not required.issubset(source) or any(
            type(source[key]) is not int or not 0 <= source[key] <= 2**32 - 1 for key in required
        ):
            raise ValueError("invalid firmware source metadata")
        if source["version"] != 1 or source["boot_id_valid"] not in (0, 1):
            raise ValueError("invalid firmware source schema")
        self.source_current_packet = True
        previous = self.source_latest
        state = "receiving"
        if previous:
            boot_changed = (
                source["boot_id_valid"] and previous["boot_id_valid"] and source["boot_id"] != previous["boot_id"]
            )
            clock = source["tick_wraps"] * 2**32 + source["tick_us"]
            old_clock = previous["tick_wraps"] * 2**32 + previous["tick_us"]
            if boot_changed:
                self.source_resets += 1
                state = "confirmed boot change"
            elif clock < old_clock:
                self.source_regressions += 1
                state = (
                    "duplicate or reordered source sample"
                    if source["boot_id_valid"] and previous["boot_id_valid"]
                    else "source clock regression or reset"
                )
            elif (source["sequence"] - previous["sequence"]) % 2**32 == 0 or (
                source["sequence"] - previous["sequence"]
            ) % 2**32 >= 2**31:
                self.source_duplicates += 1
                state = "duplicate or reordered source sample"
            elif (source["sequence"] - previous["sequence"]) % 2**32 > 1:
                self.source_gaps += (source["sequence"] - previous["sequence"]) % 2**32 - 1
                state = "source sequence gap"
        if state != "duplicate or reordered source sample":
            self.source_latest = dict(source)
        self.source_current_packet = state != "duplicate or reordered source sample"
        self.source_state = state
        return state

    def record(
        self,
        timestamp: float,
        *,
        missing: Iterable[str] = (),
        valid: bool = True,
        rpm: float | None = None,
        pwm_available: bool = False,
    ) -> None:
        self.total_packets += 1
        previous = self.history[-1] if self.history else None
        if (
            type(timestamp) not in (int, float)
            or not isfinite(timestamp)
            or timestamp < 0
            or (previous and timestamp <= previous.timestamp)
        ):
            self.rejected_timestamps += 1
            return
        self.history.append(
            Arrival(
                timestamp,
                timestamp - previous.timestamp if previous else None,
                tuple(missing),
                bool(valid),
                rpm if rpm is not None and not isinstance(rpm, bool) and isfinite(rpm) and rpm >= 0 else None,
                bool(pwm_available),
            )
        )

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
        packets = list(self.history)
        # The interval entering the retained window belongs to a discarded packet.
        intervals = [p.interval for p in packets[1:] if p.interval is not None]
        latest = packets[-1] if packets else None
        clock_valid = now is None or (
            type(now) in (int, float) and isfinite(now) and (latest is None or now >= latest.timestamp)
        )
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
            "window_duration_s": cast(Arrival, latest).timestamp - packets[0].timestamp if packets else 0,
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
            "firmware_source": dict(self.source_latest) if self.source_latest else None,
            "firmware_source_in_current_packet": self.source_current_packet,
            "firmware_source_state": self.source_state,
            "firmware_missing_samples": self.source_gaps,
            "firmware_confirmed_boot_changes": self.source_resets,
            "firmware_clock_regressions": self.source_regressions,
            "firmware_duplicate_or_reordered": self.source_duplicates,
            "firmware_sample_age_s": None,
            "one_way_transport_delay_s": None,
            "command_response_latency_s": None,
            "timing_source": "desktop monotonic receive time",
            "rpm_resolution_source": "minimum observed change; not sensor resolution",
        }

    def export(self, now: float) -> dict[str, Any]:
        return {"quality": self.snapshot(now), "arrivals": [asdict(p) for p in self.history]}
