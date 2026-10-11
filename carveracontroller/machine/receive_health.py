"""Bounded receive observations; diagnostics never establish machine readiness."""

from __future__ import annotations

import math
import threading
from collections import deque
from copy import deepcopy
from math import ceil
from statistics import mean
from typing import Any

from .telemetry_quality import valid_arrival_time


class ReceiveHealth:
    def __init__(self, generation: int, started_at: float) -> None:
        self._lock = threading.Lock()
        self.generation = generation
        self.started_at = started_at
        self._stage = "starting"
        self._stage_at = started_at
        self._loop_at: float | None = None
        self._poll_at: float | None = None
        self._wire_at: float | None = None
        self._status_at: float | None = None
        self._polls = self._bytes = self._statuses = self._errors = 0
        self._events: deque[dict[str, Any]] = deque(maxlen=32)
        self._writes: deque[dict[str, Any]] = deque(maxlen=64)
        self._write_calls = self._write_failures = self._write_observation_errors = 0

    def stage(self, name: str, now: float, *, loop: bool = False) -> None:
        with self._lock:
            if name != self._stage:
                self._stage, self._stage_at = name, now
            if loop:
                self._loop_at = now

    def poll(self, now: float) -> None:
        with self._lock:
            self._poll_at = now
            self._polls += 1

    def wire(self, count: int, now: float) -> None:
        if count <= 0:
            return
        with self._lock:
            self._wire_at = now
            self._bytes += count

    def status(self, now: float) -> None:
        with self._lock:
            self._status_at = now
            self._statuses += 1

    def error(self, error: Exception, now: float) -> None:
        with self._lock:
            self._errors += 1
            # Class and stage suffice; exception text can contain private data.
            self._events.append({"at": now, "stage": self._stage, "error_class": type(error).__name__})

    def write(
        self,
        kind: str,
        requested_bytes: int,
        started: float,
        finished: float,
        returned: bool,
        error_class: str | None = None,
    ) -> None:
        if kind not in ("command", "realtime", "file_initiation"):
            return
        valid_clock = valid_arrival_time(started) and valid_arrival_time(finished) and finished >= started
        row = {
            "kind": kind,
            "requested_bytes": requested_bytes
            if isinstance(requested_bytes, int) and not isinstance(requested_bytes, bool) and requested_bytes >= 0
            else None,
            "started_at_s": started if valid_clock else None,
            "finished_at_s": finished if valid_clock else None,
            "duration_ms": (finished - started) * 1000 if valid_clock else None,
            "call_returned": returned,
            "error_class": error_class[:64]
            if error_class and error_class.isascii() and error_class.isidentifier()
            else "Exception"
            if error_class
            else None,
            "delivery_verified": False,
            "acknowledgment_latency_ms": None,
            "physical_response_ms": None,
        }
        with self._lock:
            self._write_calls += 1
            self._write_failures += not returned
            self._writes.append(row)

    def write_gap(self) -> None:
        with self._lock:
            self._write_observation_errors += 1

    def snapshot(self, now: float) -> dict[str, Any]:
        def age(stamp: float | None) -> float | None:
            return max(0.0, now - stamp) if stamp is not None and math.isfinite(now) and now >= stamp else None

        with self._lock:
            rows = list(self._writes)
            durations = [r["duration_ms"] for r in rows if r["duration_ms"] is not None]
            return {
                "connection_generation": self.generation,
                "stage": self._stage,
                "stage_age_s": age(self._stage_at),
                "loop_age_s": age(self._loop_at),
                "poll_age_s": age(self._poll_at),
                "wire_age_s": age(self._wire_at),
                "valid_status_age_s": age(self._status_at),
                "polls_sent": self._polls,
                "bytes_received": self._bytes,
                "valid_status_packets": self._statuses,
                "receive_errors": self._errors,
                "recent_errors": deepcopy(list(self._events)),
                "control_writes": {
                    "connection_generation": self.generation,
                    "total_calls": self._write_calls,
                    "failed_calls": self._write_failures,
                    "unavailable_observations": self._write_observation_errors,
                    "window_calls": len(rows),
                    "last_call_age_s": age(rows[-1]["finished_at_s"]) if rows else None,
                    "last_call_ms": rows[-1]["duration_ms"] if rows else None,
                    "mean_call_ms": mean(durations) if durations else None,
                    "p95_call_ms": sorted(durations)[ceil(len(durations) * 0.95) - 1] if durations else None,
                    "maximum_call_ms": max(durations) if durations else None,
                    "recent_calls": deepcopy(rows),
                    "timing_source": "desktop host monotonic send-call time",
                    "scope": "Command, realtime and file initiation; protocol detection and transfer data excluded",
                    "acknowledgment_latency_ms": None,
                    "physical_response_ms": None,
                    "delivery_verified": False,
                },
                "timing_limit": "Host observations; no firmware timing, network latency or readiness inference",
            }
