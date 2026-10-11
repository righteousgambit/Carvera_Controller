"""Durable raw measurement sessions and explicit inspected-result corrections.

Host context is a snapshot, not physical custody proof. Raw console values are
preserved; unknown acquisition/configuration fields stay None. No motion or
firmware configuration commands are emitted by this module.
"""

from __future__ import annotations

import copy
import json
import math
import os
import re
import time
import uuid
from collections import deque
from pathlib import Path

from .probe_lobing import FeatureType, LobingSample, build_lobing_map

MAX_LINE = 4096
MAX_SESSION_LINES = 4096
MAX_STORE_BYTES = 32 * 1024 * 1024
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


def finite(value, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or (positive and value <= 0):
        raise ValueError("Expected a finite " + ("positive " if positive else "") + "number")
    return float(value)


def parse_latched_contact(raw):
    match = _PRH.search(raw)
    if not match:
        return None
    values = [finite(float(value)) for value in match.group(1).split(",")]
    if len(values) != 15 or values[0] != 1:
        raise ValueError("Unsupported latched-contact record")
    unsigned = (0, 1, 2, 3, 4, 5, 6, 10, 11, 13, 14)
    if any(values[index] < 0 or values[index] != int(values[index]) for index in unsigned):
        raise ValueError("Invalid latched-contact identity/masks")
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


def context_snapshot(context):
    result = dict.fromkeys(CONTEXT_FIELDS)
    result.update(copy.deepcopy(context or {}))
    return result


class ProbeEvidenceStore:
    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/measurement-evidence.jsonl")
        self._lines = deque(maxlen=MAX_SESSION_LINES)
        self._context = None
        self._session_id = None
        self._command = None
        self._started = None
        self._dropped = 0
        self.error = None

    def events(self):
        if not self.path.exists():
            return []
        if self.path.stat().st_size > MAX_STORE_BYTES:
            raise ValueError("Measurement evidence exceeds bounded read size; original preserved")
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if not isinstance(event, dict) or event.get("schema") != 1 or not event.get("id"):
                raise ValueError("Invalid measurement evidence; original preserved")
            events.append(event)
        return events

    def append(self, kind, **fields):
        event = dict(fields, schema=1, kind=kind, id=str(uuid.uuid4()), at=time.time())
        payload = (json.dumps(event, allow_nan=False) + "\n").encode()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.close(fd)
            self.events()  # Reject corruption rather than appending over it.
            if (self.path.stat().st_size if self.path.exists() else 0) + len(payload) > MAX_STORE_BYTES:
                raise ValueError("Measurement evidence full; receipt not saved")
            fd = os.open(self.path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "ab") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self.error = None
            return copy.deepcopy(event)
        finally:
            lock.unlink(missing_ok=True)

    def begin(self, context=None, command=None):
        if self._session_id and self._lines:
            self.capture("incomplete", {"reason": "superseded by submitted measurement command"}, context)
        self._lines.clear()
        self._dropped = 0
        self._context = context_snapshot(context)
        self._command = command
        self._session_id, self._started = str(uuid.uuid4()), time.time()
        return self._session_id

    def command(self, command, context=None):
        if _COMMAND.search(command):
            return self.begin(context, command)
        return None

    def feed(self, line):
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

    def complete_raw(self, line, context=None):
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

    def capture(self, result_kind, result, context=None):
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
        )
        self._lines.clear()
        self._context = self._session_id = self._command = self._started = None
        self._dropped = 0
        return event

    def save_map(self, descriptor):
        context = context_snapshot(descriptor.get("context"))
        for key in MATCH_FIELDS + ("reference_id", "source_session_id"):
            if context.get(key) is None or context[key] == "":
                raise ValueError("Map requires " + key)
        finite(context["orientation_deg"])
        finite(context["approach_feed_mm_min"], True)
        finite(context.get("configured_tip_diameter_mm"), True)
        if finite(descriptor.get("reference_uncertainty_mm")) < 0:
            raise ValueError("Reference uncertainty must be nonnegative")
        samples = [
            LobingSample(finite(s["angle_degrees"]), finite(s["measured_diameter"], True))
            for s in descriptor["samples"]
        ]
        if len({s.angle_degrees % 360 for s in samples}) < 3:
            raise ValueError("Map requires three distinct measured directions")
        result = build_lobing_map(
            finite(descriptor["known_diameter"], True), samples, FeatureType(descriptor.get("feature", "bore"))
        )
        if any(tip <= 0 for tip in result.tip_diameters):
            raise ValueError("Raw calibration must imply a positive effective tip diameter")
        return self.append(
            "lobing_map",
            context=context,
            descriptor=descriptor,
            effective_tip_diameter=result.effective_tip_diameter,
            amplitude=result.lobing_amplitude,
        )

    def qualify_map(self, map_id, validation):
        mapping = self._event(map_id, "lobing_map")
        context = context_snapshot(validation.get("context"))
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
        if len({finite(s["angle_degrees"]) % 360 for s in samples}) < 3:
            raise ValueError("Three distinct held-out directions required")
        lobing = self._map(mapping)
        residuals, baseline = [], []
        for sample in samples:
            measured = finite(sample["measured_diameter"], True)
            implied = known - measured if lobing.feature is FeatureType.BORE else measured - known
            predicted = lobing.effective_tip_diameter + lobing.correction_at(finite(sample["angle_degrees"]))
            residuals.append(implied - predicted)
            baseline.append(implied - lobing.effective_tip_diameter)
        passed = max(abs(v) for v in residuals) + uncertainty <= limit and sum(v * v for v in residuals) <= sum(
            v * v for v in baseline
        )
        return self.append(
            "lobing_qualification",
            map_id=map_id,
            context=context,
            validation=validation,
            residuals_mm=residuals,
            passed=passed,
            evidence_class="operator-supplied held-out reference observations",
        )

    def apply_correction(self, measurement_id, map_id, angle_degrees, context):
        measurement = self._event(measurement_id, "measurement")
        mapping = self._event(map_id, "lobing_map")
        qualifications = [e for e in self.events() if e["kind"] == "lobing_qualification" and e["map_id"] == map_id]
        if not qualifications or not qualifications[-1]["passed"]:
            raise ValueError("Latest held-out qualification must pass")
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
        if measurement["context"].get("approach_direction") != angle:
            raise ValueError("Recorded actual approach direction must match correction angle")
        adjustment = lobing.effective_tip_diameter + lobing.correction_at(angle) - tip
        if lobing.feature is FeatureType.BOSS:
            adjustment = -adjustment
        dimension = context.get("inspected_dimension")
        if dimension not in ("x_diameter", "y_diameter"):
            raise ValueError("Select the inspected diameter axis explicitly")
        value = measurement["result"].get(dimension)
        corrected = {} if value is None else {dimension: finite(value) + adjustment}
        if not corrected:
            raise ValueError("No reported diameter to correct")
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

    def _event(self, identity, kind):
        event = next((e for e in self.events() if e["id"] == identity and e["kind"] == kind), None)
        if not event:
            raise ValueError("Unknown " + kind + " identity")
        return event

    @staticmethod
    def _map(event):
        d = event["descriptor"]
        return build_lobing_map(
            d["known_diameter"], [LobingSample(**s) for s in d["samples"]], FeatureType(d.get("feature", "bore"))
        )


def setter_trends(events):
    """Compare only declared identical assembly/revision/seating/settings groups."""
    groups = {}
    for event in events:
        if event.get("kind") != "measurement" or event.get("result_kind") != "setter":
            continue
        c = event["context"]
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
        groups.setdefault(key, []).append(event)
    trends = []
    for key, samples in groups.items():
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
