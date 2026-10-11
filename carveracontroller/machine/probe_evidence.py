"""Durable raw measurement sessions and explicit inspected-result corrections.

Host context is a snapshot, not physical custody proof. Raw console values are
preserved; unknown acquisition/configuration fields stay None. No motion or
firmware configuration commands are emitted by this module.
"""

from __future__ import annotations

import copy
import math
import os
import re
import threading
import time
import uuid
from collections import deque
from collections.abc import Iterable, Mapping
from functools import wraps
from os import PathLike
from pathlib import Path
from typing import Any, Callable, TypeVar, cast

from .evidence_io import append_jsonl, iter_jsonl, iter_jsonl_fd, write_json_atomic
from .probe_lobing import FeatureType, LobingMap, LobingSample, build_lobing_map

# Extensible JSON receipts deliberately retain unknown source/context fields.
# Numeric and correction-critical values are narrowed by runtime validators.
JsonObject = dict[str, Any]

MAX_LINE = 4096
MAX_SESSION_LINES = 4096
MAX_STORE_BYTES = 32 * 1024 * 1024
MAX_RECORD_BYTES = 20 * 1024 * 1024
MAX_RECORDS = 50000
CONTEXT_FIELDS = (
    "probe_identity",
    "seat_revision",
    "configuration_id",
    "orientation_deg",
    "approach_feed_mm_min",
    "approach_direction",
    "reference_uncertainty_mm",
    "reference_id",
    "phase",
    "assembly_id",
    "assembly_revision_id",
    "assignment_id",
    "wcs",
    "work_offsets",
    "spindle_temperature",
    "program_sha256",
    "run_id",
    "configured_tip_diameter_mm",
    "source_session_id",
)
MATCH_FIELDS = ("probe_identity", "seat_revision", "configuration_id", "orientation_deg", "approach_feed_mm_min")
_COMMAND = re.compile(r"\b(?:M46[0-6](?!\d)|M491(?!\d)|G38\.[2-5])", re.I)
_PRH = re.compile(r"\{PRH:([^}]+)\}")
_HIT = re.compile(r"\[PRB:([^\]]+)\]|(?:#(15[0-9])\s*=\s*(-?\d+(?:\.\d+)?))", re.I)

_Result = TypeVar("_Result")


def _synchronized(method: Callable[..., _Result]) -> Callable[..., _Result]:
    @wraps(method)
    def locked(self: ProbeEvidenceStore, *args: Any, **kwargs: Any) -> _Result:
        with self._lock:
            return method(self, *args, **kwargs)

    return locked


