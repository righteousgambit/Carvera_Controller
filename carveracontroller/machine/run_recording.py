"""Bounded, packet-based run evidence. Replay never interpolates missing motion."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import threading
from bisect import bisect_right
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import TypedDict, cast
from uuid import uuid4

from carveracontroller.addons.machine_simulation.stock_model import stock_reference
from carveracontroller.machine.sensor_run_recording import parse_numeric_fields, source_field_validity
from carveracontroller.machine.wire_observation import wire_fields


class RecordedProgram(TypedDict):
    name: str
    sha256: str
    size_bytes: int


class RecordedSetupCore(TypedDict):
    work_offset_mm: list[float] | tuple[float, float, float]
    stock_origin_mm: list[float] | tuple[float, float, float]
    stock_size_mm: list[float] | tuple[float, float, float] | None
    alignment_confirmed: bool


class RecordedStockSource(TypedDict):
    schema: int
    source_sha256: str
    source_units: str
    minimum_mm: list[float]
    maximum_mm: list[float]


def stock_source_identity(value: object) -> RecordedStockSource:
    if not isinstance(value, dict):
        raise ValueError("Invalid recorded stock source")
    reference = stock_reference({"source_path": "retained-stock.stl", **value})
    return RecordedStockSource(
        schema=reference["schema"],
        source_sha256=reference["source_sha256"],
        source_units=reference["source_units"],
        minimum_mm=reference["minimum_mm"],
        maximum_mm=reference["maximum_mm"],
    )


class RecordedSetup(RecordedSetupCore, total=False):
    stock_rotation_deg: float
    stock_tilt_deg: tuple[float, float] | list[float]
    stock_source: RecordedStockSource


class RecordedConfiguration(TypedDict):
    sha256: str
    size_bytes: int
    scope: str


class RecordingContextCore(TypedDict):
    scope: str
    program: RecordedProgram
    setup: RecordedSetup


class RecordingContext(RecordingContextCore, total=False):
    configuration: RecordedConfiguration


class BackendRecordingSource(TypedDict):
    kind: str
    session_id: str
    connection_id: str
    timing_source: str


class SourceReceipt(TypedDict):
    sequence: int
    ipc_sha256: str
    status_text: str
    status_sha256: str


def backend_source(value: object) -> BackendRecordingSource:
    if not isinstance(value, dict) or set(value) != {"kind", "session_id", "connection_id", "timing_source"}:
        raise ValueError("Invalid backend recording source")
    if value["kind"] != "private_backend_ipc" or value["timing_source"] != "host_ipc_receipt":
        raise ValueError("Unsupported backend receipt semantics")
    for key in ("session_id", "connection_id"):
        identity = value[key]
        if (
            not isinstance(identity, str)
            or not 0 < len(identity) <= 100
            or any(not 33 <= ord(c) <= 126 for c in identity)
        ):
            raise ValueError("Invalid backend recording owner")
    return cast(BackendRecordingSource, copy.deepcopy(value))


def source_receipt(value: object) -> SourceReceipt:
    if not isinstance(value, dict) or set(value) != {"sequence", "ipc_sha256", "status_text", "status_sha256"}:
        raise ValueError("Invalid source receipt")
    sequence, digest = value["sequence"], value["ipc_sha256"]
    if (
        type(sequence) is not int
        or sequence < 1
        or not isinstance(digest, str)
        or len(digest) != 64
        or any(c not in "0123456789abcdef" for c in digest)
    ):
        raise ValueError("Invalid source receipt sequence or digest")
    text = value["status_text"]
    if (
        not isinstance(text, str)
        or len(text) > 8192
        or hashlib.sha256(text.encode()).hexdigest() != value["status_sha256"]
    ):
        raise ValueError("Original status text digest differs")
    _, fields = wire_fields(text, "<", ">", state=True)
    if "SE" in fields:
        parse_numeric_fields(text, status=True)
    return cast(SourceReceipt, copy.deepcopy(value))


class RecordedEventData(TypedDict, total=False):
    state: str
    fields: dict[str, list[float]]
    previous_generation: int
    duration_seconds: float
    source_receipt: SourceReceipt
    lost_receipts: int


def recording_source_validity(body: RecordedEventData) -> dict[str, bool | None]:
    """Recover validity from retained original text, including old schema 4 bodies.

    Older writers omitted SE from the field map. Its original source receipt
    remains authoritative; removing the optional field cannot hide invalidity.
    """
    receipt = body.get("source_receipt")
    if receipt:
        _, original = wire_fields(receipt["status_text"], "<", ">", state=True)
        if "SE" in original:
            _, original = parse_numeric_fields(receipt["status_text"], status=True)
            return source_field_validity(original)
    return source_field_validity(body.get("fields", {}))


class PendingEvent(TypedDict):
    monotonic_at: float
    utc_at: float
    generation: int
    kind: str
    data: RecordedEventData


class RecordedEvent(PendingEvent):
    sequence: int


class RecordingPayloadCore(TypedDict):
    schema: int
    session_id: str
    capacity: int
    dropped_events: int
    events: list[RecordedEvent]


class RecordingPayload(RecordingPayloadCore, total=False):
    context: RecordingContext
    source: BackendRecordingSource


class RecordingSummary(TypedDict):
    retained_events: int
    dropped_events: int
    latest: RecordedEvent | None
    context: RecordingContext | None


class ReplayAssociation(TypedDict):
    sample: RecordedEvent | None
    reason: str
    age_seconds: float | None


FIELDS = frozenset(("MPos", "WPos", "C", "F", "S", "T", "G", "R", "P", "A", "O", "H", "PWM", "SE"))
MAX_EVENTS = 10000
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def _finite(value: object) -> float:
    if type(value) not in (int, float) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Recording values must be finite numbers")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_context(context: object) -> RecordingContext:
    """Local selection evidence, never a claim of machine execution or calibration."""
    if not isinstance(context, dict) or set(context) not in (
        {"scope", "program", "setup"},
        {"scope", "program", "setup", "configuration"},
    ):
        raise ValueError("Invalid recording context")
    if context["scope"] != "local_selection_at_recording_start":
        raise ValueError("Unsupported recording binding scope")
    program = context["program"]
    if not isinstance(program, dict) or set(program) != {"name", "sha256", "size_bytes"}:
        raise ValueError("Invalid recorded program identity")
    if not isinstance(program["name"], str) or not 1 <= len(program["name"]) <= 255:
        raise ValueError("Invalid recorded program name")
    digest = program["sha256"]
    if not isinstance(digest, str) or len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
        raise ValueError("Invalid recorded program digest")
    if type(program["size_bytes"]) is not int or not 0 <= program["size_bytes"] <= MAX_ARCHIVE_BYTES:
        raise ValueError("Invalid recorded program size")
    setup = context["setup"]
    if not isinstance(setup, dict) or set(setup) - {"stock_rotation_deg", "stock_tilt_deg", "stock_source"} != {
        "work_offset_mm",
        "stock_origin_mm",
        "stock_size_mm",
        "alignment_confirmed",
    }:
        raise ValueError("Invalid recorded setup")
    for key in ("work_offset_mm", "stock_origin_mm", "stock_size_mm"):
        point = setup[key]
        if key == "stock_size_mm" and point is None:
            continue
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            raise ValueError("Recorded setup requires XYZ dimensions")
        for value in point:
            _finite(value)
        if key == "stock_size_mm" and min(point) <= 0:
            raise ValueError("Recorded stock dimensions must be positive")
    if "stock_rotation_deg" in setup:
        _finite(setup["stock_rotation_deg"])
    if "stock_tilt_deg" in setup:
        tilt = setup["stock_tilt_deg"]
        if not isinstance(tilt, (list, tuple)) or len(tilt) != 2:
            raise ValueError("Recorded stock tilt requires X and Y angles")
        for value in tilt:
            _finite(value)
    if type(setup["alignment_confirmed"]) is not bool:
        raise ValueError("Invalid recorded alignment declaration")
    if "stock_source" in setup:
        source = setup["stock_source"]
        if not isinstance(source, dict) or "source_path" in source:
            raise ValueError("Recorded stock identity must omit local paths")
        reference = stock_source_identity(source)
        if list(setup["stock_size_mm"] or ()) != [
            b - a for a, b in zip(reference["minimum_mm"], reference["maximum_mm"])
        ]:
            raise ValueError("Recorded stock dimensions differ from source")
    if "configuration" in context:
        configuration = context["configuration"]
        if (
            not isinstance(configuration, dict)
            or set(configuration) != {"sha256", "size_bytes", "scope"}
            or configuration["scope"] != "declared_setup_assets_at_recording_start"
            or not isinstance(configuration["sha256"], str)
            or len(configuration["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in configuration["sha256"])
            or type(configuration["size_bytes"]) is not int
            or not 0 < configuration["size_bytes"] <= 256 * 1024 * 1024
        ):
            raise ValueError("Invalid recorded configuration identity")
    return copy.deepcopy(cast(RecordingContext, context))


def selected_context(filename: str | Path, setup: object) -> RecordingContext:
    """Hash bounded program bytes on an artifact worker; omit private path names."""
    path = Path(filename)
    with path.open("rb") as stream:
        data = stream.read(MAX_ARCHIVE_BYTES + 1)
    if isinstance(setup, dict) and "stock_source" in setup:
        setup = {**setup, "stock_source": stock_source_identity(setup["stock_source"])}
    return validate_context(
        {
            "scope": "local_selection_at_recording_start",
            "program": {"name": path.name, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)},
            "setup": setup,
        }
    )


class RunRecording:
    """No disk I/O or commands on capture; snapshots own their mutable values.

    P is retained as a raw controller report. Its line counter is not promoted
    to executed progress without backend-specific execution evidence. Packet
    coordinates retain the wire units and C flags rather than mixing reports.
    """

    def __init__(
        self, capacity: int = MAX_EVENTS, gap_seconds: float = 2.0, context: object = None, source: object = None
    ) -> None:
        if type(capacity) is not int or not 2 <= capacity <= MAX_EVENTS:
            raise ValueError("Recording capacity must be between 2 and 10000")
        if _finite(gap_seconds) <= 0:
            raise ValueError("Recording gap must be positive")
        self.capacity = capacity
        self.gap_seconds = gap_seconds
        self.session_id = str(uuid4())
        self._context = validate_context(context) if context is not None else None
        self._events: deque[RecordedEvent] = deque(maxlen=capacity)
        self._lock = threading.RLock()
        self._sequence = 0
        self._last_time: float | None = None
        self._generation: int | None = None
        self._source = backend_source(source) if source is not None else None
        self._last_source_sequence = 0

    @property
    def source(self) -> BackendRecordingSource | None:
        return copy.deepcopy(self._source)

    def bind_backend_source(self, source: object) -> None:
        value = backend_source(source)
        with self._lock:
            if self._events or self._source is not None:
                raise ValueError("Only a new empty recording may bind a backend owner")
            self._source = value

    def capture_backend_status(
        self,
        state: object,
        fields: Mapping[str, object],
        monotonic_at: object,
        utc_at: object,
        receipt: object,
        lost_receipts: int = 0,
    ) -> None:
        value = source_receipt(receipt)
        stamp, utc = _finite(monotonic_at), _finite(utc_at)
        if type(lost_receipts) is not int or lost_receipts < 0:
            raise ValueError("Invalid lost-receipt count")
        with self._lock:
            if self._source is None or value["sequence"] <= self._last_source_sequence:
                raise ValueError("Backend owner or new receipt sequence required")
            if stamp < 0 or utc < 0 or self._last_time is not None and stamp < self._last_time:
                raise ValueError("Invalid backend receipt time")
            # Validate the packet before adding either a gap or its status.
            RunRecording().capture_status(state, fields, stamp, utc, 0)
            original_state, original_fields = wire_fields(value["status_text"], "<", ">", state=True)
            if original_state != state or {k: v for k, v in original_fields.items() if k in FIELDS} != {
                k: v for k, v in fields.items() if k in FIELDS
            }:
                raise ValueError("Recorded status differs from its original text")
            if lost_receipts:
                self._append(
                    {
                        "monotonic_at": stamp,
                        "utc_at": utc,
                        "generation": 0,
                        "kind": "source_gap",
                        "data": {"lost_receipts": lost_receipts},
                    }
                )
            self.capture_status(state, fields, stamp, utc, 0)
            self._events[-1]["data"]["source_receipt"] = value
            self._last_source_sequence = value["sequence"]

    def capture_status(
        self, state: object, fields: Mapping[str, object], monotonic_at: object, utc_at: object, generation: object
    ) -> None:
        monotonic_at = _finite(monotonic_at)
        utc_at = _finite(utc_at)
        if (
            monotonic_at < 0
            or utc_at < 0
            or type(generation) is not int
            or not isinstance(generation, int)
            or generation < 0
        ):
            raise ValueError("Invalid recording clock or connection generation")
        if not isinstance(state, str) or not state or len(state) > 80:
            raise ValueError("Invalid reported state")
        if not isinstance(fields, Mapping):
            raise ValueError("Invalid status fields")
        packet: dict[str, list[float]] = {}
        for key in FIELDS & fields.keys():
            values = fields[key]
            if not isinstance(values, (list, tuple)) or len(values) > 32:
                raise ValueError("Invalid status field")
            packet[key] = [_finite(value) for value in values]
        if "SE" in packet:
            text = (
                "<"
                + state
                + "|"
                + "|".join(key + ":" + ",".join(map(str, values)) for key, values in packet.items())
                + ">"
            )
            parse_numeric_fields(text, status=True)
        with self._lock:
            if self._last_time is not None and monotonic_at < self._last_time:
                raise ValueError("Recording monotonic clock moved backwards")
            if self._generation is not None and generation != self._generation:
                self._append(
                    {
                        "monotonic_at": monotonic_at,
                        "utc_at": utc_at,
                        "generation": generation,
                        "kind": "connection_boundary",
                        "data": {"previous_generation": self._generation},
                    }
                )
            elif self._last_time is not None and monotonic_at - self._last_time > self.gap_seconds:
                self._append(
                    {
                        "monotonic_at": monotonic_at,
                        "utc_at": utc_at,
                        "generation": generation,
                        "kind": "gap",
                        "data": {"duration_seconds": monotonic_at - self._last_time},
                    }
                )
            self._append(
                {
                    "monotonic_at": monotonic_at,
                    "utc_at": utc_at,
                    "generation": generation,
                    "kind": "status",
                    "data": {"state": state, "fields": packet},
                }
            )
            self._last_time, self._generation = monotonic_at, generation

    def _append(self, event: PendingEvent) -> None:
        self._sequence += 1
        self._events.append({**event, "sequence": self._sequence})

    def snapshot(self) -> RecordingPayload:
        with self._lock:
            payload: RecordingPayload = {
                "schema": 4
                if self._source is not None
                else (3 if "configuration" in self._context else 2)
                if self._context is not None
                else 1,
                "session_id": self.session_id,
                "capacity": self.capacity,
                "dropped_events": self._sequence - len(self._events),
                "events": copy.deepcopy(list(self._events)),
            }
            if self._context is not None:
                payload["context"] = copy.deepcopy(self._context)
            if self._source is not None:
                payload["source"] = copy.deepcopy(self._source)
            return payload

    def summary(self) -> RecordingSummary:
        """Constant-size UI readback; full-history copies belong on workers."""
        with self._lock:
            return {
                "retained_events": len(self._events),
                "dropped_events": self._sequence - len(self._events),
                "latest": copy.deepcopy(self._events[-1]) if self._events else None,
                "context": copy.deepcopy(self._context),
            }

    def export_bytes(self) -> bytes:
        payload = self.snapshot()
        data = _canonical({"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()})
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("Run recording exceeds 16 MiB; reduce the retained interval")
        return data


def load_recording(data: bytes) -> RecordingPayload:
    """Validate a local archive before exposing it to replay or scene consumers."""
    if not isinstance(data, bytes):
        raise ValueError("Recording archive must be bytes")
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("Run recording exceeds 16 MiB")

    def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        value: dict[str, object] = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate recording key")
            value[key] = item
        return value

    archive = json.loads(data, object_pairs_hook=unique)
    if not isinstance(archive, dict) or set(archive) != {"payload", "sha256"}:
        raise ValueError("Invalid recording envelope")
    payload = archive["payload"]
    if hashlib.sha256(_canonical(payload)).hexdigest() != archive["sha256"]:
        raise ValueError("Run recording digest differs")
    if not isinstance(payload, dict):
        raise ValueError("Invalid recording payload")
    schema = payload.get("schema")
    if type(schema) is not int or schema not in (1, 2, 3, 4):
        raise ValueError("Unsupported recording schema")
    if set(payload) != {
        "schema",
        "session_id",
        "capacity",
        "dropped_events",
        "events",
    } | ({"context"} if schema in (2, 3) or schema == 4 and "context" in payload else set()) | (
        {"source"} if schema == 4 else set()
    ):
        raise ValueError("Invalid recording payload")
    if schema == 4:
        backend_source(payload["source"])
    if "context" in payload:
        validate_context(payload["context"])
        if schema != 4 and ("configuration" in payload["context"]) != (schema == 3):
            raise ValueError("Recording configuration schema differs")
    if not isinstance(payload["session_id"], str) or not 1 <= len(payload["session_id"]) <= 80:
        raise ValueError("Invalid recording session")
    capacity, dropped, events = payload["capacity"], payload["dropped_events"], payload["events"]
    RunRecording(capacity)
    if type(dropped) is not int or dropped < 0 or not isinstance(events, list) or len(events) > capacity:
        raise ValueError("Invalid recording retention")
    previous_time = None
    previous_source_sequence = 0
    for index, event in enumerate(events, start=dropped + 1):
        if not isinstance(event, dict) or set(event) != {
            "kind",
            "data",
            "sequence",
            "monotonic_at",
            "utc_at",
            "generation",
        }:
            raise ValueError("Invalid recorded event")
        if type(event["sequence"]) is not int or event["sequence"] != index:
            raise ValueError("Recording sequence differs")
        now = _finite(event["monotonic_at"])
        if now < 0 or _finite(event["utc_at"]) < 0 or previous_time is not None and now < previous_time:
            raise ValueError("Invalid recorded time")
        previous_time = now
        generation, body = event["generation"], event["data"]
        if type(generation) is not int or generation < 0 or not isinstance(body, dict):
            raise ValueError("Invalid event generation or data")
        if event["kind"] == "status" and set(body) == {"state", "fields"} | (
            {"source_receipt"} if schema == 4 else set()
        ):
            if not isinstance(body["fields"], dict) or not set(body["fields"]) <= FIELDS:
                raise ValueError("Invalid packet fields")
            RunRecording().capture_status(body["state"], body["fields"], now, event["utc_at"], generation)
            if schema == 4:
                receipt = source_receipt(body["source_receipt"])
                original_state, original_fields = wire_fields(receipt["status_text"], "<", ">", state=True)
                if (
                    original_state != body["state"]
                    or {
                        k: v
                        for k, v in original_fields.items()
                        if k in FIELDS and (k != "SE" or "SE" in body["fields"])
                    }
                    != body["fields"]
                ):
                    raise ValueError("Recorded packet differs from its original status text")
                if receipt["sequence"] <= previous_source_sequence or generation != 0:
                    raise ValueError("Backend receipt sequence or single-owner generation differs")
                previous_source_sequence = receipt["sequence"]
        elif schema == 4 and event["kind"] == "source_gap" and set(body) == {"lost_receipts"}:
            if type(body["lost_receipts"]) is not int or body["lost_receipts"] <= 0 or generation != 0:
                raise ValueError("Invalid source observation gap")
        elif event["kind"] == "gap" and set(body) == {"duration_seconds"}:
            if _finite(body["duration_seconds"]) <= 0:
                raise ValueError("Invalid telemetry gap")
        elif event["kind"] == "connection_boundary" and set(body) == {"previous_generation"}:
            if type(body["previous_generation"]) is not int or body["previous_generation"] < 0:
                raise ValueError("Invalid connection boundary")
        else:
            raise ValueError("Unknown recording event")
    return cast(RecordingPayload, payload)


class RecordingReplay:
    """Seek retained observations; never invent a pose across missing evidence."""

    def __init__(self, data: bytes) -> None:
        self.payload = load_recording(data)
        self._events = self.payload["events"]
        self._times = [event["monotonic_at"] for event in self._events]

    def export_bytes(self) -> bytes:
        data = _canonical({"payload": self.payload, "sha256": hashlib.sha256(_canonical(self.payload)).hexdigest()})
        load_recording(data)
        return data

    def stage_program(self, filename: str | Path, directory: str | Path) -> Path:
        """Verify exact bytes before installing a content-addressed local preview."""
        context = self.payload.get("context")
        if context is None:
            raise ValueError("Recording has no selected program binding")
        identity = context["program"]
        with Path(filename).open("rb") as stream:
            data = stream.read(MAX_ARCHIVE_BYTES + 1)
        if len(data) != identity["size_bytes"] or hashlib.sha256(data).hexdigest() != identity["sha256"]:
            raise ValueError("Selected program bytes do not match this recording")
        data.decode("utf-8", errors="strict")
        if b"\x00" in data:
            raise ValueError("Recorded preview requires a decoded text program; compressed/binary bytes preserved")
        folder = Path(directory)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / ("recorded-" + identity["sha256"] + ".nc")
        try:
            with destination.open("xb") as stream:
                stream.write(data)
        except FileExistsError:
            pass
        with destination.open("rb") as stream:
            readback = stream.read(MAX_ARCHIVE_BYTES + 1)
        if readback != data:
            raise ValueError("Cached recorded program differs; existing file preserved")
        return destination

    def machine_point(self, event_index: int) -> tuple[float, float, float] | None:
        """Exact retained XYZ only; never borrow unit flags from another packet."""
        if type(event_index) is not int or not 0 <= event_index < len(self._events):
            return None
        event = self._events[event_index]
        if event["kind"] != "status":
            return None
        fields = event["data"]["fields"]
        position, flags = fields.get("MPos", []), fields.get("C", [])
        if len(position) < 3 or len(flags) < 3 or flags[2] not in (0, 1):
            return None
        # This C1 marker cannot represent rotary workholding.
        if len(position) > 3 and abs(position[3]) > 1e-6:
            return None
        factor = 25.4 if flags[2] == 1 else 1
        return position[0] * factor, position[1] * factor, position[2] * factor

    def at(self, monotonic_at: float) -> ReplayAssociation:
        _finite(monotonic_at)
        if not self._events or monotonic_at < self._times[0] or monotonic_at > self._times[-1]:
            return {"sample": None, "reason": "Outside the retained recording", "age_seconds": None}
        index = bisect_right(self._times, monotonic_at) - 1
        following = self._events[index + 1] if index + 1 < len(self._events) else None
        if (
            following
            and following["kind"] in ("gap", "connection_boundary", "source_gap")
            and monotonic_at > self._times[index]
        ):
            return {
                "sample": None,
                "reason": "Missing telemetry or connection boundary; motion unknown",
                "age_seconds": None,
            }
        event = self._events[index]
        if event["kind"] != "status":
            return {"sample": None, "reason": "No status sample at this event", "age_seconds": None}
        return {
            "sample": copy.deepcopy(event),
            "reason": "Recorded status only; no motion interpolation or execution inference",
            "age_seconds": monotonic_at - event["monotonic_at"],
        }
