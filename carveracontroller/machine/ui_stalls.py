"""Bounded read-only heartbeat diagnostics; never read source files or locals."""

from __future__ import annotations

import os
import sys
import threading
from collections import deque
from collections.abc import Callable
from copy import deepcopy
from time import monotonic
from typing import TypedDict


class StackLocation(TypedDict):
    file: str
    function: str
    line: int


class StackSample(TypedDict):
    sampled_monotonic_s: float
    heartbeat_age_s: float
    stack: list[StackLocation]


class StallRecord(TypedDict):
    sequence: int
    last_heartbeat_monotonic_s: float
    context: str
    samples: list[StackSample]
    recovered_monotonic_s: float | None
    heartbeat_gap_s: float | None


class StallSnapshot(TypedDict):
    schema_version: int
    threshold_s: float
    retention_limit: int | None
    evicted: int
    records: list[StallRecord]
    stopped: bool
    limits: str


def stack_locations(thread_id: int) -> list[StackLocation]:
    frame = sys._current_frames().get(thread_id)
    locations: list[StackLocation] = []
    while frame is not None and len(locations) < 32:
        locations.append(
            {
                "file": os.path.basename(frame.f_code.co_filename),
                "function": frame.f_code.co_name,
                "line": frame.f_lineno,
            }
        )
        frame = frame.f_back
    return locations


class UIStallMonitor:
    """Samples the UI thread when its heartbeat is late, with at most 3 stacks per episode.

    OS suspension, debugger pauses and GIL starvation can also delay heartbeats.
    Python stacks identify sampled locations, not a proven root cause.
    """

    def __init__(
        self,
        *,
        threshold: float = 1.0,
        limit: int = 20,
        clock: Callable[[], float] = monotonic,
        capture: Callable[[int], list[StackLocation]] = stack_locations,
    ) -> None:
        if not 0 < threshold <= 60 or type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("Invalid UI stall retention or threshold")
        self.threshold, self.clock, self.capture = threshold, clock, capture
        self.thread_id = threading.get_ident()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last = clock()
        self._generation = 0
        self._context = "workspace startup"
        self._active: StallRecord | None = None
        self._records: deque[StallRecord] = deque(maxlen=limit)
        self._evicted = 0
        self._sequence = 0

    def heartbeat(self, context: object) -> None:
        now = self.clock()
        with self._lock:
            if self._active is not None:
                self._active["recovered_monotonic_s"] = now
                self._active["heartbeat_gap_s"] = now - self._last
                self._active = None
            self._last, self._context = now, str(context)[:80]
            self._generation += 1

    def check(self) -> None:
        now = self.clock()
        with self._lock:
            generation, last = self._generation, self._last
            if self._stop.is_set() or now - last < self.threshold:
                return
            if self._active is not None:
                samples = self._active["samples"]
                if len(samples) >= 3 or now - samples[-1]["sampled_monotonic_s"] < self.threshold:
                    return
        locations = self.capture(self.thread_id)
        with self._lock:
            if self._stop.is_set() or generation != self._generation:
                return  # Heartbeat recovered during sampling; do not invent a stall.
            if self._active is None:
                self._sequence += 1
                if len(self._records) == self._records.maxlen:
                    self._evicted += 1
                self._active = {
                    "sequence": self._sequence,
                    "last_heartbeat_monotonic_s": last,
                    "context": self._context,
                    "samples": [],
                    "recovered_monotonic_s": None,
                    "heartbeat_gap_s": None,
                }
                self._records.append(self._active)
            self._active["samples"].append(
                {"sampled_monotonic_s": now, "heartbeat_age_s": now - last, "stack": locations[:32]}
            )

    def start(self) -> None:
        if self._thread is not None or self._stop.is_set():
            return

        def run() -> None:
            while not self._stop.wait(min(0.25, self.threshold / 4)):
                self.check()

        self._thread = threading.Thread(target=run, name="ui-stall-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()  # Never join a worker from the UI thread.

    def snapshot(self) -> StallSnapshot:
        with self._lock:
            return {
                "schema_version": 1,
                "threshold_s": self.threshold,
                "retention_limit": self._records.maxlen,
                "evicted": self._evicted,
                "records": deepcopy(list(self._records)),
                "stopped": self._stop.is_set(),
                "limits": "Late UI heartbeat; not proof of input latency or root cause. OS suspension, debugger pauses "
                "and GIL starvation may delay both UI and sampling. At most 3 stacks of 32 locations per episode; "
                "no source text, local values or full paths captured.",
            }
