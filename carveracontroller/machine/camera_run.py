"""Asynchronous JPEG custody and receipt-time replay; no CNC or UI dependencies."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import queue
import threading
import time
import zipfile
from bisect import bisect_right
from pathlib import Path
from typing import IO, Protocol, TypedDict, Union, cast
from uuid import UUID, uuid4


class AcceptedCameraFrame(Protocol):
    """Accepted capture data; the writer still validates every receipt."""

    @property
    def jpeg(self) -> bytes: ...
    @property
    def size(self) -> tuple[int, int]: ...
    @property
    def received_at(self) -> float: ...
    @property
    def captured_at(self) -> float | None: ...
    @property
    def sequence(self) -> int: ...


class CameraStatus(TypedDict):
    submitted: int
    accepted: int
    written: int
    dropped: int
    pending_bytes: int
    error: str
    closed: bool


class CameraHeader(TypedDict):
    kind: str
    schema: int
    recording_session_id: str
    part_id: str
    created_utc: float


class PendingCameraReceipt(TypedDict):
    kind: str
    attempt: int
    sequence: int
    generation: int
    received_at: float
    server_captured_at: float | None
    size: tuple[int, int] | list[int]
    size_bytes: int


class CameraReceipt(PendingCameraReceipt):
    sha256: str


class CameraAssociation(TypedDict, total=False):
    frame: CameraReceipt | None
    reason: str
    receipt_age_seconds: float


class CameraBundleReceipt(TypedDict):
    manifest_sha256: str
    frames: int
    assets: int


CameraPath = Union[str, os.PathLike[str]]

MAX_FRAME_BYTES = 8 * 1024 * 1024
MAX_PENDING_BYTES = 16 * 1024 * 1024
MAX_INDEX_BYTES = 16 * 1024 * 1024
MAX_FRAMES = 10000
MAX_BUNDLE_BYTES = 272 * 1024 * 1024
MAX_ASSET_BYTES = 256 * 1024 * 1024
MAX_COMMIT_FRAMES = 8


def _number(value: object) -> float:
    if type(value) not in (int, float) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError("Camera receipt requires a finite nonnegative clock")
    return value


def _integer(value: object) -> int:
    if type(value) is not int or not isinstance(value, int) or value < 0:
        raise ValueError("Invalid camera sequence or generation")
    return value


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


class CameraRunWriter:
    """One owned writer, bounded enqueue, immutable assets and explicit losses.

    Construct off the UI thread. close() requests a drain and waits only for its
    existing worker. A timeout does not retire that worker or permit a restart.
    """

    def __init__(
        self, directory: CameraPath, session_id: str, *, max_bytes: int = 256 * 1024 * 1024, capacity: int = 8
    ) -> None:
        session_id = str(UUID(session_id))
        if type(max_bytes) is not int or max_bytes <= 0 or type(capacity) is not int or not 1 <= capacity <= 64:
            raise ValueError("Invalid camera recording limits")
        self.folder = Path(directory) / session_id / str(uuid4())
        self.folder.mkdir(parents=True, exist_ok=False)
        self._journal = (self.folder / "frames.jsonl").open("xb")
        self._lock = threading.Lock()
        self._queue: queue.Queue[tuple[PendingCameraReceipt, bytes]] = queue.Queue(maxsize=capacity)
        self._stop = threading.Event()
        self._max_bytes = max_bytes
        self._reserved = self._pending_bytes = self._submitted = self._accepted = self._written = self._dropped = 0
        self._last_received: float | None = None
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

    def _append(self, value: object) -> None:
        self._append_many([value])

    def _append_many(self, values: list[object]) -> None:
        if not values:
            return
        chain, lines = self._chain, []
        for value in values:
            if not isinstance(value, dict):
                raise ValueError("Camera journal record must be an object")
            chain = hashlib.sha256(chain.encode() + _json(value)).hexdigest()
            lines.append(_json(dict(value, chain_sha256=chain)))
        self._journal.write(b"".join(lines))
        self._journal.flush()
        os.fsync(self._journal.fileno())
        self._chain = chain

    def submit(self, frame: AcceptedCameraFrame, generation: int) -> bool:
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
            item: PendingCameraReceipt = {
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

    def _persist(self, item: PendingCameraReceipt, data: bytes) -> CameraReceipt:
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
        return {**item, "sha256": digest}

    def _commit_batch(self, batch: list[tuple[PendingCameraReceipt, bytes]]) -> None:
        receipts: list[object] = []
        try:
            for item, data in batch:
                try:
                    receipts.append(self._persist(item, data))
                except Exception:
                    with self._lock:
                        self._error = "Camera asset persistence failed"
                        self._dropped += 1
                    self._stop.set()
            try:
                self._append_many(receipts)
            except Exception:
                with self._lock:
                    self._dropped += len(receipts)
                raise
            # Asset readback and the entire journal group must succeed before
            # any frame in this batch is reported as durably written.
            with self._lock:
                self._written += len(receipts)
        finally:
            with self._lock:
                self._pending_bytes -= sum(len(data) for _item, data in batch)
            for _entry in batch:
                self._queue.task_done()

    def _run(self) -> None:
        try:
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    item, data = self._queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                batch = [(item, data)]
                # Commit only frames already queued. Never wait for a group to
                # fill, and retain the byte/queue bounds while disk I/O runs.
                while len(batch) < MAX_COMMIT_FRAMES:
                    try:
                        batch.append(self._queue.get_nowait())
                    except queue.Empty:
                        break
                self._commit_batch(batch)
            self._append({"kind": "footer", **self.status()})
        except Exception:
            with self._lock:
                self._stop.set()
                self._error = "Camera journal persistence failed; partial session preserved"
            # The journal cannot admit more receipts. Account for every frame
            # already accepted without restarting a writer or losing its files.
            while True:
                try:
                    _item, data = self._queue.get_nowait()
                except queue.Empty:
                    break
                with self._lock:
                    self._pending_bytes -= len(data)
                    self._dropped += 1
                self._queue.task_done()
        finally:
            try:
                self._journal.close()
            except Exception:
                with self._lock:
                    self._error = "Camera journal persistence failed; partial session preserved"
            finally:
                with self._lock:
                    self._closed = True

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def status(self) -> CameraStatus:
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

    def request_stop(self) -> None:
        self._stop.set()

    def close(self, timeout: float = 5) -> CameraStatus:
        self.request_stop()
        self.thread.join(timeout)
        if self.thread.is_alive():
            raise TimeoutError("Camera writer still flushing; retain the existing worker")
        return self.status()


class CameraRunReplay:
    """Receipt-time association; server clock and exposure offset remain unknown."""

    def __init__(self, folder: CameraPath, *, manifest_bytes: bytes | None = None) -> None:
        self.folder = Path(folder)
        if manifest_bytes is None:
            with (self.folder / "frames.jsonl").open("rb") as stream:
                data = stream.read(MAX_INDEX_BYTES + 1)
        else:
            if not isinstance(manifest_bytes, bytes):
                raise ValueError("Camera manifest must be bytes")
            data = manifest_bytes
        if len(data) > MAX_INDEX_BYTES or not data.endswith(b"\n"):
            raise ValueError("Oversized or incomplete camera manifest")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate camera manifest key")
                result[key] = value
            return result

        records: list[dict[str, object]] = []
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
        header = records[0]
        if not isinstance(header["recording_session_id"], str) or not isinstance(header["part_id"], str):
            raise ValueError("Invalid camera manifest session identity")
        _number(header["created_utc"])
        self.header = cast(CameraHeader, header)
        UUID(self.header["recording_session_id"])
        UUID(self.header["part_id"])
        self._frames: list[CameraReceipt] = []
        self.footer: CameraStatus | None = None
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
                counts = {
                    key: _integer(record[key])
                    for key in ("submitted", "accepted", "written", "dropped", "pending_bytes")
                }
                if (
                    counts["written"] != len(self._frames)
                    or counts["pending_bytes"] != 0
                    or counts["accepted"] < counts["written"]
                    or counts["accepted"] > counts["submitted"]
                    or counts["submitted"] != counts["written"] + counts["dropped"]
                    or type(record["closed"]) is not bool
                    or not isinstance(record["error"], str)
                ):
                    raise ValueError("Camera final accounting differs")
                self.footer = cast(CameraStatus, record)
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
            if not 4 <= _integer(record["size_bytes"]) <= MAX_FRAME_BYTES:
                raise ValueError("Invalid camera asset size")
            self._frames.append(cast(CameraReceipt, record))
        if len(self._frames) > MAX_FRAMES:
            raise ValueError("Camera frame count exceeds retention")
        self._times = [frame["received_at"] for frame in self._frames]

    @property
    def frames(self) -> list[CameraReceipt]:
        return copy.deepcopy(self._frames)

    def read_frame(self, frame: CameraReceipt) -> bytes:
        if frame not in self._frames:
            raise ValueError("Frame does not belong to this recording")
        with (self.folder / (frame["sha256"] + ".jpg")).open("rb") as stream:
            data = stream.read(MAX_FRAME_BYTES + 1)
        if len(data) != frame["size_bytes"] or hashlib.sha256(data).hexdigest() != frame["sha256"]:
            raise ValueError("Recorded JPEG bytes differ")
        return data

    def at(self, received_at: float, max_age: float = 2) -> CameraAssociation:
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


def _bundle_index(archive: zipfile.ZipFile) -> tuple[CameraRunReplay, bytes, dict[str, CameraReceipt]]:
    """Validate the exact portable part member set before writing any files."""
    entries = archive.infolist()
    names = [entry.filename for entry in entries]
    if not entries or len(entries) > MAX_FRAMES + 1 or len(names) != len(set(names)):
        raise ValueError("Invalid or duplicate camera bundle members")
    if "frames.jsonl" not in names:
        raise ValueError("Camera bundle has no manifest")
    total = 0
    for entry in entries:
        limit = MAX_INDEX_BYTES if entry.filename == "frames.jsonl" else MAX_FRAME_BYTES
        mode = entry.external_attr >> 16
        if (
            entry.compress_type != zipfile.ZIP_STORED
            or entry.flag_bits & 1
            or entry.is_dir()
            or mode & 0o170000 not in (0, 0o100000)
            or not 0 <= entry.file_size <= limit
        ):
            raise ValueError("Unsupported camera bundle member or size")
        total += entry.file_size
    if total > MAX_BUNDLE_BYTES:
        raise ValueError("Camera bundle exceeds retention budget")
    manifest = archive.read("frames.jsonl")
    replay = CameraRunReplay(".", manifest_bytes=manifest)
    assets: dict[str, CameraReceipt] = {}
    for frame in replay.frames:
        name = frame["sha256"] + ".jpg"
        if name in assets and assets[name]["size_bytes"] != frame["size_bytes"]:
            raise ValueError("Camera asset receipts disagree")
        assets[name] = frame
    if set(names) != {"frames.jsonl", *assets}:
        raise ValueError("Camera bundle contains missing or unexpected assets")
    if sum(frame["size_bytes"] for frame in assets.values()) > MAX_ASSET_BYTES:
        raise ValueError("Camera assets exceed retention budget")
    for name, frame in assets.items():
        if archive.getinfo(name).file_size != frame["size_bytes"]:
            raise ValueError("Camera bundle asset size differs")
    return replay, manifest, assets


def _bundle_asset(archive: zipfile.ZipFile, name: str, receipt: CameraReceipt) -> bytes:
    data = archive.read(name)
    if len(data) != receipt["size_bytes"] or hashlib.sha256(data).hexdigest() != receipt["sha256"]:
        raise ValueError("Camera bundle JPEG bytes differ")
    return data


def export_camera_bundle(replay: CameraRunReplay, filename: CameraPath) -> CameraBundleReceipt:
    """Export an exact manifest and verified JPEGs; never overwrite a destination."""
    with (replay.folder / "frames.jsonl").open("rb") as source:
        manifest = source.read(MAX_INDEX_BYTES + 1)
    snapshot = CameraRunReplay(replay.folder, manifest_bytes=manifest)
    if snapshot.manifest_digest != replay.manifest_digest:
        raise ValueError("Camera manifest changed after selection")
    unique = {frame["sha256"]: frame for frame in snapshot.frames}
    if sum(frame["size_bytes"] for frame in unique.values()) > MAX_ASSET_BYTES:
        raise ValueError("Camera assets exceed retention budget")
    path = Path(filename)
    with path.open("xb") as destination:
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
            archive.writestr("frames.jsonl", manifest)
            for digest, frame in unique.items():
                archive.writestr(digest + ".jpg", snapshot.read_frame(frame))
        destination.flush()
        os.fsync(destination.fileno())
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Camera bundle exceeds retention budget")
    with zipfile.ZipFile(path) as archive:
        checked, _, assets = _bundle_index(archive)
        for name, receipt in assets.items():
            _bundle_asset(archive, name, receipt)
    if checked.manifest_digest != replay.manifest_digest:
        raise ValueError("Saved camera manifest differs")
    return {"manifest_sha256": checked.manifest_digest, "frames": len(checked.frames), "assets": len(assets)}


def import_camera_bundle(filename: CameraPath, directory: CameraPath, session_id: str) -> CameraRunReplay:
    """Validate before installation into a new owned part; preserve existing parts."""
    session_id = str(UUID(session_id))
    path = Path(filename)
    source = path.open("rb")
    try:
        if os.fstat(source.fileno()).st_size > MAX_BUNDLE_BYTES:
            raise ValueError("Camera bundle exceeds retention budget")
        return _install_camera_bundle(source, directory, session_id)
    finally:
        source.close()


def _install_camera_bundle(source: IO[bytes], directory: CameraPath, session_id: str) -> CameraRunReplay:
    with zipfile.ZipFile(source) as archive:
        indexed, manifest, assets = _bundle_index(archive)
        if indexed.header["recording_session_id"] != session_id:
            raise ValueError("Camera bundle belongs to a different status session")
        for name, receipt in assets.items():
            _bundle_asset(archive, name, receipt)
        folder = Path(directory) / session_id / ("import-" + str(uuid4()))
        folder.mkdir(parents=True, exist_ok=False)
        with (folder / "frames.jsonl").open("xb") as stream:
            stream.write(manifest)
            stream.flush()
            os.fsync(stream.fileno())
        for name, receipt in assets.items():
            with (folder / name).open("xb") as stream:
                stream.write(_bundle_asset(archive, name, receipt))
                stream.flush()
                os.fsync(stream.fileno())
    installed = CameraRunReplay(folder)
    if installed.manifest_digest != indexed.manifest_digest:
        raise ValueError("Installed camera manifest differs")
    for frame in installed.frames:
        installed.read_frame(frame)
    return installed


def validate_camera_bundle_stream(source: IO[bytes], session_id: str) -> str:
    """Validate a bounded seekable nested bundle without installing assets."""
    source.seek(0, 2)
    if source.tell() > MAX_BUNDLE_BYTES:
        raise ValueError("Camera bundle exceeds retention budget")
    source.seek(0)
    with zipfile.ZipFile(source) as archive:
        replay, _, assets = _bundle_index(archive)
        if replay.header["recording_session_id"] != str(UUID(session_id)):
            raise ValueError("Camera bundle belongs to a different status session")
        for name, receipt in assets.items():
            _bundle_asset(archive, name, receipt)
    return replay.manifest_digest


def import_camera_bundle_stream(source: IO[bytes], directory: CameraPath, session_id: str) -> CameraRunReplay:
    validate_camera_bundle_stream(source, session_id)
    source.seek(0)
    return _install_camera_bundle(source, directory, str(UUID(session_id)))