def _validate_event(event: JsonObject) -> None:
    if type(event.get("schema")) is not int or event["schema"] != 1:
        raise ValueError("Invalid measurement evidence schema; original preserved")
    if not all(isinstance(event.get(key), str) and event[key].strip() for key in ("id", "kind")):
        raise ValueError("Invalid measurement evidence identity; original preserved")
    finite(event.get("at"))
    kind = event["kind"]
    if kind == "measurement":
        _required_text(event, "session_id", "result_kind")
        for key in ("result", "context", "end_context"):
            _required_object(event, key)
        if event.get("started_at") is not None:
            finite(event["started_at"])
        if event.get("command") is not None and not isinstance(event["command"], str):
            raise ValueError("Invalid measurement command")
        for key in ("session_contaminated", "attribution_ambiguous", "setup_changed", "raw_hits_available"):
            # Receipts before overlap instrumentation legitimately omit this.
            if key in event and type(event[key]) is not bool:
                raise ValueError("Invalid measurement boolean: " + key)
        _nonnegative_integer(event.get("dropped_lines"), "dropped_lines")
        for key in ("raw_console", "reported_hits", "reported_variables", "rejected_contacts", "superseding_commands"):
            if key in event:
                entries = _object_list(
                    event[key], key, MAX_SESSION_LINES if key == "raw_console" else MAX_SESSION_LINES * 16
                )
                if key == "raw_console":
                    for entry in entries:
                        _validate_raw_line(entry)
        result = event["result"]
        for key in ("x_diameter", "y_diameter", "max_delta"):
            if result.get(key) is not None:
                finite(result[key])
        if "measurements" in result:
            _finite_list(result["measurements"], "measurements", MAX_SESSION_LINES)
        if "reported_variables" in result:
            values = _required_object(result, "reported_variables")
            for value in values.values():
                finite(value)
    elif kind == "lobing_map":
        context = _required_object(event, "context")
        _validate_map_context(context, source=True)
        finite(context.get("configured_tip_diameter_mm"), True)
        descriptor = _required_object(event, "descriptor")
        if context != context_snapshot(_required_object(descriptor, "context")):
            raise ValueError("Map context does not match fitting declaration")
        lobing = _descriptor_map(descriptor)
        effective = finite(event.get("effective_tip_diameter"), True)
        amplitude = finite(event.get("amplitude"))
        if effective != lobing.effective_tip_diameter or amplitude != lobing.lobing_amplitude:
            raise ValueError("Map summary does not match recorded observations")
    elif kind == "lobing_qualification":
        _required_text(event, "map_id")
        _validate_map_context(_required_object(event, "context"), source=True)
        validation = _required_object(event, "validation")
        if event["context"] != context_snapshot(_required_object(validation, "context")):
            raise ValueError("Qualification context does not match validation declaration")
        _descriptor_map(validation, require_positive_tips=False)
        finite(validation.get("max_residual_mm"), True)
        if type(event.get("passed")) is not bool:
            raise ValueError("Qualification passed must be an exact boolean")
        residuals = _finite_list(event.get("residuals_mm"), "residuals_mm", 4096)
        if len(residuals) != len(validation["samples"]):
            raise ValueError("Qualification residual count mismatch")
        if finite(event.get("reference_guard_mm")) < 0:
            raise ValueError("Qualification uncertainty guard must be nonnegative")
    elif kind == "inspected_correction":
        _required_text(event, "measurement_id", "map_id", "qualification_id")
        _required_object(event, "context")
        finite(event.get("correction_mm"))
        corrected = _required_object(event, "corrected")
        if len(corrected) != 1 or not set(corrected) <= {"x_diameter", "y_diameter"}:
            raise ValueError("Invalid corrected dimension")
        finite(next(iter(corrected.values())), True)
        if event.get("raw_result_preserved") is not True:
            raise ValueError("Correction must preserve raw result")
    elif kind == "latched_contact":
        raw = _required_object(event, "raw_console")
        _validate_raw_line(raw)
        source = _required_object(event, "source")
        try:
            parsed = parse_latched_contact(raw["text"])
        except ValueError:
            if source.get("valid") is not False or not isinstance(source.get("reason"), str):
                raise ValueError("Invalid rejected contact receipt") from None
        else:
            if parsed is None or source != parsed:
                raise ValueError("Contact source does not match raw frame")
    elif kind == "attribution_boundary":
        _required_text(event, "reason")
        if (
            event.get("machine_idle") is not True
            or type(event.get("pending_commands")) is not int
            or event["pending_commands"] != 0
        ):
            raise ValueError("Invalid attribution boundary declaration")
        if type(event.get("prior_ambiguity")) is not bool:
            raise ValueError("Invalid attribution boundary ambiguity")
        _object_list(event.get("superseding_commands"), "superseding_commands", 32)


def _required_text(data: JsonObject, *keys: str) -> None:
    for key in keys:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError("Missing receipt identity: " + key)


def _required_object(data: JsonObject, key: str) -> JsonObject:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ValueError("Expected receipt object: " + key)
    return value


def _nonnegative_integer(value: object, name: str) -> None:
    if type(value) is not int or value < 0:
        raise ValueError("Expected nonnegative receipt count: " + name)


def _object_list(value: object, name: str, maximum: int) -> list[JsonObject]:
    if not isinstance(value, list) or len(value) > maximum or any(not isinstance(v, dict) for v in value):
        raise ValueError("Invalid bounded receipt list: " + name)
    return cast(list[JsonObject], value)


def _finite_list(value: object, name: str, maximum: int) -> list[float]:
    if not isinstance(value, list) or not value or len(value) > maximum:
        raise ValueError("Invalid bounded numeric list: " + name)
    return [finite(v) for v in value]


