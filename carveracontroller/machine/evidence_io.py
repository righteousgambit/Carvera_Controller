"""Bounded, locked evidence IO; failed writes are preserved, never silently repaired."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import stat
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

JsonObject = dict[str, Any]


def _bound(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("invalid " + name)


def _shape(value: Any, depth: int = 0) -> None:
    if depth > 64:
        raise ValueError("evidence nesting exceeds 64 levels")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite evidence number")
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("evidence keys must be strings")
        for item in value.values():
            _shape(item, depth + 1)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _shape(item, depth + 1)


def _pairs(pairs: list[tuple[str, Any]]) -> JsonObject:
    result: JsonObject = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate evidence key")
        result[key] = value
    return result


def decode_json(data: bytes | str) -> JsonObject:
    def reject_constant(value: str) -> Any:
        raise ValueError("nonfinite evidence number: " + value)

    try:
        result = json.loads(data, object_pairs_hook=_pairs, parse_constant=reject_constant)
        if not isinstance(result, dict):
            raise ValueError("evidence record must be an object")
        _shape(result)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("invalid evidence encoding or nesting") from exc
    return result


def _encode(record: JsonObject, limit: int, *, newline: bool) -> bytes:
    _bound(limit, "record size bound")
    if not isinstance(record, dict):
        raise ValueError("evidence record must be an object")
    _shape(record)
    # iterencode limits allocation before a large collection can accumulate.
    encoder = json.JSONEncoder(allow_nan=False, ensure_ascii=True, separators=(",", ":"))
    chunks: list[bytes] = []
    size = 1 if newline else 0
    for chunk in encoder.iterencode(record):
        encoded = chunk.encode("utf-8")
        size += len(encoded)
        if size > limit:
            raise ValueError("evidence record exceeds size bound")
        chunks.append(encoded)
    return b"".join(chunks) + (b"\n" if newline else b"")


@contextmanager
def _locked(fd: int, *, exclusive: bool, timeout_s: float) -> Iterator[None]:
    try:
        import fcntl
    except ImportError as exc:
        raise OSError(errno.ENOSYS, "durable evidence OS locking is unavailable on this platform") from exc

    if not 0 <= timeout_s <= 60:
        raise ValueError("invalid evidence lock timeout")
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise OSError(errno.EBUSY, "evidence file is busy") from None
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)


def _open_regular(path: Path, *, write: bool) -> tuple[int, bool]:
    if not hasattr(os, "pread"):
        raise OSError(errno.ENOSYS, "durable evidence positional IO is unavailable on this platform")
    flags = os.O_RDWR if write else os.O_RDONLY
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    created = False
    if write:
        try:
            fd = os.open(path, flags | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
        except FileExistsError:
            fd = os.open(path, flags)
    else:
        fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        named = path.lstat()
        if not stat.S_ISREG(info.st_mode) or stat.S_ISLNK(named.st_mode):
            raise ValueError("evidence target must be a regular nonsymlink file")
        if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino) or (write and info.st_nlink != 1):
            raise ValueError("evidence file identity changed or is multiply linked")
    except BaseException:
        os.close(fd)
        raise
    return fd, created


def _sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "evidence write made no progress")
        view = view[written:]


def append_jsonl(
    path: str | os.PathLike[str],
    record: JsonObject,
    *,
    max_bytes: int,
    max_line_bytes: int = 65536,
    lock_timeout_s: float = 0.25,
    validate_existing: Callable[[int], None] | None = None,
) -> JsonObject:
    """Append under an OS lock. Validator gets the locked descriptor, never a reopened path.

    A partial failure remains on disk; subsequent appends reject an incomplete tail.
    Callers may cache a validated inode/size/mtime prefix inside validate_existing.
    """
    _bound(max_bytes, "journal size bound")
    data = _encode(record, max_line_bytes, newline=True)
    target = Path(path).expanduser()
    fd, created = _open_regular(target, write=True)
    try:
        with _locked(fd, exclusive=True, timeout_s=lock_timeout_s):
            original_info = os.fstat(fd)
            offset = original_info.st_size
            if offset + len(data) > max_bytes:
                raise ValueError("evidence journal exceeds size bound")
            if offset and os.pread(fd, 1, offset - 1) != b"\n":
                raise ValueError("incomplete evidence tail; preserve file and recover explicitly")
            if validate_existing is not None:
                validate_existing(fd)
                validated_info = os.fstat(fd)
                if (validated_info.st_size, validated_info.st_mtime_ns) != (
                    original_info.st_size,
                    original_info.st_mtime_ns,
                ):
                    raise OSError(errno.ESTALE, "evidence file changed during validation")
            os.lseek(fd, offset, os.SEEK_SET)
            _write_all(fd, data)
            os.fsync(fd)
            if os.pread(fd, len(data), offset) != data or os.fstat(fd).st_size != offset + len(data):
                raise OSError(errno.EIO, "evidence append readback failed")
            if created:
                _sync_directory(target.parent)
            info = os.fstat(fd)
            named = target.lstat()
            if (info.st_dev, info.st_ino) != (named.st_dev, named.st_ino):
                raise OSError(errno.ESTALE, "evidence pathname changed during append")
            return {
                "offset": offset,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "durable": True,
                "readback": True,
                "file_identity": [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns],
            }
    finally:
        os.close(fd)


def iter_jsonl_fd(
    fd: int, *, max_bytes: int, max_line_bytes: int = 65536, max_records: int = 10000, strict_tail: bool = True
) -> Iterator[JsonObject]:
    """Read a caller-owned locked descriptor without changing its seek position."""
    for value, name in (
        (max_bytes, "journal size bound"),
        (max_line_bytes, "record size bound"),
        (max_records, "record count bound"),
    ):
        _bound(value, name)
    offset = 0
    buffer = bytearray()
    records = 0
    while True:
        chunk = os.pread(fd, min(65536, max_bytes - offset + 1), offset)
        if not chunk:
            break
        offset += len(chunk)
        if offset > max_bytes:
            raise ValueError("evidence journal exceeds size bound")
        buffer.extend(chunk)
        while b"\n" in buffer:
            end = buffer.index(10)
            line = bytes(buffer[:end])
            del buffer[: end + 1]
            if len(line) + 1 > max_line_bytes:
                raise ValueError("oversized evidence record")
            records += 1
            if records > max_records:
                raise ValueError("evidence record count exceeded")
            yield decode_json(line)
        if len(buffer) >= max_line_bytes:
            raise ValueError("oversized evidence record")
    if buffer:
        if strict_tail:
            raise ValueError("incomplete evidence tail")
        if records >= max_records:
            raise ValueError("evidence record count exceeded")
        yield decode_json(bytes(buffer))


def iter_jsonl(
    path: str | os.PathLike[str],
    *,
    max_bytes: int,
    max_line_bytes: int = 65536,
    max_records: int = 10000,
    strict_tail: bool = True,
    lock_timeout_s: float = 0.25,
) -> Iterator[JsonObject]:
    fd, _ = _open_regular(Path(path).expanduser(), write=False)
    try:
        with _locked(fd, exclusive=False, timeout_s=lock_timeout_s):
            yield from iter_jsonl_fd(
                fd, max_bytes=max_bytes, max_line_bytes=max_line_bytes, max_records=max_records, strict_tail=strict_tail
            )
    finally:
        os.close(fd)


def write_json_atomic(
    path: str | os.PathLike[str], record: JsonObject, *, max_bytes: int = 16 * 1024 * 1024
) -> JsonObject:
    if not hasattr(os, "pread"):
        raise OSError(errno.ENOSYS, "durable evidence positional IO is unavailable on this platform")
    data = _encode(record, max_bytes, newline=True)
    target = Path(path).expanduser()
    if target.exists() or target.is_symlink():
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("export target must be a regular nonsymlink file")
    fd, staging = tempfile.mkstemp(prefix="." + target.name + ".pending-", dir=target.parent)
    try:
        _write_all(fd, data)
        os.fsync(fd)
        if os.pread(fd, len(data), 0) != data:
            raise OSError(errno.EIO, "evidence export readback failed")
        if target.exists() or target.is_symlink():
            info = target.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise ValueError("export target changed to an unsafe file")
        os.replace(staging, target)
        _sync_directory(target.parent)
        return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "durable": True, "readback": True}
    finally:
        # Preserve failed staging files; they are evidence, not successful exports.
        os.close(fd)


class BoundedJournalWriter:
    """One lazy worker with bounded admission; queue acceptance is not durability."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        max_bytes: int,
        max_pending_records: int = 256,
        max_pending_bytes: int = 2 * 1024 * 1024,
        max_line_bytes: int = 65536,
    ) -> None:
        import threading
        from collections import deque

        for value, name in (
            (max_bytes, "journal size bound"),
            (max_pending_records, "queue count bound"),
            (max_pending_bytes, "queue byte bound"),
            (max_line_bytes, "record size bound"),
        ):
            _bound(value, name)
        self.path = Path(path).expanduser()
        self.max_bytes = max_bytes
        self.max_pending_records = max_pending_records
        self.max_pending_bytes = max_pending_bytes
        self.max_line_bytes = max_line_bytes
        self._condition = threading.Condition()
        self._pending: deque[bytes] = deque()
        self._pending_bytes = 0
        self._thread: threading.Thread | None = None
        self._closed = False
        self._accepted = 0
        self._durable = 0
        self._dropped = 0
        self._error: str | None = None
        self._submission_error: str | None = None
        self._last_receipt: JsonObject | None = None

    def submit(self, record: JsonObject) -> bool:
        import threading

        try:
            encoded = _encode(record, self.max_line_bytes, newline=True)
        except (ValueError, TypeError, RecursionError) as exc:
            with self._condition:
                self._dropped += 1
                self._submission_error = "invalid evidence submission: " + type(exc).__name__
                self._condition.notify_all()
            return False
        with self._condition:
            if (
                self._closed
                or self._error
                or len(self._pending) >= self.max_pending_records
                or self._pending_bytes + len(encoded) > self.max_pending_bytes
            ):
                self._dropped += 1
                return False
            self._pending.append(encoded)
            self._pending_bytes += len(encoded)
            self._accepted += 1
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="carvera-evidence-writer", daemon=True)
                self._thread.start()
            self._condition.notify_all()
            return True

    def _run(self) -> None:
        while True:
            with self._condition:
                while not self._pending and not self._closed and not self._error:
                    self._condition.wait(2.0)
                    if not self._pending:
                        self._thread = None
                        return
                if self._error or (self._closed and not self._pending):
                    return
                encoded = self._pending[0]
            try:
                receipt = append_jsonl(
                    self.path, decode_json(encoded), max_bytes=self.max_bytes, max_line_bytes=self.max_line_bytes
                )
            except Exception as exc:
                with self._condition:
                    self._error = type(exc).__name__ + ": " + str(exc)[:300]
                    self._condition.notify_all()
                return
            with self._condition:
                self._pending.popleft()
                self._pending_bytes -= len(encoded)
                self._durable += 1
                self._last_receipt = receipt
                self._condition.notify_all()

    def status(self) -> JsonObject:
        with self._condition:
            return {
                "accepted": self._accepted,
                "durable": self._durable,
                "dropped": self._dropped,
                "pending_records": len(self._pending),
                "pending_bytes": self._pending_bytes,
                "closed": self._closed,
                "error": self._error,
                "last_submission_error": self._submission_error,
                "last_receipt": dict(self._last_receipt) if self._last_receipt else None,
            }

    def pending_records(self) -> list[JsonObject]:
        """Bounded forensic snapshot; callers must not mistake it for disk receipt."""
        with self._condition:
            return [decode_json(record) for record in self._pending]

    def flush(self, timeout_s: float = 0.5) -> bool:
        if not 0 <= timeout_s <= 60:
            raise ValueError("invalid evidence flush timeout")
        deadline = time.monotonic() + timeout_s
        with self._condition:
            while self._pending and self._error is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return not self._pending and self._error is None

    def close(self, timeout_s: float = 0.5) -> bool:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        return self.flush(timeout_s)
