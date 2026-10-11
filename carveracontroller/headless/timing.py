"""Bounded host-clock evidence; no firmware-age or physical-response inference."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import ceil
from statistics import mean
from typing import Any

from ..machine.telemetry_quality import TelemetryQuality, valid_arrival_time


@dataclass
class CommandTiming:
    queued_at: float
    admitted_at: float
    send_started_at: float | None = None
    send_completed_at: float | None = None
    acknowledged_at: float | None = None

    def finish(self, now: float, connection_id: str | None, outcome: str) -> dict[str, Any]:
        stamps = [self.queued_at, self.admitted_at, now]
        stamps.extend(v for v in (self.send_started_at, self.send_completed_at, self.acknowledged_at) if v is not None)
        supported_clock = all(valid_arrival_time(v) for v in stamps)
        valid = supported_clock and self.queued_at <= self.admitted_at <= now
        if self.send_started_at is not None:
            valid = valid and self.admitted_at <= self.send_started_at <= now
        if self.send_completed_at is not None:
            valid = valid and self.send_started_at is not None and self.send_started_at <= self.send_completed_at <= now
        if self.acknowledged_at is not None:
            valid = valid and self.send_started_at is not None and self.send_started_at <= self.acknowledged_at <= now

        def interval(start: float | None, end: float | None) -> float | None:
            return (end - start) * 1000 if valid and start is not None and end is not None else None

        return {
            "connection_id": connection_id,
            "outcome": outcome,
            "clock_state": "valid" if valid else "invalid",
            "clock_issue": None if valid else "timestamp_order" if supported_clock else "unsupported_timestamp",
            "timing_source": "headless host monotonic clock",
            "queued_at_s": self.queued_at if valid else None,
            "admitted_at_s": self.admitted_at if valid else None,
            "send_started_at_s": self.send_started_at if valid else None,
            "send_completed_at_s": self.send_completed_at if valid else None,
            "acknowledged_at_s": self.acknowledged_at if valid else None,
            "finished_at_s": now if valid else None,
            "command_queue_ms": interval(self.queued_at, self.admitted_at),
            "dispatch_to_send_ms": interval(self.admitted_at, self.send_started_at),
            "send_call_ms": interval(self.send_started_at, self.send_completed_at),
            "send_start_to_ack_ms": interval(self.send_started_at, self.acknowledged_at),
            "ack_to_return_ms": interval(self.acknowledged_at, now),
            "total_ms": interval(self.queued_at, now),
            "ack_observed_during_send": self.acknowledged_at < self.send_completed_at
            if valid and self.acknowledged_at is not None and self.send_completed_at is not None
            else None,
            "firmware_sample_age_ms": None,
            "one_way_network_latency_ms": None,
            "physical_response_ms": None,
            "motion_completed": False,
        }


class TransportDiagnostics:
    """Owned by the link condition lock; reset on every new connection."""

    def __init__(self) -> None:
        self.reset(None)

    def reset(self, connection_id: str | None) -> None:
        self.connection_id = connection_id
        self.status = TelemetryQuality(expected_interval=0.3, stale_after=1.2)
        self.diagnostics = TelemetryQuality(expected_interval=1.3, stale_after=3)
        self.commands: deque[dict[str, Any]] = deque(maxlen=64)
        self.total_commands = 0
        self.rejected_connection_timings = 0

    def observation(self, kind: str, now: float, observation: dict[str, Any]) -> None:
        if kind == "status":
            required = ("spindle_rpm", "spindle_target_rpm")
            self.status.record(
                now,
                missing=tuple(key for key in required if observation.get(key) is None),
                valid=observation.get("state") != "Unknown",
                rpm=observation.get("spindle_rpm"),
            )
        elif kind == "diagnostics":
            self.diagnostics.record(now)
        else:
            raise ValueError("Unknown transport observation")

    def record_command(self, timing: dict[str, Any]) -> bool:
        if self.connection_id is None or timing["connection_id"] != self.connection_id:
            self.rejected_connection_timings += 1
            return False
        self.total_commands += 1
        self.commands.append(dict(timing))
        return True

    def snapshot(self, now: float) -> dict[str, Any]:
        status = self.status.snapshot(now)
        diagnostics = self.diagnostics.snapshot(now)
        status["timing_source"] = diagnostics["timing_source"] = "headless host monotonic receive time"
        rows = list(self.commands)
        values = [
            r["send_start_to_ack_ms"]
            for r in rows
            if r["clock_state"] == "valid" and r["send_start_to_ack_ms"] is not None
        ]
        return {
            "connection_id": self.connection_id,
            "status_arrivals": status,
            "diagnostic_arrivals": diagnostics,
            "total_commands": self.total_commands,
            "rejected_connection_timings": self.rejected_connection_timings,
            "window_commands": len(rows),
            "invalid_clock_commands": sum(r["clock_state"] != "valid" for r in rows),
            "outcomes": {
                key: sum(r["outcome"] == key for r in rows)
                for key in ("controller_acknowledged", "controller_rejected", "unknown_outcome")
            },
            "mean_send_start_to_ack_ms": mean(values) if values else None,
            "p95_send_start_to_ack_ms": sorted(values)[ceil(len(values) * 0.95) - 1] if values else None,
            "maximum_send_start_to_ack_ms": max(values) if values else None,
            "recent_commands": [dict(r) for r in rows],
            "poll_schedule_limit": "Nominal status0.3s/diagnostics1.3s; command/transfer contention and host scheduling can delay polling",
            "timing_limit": "Host arrival and command acknowledgment evidence only; no firmware sample age, one-way network delay, physical response or safety/readiness inference",
            "realtime_acknowledgments_available": False,
        }