def _validate_raw_line(entry: JsonObject) -> None:
    if not isinstance(entry.get("text"), str) or len(entry["text"]) > MAX_LINE:
        raise ValueError("Invalid raw console receipt")
    finite(entry.get("arrival_at"))
    if type(entry.get("truncated")) is not bool:
        raise ValueError("Invalid console truncation flag")


def _validate_map_context(context: JsonObject, *, source: bool) -> None:
    for key in MATCH_FIELDS + (("reference_id", "source_session_id") if source else ()):
        if context.get(key) is None or context[key] == "":
            raise ValueError("Map requires " + key)
    for key in ("probe_identity", "configuration_id") + (("reference_id", "source_session_id") if source else ()):
        _required_text(context, key)
    if type(context["seat_revision"]) not in (str, int, float):
        raise ValueError("Invalid seating revision")
    if type(context["seat_revision"]) in (int, float):
        finite(context["seat_revision"])
    finite(context["orientation_deg"])
    finite(context["approach_feed_mm_min"], True)


def _descriptor_map(descriptor: JsonObject, *, require_positive_tips: bool = True) -> LobingMap:
    known = finite(descriptor.get("known_diameter"), True)
    if finite(descriptor.get("reference_uncertainty_mm")) < 0:
        raise ValueError("Reference uncertainty must be nonnegative")
    samples = _object_list(descriptor.get("samples"), "samples", 4096)
    if len(samples) < 3:
        raise ValueError("Map requires three distinct measured directions")
    result = build_lobing_map(
        known,
        [LobingSample(finite(s.get("angle_degrees")), finite(s.get("measured_diameter"), True)) for s in samples],
        FeatureType(descriptor.get("feature", "bore")),
    )
    if require_positive_tips and any(not math.isfinite(tip) or tip <= 0 for tip in result.tip_diameters):
        raise ValueError("Raw calibration must imply a positive effective tip diameter")
    return result


def finite(value: object, positive: bool = False) -> float:
    if type(value) not in (int, float):
        raise ValueError("Expected a finite " + ("positive " if positive else "") + "number")
    try:
        result = float(cast(float, value))
    except OverflowError:
        raise ValueError("Expected a finite number") from None
    if not math.isfinite(result) or positive and result <= 0:
        raise ValueError("Expected a finite " + ("positive " if positive else "") + "number")
    return result


def parse_latched_contact(raw: str) -> JsonObject | None:
    match = _PRH.fullmatch(raw.strip())
    if not match:
        if "{PRH:" in raw:
            raise ValueError("Malformed latched-contact frame")
        return None
    values = [finite(float(value)) for value in match.group(1).split(",")]
    if len(values) != 15 or values[0] != 1:
        raise ValueError("Unsupported latched-contact record")
    unsigned = (0, 1, 2, 3, 4, 5, 6, 10, 11, 13, 14)
    if any(values[index] < 0 or values[index] != int(values[index]) for index in unsigned):
        raise ValueError("Invalid latched-contact identity/masks")
    if any(values[index] > 2**32 - 1 for index in unsigned):
        raise ValueError("Latched-contact identity exceeds firmware range")
    if values[2] == 1 and values[1] == 0:
        raise ValueError("Valid latched-contact boot identity cannot be zero")
    if values[12] < 0:
        raise ValueError("Latched-contact feed must be nonnegative")
    if values[2] not in (0, 1) or values[6] not in (1, 2) or values[13] > 3 or values[10] > 7 or values[11] > 7:
        raise ValueError("Invalid latched-contact context")
    valid = int(values[13])
    return {
        "schema": 1,
        "boot_id": int(values[1]) if values[2] else None,
        "boot_id_valid": bool(values[2]),
        "hit_sequence": int(values[3]),
        "tick_us": int(values[4]),
        "tick_wraps": int(values[5]),
        "contact_type": "probe" if values[6] == 1 else "setter",
        "machine_position": values[7:10] if valid & 1 else None,
        "negative_direction_mask": int(values[10]),
        "moving_axes_mask": int(values[11]),
        "planner_nominal_feed_mm_min": values[12] if valid & 2 else None,
        "context_valid_mask": valid,
        "dropped_hits_total": int(values[14]),
        "position_basis": "issued-step position latched at qualified contact; not encoder readback",
        "clock_basis": "firmware monotonic tick within boot; not wall time",
    }


