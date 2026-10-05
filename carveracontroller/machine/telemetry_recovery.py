"""Explicit new-segment recovery; failed logs and missing records remain evidence."""

import hashlib
import json
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .telemetry_log import TelemetryLog


class TelemetryRecovery:
    def __init__(self):
        self._lock = threading.Lock()
        self._closed = False
        self._record = None
        self._history = deque(maxlen=20)
        self._candidate = None

    def snapshot(self):
        with self._lock:
            return {"current": deepcopy(self._record), "history": deepcopy(list(self._history)), "closed": self._closed}

    def close(self):
        with self._lock:
            self._closed = True
            candidate = self._candidate
        if candidate is not None:
            candidate.close(0)

    def start(self, previous, folder, publish, *, metadata=None, on_error=None):
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
            header = {
                "record_type": "telemetry_recovery_gap",
                "operation_id": operation,
                "utc": datetime.now(timezone.utc).isoformat(),
                "previous": old,
                "metadata": deepcopy(metadata or {}),
                "complete_run": False,
                "limits": "Missing telemetry is not recovered; flushed/read-back bytes do not prove power-loss durability.",
            }
            self._record = {
                "state": "pending",
                "operation_id": operation,
                "path": str(path),
                "previous": old,
                "error": None,
            }
            candidate = self._candidate = TelemetryLog(path, on_error=on_error)

        def finish(state, error=None, boundary=None, digest=None):
            with self._lock:
                self._record.update(state=state, error=error, boundary=boundary, gap_record_sha256=digest)
                if self._candidate is candidate:
                    self._candidate = None

        def worker():
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
