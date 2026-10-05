"""Asynchronous JPEG custody and receipt-time replay; no CNC or UI dependencies."""

import copy
import hashlib
import json
import math
import os
import queue
import threading
import time
from bisect import bisect_right
from pathlib import Path
from uuid import UUID, uuid4

MAX_FRAME_BYTES = 8 * 1024 * 1024
MAX_PENDING_BYTES = 16 * 1024 * 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_FRAMES = 10000


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError("Camera receipt requires a finite nonnegative clock")
    return value


def _integer(value):
    if type(value) is not int or value < 0:
        raise ValueError("Invalid camera sequence or generation")
    return value


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


class CameraRunWriter:
    """One owned writer, bounded enqueue, immutable assets and explicit losses.

    Construct off the UI thread. close() requests a drain and waits only for its
    existing worker. A timeout does not retire that worker or permit a restart.
    """

    def __init__(self, directory, session_id, *, max_bytes=256 * 1024 * 1024, capacity=8):
        session_id = str(UUID(session_id))
        if type(max_bytes) is not int or max_bytes <= 0 or type(capacity) is not int or not 1 <= capacity <= 64:
            raise ValueError("Invalid camera recording limits")
        self.folder = Path(directory) / session_id / str(uuid4())
        self.folder.mkdir(parents=True, exist_ok=False)
        self._journal = (self.folder / "frames.jsonl").open("xb")
        self._lock = threading.Lock()
        self._queue = queue.Queue(maxsize=capacity)
        self._stop = threading.Event()
        self._max_bytes = max_bytes
        self._reserved = self._pending_bytes = self._submitted = self._accepted = self._written = self._dropped = 0
        self._last_received = None
        self._error = ""
        self._closed = False
        self._chain = "0" * 64
        self._append(
            {
                "kind": "header",
                "schema": 1,
                "recording_session_id": session_id,
                "part_id": self.folder.name,
                "created_utc": time.time(),
            }
        )
        self.thread = threading.Thread(target=self._run, name="camera-run-writer", daemon=False)
        self.thread.start()

    def _append(self, value):
        digest = hashlib.sha256(self._chain.encode() + _json(value)).hexdigest()
        self._journal.write(_json(dict(value, chain_sha256=digest)))
        self._journal.flush()
        os.fsync(self._journal.fileno())
        self._chain = digest

    def submit(self, frame, generation):
        data = frame.jpeg
        if not isinstance(data, bytes) or not 4 <= len(data) <= MAX_FRAME_BYTES or not data.startswith(b"\xff\xd8"):
            raise ValueError("Camera recording requires bounded accepted JPEG bytes")
        received = _number(frame.received_at)
        captured = None if frame.captured_at is None else _number(frame.captured_at)
        sequence, generation = _integer(frame.sequence), _integer(generation)
        size = tuple(frame.size)
        if len(size) != 2 or any(type(v) is not int or not 1 <= v <= 4096 for v in size):
            raise ValueError("Invalid recorded image dimensions")
        with self._lock:
            if self._stop.is_set():
                return False
            self._submitted += 1
            if self._error:
                self._dropped += 1
                return False
            if self._last_received is not None and received < self._last_received:
                self._dropped += 1
                return False
            if self._accepted >= MAX_FRAMES or self._reserved + len(data) > self._max_bytes:
                self._error = "Camera recording limit reached"
                self._dropped += 1
                return False
            if self._pending_bytes + len(data) > MAX_PENDING_BYTES:
                self._dropped += 1
                return False
            item = {
                "kind": "frame",
                "attempt": self._submitted,
                "sequence": sequence,
                "generation": generation,
                "received_at": received,
                "server_captured_at": captured,
                "size": size,
                "size_bytes": len(data),
            }
            try:
                self._queue.put_nowait((item, data))
            except queue.Full:
                self._dropped += 1
                return False
            self._last_received = received
            self._accepted += 1
            self._reserved += len(data)
            self._pending_bytes += len(data)
            return True

    def _persist(self, item, data):
        digest = hashlib.sha256(data).hexdigest()
        asset = self.folder / (digest + ".jpg")
        try:
            with asset.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            pass
        with asset.open("rb") as stream:
            readback = stream.read(MAX_FRAME_BYTES + 1)
        if readback != data:
            raise ValueError("Existing camera asset differs")
        self._append(dict(item, sha256=digest))

    def _run(self):
        try:
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    item, data = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    self._persist(item, data)
                    with self._lock:
                        self._written += 1
                except Exception:
                    with self._lock:
                        self._error = "Camera asset persistence failed"
                        self._dropped += 1
                    self._stop.set()
                finally:
                    with self._lock:
                        self._pending_bytes -= len(data)
                    self._queue.task_done()
            self._append({"kind": "footer", **self.status()})
        except Exception:
            with self._lock:
                self._error = "Camera journal persistence failed; partial session preserved"
        finally:
            self._journal.close()
            with self._lock:
                self._closed = True

    def status(self):
        with self._lock:
            return {
                "submitted": self._submitted,
                "accepted": self._accepted,
                "written": self._written,
                "dropped": self._dropped,
                "pending_bytes": self._pending_bytes,
                "error": self._error,
                "closed": self._closed,
            }

    def request_stop(self):
        self._stop.set()

    def close(self, timeout=5):
        self.request_stop()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise TimeoutError("Camera writer still flushing; retain the existing worker")
        return self.status()


