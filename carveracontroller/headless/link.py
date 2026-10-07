"""One socket owner with serialized receipts and exclusive XMODEM byte access.

There is no automatic reconnect or command retry. A lost acknowledgement
closes the connection and latches unknown_outcome. Firmware `ok` means accepted,
not completed motion; callers must observe subsequent machine state separately.
"""

from __future__ import annotations

import copy
import hashlib
import io
import re
import socket
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Callable

from ..protocols import MessageKind, ProtocolSession
from ..XMODEM import XMODEM
from .ownership import EndpointLock
from .telemetry import parse_diagnostics, parse_status
from .wire_evidence import ReceiveWindow

MAX_LINE = 8192
MAX_REPLY = 65536
MAX_FILE = 8 * 1024 * 1024
FILE_PATH = re.compile(r"/sd/gcodes/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]{1,80}\Z")
BACKGROUND_WARNING = re.compile(r"ERROR: Failed to query STA (?:Netmask|IP Addr), status: \d+\Z")
READ_ONLY_COMMANDS = frozenset(
    (
        "diagnose",
        "config-get sd zprobe.probe_tip_diameter",
        "config-get sd zprobe.three_axis_probe_tlo_correction",
        "version",
        "model",
        "$G",
        "$#",
        "$I",
        "M493.4",
        "M499.1",
        "M114.2",
        "M114",
        "M115",
        "M105",
        "get wcs",
        "get state",
        "get status",
        "M499",
        "ls /sd/gcodes",
    )
)


def remote_path(value: str) -> str:
    if not isinstance(value, str) or not FILE_PATH.fullmatch(value) or ".." in value or len(value) > 110:
        raise ValueError("Only bounded, unambiguous paths beneath /sd/gcodes are accepted")
    return value


class LinkUnavailable(RuntimeError):
    pass


class OutcomeUnknown(LinkUnavailable):
    def __init__(self, message: str, receipt: dict | None = None):
        super().__init__(message)
        self.receipt = receipt


class ControllerRejected(RuntimeError):
    def __init__(self, receipt: dict):
        super().__init__("Controller rejected the command; inspect its recorded receipt")
        self.receipt = receipt


class BoundedFile(io.BytesIO):
    def write(self, data) -> int:
        if self.tell() + len(data) > MAX_FILE:
            raise ValueError("Download exceeds the file size limit")
        return super().write(data)


