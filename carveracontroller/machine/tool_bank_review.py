"""Revision-bound tool-bank preparation. Declarations never authorize execution."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
import time
import uuid
from pathlib import Path

from carveracontroller.machine.assembly_preview import design_fingerprint
from carveracontroller.machine.observed_pose import ObservedPose

MAX_BYTES = 4 * 1024 * 1024


def mapped_offset_status(row, pose, now, tolerance_mm=0.001):
    """Compare current-spindle reported TLO with a mapped calibration receipt.

    This validates only the numeric report for the currently observed tool, not
    physical assembly identity, magazine mapping or a qualified cutting offset.
    The displayed comparison tolerance is not a part tolerance.
    """
    if type(tolerance_mm) not in (int, float) or not math.isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("TLO comparison tolerance must be finite and positive")
    controller_tool = row["controller_tool"]
    receipts = row["controller_applicable"]
    result = {
        "state": "unknown",
        "expected_mm": None,
        "reported_mm": None,
        "difference_mm": None,
        "tolerance_mm": tolerance_mm,
    }
    if not receipts:
        return dict(result, detail=f"T{controller_tool} TLO: no post-placement controller receipt")
    expected = receipts[-1]["report"]["applied"]
    result["expected_mm"] = expected
    if not isinstance(pose, ObservedPose) or not pose.fresh(now):
        return dict(result, detail=f"T{controller_tool} TLO: awaiting fresh status")
    if pose.tool != controller_tool or pose.tool_length_mm is None:
        return dict(result, detail=f"T{controller_tool} TLO: not present in current-spindle status")
    difference = pose.tool_length_mm - expected
    result.update(reported_mm=pose.tool_length_mm, difference_mm=difference)
    matches = abs(difference) <= tolerance_mm
    return dict(
        result,
        state="matched" if matches else "mismatch",
        detail=(
            f"T{controller_tool} TLO: {pose.tool_length_mm:g} mm reported / {expected:g} mm receipt · "
            f"{'within' if matches else 'outside'} {tolerance_mm:g} mm comparison"
        ),
    )


def bank_key(program_hash, machine_id, bank_index):
    return hashlib.sha256(json.dumps([program_hash, machine_id, bank_index]).encode()).hexdigest()


def _text(value, name, limit=256):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {name}")
    return value


def _digest(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Invalid program or design fingerprint")


def validate_record(record):
    if not isinstance(record, dict):
        raise ValueError("Invalid bank preparation")
    _digest(record.get("program_hash"))
    _text(record.get("machine_id"), "machine profile ID")
    _text(record.get("revision"), "review revision")
    for field in ("bank_index", "start_line", "end_line"):
        if type(record.get(field)) is not int or record[field] < 1:
            raise ValueError(f"Invalid {field}")
    if record["start_line"] > record["end_line"]:
        raise ValueError("Invalid bank source range")
    if (
        type(record.get("updated_at")) not in (int, float)
        or not math.isfinite(record["updated_at"])
        or record["updated_at"] <= 0
    ):
        raise ValueError("Invalid review timestamp")
    note = record.get("note", "")
    if not isinstance(note, str) or len(note) > 2048 or any(ord(c) < 32 and c not in "\n\t" for c in note):
        raise ValueError("Invalid preparation note")
    bindings = record.get("bindings")
    if not isinstance(bindings, list) or len(bindings) > 6:
        raise ValueError("A bank preparation has at most six pockets")
    pockets, assemblies = set(), set()
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("Invalid pocket binding")
        for field, low, high in (("pocket", 1, 6), ("tool", 0, 9999)):
            if type(binding.get(field)) is not int or not low <= binding[field] <= high:
                raise ValueError(f"Invalid {field}")
        for field in ("assembly_id", "revision_id"):
            _text(binding.get(field), field)
        _digest(binding.get("design_fingerprint"))
        if binding["pocket"] in pockets or binding["assembly_id"] in assemblies:
            raise ValueError("Each pocket needs its own physical assembly")
        pockets.add(binding["pocket"])
        assemblies.add(binding["assembly_id"])
    expected = bank_key(record["program_hash"], record["machine_id"], record["bank_index"])
    if record.get("id") != expected:
        raise ValueError("Bank preparation identity does not match its context")
    return copy.deepcopy(record)


def capture_bank(program, bank, machine_id, choices, custody, profiles, note=""):
    """Bind each choice to its current definition, without declaring a physical move."""
    bindings = []
    designs = {p["id"]: p for p in profiles}
    for pocket, tool in bank.slots:
        identity = choices.get(pocket)
        if not identity:
            continue
        assembly = custody.assembly(identity)
        if assembly is None or assembly["profile_id"] not in designs:
            raise ValueError(f"Pocket {pocket}: assembly or linked cutter design is missing")
        bindings.append(
            {
                "pocket": pocket,
                "tool": tool,
                "assembly_id": identity,
                "revision_id": assembly["revision_id"],
                "design_fingerprint": design_fingerprint(designs[assembly["profile_id"]]),
            }
        )
    return validate_record(
        {
            "id": bank_key(program.file_hash, machine_id, bank.index),
            "revision": str(uuid.uuid4()),
            "program_hash": program.file_hash,
            "machine_id": machine_id,
            "bank_index": bank.index,
            "start_line": bank.start_line,
            "end_line": bank.end_line,
            "updated_at": time.time(),
            "bindings": bindings,
            "note": note,
        }
    )


def inspect_bank(program, bank, record, custody, profiles, endpoint="", *, machine_id=None):
    """Return independent identity, placement and raw-receipt observations per pocket."""
    if record:
        record = validate_record(record)
    if record and (
        record["program_hash"] != program.file_hash
        or (machine_id is not None and record["machine_id"] != machine_id)
        or record["bank_index"] != bank.index
        or (record["start_line"], record["end_line"]) != (bank.start_line, bank.end_line)
        or any((b["pocket"], b["tool"]) not in bank.slots for b in record["bindings"])
    ):
        raise ValueError("Saved preparation belongs to a different program or bank plan")
    bindings = {b["pocket"]: b for b in record["bindings"]} if record else {}
    designs = {p["id"]: p for p in profiles}
    events = custody.events
    links = {e["report_id"]: e for e in events if e["kind"] == "link"}
    placements = custody.locations()
    rows = []
    for pocket, tool in bank.slots:
        binding = bindings.get(pocket)
        assembly = custody.assembly(binding["assembly_id"]) if binding else None
        issues = []
        profile = designs.get(assembly["profile_id"]) if assembly else None
        definition_current = bool(
            assembly
            and profile
            and assembly["revision_id"] == binding["revision_id"]
            and design_fingerprint(profile) == binding["design_fingerprint"]
        )
        if assembly is None:
            issues.append("Choose a physical assembly")
        elif profile is None:
            issues.append("Linked cutter design is missing")
        elif (
            assembly["revision_id"] != binding["revision_id"]
            or design_fingerprint(profile) != binding["design_fingerprint"]
        ):
            issues.append("Assembly or cutter design changed; review and save again")
        placement = placements.get((record["machine_id"], pocket)) if record else None
        if (
            not assembly
            or not placement
            or placement["assembly_id"] != assembly["id"]
            or placement.get("revision_id") != assembly["revision_id"]
        ):
            issues.append("Pocket declaration does not match selected assembly revision")
        reports = []
        if assembly:
            reports = [
                e
                for e in events
                if e["kind"] == "report"
                and e["id"] in links
                and links[e["id"]]["assembly_id"] == assembly["id"]
                and links[e["id"]].get("revision_id") == assembly["revision_id"]
            ]
        applicable = [
            e
            for e in reports
            if definition_current and endpoint and e["endpoint"] == endpoint and e["tool_number"] == tool
        ]
        if not applicable:
            issues.append("No current-definition receipt from this endpoint at the program tool number")
        # A second bank's logical T7 may be controller T1. Keep these receipt
        # identities separate; an old calibration before the latest declared
        # placement cannot establish the reloaded controller tool's calibration.
        placement_matches = bool(
            definition_current
            and placement
            and placement["assembly_id"] == assembly["id"]
            and placement.get("revision_id") == assembly["revision_id"]
        )
        controller_applicable = [
            e
            for e in reports
            if placement_matches
            and endpoint
            and e["endpoint"] == endpoint
            and e["tool_number"] == pocket
            and e["at"] >= placement["at"]
            and e["report"]["timestamp"] >= placement["at"]
            and e["report"].get("applied") is not None
        ]
        rows.append(
            {
                "pocket": pocket,
                "tool": tool,
                "assembly": assembly,
                "profile": profile,
                "reports": reports,
                "applicable": applicable,
                "controller_tool": pocket,
                "controller_applicable": controller_applicable,
                "placement_at": placement["at"] if placement_matches else None,
                "issues": issues,
            }
        )
    return rows


class BankReviewStore:
    """Atomic local preparations with stale-writer rejection; invalid originals stay intact."""

    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/tool-bank-reviews.json")
        self.error = None
        try:
            self.records = self._read()
        except (OSError, ValueError) as exc:
            self.records, self.error = {}, str(exc)

    def _read(self):
        if not self.path.exists():
            return {}
        if self.path.stat().st_size > MAX_BYTES:
            raise ValueError("Bank preparations exceed the size limit; original preserved")
        data = json.loads(self.path.read_text())
        if (
            not isinstance(data, dict)
            or type(data.get("schema")) is not int
            or data["schema"] != 1
            or not isinstance(data.get("reviews"), list)
            or len(data["reviews"]) > 500
        ):
            raise ValueError("Invalid bank preparation store; original preserved")
        records = [validate_record(r) for r in data["reviews"]]
        if len({r["id"] for r in records}) != len(records):
            raise ValueError("Duplicate bank preparation identities")
        return {r["id"]: r for r in records}

    def get(self, program_hash, machine_id, bank_index):
        return copy.deepcopy(self.records.get(bank_key(program_hash, machine_id, bank_index)))

    def reload(self):
        try:
            self.records, self.error = self._read(), None
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    def save(self, record, expected_revision=None):
        record = validate_record(record)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        temporary = None
        try:
            current = self._read()
            self.records = current
            previous = current.get(record["id"])
            if (previous["revision"] if previous else None) != expected_revision:
                raise ValueError("Preparation changed elsewhere; reload before saving")
            current = dict(current, **{record["id"]: record})
            payload = json.dumps({"schema": 1, "reviews": list(current.values())}, indent=2, allow_nan=False)
            if len(current) > 500 or len(payload.encode()) > MAX_BYTES:
                raise ValueError("Bank preparation store limit reached")
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=".bank-review-")
            with os.fdopen(fd, "w") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            temporary = None
            self.records, self.error = current, None
        finally:
            if temporary:
                Path(temporary).unlink(missing_ok=True)
            lock.unlink(missing_ok=True)
