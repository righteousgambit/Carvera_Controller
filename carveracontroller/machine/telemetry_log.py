"""Bounded best-effort telemetry persistence, independent of receive/UI locks.

Written means a line was flushed to the OS, not fsync or physical durability.
Rejected/failed records are counted; they must never be represented as a complete run.
"""

import json
import threading
import time
from collections import deque
from copy import deepcopy
from pathlib import Path


class TelemetryLog:
    def __init__(self, path, *, capacity=512, on_error=None):
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.path = Path(path)
        self.capacity = capacity
        self.on_error = on_error
        self._condition = threading.Condition()
        self._queue = deque()
        self._thread = None
        self._closing = False
        self._inflight = 0
        self._accepted = self._written = self._rejected = self._failed = 0
        self._attempted = 0
        self._error = None

    def submit(self, record):
        # Controller records are bounded monitor snapshots, not arbitrary assets.
        # Freeze before handoff; encoding and all filesystem work happen on worker.
        frozen = deepcopy(record)
        with self._condition:
            self._attempted += 1
            if self._closing or self._error or len(self._queue) + self._inflight >= self.capacity:
                self._rejected += 1
                return False
            frozen["persistence"] = {
                "sequence": self._attempted,
                "rejected_before": self._rejected,
                "failed_before": self._failed,
            }
            self._queue.append(frozen)
            self._accepted += 1
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="adaptive-telemetry", daemon=True)
                self._thread.start()
            self._condition.notify_all()
            return True

    def snapshot(self):
        with self._condition:
            return {
                "path": str(self.path),
                "capacity": self.capacity,
                "accepted": self._accepted,
                "attempted": self._attempted,
                "written": self._written,
                "rejected": self._rejected,
                "failed": self._failed,
                "queued": len(self._queue),
                "inflight": self._inflight,
                "closing": self._closing,
                "drained": not self._queue and not self._inflight,
                "error": self._error,
                "write_semantics": "Flushed to OS; power-loss durability and readback unverified",
            }

    def drain(self, timeout=1.0):
        """Bounded wait for accepted work; never call while holding receive lock."""
        deadline = time.monotonic() + max(0, timeout)
        with self._condition:
            while self._queue or self._inflight:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
        return self.snapshot()

    def close(self, timeout=1.0):
        with self._condition:
            self._closing = True
            self._condition.notify_all()
        return self.drain(timeout)

    def _write(self, record):
        payload = json.dumps(record, allow_nan=False) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as destination:
            destination.write(payload)
            destination.flush()

    def _run(self):
        while True:
            with self._condition:
                if not self._queue:
                    if not self._closing:
                        self._condition.wait(0.5)
                    if not self._queue:
                        self._thread = None
                        self._condition.notify_all()
                        return
                record = self._queue.popleft()
                self._inflight = 1
            try:
                self._write(record)
            except Exception as error:
                # A partially written line may exist. Preserve it, stop this log,
                # and expose every abandoned record rather than retry/duplicate.
                with self._condition:
                    self._error = f"{type(error).__name__}: {error}"
                    self._failed += 1 + len(self._queue)
                    self._queue.clear()
                    self._inflight = 0
                    self._thread = None
                    self._condition.notify_all()
                if self.on_error:
                    self.on_error(self._error)
                return
            with self._condition:
                self._written += 1
                self._inflight = 0
                self._condition.notify_all()