class CameraRunReplay:
    """Receipt-time association; server clock and exposure offset remain unknown."""

    def __init__(self, folder):
        self.folder = Path(folder)
        with (self.folder / "frames.jsonl").open("rb") as stream:
            data = stream.read(MAX_INDEX_BYTES + 1)
        if len(data) > MAX_INDEX_BYTES or not data.endswith(b"\n"):
            raise ValueError("Oversized or incomplete camera manifest")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate camera manifest key")
                result[key] = value
            return result

        records = []
        chain = "0" * 64
        for line in data.splitlines():
            record = json.loads(line, object_pairs_hook=unique)
            if not isinstance(record, dict):
                raise ValueError("Invalid camera manifest record")
            digest = record.pop("chain_sha256", None)
            expected = hashlib.sha256(chain.encode() + _json(record)).hexdigest()
            if digest != expected:
                raise ValueError("Camera manifest digest chain differs")
            chain = digest
            records.append(record)
        self.manifest_digest = chain
        if (
            not records
            or set(records[0]) != {"kind", "schema", "recording_session_id", "part_id", "created_utc"}
            or records[0]["kind"] != "header"
            or type(records[0]["schema"]) is not int
            or records[0]["schema"] != 1
        ):
            raise ValueError("Invalid camera manifest header")
        self.header = records[0]
        UUID(self.header["recording_session_id"])
        UUID(self.header["part_id"])
        _number(self.header["created_utc"])
        self._frames = []
        self.footer = None
        previous_time, previous_attempt = None, 0
        for record in records[1:]:
            if self.footer is not None:
                raise ValueError("Camera records follow the footer")
            if record.get("kind") == "footer":
                if set(record) != {
                    "kind",
                    "submitted",
                    "accepted",
                    "written",
                    "dropped",
                    "pending_bytes",
                    "error",
                    "closed",
                }:
                    raise ValueError("Invalid camera manifest footer")
                for key in ("submitted", "accepted", "written", "dropped", "pending_bytes"):
                    _integer(record[key])
                if (
                    record["written"] != len(self._frames)
                    or record["pending_bytes"] != 0
                    or record["accepted"] < record["written"]
                    or record["accepted"] > record["submitted"]
                    or record["submitted"] != record["written"] + record["dropped"]
                    or type(record["closed"]) is not bool
                    or not isinstance(record["error"], str)
                ):
                    raise ValueError("Camera final accounting differs")
                self.footer = record
                continue
            if (
                set(record)
                != {
                    "kind",
                    "attempt",
                    "sequence",
                    "generation",
                    "received_at",
                    "server_captured_at",
                    "size",
                    "size_bytes",
                    "sha256",
                }
                or record["kind"] != "frame"
            ):
                raise ValueError("Invalid camera frame receipt")
            now, attempt = _number(record["received_at"]), _integer(record["attempt"])
            if attempt <= previous_attempt or previous_time is not None and now < previous_time:
                raise ValueError("Camera receipt order differs")
            previous_time, previous_attempt = now, attempt
            _integer(record["sequence"])
            _integer(record["generation"])
            if record["server_captured_at"] is not None:
                _number(record["server_captured_at"])
            digest, size = record["sha256"], record["size"]
            if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
                raise ValueError("Invalid camera asset digest")
            if (
                not isinstance(size, list)
                or len(size) != 2
                or any(type(v) is not int or not 1 <= v <= 4096 for v in size)
            ):
                raise ValueError("Invalid camera frame dimensions")
            if type(record["size_bytes"]) is not int or not 4 <= record["size_bytes"] <= MAX_FRAME_BYTES:
                raise ValueError("Invalid camera asset size")
            self._frames.append(record)
        if len(self._frames) > MAX_FRAMES:
            raise ValueError("Camera frame count exceeds retention")
        self._times = [frame["received_at"] for frame in self._frames]

    @property
    def frames(self):
        return copy.deepcopy(self._frames)

    def read_frame(self, frame):
        if frame not in self._frames:
            raise ValueError("Frame does not belong to this recording")
        with (self.folder / (frame["sha256"] + ".jpg")).open("rb") as stream:
            data = stream.read(MAX_FRAME_BYTES + 1)
        if len(data) != frame["size_bytes"] or hashlib.sha256(data).hexdigest() != frame["sha256"]:
            raise ValueError("Recorded JPEG bytes differ")
        return data

    def at(self, received_at, max_age=2):
        now = _number(received_at)
        if _number(max_age) <= 0:
            raise ValueError("Camera replay age limit must be positive")
        if not self._frames or now < self._times[0] or now > self._times[-1]:
            return {"frame": None, "reason": "Outside retained camera receipts"}
        index = bisect_right(self._times, now) - 1
        frame = self._frames[index]
        following = self._frames[index + 1] if index + 1 < len(self._frames) else None
        age = now - frame["received_at"]
        boundary = following and (
            following["attempt"] != frame["attempt"] + 1 or following["generation"] != frame["generation"]
        )
        if age > max_age or boundary and age > 0:
            return {"frame": None, "reason": "Camera receipt gap or source boundary"}
        return {
            "frame": copy.deepcopy(frame),
            "receipt_age_seconds": age,
            "reason": "Receipt-time association; server clock and exposure offset unqualified",
        }