class CarveraLink:
    def __init__(
        self,
        host: str,
        port: int = 2222,
        *,
        on_event: Callable[[dict], None] | None = None,
        lock_directory: Path | None = None,
        poll: bool = True,
    ) -> None:
        self.host, self.port = host, port
        self.on_event = on_event or (lambda _: None)
        self.endpoint_lock = EndpointLock(host, port, lock_directory)
        self.poll = poll
        self.socket: socket.socket | None = None
        self.protocol = ProtocolSession("smoothie")
        self._condition = threading.Condition()
        self._command_lock = threading.Lock()
        self._wire_lock = threading.RLock()
        self._reader_lock = threading.Lock()
        self._stop = threading.Event()
        self._reader: threading.Thread | None = None
        self._poller: threading.Thread | None = None
        self._pending: dict | None = None
        self._unknown = False
        self._transfer = False
        self._transfer_deadline = 0.0
        self._modem: XMODEM | None = None
        self._partial_bytes = 0
        self._events: deque[dict] = deque(maxlen=128)
        self._status: dict | None = None
        self._diagnostics: dict | None = None
        self._status_time: float | None = None
        self._diagnostic_time: float | None = None
        self.connection_id: str | None = None

    def _emit(self, event: dict) -> None:
        with self._condition:
            self._events.append(event)
        try:
            self.on_event(event)
        except Exception:
            # A failed consumer must not kill the only RX owner.
            pass

    def connect(self) -> None:
        if self.socket is not None or (self._reader is not None and self._reader.is_alive()):
            raise LinkUnavailable("Connection already owned")
        self.endpoint_lock.acquire()
        try:
            sock = socket.create_connection((self.host, self.port), timeout=3)
            sock.settimeout(0.1)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except BaseException:
            self.endpoint_lock.release()
            raise
        with self._condition:
            self.socket = sock
            self.connection_id = str(uuid.uuid4())
            self._status = self._diagnostics = None
            self._status_time = self._diagnostic_time = None
            self._partial_bytes = 0
            self.protocol.select("smoothie")
            self.protocol.reset_parser()
            self._stop.clear()
        self._reader = threading.Thread(target=self._read_loop, name="carvera-rx", daemon=True)
        self._reader.start()
        if self.poll:
            self._poller = threading.Thread(target=self._poll_loop, name="carvera-observation", daemon=True)
            self._poller.start()
        self._emit({"event": "connection", "connected": True, "connection_id": self.connection_id})

    def close(self) -> None:
        self._fail("Connection closed")
        for thread in (self._reader, self._poller):
            if thread and thread is not threading.current_thread():
                thread.join(timeout=4)
        # Do not release ownership while a transfer still owns the descriptor.
        with self._reader_lock:
            self.endpoint_lock.release()

    def _fail(self, reason: str) -> None:
        with self._condition:
            if self._pending is not None or self._transfer:
                self._unknown = True
            sock, self.socket = self.socket, None
            self._stop.set()
            self._condition.notify_all()
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()
            self._emit({"event": "connection", "connected": False, "reason": reason, "unknown_outcome": self._unknown})

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._condition:
            return copy.deepcopy(
                {
                    "connection_id": self.connection_id,
                    "connected": self.socket is not None,
                    "unknown_outcome": self._unknown,
                    "transfer_active": self._transfer,
                    "status": self._status,
                    "diagnostics": self._diagnostics,
                    "status_age_ms": (now - self._status_time) * 1000 if self._status_time is not None else None,
                    "diagnostics_age_ms": (now - self._diagnostic_time) * 1000
                    if self._diagnostic_time is not None
                    else None,
                }
            )

    def acknowledge_unknown_outcome(self, connection_id: str) -> dict:
        """Clear only the local latch after the supervisor's recorded review.

        No controller command is sent and no old command is retried. The exact
        current connection must report fresh idle, spindle off and no program.
        """
        with self._condition:
            snapshot = self.snapshot()
            status = snapshot["status"] or {}
            diagnostics = snapshot["diagnostics"] or {}
            if (
                connection_id != self.connection_id
                or not snapshot["connected"]
                or snapshot["status_age_ms"] is None
                or snapshot["status_age_ms"] > 2000
                or snapshot["diagnostics_age_ms"] is None
                or snapshot["diagnostics_age_ms"] > 3000
                or self._pending is not None
                or self._transfer
                or status.get("state") != "Idle"
                or status.get("is_playing") is not False
                or status.get("spindle_rpm") != 0
                or status.get("spindle_target_rpm") != 0
                or diagnostics.get("spindle_enabled") is not False
            ):
                raise LinkUnavailable("Reconciliation requires the exact fresh idle connection")
            self._unknown = False
            return {"outcome": "local_latch_reconciled", "original_command_replayed": False}

    def _write(self, data: bytes) -> None:
        with self._wire_lock:
            sock = self.socket
            if sock is None:
                raise LinkUnavailable("Controller is disconnected")
            # The socket timeout also bounds sendall. Partial transmission is
            # deliberately treated as ambiguous rather than repeated.
            sock.sendall(data)

    def _read_loop(self) -> None:
        try:
            while not self._stop.is_set():
                if self._transfer:
                    self._stop.wait(0.01)
                    continue
                with self._reader_lock:
                    if self._transfer:
                        continue
                    sock = self.socket
                    if sock is None:
                        break
                    try:
                        data = sock.recv(4096)
                    except socket.timeout:
                        continue
                    if not data:
                        raise LinkUnavailable("Controller closed the connection")
                    with self._condition:
                        if self._pending is not None and not self._pending["acknowledged"]:
                            self._pending["receive_window"].append(data)
                    for byte in data:
                        self._partial_bytes = 0 if byte in (10, 4, 22) else self._partial_bytes + 1
                        if self._partial_bytes > MAX_LINE:
                            raise LinkUnavailable("Oversized controller line")
                    with self._condition:
                        for message in self.protocol.feed(data, allow_wire_switch=False):
                            if message.kind is not MessageKind.LINE:
                                raise LinkUnavailable("Unexpected binary transfer data")
                            self._receive(message.text.strip())
        except Exception as error:
            self._fail(type(error).__name__)

    def _receive(self, text: str) -> None:
        if not text:
            return
        now = time.monotonic()
        if text.startswith(("<", "{")):
            try:
                observation = parse_status(text) if text[0] == "<" else parse_diagnostics(text)
            except (ValueError, OverflowError):
                self._emit({"event": "invalid_observation"})
                return
            with self._condition:
                if text[0] == "<":
                    self._status, self._status_time = observation, now
                else:
                    self._diagnostics, self._diagnostic_time = observation, now
                self._condition.notify_all()
            self._emit(
                {
                    "event": "observation",
                    "kind": "status" if text[0] == "<" else "diagnostics",
                    "observation": observation,
                    "observed_at_ms": int(time.time() * 1000),
                }
            )
            return
        if BACKGROUND_WARNING.fullmatch(text):
            self._emit({"event": "firmware_warning", "code": "wifi_parameter_query_failed"})
            return
        with self._condition:
            pending = self._pending if self._pending and not self._pending["acknowledged"] else None
            if pending is not None:
                pending["reply_bytes"] += len(text.encode())
                if pending["reply_bytes"] > MAX_REPLY:
                    raise LinkUnavailable("Controller response exceeded the receipt budget")
                pending["lines"].append(text)
                if text == "ok" or text.startswith("ok "):
                    pending["acknowledged"] = True
                    self._condition.notify_all()
                elif text.lower().startswith(("error", "alarm:", "halted")):
                    pending["rejected"] = True
                    # Wait for the trailing acknowledgement or disconnect;
                    # otherwise a late `ok` could settle the next command.
                    self._condition.notify_all()
            else:
                if text.lower().startswith(("error", "alarm:", "halted")) or text == "ok":
                    self._unknown = True
                self._emit({"event": "unsolicited_response", "text": text[:512]})

    def command(self, command: str, *, timeout: float = 10, read_only: bool = False) -> dict:
        if not isinstance(command, str) or not command or len(command.encode("ascii")) > 120:
            raise ValueError("Command must be non-empty ASCII of at most 120 bytes")
        if any(ord(char) < 32 or ord(char) > 126 for char in command):
            raise ValueError("A command contains exactly one printable line")
        if not 0 < timeout <= 300:
            raise ValueError("Command deadline is outside the supported range")
        if read_only and command not in READ_ONLY_COMMANDS:
            raise ValueError("The command is not admitted as read-only")
        # Community shell commands do NOT emit `ok` (SimpleShell.cpp:414).
        # M105 is an explicit read-only acknowledgement barrier. It does not
        # wait for motion or initiate a queued job. File transfer bypasses this
        # route because Player owns the bytes until its final success report.
        wire_commands = [command, "M105"] if command[0].islower() or command == "$I" else [command]
        payload = b"".join(self.protocol.encode_command(line.encode("ascii")) for line in wire_commands)
        if len(payload) > 126:
            raise ValueError("Command and receipt barrier exceed the firmware receive budget")
        with self._command_lock:
            with self._condition:
                if self.socket is None or self._transfer or (self._unknown and not read_only):
                    raise LinkUnavailable("Controller disconnected, transferring, or has an unresolved outcome")
                pending: dict[str, Any] = {
                    "command": command,
                    "lines": [],
                    "reply_bytes": 0,
                    "acknowledged": False,
                    "rejected": False,
                    "receive_window": ReceiveWindow(),
                    "sendall_completed": False,
                }
                self._pending = pending
            started = time.monotonic()
            try:
                self._write(payload)
                with self._condition:
                    pending["sendall_completed"] = True
                    acknowledged = self._condition.wait_for(
                        lambda: pending["acknowledged"] or self.socket is None,
                        timeout=timeout,
                    )
                    if not acknowledged or not pending["acknowledged"]:
                        self._fail("Acknowledgement lost")
                        raise OutcomeUnknown("Command outcome unknown; this command was not retried")
                    receipt = {
                        "controller_receive_evidence": pending["receive_window"].evidence(
                            self.connection_id, payload, pending["sendall_completed"]
                        ),
                        "command": command,
                        "outcome": "controller_rejected" if pending["rejected"] else "controller_acknowledged",
                        "lines": list(pending["lines"]),
                        "elapsed_ms": (time.monotonic() - started) * 1000,
                        "connection_id": self.connection_id,
                        "motion_completed": False,
                        "wire_commands": wire_commands,
                    }
                    if pending["rejected"]:
                        raise ControllerRejected(receipt)
                    return receipt
            except (OSError, LinkUnavailable):
                self._fail("Command transmission or acknowledgement lost")
                with self._condition:
                    receipt = {
                        "command": command,
                        "outcome": "unknown_outcome",
                        "lines": list(pending["lines"]),
                        "elapsed_ms": (time.monotonic() - started) * 1000,
                        "connection_id": self.connection_id,
                        "motion_completed": False,
                        "wire_commands": wire_commands,
                        "controller_receive_evidence": pending["receive_window"].evidence(
                            self.connection_id, payload, pending["sendall_completed"]
                        ),
                    }
                raise OutcomeUnknown("Command outcome unknown; this command was not retried", receipt) from None
            finally:
                with self._condition:
                    self._pending = None

    def realtime(self, action: str) -> dict:
        tokens = {
            "status": b"?",
            "feed_hold": b"!",
            "cycle_resume": b"~",
            "software_abort": b"\x18",
            "jog_cancel": b"\x19",
            "jog_keepalive": b"?1",
        }
        if action not in tokens:
            raise ValueError("Unknown realtime operation")
        # File transfer has its own cancel route; do not corrupt its framing.
        with self._wire_lock:
            if self._transfer:
                raise LinkUnavailable("File transfer owns the byte stream")
            if self._unknown and action not in ("status", "feed_hold", "software_abort", "jog_cancel"):
                raise LinkUnavailable("Unresolved command outcome")
            try:
                self._write(tokens[action])
            except OSError:
                self._unknown = True
                self._fail("Realtime transmission lost")
                raise OutcomeUnknown("Realtime delivery is unknown") from None
        return {
            "action": action,
            "outcome": "sent_unacknowledged",
            "connection_id": self.connection_id,
            "motion_completed": False,
        }

    def _poll_loop(self) -> None:
        next_diagnostics = 0.0
        while not self._stop.wait(0.3):
            try:
                if self._transfer:
                    continue
                self.realtime("status")
                if time.monotonic() >= next_diagnostics and self._command_lock.acquire(blocking=False):
                    self._command_lock.release()
                    self.command("diagnose", read_only=True, timeout=3)
                    next_diagnostics = time.monotonic() + 1
            except ControllerRejected:
                next_diagnostics = time.monotonic() + 2
            except LinkUnavailable:
                break

    def wait_for_observation(self, kind: str = "status", *, timeout: float = 3, after: float = 0) -> dict:
        if kind not in ("status", "diagnostics"):
            raise ValueError("Unknown observation kind")

        def arrived() -> bool:
            stamp = self._status_time if kind == "status" else self._diagnostic_time
            return (stamp is not None and stamp > after) or self.socket is None

        with self._condition:
            self._condition.wait_for(
                arrived,
                timeout,
            )
            stamp = self._status_time if kind == "status" else self._diagnostic_time
            if stamp is None or stamp <= after or self.socket is None:
                raise LinkUnavailable("A fresh controller observation was not received")
            return self.snapshot()

    def transfer(self, direction: str, path: str, data: bytes = b"", *, timeout: float = 120) -> dict:
        path = remote_path(path)
        if direction not in ("upload", "download") or len(data) > MAX_FILE or not 0 < timeout <= 300:
            raise ValueError("Invalid transfer direction, size or deadline")
        with self._command_lock:
            if self.socket is None or self._unknown:
                raise LinkUnavailable("Transfer requires an unambiguous connection")
            with self._wire_lock:
                self._transfer = True
            try:
                with self._reader_lock:
                    return self._transfer_locked(direction, path, data, timeout)
            finally:
                self._transfer = False

    def _transfer_locked(self, direction: str, path: str, data: bytes, timeout: float) -> dict:
        self._transfer_deadline = time.monotonic() + timeout
        # Finish any observation sent before exclusive byte ownership began.
        self._drain_before_transfer()
        stream = BoundedFile(data if direction == "upload" else b"")
        self._modem = XMODEM(self._getc, self._putc, "xmodem8k")
        try:
            self._write(self.protocol.encode_file_command(f"{direction} {path}".encode("ascii")))
            if direction == "upload":
                result = self._modem.send_legacy(stream, hashlib.md5(data).hexdigest(), retry=10, timeout=2)
                success = result is True
            else:
                result = self._modem.recv_legacy(stream, retry=10, timeout=1)
                success = isinstance(result, int) and not isinstance(result, bool) and result >= 0
            if not success:
                raise OutcomeUnknown("File transfer did not reach a confirmed completion")
            completion = self._transfer_completion(direction)
            received = data if direction == "upload" else stream.getvalue()
            if len(received) > MAX_FILE:
                raise OutcomeUnknown("File transfer exceeded the size limit")
            return {
                "outcome": "transfer_acknowledged",
                "direction": direction,
                "path": path,
                "size": len(received),
                "sha256": hashlib.sha256(received).hexdigest(),
                "md5": hashlib.md5(received).hexdigest(),
                "data": received if direction == "download" else None,
                "completion": completion,
                "readback_verified": False,
            }
        except Exception:
            self._unknown = True
            self._fail("File transfer outcome unknown")
            raise OutcomeUnknown("File transfer outcome unknown; no automatic retry") from None
        finally:
            self._modem = None
            self.protocol.reset_parser()
            self._partial_bytes = 0

    def _drain_before_transfer(self) -> None:
        deadline = min(time.monotonic() + 2, self._transfer_deadline)
        while time.monotonic() < deadline:
            if self.socket is None:
                raise LinkUnavailable("Controller disconnected before transfer")
            try:
                data = self.socket.recv(4096)
            except socket.timeout:
                if self._partial_bytes == 0:
                    if self._unknown:
                        raise LinkUnavailable("Unresolved response before transfer")
                    return
                continue
            if not data:
                raise LinkUnavailable("Controller disconnected before transfer")
            for byte in data:
                self._partial_bytes = 0 if byte == 10 else self._partial_bytes + 1
                if self._partial_bytes > MAX_LINE:
                    raise LinkUnavailable("Oversized response before transfer")
            with self._condition:
                for message in self.protocol.feed(data, allow_wire_switch=False):
                    if message.kind is not MessageKind.LINE:
                        raise LinkUnavailable("Unexpected binary data before transfer")
                    self._receive(message.text.strip())
        raise LinkUnavailable("Controller stream did not quiesce before transfer")

    def _transfer_completion(self, direction: str) -> str:
        line = bytearray()
        total = 0
        while time.monotonic() < self._transfer_deadline:
            char = self._getc(1)
            if char is None:
                continue
            total += 1
            if total > MAX_LINE:
                raise OutcomeUnknown("File completion exceeded its response limit")
            if char == b"\n":
                text = line.decode("ascii", errors="strict").strip()
                line.clear()
                if text.startswith(f"Info: {direction} success: "):
                    return text
                if text.lower().startswith(("error", "alarm:", "halted")):
                    raise OutcomeUnknown("Firmware did not confirm file completion")
            else:
                line.extend(char)
        raise OutcomeUnknown("File completion report was not received")

    def cancel_transfer(self) -> None:
        if self._modem is not None:
            self._modem.canceled = True

    def _getc(self, size: int, timeout: float = 0.5) -> bytes | None:
        deadline = min(time.monotonic() + timeout, self._transfer_deadline)
        data = bytearray()
        while len(data) < size and time.monotonic() < deadline:
            if self.socket is None:
                raise LinkUnavailable("Transfer connection lost")
            try:
                chunk = self.socket.recv(size - len(data))
            except socket.timeout:
                continue
            if not chunk:
                raise LinkUnavailable("Transfer connection closed")
            data.extend(chunk)
        if time.monotonic() >= self._transfer_deadline:
            raise OutcomeUnknown("Transfer deadline elapsed")
        return bytes(data) if len(data) == size else None

    def _putc(self, data: bytes, timeout: float = 0.5) -> int:
        if time.monotonic() >= self._transfer_deadline:
            raise OutcomeUnknown("Transfer deadline elapsed")
        self._write(data)
        return len(data)
