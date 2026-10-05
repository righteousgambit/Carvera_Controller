"""Bounded, packet-based run evidence. Replay never interpolates missing motion."""

import copy
import hashlib
import json
import math
import threading
from bisect import bisect_right
from collections import deque
from uuid import uuid4

FIELDS = frozenset(("MPos", "WPos", "C", "F", "S", "T", "G", "R", "P", "A", "O", "H"))
MAX_EVENTS = 10000
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024


def _finite(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("Recording values must be finite numbers")
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


class RunRecording:
    """No disk I/O or commands on capture; snapshots own their mutable values.

    P is retained as a raw controller report. Its line counter is not promoted
    to executed progress without backend-specific execution evidence. Packet
    coordinates retain the wire units and C flags rather than mixing reports.
    """

    def __init__(self, capacity=MAX_EVENTS, gap_seconds=2.0):
        if type(capacity) is not int or not 2 <= capacity <= MAX_EVENTS:
            raise ValueError("Recording capacity must be between 2 and 10000")
        if _finite(gap_seconds) <= 0:
            raise ValueError("Recording gap must be positive")
        self.capacity = capacity
        self.gap_seconds = gap_seconds
        self.session_id = str(uuid4())
        self._events = deque(maxlen=capacity)
        self._lock = threading.RLock()
        self._sequence = 0
        self._last_time = None
        self._generation = None

    def capture_status(self, state, fields, monotonic_at, utc_at, generation):
        _finite(monotonic_at)
        _finite(utc_at)
        if monotonic_at < 0 or utc_at < 0 or type(generation) is not int or generation < 0:
            raise ValueError("Invalid recording clock or connection generation")
        if not isinstance(state, str) or not state or len(state) > 80:
            raise ValueError("Invalid reported state")
        packet = {}
        for key in FIELDS & fields.keys():
            values = fields[key]
            if not isinstance(values, (list, tuple)) or len(values) > 32:
                raise ValueError("Invalid status field")
            packet[key] = [_finite(value) for value in values]
        with self._lock:
            if self._last_time is not None and monotonic_at < self._last_time:
                raise ValueError("Recording monotonic clock moved backwards")
            base = {"monotonic_at": monotonic_at, "utc_at": utc_at, "generation": generation}
            if self._generation is not None and generation != self._generation:
                self._append(dict(base, kind="connection_boundary", data={"previous_generation": self._generation}))
            elif self._last_time is not None and monotonic_at - self._last_time > self.gap_seconds:
                self._append(dict(base, kind="gap", data={"duration_seconds": monotonic_at - self._last_time}))
            self._append(dict(base, kind="status", data={"state": state, "fields": packet}))
            self._last_time, self._generation = monotonic_at, generation

    def _append(self, event):
        self._sequence += 1
        self._events.append(dict(event, sequence=self._sequence))

    def snapshot(self):
        with self._lock:
            return {
                "schema": 1,
                "session_id": self.session_id,
                "capacity": self.capacity,
                "dropped_events": self._sequence - len(self._events),
                "events": copy.deepcopy(list(self._events)),
            }

    def summary(self):
        """Constant-size UI readback; full-history copies belong on workers."""
        with self._lock:
            return {
                "retained_events": len(self._events),
                "dropped_events": self._sequence - len(self._events),
                "latest": copy.deepcopy(self._events[-1]) if self._events else None,
            }

    def export_bytes(self):
        payload = self.snapshot()
        data = _canonical({"payload": payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()})
        if len(data) > MAX_ARCHIVE_BYTES:
            raise ValueError("Run recording exceeds 16 MiB; reduce the retained interval")
        return data


def load_recording(data):
    """Validate a local archive before exposing it to replay or scene consumers."""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise ValueError("Run recording exceeds 16 MiB")

    def unique(pairs):
        value = {}
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
    if not isinstance(payload, dict) or set(payload) != {
        "schema",
        "session_id",
        "capacity",
        "dropped_events",
        "events",
    }:
        raise ValueError("Invalid recording payload")
    if type(payload["schema"]) is not int or payload["schema"] != 1:
        raise ValueError("Unsupported recording schema")
    if not isinstance(payload["session_id"], str) or not 1 <= len(payload["session_id"]) <= 80:
        raise ValueError("Invalid recording session")
    capacity, dropped, events = payload["capacity"], payload["dropped_events"], payload["events"]
    RunRecording(capacity)
    if type(dropped) is not int or dropped < 0 or not isinstance(events, list) or len(events) > capacity:
        raise ValueError("Invalid recording retention")
    previous_time = None
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
        if event["kind"] == "status" and set(body) == {"state", "fields"}:
            if not isinstance(body["fields"], dict) or not set(body["fields"]) <= FIELDS:
                raise ValueError("Invalid packet fields")
            RunRecording().capture_status(body["state"], body["fields"], now, event["utc_at"], generation)
        elif event["kind"] == "gap" and set(body) == {"duration_seconds"}:
            if _finite(body["duration_seconds"]) <= 0:
                raise ValueError("Invalid telemetry gap")
        elif event["kind"] == "connection_boundary" and set(body) == {"previous_generation"}:
            if type(body["previous_generation"]) is not int or body["previous_generation"] < 0:
                raise ValueError("Invalid connection boundary")
        else:
            raise ValueError("Unknown recording event")
    return payload


class RecordingReplay:
    """Seek retained observations; never invent a pose across missing evidence."""

    def __init__(self, data):
        self.payload = load_recording(data)
        self._events = self.payload["events"]
        self._times = [event["monotonic_at"] for event in self._events]

    def export_bytes(self):
        data = _canonical({"payload": self.payload, "sha256": hashlib.sha256(_canonical(self.payload)).hexdigest()})
        load_recording(data)
        return data

    def at(self, monotonic_at):
        _finite(monotonic_at)
        if not self._events or monotonic_at < self._times[0] or monotonic_at > self._times[-1]:
            return {"sample": None, "reason": "Outside the retained recording", "age_seconds": None}
        index = bisect_right(self._times, monotonic_at) - 1
        following = self._events[index + 1] if index + 1 < len(self._events) else None
        if following and following["kind"] in ("gap", "connection_boundary") and monotonic_at > self._times[index]:
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
