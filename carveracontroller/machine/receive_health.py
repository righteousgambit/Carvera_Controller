"""Bounded receive observations; diagnostics never establish machine readiness."""

from __future__ import annotations

import math
import threading
from collections import deque
from copy import deepcopy
from typing import Any


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

    def snapshot(self, now: float) -> dict[str, Any]:
        def age(stamp: float | None) -> float | None:
            return max(0.0, now - stamp) if stamp is not None and math.isfinite(now) and now >= stamp else None

        with self._lock:
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
                "timing_limit": "Host observations; no firmware timing, network latency or readiness inference",
            }
