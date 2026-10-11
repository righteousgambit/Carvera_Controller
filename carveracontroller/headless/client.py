"""Supervised private child client; no automatic connection, retry or admission.

The caller owns execution authorization and journaling. Submit never waits for
pipe IO. Responses preserve the backend envelope; IPC timing is not CNC timing.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import queue
import subprocess
import sys
import threading
import time
import uuid
from collections import deque
from collections.abc import Sequence
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import RUNTIME_VERSION
from .arguments import deadline
from .requests import decode_record, decode_request, validate_parameters
from .startup_receipts import StartupReceipt
from .status_receipts import StatusReceipts
from .text_receipts import TextReceipts

MAX_RESPONSE = 16 * 1024 * 1024


class ClientUnavailable(RuntimeError):
    def __init__(self, reason: str, request_id: str | None = None, submission: str = "not_submitted") -> None:
        super().__init__(reason)
        self.reason, self.request_id, self.submission = reason, request_id, submission


class ClientBusy(RuntimeError):
    pass


@dataclass(frozen=True)
class Response:
    envelope: dict[str, Any]
    request_sha256: str
    response_sha256: str
    received_at_s: float | None
    elapsed_ms: float | None
    original_line: bytes | None = None


@dataclass
class _Pending:
    request_id: str
    method: str
    payload: bytes
    request_sha256: str
    future: Future[Response]
    urgent: bool
    submitted_at: float | None
    phase: str = "queued"
    retain_original_response: bool = False


def _stamp() -> float | None:
    try:
        value = time.monotonic()
        return value if math.isfinite(value) and value >= 0 else None
    except Exception:
        return None


def _age(now: float | None, stamp: float | None) -> float | None:
    return now - stamp if now is not None and stamp is not None and now >= stamp else None


def child_arguments(host: str, port: int, *, frozen: bool | None = None) -> list[str]:
    address = ipaddress.ip_address(host)
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8")
    if address.version != 4 or not any(address in ipaddress.ip_network(value) for value in networks):
        raise ValueError("A private IPv4 backend endpoint is required")
    if type(port) is not int or not 1 <= port <= 65535 or (port != 2222 and not address.is_loopback):
        raise ValueError("The supported CNC port is 2222; loopback test ports may differ")
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    return [
        sys.executable,
        *([] if frozen else ["-m", "carveracontroller"]),
        "--headless-supervisor",
        "--host",
        str(address),
        "--port",
        str(port),
    ]


class SupervisorClient:
    def __init__(
        self, host: str, port: int = 2222, *, argv: Sequence[str] | None = None, cwd: str | None = None
    ) -> None:
        self.host, self.port = host, port
        self.argv = list(argv) if argv is not None else child_arguments(host, port)
        self.cwd = cwd if cwd is not None else None if getattr(sys, "frozen", False) else str(Path(__file__).parents[2])
        self.session_id = str(uuid.uuid4())
        self._lock = threading.RLock()
        self._lifecycle_lock = threading.RLock()
        self._ready = threading.Event()
        self._queue: queue.PriorityQueue[tuple[int, int, _Pending]] = queue.PriorityQueue(maxsize=20)
        self._pending: dict[str, _Pending] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=64)
        self._events: deque[dict[str, Any]] = deque(maxlen=128)
        self._process: subprocess.Popen[bytes] | None = None
        self._threads: list[threading.Thread] = []
        self._started = self._accepting = self._closing = False
        self._failure: str | None = None
        self._sequence = self._responses = 0
        self._last_response_at: float | None = None
        self._last_snapshot: dict[str, Any] | None = None
        self._last_snapshot_at: float | None = None
        self._status_receipts = StatusReceipts()
        self._text_receipts = TextReceipts()
        self._startup = StartupReceipt()

    def start(self, timeout: float = 5) -> None:
        """Blocking lifecycle operation; desktop callers run this off the UI thread."""
        with self._lifecycle_lock:
            self._start(timeout)

    def _start(self, timeout: float) -> None:
        deadline(timeout)
        with self._lock:
            if self._started or self._closing:
                raise ClientUnavailable("Session has already been started")
            self._started = True
            self._startup.begin(timeout, _stamp())
        timed_out = False
        try:
            self._process = subprocess.Popen(
                self.argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                bufsize=0,
            )
            with self._lock:
                self._startup.process_created_at_s = _stamp()
            for name, target in (
                ("writer", self._write_loop),
                ("reader", self._read_loop),
                ("stderr", self._drain_stderr),
            ):
                worker = threading.Thread(target=target, name=f"backend-{name}", daemon=True)
                self._threads.append(worker)
                worker.start()
            with self._lock:
                self._startup.wait_started_at_s = _stamp()
            if not self._ready.wait(timeout):
                timed_out = True
                raise ClientUnavailable("Backend startup timed out")
            with self._lock:
                if not self._accepting:
                    raise ClientUnavailable(self._failure or "Backend did not become ready")
                self._startup.finish("ready", _stamp())
        except Exception:
            with self._lock:
                code = (
                    "readiness_wait_timed_out"
                    if timed_out
                    else "process_launch_failed"
                    if self._process is None
                    else "readiness_protocol_failed"
                    if self._failure == "Private backend protocol failed"
                    else "child_ended_before_ready"
                    if self._failure == "Private backend output ended"
                    else "readiness_unavailable"
                )
                self._startup.finish("timed_out" if timed_out else "failed", _stamp(), code)
            self.close()
            raise

    def submit(self, method: str, params: dict[str, Any] | None = None) -> Future[Response]:
        request_id = uuid.uuid4().hex
        payload = (
            json.dumps(
                {"id": request_id, "method": method, "params": params if params is not None else {}},
                allow_nan=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode()
        request = decode_request(payload)
        validate_parameters(request["method"], request["params"])
        urgent = method in ("realtime", "snapshot", "cancel_transfer", "catalog", "compile") or (
            method == "operation"
            and request["params"].get("operation") in ("machine.hold", "machine.abort", "machine.jog_cancel")
        )
        request_sha256 = hashlib.sha256(payload).hexdigest()
        with self._lock:
            if not self._accepting or self._closing:
                raise ClientUnavailable(self._failure or "Backend is not accepting requests")
            if sum(item.urgent == urgent for item in self._pending.values()) >= (4 if urgent else 16):
                raise ClientBusy("Backend request capacity is occupied")
            future: Future[Response] = Future()
            pending = _Pending(request_id, method, payload, request_sha256, future, urgent, _stamp())
            pending.retain_original_response = method in ("probe_profile_read", "probe_profile_apply") or (
                method == "operation"
                and (
                    request["params"].get("operation") in ("tool.change", "tool.measure")
                    or request["params"].get("operation") == "observe.query"
                    and request["params"].get("parameters", {}).get("query") in ("model", "version")
                )
            )
            self._sequence += 1
            self._pending[request_id] = pending
            try:
                self._queue.put_nowait((0 if urgent else 1, self._sequence, pending))
            except queue.Full:
                self._pending.pop(request_id)
                raise ClientBusy("Backend request queue is occupied") from None
            return future

    def _metadata(self, item: _Pending, outcome: str) -> dict[str, Any]:
        return {
            "request_id": item.request_id,
            "method": item.method,
            "phase": item.phase,
            "outcome": outcome,
            "request_sha256": item.request_sha256,
        }

    def _retire(self, reason: str) -> None:
        with self._lock:
            self._failure = self._failure or reason
            self._accepting = False
            pending = list(self._pending.values())
            self._pending.clear()
            for item in pending:
                self._history.append(
                    self._metadata(item, "not_submitted" if item.phase == "queued" else "backend_response_unknown")
                )
            self._ready.set()
        for item in pending:
            if not item.future.done():
                item.future.set_exception(
                    ClientUnavailable(
                        reason,
                        item.request_id,
                        "not_submitted" if item.phase == "queued" else "backend_response_unknown",
                    )
                )

    def _write_loop(self) -> None:
        process = self._process
        assert process is not None and process.stdin is not None
        try:
            while True:
                with self._lock:
                    if self._failure or self._closing:
                        return
                try:
                    _, _, item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                with self._lock:
                    if self._failure or self._closing:
                        return
                    if not item.future.set_running_or_notify_cancel():
                        self._pending.pop(item.request_id, None)
                        self._history.append(self._metadata(item, "cancelled_before_submission"))
                        continue
                    item.phase = "writing"
                view = memoryview(item.payload)
                while view:
                    sent = process.stdin.write(view)
                    if sent is None or sent <= 0:
                        raise OSError("Private pipe write did not complete")
                    view = view[sent:]
                with self._lock:
                    if item.phase == "writing":
                        item.phase = "written"
        except Exception:
            self._retire("Private backend write failed")
        finally:
            process.stdin.close()

    def _read_loop(self) -> None:
        process = self._process
        assert process is not None and process.stdout is not None
        try:
            while True:
                raw = process.stdout.readline(MAX_RESPONSE + 1)
                if not raw:
                    self._retire("Private backend output ended")
                    return
                record = decode_record(raw, MAX_RESPONSE)
                if not isinstance(record, dict):
                    raise ValueError("Backend record must be an object")
                now = _stamp()
                if "event" in record:
                    if "id" in record or not isinstance(record["event"], str) or len(raw) > 65536:
                        raise ValueError("Invalid backend event")
                    with self._lock:
                        if not self._ready.is_set() and record["event"] != "ready":
                            raise ValueError("Backend event preceded readiness")
                        if record["event"] == "ready":
                            if (
                                self._ready.is_set()
                                or record.get("runtime_version") != RUNTIME_VERSION
                                or record.get("connection_owned") is not False
                                or record.get("protocol") != "smoothie"
                            ):
                                raise ValueError("Unrecognized backend readiness")
                            self._accepting = True
                            self._startup.accepted(now, hashlib.sha256(raw).hexdigest())
                            self._ready.set()
                        self._events.append(
                            {"event": record["event"], "received_at_s": now, "sha256": hashlib.sha256(raw).hexdigest()}
                        )
                        self._status_receipts.observe(record, raw, now, time.time())
                        self._text_receipts.observe(record, raw, now, time.time())
                    continue
                if not isinstance(record.get("id"), str) or type(record.get("ok")) is not bool:
                    raise ValueError("Invalid backend response")
                with self._lock:
                    item = self._pending.get(record["id"])
                    if item is None or item.phase == "queued":
                        raise ValueError("Unmatched backend response")
                    if record["ok"] and not isinstance(record.get("result"), dict):
                        raise ValueError("Invalid backend result")
                    if not record["ok"] and not isinstance(record.get("error"), str):
                        raise ValueError("Invalid backend error")
                    if record["ok"] and item.method in ("snapshot", "connect", "disconnect"):
                        state = record["result"]
                        if any(
                            type(state.get(key)) is not bool
                            for key in ("connected", "unknown_outcome", "transfer_active")
                        ):
                            raise ValueError("Invalid backend connection flags")
                        connection = state.get("connection_id")
                        if connection is not None and (
                            not isinstance(connection, str) or not 0 < len(connection) <= 100
                        ):
                            raise ValueError("Invalid backend connection identity")
                        if state["connected"] and connection is None:
                            raise ValueError("Connected snapshot lacks its identity")
                        self._last_snapshot, self._last_snapshot_at = deepcopy(record["result"]), now
                    self._pending.pop(item.request_id)
                    item.phase = "resolved"
                    self._responses += 1
                    self._last_response_at = now
                    self._history.append(self._metadata(item, "response_received"))
                age = _age(now, item.submitted_at)
                item.future.set_result(
                    Response(
                        deepcopy(record),
                        item.request_sha256,
                        hashlib.sha256(raw).hexdigest(),
                        now,
                        age * 1000 if age is not None else None,
                        raw if item.retain_original_response else None,
                    )
                )
        except Exception:
            self._retire("Private backend protocol failed")

    def _drain_stderr(self) -> None:
        process = self._process
        assert process is not None and process.stderr is not None
        while True:
            data = process.stderr.read(4096)
            if not data:
                return
            with self._lock:
                self._startup.stderr_bytes = min(2**63 - 1, self._startup.stderr_bytes + len(data))
            # Drain bounded chunks without exposing or retaining private logs.

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = _stamp()
            process_returncode = self._process.poll() if self._process else None
            return deepcopy(
                {
                    "session_id": self.session_id,
                    "host": self.host,
                    "port": self.port,
                    "pid": self._process.pid if self._process else None,
                    "running": self._process is not None and process_returncode is None,
                    "ready": self._accepting and not self._closing,
                    "failure": self._failure,
                    "startup": self._startup.snapshot(now, process_returncode),
                    "pending_requests": len(self._pending),
                    "responses_received": self._responses,
                    "last_response_age_s": _age(now, self._last_response_at),
                    "last_machine_snapshot": self._last_snapshot,
                    "last_machine_snapshot_age_s": _age(now, self._last_snapshot_at),
                    "recent_requests": list(self._history),
                    "recent_events": list(self._events),
                    "timing_source": "client host private IPC observations; not CNC acknowledgment or physical response",
                }
            )

    def status_receipts(self, after_sequence: int = 0) -> dict[str, Any]:
        """Local bounded readback only; never polls the child or sends CNC commands."""
        with self._lock:
            return {"session_id": self.session_id, **self._status_receipts.since(after_sequence)}

    def text_receipts(self, after_sequence: int = 0) -> dict[str, Any]:
        """Independent bounded cursor; never drains another consumer or sends a command."""
        with self._lock:
            return {"session_id": self.session_id, **self._text_receipts.since(after_sequence)}

    def close(self, timeout: float = 5) -> None:
        """Close only this owned child; callers keep lifecycle waits off the UI thread."""
        with self._lifecycle_lock:
            self._close(timeout)

    def _close(self, timeout: float) -> None:
        deadline(timeout)
        with self._lock:
            self._closing = True
            self._accepting = False
            process = self._process
            queued = [item for item in self._pending.values() if item.phase == "queued"]
            for item in queued:
                self._pending.pop(item.request_id)
                self._history.append(self._metadata(item, "not_submitted"))
        for item in queued:
            if not item.future.done():
                item.future.set_exception(ClientUnavailable("Session closed before submission", item.request_id))
        if process is not None:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for worker in self._threads:
                if worker is not threading.current_thread():
                    worker.join(2)
        self._retire("Private backend session closed")
        for stream in (process.stdin, process.stdout, process.stderr) if process else ():
            if stream is not None:
                stream.close()
