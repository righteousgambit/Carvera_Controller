"""Explicit new-segment recovery; failed logs and missing records remain evidence."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections import deque
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Literal, TypedDict
from uuid import uuid4

from .telemetry_log import TelemetryLog, TelemetryLogSnapshot

RecoveryState = Literal["pending", "resumed", "failed"]


class RecoveryRecord(TypedDict):
    state: RecoveryState
    operation_id: str
    path: str
    previous: TelemetryLogSnapshot
    error: str | None


class CompletedRecoveryRecord(RecoveryRecord, total=False):
    boundary: Mapping[str, object] | None
    gap_record_sha256: str | None


class RecoverySnapshot(TypedDict):
    current: CompletedRecoveryRecord | None
    history: list[CompletedRecoveryRecord]
    closed: bool


class TelemetryRecovery:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._closed = False
        self._record: CompletedRecoveryRecord | None = None
        self._history: deque[CompletedRecoveryRecord] = deque(maxlen=20)
        self._candidate: TelemetryLog | None = None

    def snapshot(self) -> RecoverySnapshot:
        with self._lock:
            return {"current": deepcopy(self._record), "history": deepcopy(list(self._history)), "closed": self._closed}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            candidate = self._candidate
        if candidate is not None:
            candidate.close(0)

    def start(
        self,
        previous: TelemetryLog,
        folder: str | os.PathLike[str],
        publish: Callable[[TelemetryLog, str], Mapping[str, object] | None],
        *,
        metadata: Mapping[str, object] | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> bool:
        old = previous.snapshot()
        if not old["error"] or not old["drained"]:
            return False
        with self._lock:
            if self._closed or (self._record and self._record["state"] == "pending"):
                return False
            if self._record:
                self._history.append(self._record)
            operation = uuid4().hex
            path = Path(folder) / f"telemetry-recovery-{operation}.jsonl"
            header: dict[str, object] = {
                "record_type": "telemetry_recovery_gap",
                "operation_id": operation,
                "utc": datetime.now(timezone.utc).isoformat(),
                "previous": old,
                "metadata": deepcopy(metadata or {}),
                "complete_run": False,
                "limits": "Missing telemetry is not recovered; flushed/read-back bytes do not prove power-loss durability.",
            }
            record: CompletedRecoveryRecord = {
                "state": "pending",
                "operation_id": operation,
                "path": str(path),
                "previous": old,
                "error": None,
            }
            self._record = record
            candidate = self._candidate = TelemetryLog(path, on_error=on_error)

        def finish(
            state: RecoveryState,
            error: str | None = None,
            boundary: Mapping[str, object] | None = None,
            digest: str | None = None,
        ) -> None:
            with self._lock:
                record["state"] = state
                record["error"] = error
                record["boundary"] = boundary
                record["gap_record_sha256"] = digest
                if self._candidate is candidate:
                    self._candidate = None

        def worker() -> None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Never append a recovery header to an existing/partial segment.
                with path.open("x", encoding="utf-8"):
                    pass
                if not candidate.submit(header):
                    raise OSError("Recovery header was not accepted")
                while True:
                    status = candidate.drain(0.1)
                    with self._lock:
                        closed = self._closed
                    if closed:
                        raise OSError("Recording recovery closed before publication")
                    if status["error"]:
                        raise OSError(status["error"])
                    if status["written"] == 1 and status["drained"]:
                        break
                with path.open("rb") as source:
                    raw = source.read(65537)
                expected = {**header, "persistence": {"sequence": 1, "rejected_before": 0, "failed_before": 0}}
                if len(raw) > 65536 or json.loads(raw) != expected:
                    raise OSError("Recovery gap readback differs")
                # The owner performs a fresh connection/writer check and queues
                # its final boundary before exposing this writer to producers.
                boundary = publish(candidate, operation)
                if boundary is None:
                    raise OSError("Recording owner changed before recovery publication")
                finish("resumed", boundary=boundary, digest=hashlib.sha256(raw).hexdigest())
            except Exception as exc:
                candidate.close(0)
                finish("failed", error=f"{type(exc).__name__}: {exc}")

        threading.Thread(target=worker, name="telemetry-recovery", daemon=True).start()
        return True