def context_snapshot(context: Mapping[str, Any] | None) -> JsonObject:
    if context is not None and not isinstance(context, Mapping):
        raise ValueError("Measurement context must be an object")
    result: JsonObject = dict.fromkeys(CONTEXT_FIELDS)
    result.update(copy.deepcopy(context or {}))
    return result


class ProbeEvidenceStore:
    def __init__(self, path: str | PathLike[str] | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/measurement-evidence.jsonl")
        self._lines: deque[JsonObject] = deque(maxlen=MAX_SESSION_LINES)
        self._context: JsonObject | None = None
        self._session_id: str | None = None
        self._command: str | None = None
        self._started: float | None = None
        self._dropped = 0
        self.error: str | None = None
        self._lock = threading.RLock()
        self._validated_identity: tuple[int, ...] | None = None
        self._validated_records = 0
        self.last_receipt: JsonObject | None = None
        self._superseding_commands: deque[JsonObject] = deque(maxlen=32)
        self._session_contaminated = False
        self._attribution_ambiguous = False
        self._attribution_restored = False

    def _restore_attribution(self) -> None:
        if self._attribution_restored:
            return
        # A restart cannot silently qualify receipts after an unresolved
        # overlap. Restore only host declaration history; no machine inference.
        for event in self.events():
            if event["kind"] == "attribution_boundary":
                self._attribution_ambiguous = False
                self._superseding_commands.clear()
            elif event["kind"] == "measurement" and (
                event.get("session_contaminated") is True or event.get("attribution_ambiguous") is True
            ):
                self._attribution_ambiguous = True
                self._superseding_commands = deque(event.get("superseding_commands", []), maxlen=32)
        self._session_contaminated = self._attribution_ambiguous
        self._attribution_restored = True

    @_synchronized
    def events(self) -> list[JsonObject]:
        if not self.path.exists():
            return []
        events = list(
            iter_jsonl(self.path, max_bytes=MAX_STORE_BYTES, max_line_bytes=MAX_RECORD_BYTES, max_records=MAX_RECORDS)
        )
        for event in events:
            _validate_event(event)
        return events

    def _validate_existing(self, fd: int) -> None:
        info = os.fstat(fd)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity != self._validated_identity:
            count = 0
            for event in iter_jsonl_fd(
                fd, max_bytes=MAX_STORE_BYTES, max_line_bytes=MAX_RECORD_BYTES, max_records=MAX_RECORDS
            ):
                _validate_event(event)
                count += 1
            self._validated_identity = identity
            self._validated_records = count
        if self._validated_records >= MAX_RECORDS:
            raise ValueError("Measurement evidence record limit reached; receipt not saved")

    @_synchronized
    def append(self, kind: str, **fields: Any) -> JsonObject:
        event = dict(fields, schema=1, kind=kind, id=str(uuid.uuid4()), at=time.time())
        _validate_event(event)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            receipt = append_jsonl(
                self.path,
                event,
                max_bytes=MAX_STORE_BYTES,
                max_line_bytes=MAX_RECORD_BYTES,
                validate_existing=self._validate_existing,
            )
            self._validated_identity = tuple(receipt["file_identity"])
            self._validated_records += 1
            self.last_receipt = receipt
            self.error = None
            return copy.deepcopy(event)
        except (OSError, ValueError) as exc:
            self._validated_identity = None
            self.error = str(exc)
            raise

    @_synchronized
    def begin(self, context: Mapping[str, Any] | None = None, command: str | None = None) -> str:
        next_session = str(uuid.uuid4())
        try:
            self._restore_attribution()
        except (OSError, ValueError):
            # Submission already occurred. Journal corruption cannot erase the
            # host's knowledge of that attempted command or make its hits clean.
            self._attribution_ambiguous = self._session_contaminated = True
            if self._session_id is None:
                self._session_id, self._started = next_session, time.time()
                self._context, self._command = context_snapshot(context), command
            raise
        if self._session_id:
            self._attribution_ambiguous = self._session_contaminated = True
            self._superseding_commands.append(
                {
                    "prior_session_id": self._session_id,
                    "submitted_session_id": next_session,
                    "command": command,
                    "context": context_snapshot(context),
                    "arrival_at": time.time(),
                    "basis": "overlapping host submissions; completion attribution unknown",
                }
            )
            try:
                self.capture("incomplete", {"reason": "superseded by submitted measurement command"}, context)
            except (OSError, ValueError):
                # The command callback runs after transmission. If the old
                # receipt cannot close, later hits cannot be attributed solely
                # to that earlier command or used for correction.
                raise
        self._lines.clear()
        self._dropped = 0
        self._context = context_snapshot(context)
        self._command = command
        self._session_id, self._started = next_session, time.time()
        self._session_contaminated = self._attribution_ambiguous
        return self._session_id

    @_synchronized
    def attribution_status(self) -> JsonObject:
        """Return declaration state without exposing mutable session buffers."""
        self._restore_attribution()
        return {
            "active_session": self._session_id is not None,
            "session_contaminated": self._session_contaminated,
            "attribution_ambiguous": self._attribution_ambiguous,
            "superseding_commands": len(self._superseding_commands),
        }

    @_synchronized
    def confirm_completed_boundary(self, reason: str, *, machine_idle: bool, pending_commands: int) -> JsonObject:
        """Persist an explicit operator boundary; untagged END/hits cannot prove it."""
        self._restore_attribution()
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("An operator boundary explanation is required")
        if machine_idle is not True or type(pending_commands) is not int or pending_commands != 0:
            raise ValueError("Boundary requires fresh idle and declared no pending commands")
        if self._session_id:
            raise ValueError("Capture the active session as incomplete before declaring a boundary")
        event = self.append(
            "attribution_boundary",
            reason=reason,
            machine_idle=machine_idle,
            pending_commands=pending_commands,
            prior_ambiguity=self._attribution_ambiguous,
            superseding_commands=list(self._superseding_commands),
            evidence_class="explicit operator declaration; not firmware command identity or stream-drain proof",
        )
        self._attribution_ambiguous = self._session_contaminated = False
        self._superseding_commands.clear()
        return event

    @_synchronized
    def command(self, command: str, context: Mapping[str, Any] | None = None) -> str | None:
        if _COMMAND.search(command):
            return self.begin(context, command)
        return None

    @_synchronized
    def feed(self, line: str) -> None:
        if len(self._lines) == MAX_SESSION_LINES:
            self._dropped += 1
        entry = {"text": line[:MAX_LINE], "arrival_at": time.time(), "truncated": len(line) > MAX_LINE}
        self._lines.append(entry)
        if _PRH.search(line):
            try:
                source = parse_latched_contact(line)
            except ValueError as exc:
                source = {"valid": False, "reason": str(exc)}
            # A contact can arrive after the textual result; preserve it even
            # without a recognised cycle terminator or host session linkage.
            self.append(
                "latched_contact",
                session_id=self._session_id,
                raw_console=entry,
                source=source,
                context=self._context,
                session_linkage="submitted host session" if self._session_id else "unassigned",
            )

    @_synchronized
    def complete_raw(self, line: str, context: Mapping[str, Any] | None = None) -> JsonObject | None:
        """Close variable-only CMM, G38 contact and single-shot setter receipts."""
        if "CMMProbe END" in line:
            values = {}
            for raw in self._lines:
                for match in _HIT.finditer(raw["text"]):
                    if match.group(2):
                        values[match.group(2)] = float(match.group(3))
            if values:
                return self.capture("probe_variables", {"reported_variables": values}, context)
        if self._command and "G38." in self._command.upper() and "[PRB:" in line:
            return self.capture("probe_contact", {"raw_contact": line}, context)
        if self._command and "M491" in self._command.upper() and line.startswith("[TLO:"):
            return self.capture("setter_single", {"raw_tlo": line}, context)
        return None

    @_synchronized
    def capture(self, result_kind: str, result: JsonObject, context: Mapping[str, Any] | None = None) -> JsonObject:
        self._restore_attribution()
        end_context = context_snapshot(context)
        raw = list(self._lines)
        hits = []
        variables = []
        rejected_contacts = []
        for i, raw_line in enumerate(raw):
            if _PRH.search(raw_line["text"]):
                try:
                    contact = parse_latched_contact(raw_line["text"])
                    hits.append({"line_index": i, "raw": raw_line["text"], "source": contact, "acquisition_at": None})
                except ValueError as exc:
                    rejected_contacts.append({"line_index": i, "reason": str(exc)})
            for match in _HIT.finditer(raw_line["text"]):
                observation = {"line_index": i, "raw": match.group(0), "acquisition_at": None}
                if match.group(1):
                    hits.append(observation)
                else:
                    variables.append(observation)
        event = self.append(
            "measurement",
            session_id=self._session_id or str(uuid.uuid4()),
            started_at=self._started,
            command=self._command,
            result_kind=result_kind,
            result=result,
            context=self._context or end_context,
            end_context=end_context,
            raw_console=raw,
            reported_hits=hits,
            reported_variables=variables,
            rejected_contacts=rejected_contacts,
            raw_hits_available=bool(hits),
            dropped_lines=self._dropped,
            acquisition_time_basis="unknown; host arrival retained",
            attribution="operator declaration where present; not physical readback",
            session_contaminated=self._session_contaminated,
            attribution_ambiguous=self._attribution_ambiguous,
            superseding_commands=list(self._superseding_commands),
            setup_changed=any(
                self._context
                and self._context.get(key) is not None
                and end_context.get(key) is not None
                and self._context[key] != end_context[key]
                for key in (*MATCH_FIELDS, "configured_tip_diameter_mm", "inspected_dimension", "approach_direction")
            ),
        )
        self._lines.clear()
        self._context = self._session_id = self._command = self._started = None
        self._dropped = 0
        self._session_contaminated = self._attribution_ambiguous
        if not self._attribution_ambiguous:
            self._superseding_commands.clear()
        return event

    @_synchronized
    def shutdown_pending(self) -> JsonObject | None:
        """Retain an interrupted submitted cycle, including failed-append forensics."""
        if not self._session_id:
            return None
        try:
            return self.capture("incomplete", {"reason": "controller shutdown"})
        except (OSError, ValueError):
            path = Path(str(self.path) + f".pending-exit-{time.time_ns()}.json")
            receipt = write_json_atomic(
                path,
                {
                    "schema": 1,
                    "kind": "pending_measurement",
                    "id": str(uuid.uuid4()),
                    "at": time.time(),
                    "session_id": self._session_id,
                    "command": self._command,
                    "context": self._context,
                    "raw_console": list(self._lines),
                    "dropped_lines": self._dropped,
                    "session_contaminated": self._session_contaminated,
                    "superseding_commands": list(self._superseding_commands),
                    "basis": "interrupted/failed journal session; not a completed qualified measurement",
                },
                max_bytes=32 * 1024 * 1024,
            )
            return {"pending_preserved": str(path), "receipt": receipt}

    @_synchronized
    def save_map(self, descriptor: JsonObject) -> JsonObject:
        context = context_snapshot(descriptor.get("context"))
        _validate_map_context(context, source=True)
        finite(context.get("configured_tip_diameter_mm"), True)
        result = _descriptor_map(descriptor)
        return self.append(
            "lobing_map",
            context=context,
            descriptor=descriptor,
            effective_tip_diameter=result.effective_tip_diameter,
            amplitude=result.lobing_amplitude,
            source_linkage=self._source_linkage(context),
        )

    @_synchronized
    def qualify_map(self, map_id: str, validation: JsonObject) -> JsonObject:
        mapping = self._event(map_id, "lobing_map")
        context, residuals, guard, passed = self._qualification_result(mapping, validation)
        return self.append(
            "lobing_qualification",
            map_id=map_id,
            context=context,
            validation=validation,
            residuals_mm=residuals,
            reference_guard_mm=guard,
            guard_basis="sum of declared fit and held-out reference uncertainty; conservative acceptance guard",
            passed=passed,
            evidence_class="operator-supplied held-out reference observations",
            source_linkage=self._source_linkage(context),
        )

    @staticmethod
    def _qualification_result(
        mapping: JsonObject, validation: JsonObject
    ) -> tuple[JsonObject, list[float], float, bool]:
        context = context_snapshot(validation.get("context"))
        _validate_map_context(context, source=True)
        _descriptor_map(validation, require_positive_tips=False)
        for key in MATCH_FIELDS:
            if context[key] != mapping["context"][key]:
                raise ValueError("Qualification context mismatch: " + key)
        if not context["reference_id"] or not context["source_session_id"]:
            raise ValueError("Independent reference and held-out session identity required")
        if context["source_session_id"] == mapping["context"]["source_session_id"]:
            raise ValueError("Qualification session must be held out from map fitting")
        if validation.get("feature", "bore") != mapping["descriptor"].get("feature", "bore"):
            raise ValueError("Validation feature geometry mismatch")
        limit = finite(validation["max_residual_mm"], True)
        uncertainty = finite(validation.get("reference_uncertainty_mm"))
        if uncertainty < 0 or uncertainty > limit:
            raise ValueError("Residual limit must accommodate declared reference uncertainty")
        known = finite(validation["known_diameter"], True)
        samples = validation["samples"]
        if len(samples) > 4096:
            raise ValueError("Held-out sample limit exceeded")
        directions = {finite(s["angle_degrees"]) % 360 for s in samples}
        if len(directions) < 3 or len(directions) != len(samples):
            raise ValueError("Three distinct held-out directions required; duplicate directions are unsupported")
        fit_uncertainty = mapping["descriptor"].get("reference_uncertainty_mm")
        if fit_uncertainty is None:
            raise ValueError("Fit reference uncertainty is required for qualification")
        guard = uncertainty + finite(fit_uncertainty)
        if guard < 0:
            raise ValueError("Reference uncertainty must be nonnegative")
        lobing = ProbeEvidenceStore._map(mapping)
        residuals, baseline = [], []
        for sample in samples:
            measured = finite(sample["measured_diameter"], True)
            implied = known - measured if lobing.feature is FeatureType.BORE else measured - known
            predicted = lobing.effective_tip_diameter + lobing.correction_at(finite(sample["angle_degrees"]))
            residuals.append(implied - predicted)
            baseline.append(implied - lobing.effective_tip_diameter)
        passed = max(abs(v) for v in residuals) + guard <= limit and sum(v * v for v in residuals) <= sum(
            v * v for v in baseline
        )
        return context, residuals, guard, passed

    @_synchronized
    def apply_correction(
        self, measurement_id: str, map_id: str, angle_degrees: float, context: JsonObject
    ) -> JsonObject:
        measurement = self._event(measurement_id, "measurement")
        if measurement.get("session_contaminated") or measurement.get("attribution_ambiguous"):
            raise ValueError("Measurement contains ambiguous overlapping command attribution")
        if measurement.get("setup_changed"):
            raise ValueError("Measurement setup changed during the session")
        mapping = self._event(map_id, "lobing_map")
        qualifications = [e for e in self.events() if e["kind"] == "lobing_qualification" and e["map_id"] == map_id]
        if not qualifications or qualifications[-1]["passed"] is not True:
            raise ValueError("Latest held-out qualification must pass")
        latest = qualifications[-1]
        verified_context, residuals, guard, passed = self._qualification_result(mapping, latest["validation"])
        if (
            not passed
            or latest["context"] != verified_context
            or latest["residuals_mm"] != residuals
            or latest["reference_guard_mm"] != guard
        ):
            raise ValueError("Recorded qualification does not match held-out observations")
        for key in MATCH_FIELDS:
            if (
                context.get(key) is None
                or context[key] != mapping["context"][key]
                or context[key] != measurement["context"].get(key)
            ):
                raise ValueError("Correction context mismatch: " + key)
        if measurement["result_kind"] != "probe" or measurement["result"].get("kind") not in ("bore", "boss"):
            raise ValueError("Only inspected bore/boss diameter results support this map")
        lobing = self._map(mapping)
        if measurement["result"]["kind"] != lobing.feature.value:
            raise ValueError("Feature geometry mismatch")
        tip = finite(measurement["context"].get("configured_tip_diameter_mm"), True)
        angle = finite(angle_degrees)
        adjustment = lobing.effective_tip_diameter + lobing.correction_at(angle) - tip
        if lobing.feature is FeatureType.BOSS:
            adjustment = -adjustment
        dimension = context.get("inspected_dimension")
        if dimension not in ("x_diameter", "y_diameter"):
            raise ValueError("Select the inspected diameter axis explicitly")
        recorded_dimension = measurement["context"].get("inspected_dimension")
        directions = measurement["context"].get("approach_directions") or {}
        actual_angle = directions.get(dimension) if isinstance(directions, dict) else None
        if actual_angle is None and (
            recorded_dimension == dimension or (recorded_dimension is None and dimension == "x_diameter")
        ):
            actual_angle = measurement["context"].get("approach_direction")
        if actual_angle is None or not math.isclose(finite(actual_angle) % 360, angle % 360, abs_tol=1e-9):
            raise ValueError("Recorded actual approach direction for the selected diameter must match correction angle")
        value = measurement["result"].get(dimension)
        corrected = {} if value is None else {dimension: finite(value) + adjustment}
        if not corrected:
            raise ValueError("No reported diameter to correct")
        if not math.isfinite(corrected[dimension]) or corrected[dimension] <= 0:
            raise ValueError("Corrected diameter must remain finite and positive")
        return self.append(
            "inspected_correction",
            measurement_id=measurement_id,
            map_id=map_id,
            qualification_id=qualifications[-1]["id"],
            context=context,
            correction_mm=adjustment,
            corrected=corrected,
            raw_result_preserved=True,
        )

    def _source_linkage(self, context: JsonObject) -> JsonObject:
        session = context.get("source_session_id")
        records = [
            event
            for event in self.events()
            if event.get("kind") == "measurement" and event.get("session_id") == session
        ]
        return {
            "session_id": session,
            "receipt_ids": [event["id"] for event in records],
            "basis": "recorded host session"
            if records
            else "operator-declared external session; raw linkage unverified",
        }

    def _event(self, identity: str, kind: str) -> JsonObject:
        event = next((e for e in self.events() if e["id"] == identity and e["kind"] == kind), None)
        if not event:
            raise ValueError("Unknown " + kind + " identity")
        return event

    @staticmethod
    def _map(event: JsonObject) -> LobingMap:
        return _descriptor_map(event["descriptor"])


def setter_trends(events: Iterable[JsonObject]) -> list[JsonObject]:
    """Compare only declared identical assembly/revision/seating/settings groups."""
    groups: dict[tuple[Any, ...], list[JsonObject]] = {}
    for event in events:
        if event.get("kind") != "measurement" or event.get("result_kind") != "setter":
            continue
        c = event.get("context")
        result = event.get("result")
        if (
            event.get("setup_changed")
            or event.get("session_contaminated")
            or not isinstance(c, dict)
            or not isinstance(result, dict)
        ):
            continue
        measurements = result.get("measurements")
        if not isinstance(measurements, (list, tuple)) or not measurements:
            continue
        try:
            for value in measurements:
                finite(value)
            finite(result.get("max_delta"))
        except ValueError:
            continue
        keys = (
            "assembly_id",
            "assembly_revision_id",
            "assignment_id",
            "seat_revision",
            "configuration_id",
            "approach_feed_mm_min",
        )
        if any(c.get(k) is None for k in keys):
            continue
        key = tuple(c[k] for k in keys)
        if any(
            type(value) not in (str, int, float) or isinstance(value, float) and not math.isfinite(value)
            for value in key
        ):
            continue
        groups.setdefault(key, []).append(event)
    trends: list[JsonObject] = []
    for key, samples in groups.items():
        # Arrival order is the durable observation order. This deliberately does
        # not infer cutting phases or physical tool wear from timestamps.
        means = [sum(e["result"]["measurements"]) / len(e["result"]["measurements"]) for e in samples]
        trends.append(
            {
                "identity": key,
                "count": len(samples),
                "mean_change_mm": means[-1] - means[0] if len(samples) > 1 else None,
                "reported_spreads_mm": [e["result"]["max_delta"] for e in samples],
                "temperatures": [e["context"].get("spindle_temperature") for e in samples],
                "phases": [e["context"].get("phase") for e in samples],
                "interpretation": "Repeatability/change evidence; wear, debris, seating and thermal causes not distinguished",
            }
        )
    return trends
