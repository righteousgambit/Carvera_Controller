"""Local child startup timing, independent of CNC connection or command admission."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def interval_ms(start: float | None, finish: float | None) -> float | None:
    if start is None or finish is None or not math.isfinite(start) or not math.isfinite(finish) or finish < start:
        return None
    value = (finish - start) * 1000
    return value if math.isfinite(value) else None


@dataclass
class StartupReceipt:
    """Caller serializes writes with its existing client lock; no IO or retry."""

    phase: str = "not_started"
    deadline_s: float | None = None
    started_at_s: float | None = None
    process_created_at_s: float | None = None
    wait_started_at_s: float | None = None
    ready_received_at_s: float | None = None
    finished_at_s: float | None = None
    ready_event_sha256: str | None = None
    failure_code: str | None = None
    stderr_bytes: int = 0

    def begin(self, timeout: float, now: float | None) -> None:
        self.phase, self.deadline_s, self.started_at_s = "awaiting_ready", timeout, now

    def accepted(self, now: float | None, event_sha256: str) -> None:
        if self.phase == "awaiting_ready" and self.ready_event_sha256 is None:
            self.ready_received_at_s, self.ready_event_sha256 = now, event_sha256

    def finish(self, phase: str, now: float | None, failure_code: str | None = None) -> None:
        self.phase, self.finished_at_s, self.failure_code = phase, now, failure_code

    def snapshot(self, now: float | None, returncode: int | None) -> dict[str, Any]:
        end = now if self.phase == "awaiting_ready" else self.finished_at_s
        return {
            "schema_version": "carvera.private_startup.v1",
            "phase": self.phase,
            "configured_ready_wait_limit_s": self.deadline_s,
            "started_at_s": self.started_at_s,
            "process_created_at_s": self.process_created_at_s,
            "wait_started_at_s": self.wait_started_at_s,
            "ready_received_at_s": self.ready_received_at_s,
            "finished_at_s": self.finished_at_s,
            "process_launch_ms": interval_ms(self.started_at_s, self.process_created_at_s),
            "ready_wait_ms": interval_ms(self.process_created_at_s, self.ready_received_at_s),
            "total_startup_ms": interval_ms(self.started_at_s, self.finished_at_s),
            "elapsed_ms": interval_ms(self.started_at_s, end),
            "ready_event_sha256": self.ready_event_sha256,
            "failure_code": self.failure_code,
            "process_returncode": returncode,
            "stderr_bytes_drained": self.stderr_bytes,
            "stderr_retained": False,
            "timing_source": "client host monotonic observations",
            "cnc_connection_or_motion_verified": False,
        }
