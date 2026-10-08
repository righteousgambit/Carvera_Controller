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
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TypedDict

from carveracontroller.machine.assembly_preview import design_fingerprint
from carveracontroller.machine.desktop_profiles import ProfileRecord
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.program_operations import ProgramOperations, ToolBank
from carveracontroller.machine.tool_custody import CustodyEvent, ToolCustodyStore

MAX_BYTES = 4 * 1024 * 1024


class PocketBinding(TypedDict):
    pocket: int
    tool: int
    assembly_id: str
    revision_id: str
    design_fingerprint: str


class BankRecord(TypedDict):
    id: str
    revision: str
    program_hash: str
    machine_id: str
    bank_index: int
    start_line: int
    end_line: int
    updated_at: float
    bindings: list[PocketBinding]
    note: str


class OffsetStatus(TypedDict):
    state: str
    expected_mm: float | None
    reported_mm: float | None
    difference_mm: float | None
    tolerance_mm: float
    detail: str


class BankRowBase(TypedDict):
    pocket: int
    tool: int
    assembly: CustodyEvent | None
    profile: ProfileRecord | None
    reports: list[CustodyEvent]
    applicable: list[CustodyEvent]
    controller_tool: int
    controller_applicable: list[CustodyEvent]
    placement_at: float | None
    issues: list[str]


class BankRow(BankRowBase, total=False):
    offset_status: OffsetStatus


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid {name}")
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError(f"Invalid {name}") from exc
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"Invalid {name}")
    return result


def mapped_offset_status(
    row: BankRow,
    pose: object,
    now: float,
    tolerance_mm: float = 0.001,
) -> OffsetStatus:
    """Compare a current-spindle report with a post-placement mapped receipt.

    Numeric agreement does not identify the physical assembly or certify cutting.
    """
    tolerance = _number(tolerance_mm, "TLO comparison tolerance", positive=True)
    controller_tool = row["controller_tool"]
    receipts = row["controller_applicable"]
    result: OffsetStatus = {
        "state": "unknown",
        "expected_mm": None,
        "reported_mm": None,
        "difference_mm": None,
        "tolerance_mm": tolerance,
        "detail": f"T{controller_tool} TLO: no post-placement controller receipt",
    }
    if not receipts:
        return result
    try:
        expected = _number(receipts[-1]["report"].get("applied"), "receipt TLO")
        clock = _number(now, "comparison clock")
    except ValueError:
        result["detail"] = f"T{controller_tool} TLO: invalid receipt or comparison clock"
        return result
    result["expected_mm"] = expected
    if not isinstance(pose, ObservedPose) or not pose.fresh(clock):
        result["detail"] = f"T{controller_tool} TLO: awaiting fresh status"
        return result
    if pose.tool != controller_tool or pose.tool_length_mm is None:
        result["detail"] = f"T{controller_tool} TLO: not present in current-spindle status"
        return result
    difference = pose.tool_length_mm - expected
    if not math.isfinite(difference):
        result["detail"] = f"T{controller_tool} TLO: comparison arithmetic is not finite"
        return result
    result["reported_mm"] = pose.tool_length_mm
    result["difference_mm"] = difference
    matches = abs(difference) <= tolerance
    result["state"] = "matched" if matches else "mismatch"
    result["detail"] = (
        f"T{controller_tool} TLO: {pose.tool_length_mm:g} mm reported / {expected:g} mm receipt · "
        f"{'within' if matches else 'outside'} {tolerance:g} mm comparison"
    )
    return result


def _text(value: object, name: str, limit: int = 256) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {name}")
    return value


def _digest(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Invalid program or design fingerprint")
    return value


def _integer(value: object, field: str, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ValueError(f"Invalid {field}")
    return value


def bank_key(program_hash: str, machine_id: str, bank_index: int) -> str:
    _digest(program_hash)
    _text(machine_id, "machine profile ID")
    _integer(bank_index, "bank_index", 1, 999999)
    return hashlib.sha256(json.dumps([program_hash, machine_id, bank_index]).encode()).hexdigest()


def validate_record(record: object) -> BankRecord:
    if not isinstance(record, dict):
        raise ValueError("Invalid bank preparation")
    program_hash = _digest(record.get("program_hash"))
    machine_id = _text(record.get("machine_id"), "machine profile ID")
    revision = _text(record.get("revision"), "review revision")
    bank_index = _integer(record.get("bank_index"), "bank_index", 1, 999999)
    start = _integer(record.get("start_line"), "start_line", 1, 1000000000)
    end = _integer(record.get("end_line"), "end_line", start, 1000000000)
    updated_at = _number(record.get("updated_at"), "review timestamp", positive=True)
    note = record.get("note", "")
    if not isinstance(note, str) or len(note) > 2048 or any(ord(c) < 32 and c not in "\n\t" for c in note):
        raise ValueError("Invalid preparation note")
    bindings = record.get("bindings")
    if not isinstance(bindings, list) or len(bindings) > 6:
        raise ValueError("A bank preparation has at most six pockets")
    pockets: set[int] = set()
    assemblies: set[str] = set()
    tools: set[int] = set()
    validated: list[PocketBinding] = []
    for binding in bindings:
        if not isinstance(binding, dict):
            raise ValueError("Invalid pocket binding")
        pocket = _integer(binding.get("pocket"), "pocket", 1, 6)
        tool = _integer(binding.get("tool"), "tool", 0, 9999)
        assembly_id = _text(binding.get("assembly_id"), "assembly_id")
        revision_id = _text(binding.get("revision_id"), "revision_id")
        fingerprint = _digest(binding.get("design_fingerprint"))
        if pocket in pockets or assembly_id in assemblies:
            raise ValueError("Each pocket needs its own physical assembly")
        if tool in tools:
            raise ValueError("Each program tool needs one pocket per bank")
        pockets.add(pocket)
        assemblies.add(assembly_id)
        tools.add(tool)
        validated.append(
            {
                "pocket": pocket,
                "tool": tool,
                "assembly_id": assembly_id,
                "revision_id": revision_id,
                "design_fingerprint": fingerprint,
            }
        )
    expected = bank_key(program_hash, machine_id, bank_index)
    if record.get("id") != expected:
        raise ValueError("Bank preparation identity does not match its context")
    return {
        "id": expected,
        "revision": revision,
        "program_hash": program_hash,
        "machine_id": machine_id,
        "bank_index": bank_index,
        "start_line": start,
        "end_line": end,
        "updated_at": updated_at,
        "bindings": validated,
        "note": note,
    }


def capture_bank(
    program: ProgramOperations,
    bank: ToolBank,
    machine_id: str,
    choices: Mapping[int, str],
    custody: ToolCustodyStore,
    profiles: Sequence[ProfileRecord],
    note: str = "",
) -> BankRecord:
    """Bind each choice to its current definition, without declaring a physical move."""
    bindings = []
    designs = {p["id"]: p for p in profiles}
    retired = {e["assembly_id"] for e in custody.events if e["kind"] == "replacement"}
    for pocket, tool in bank.slots:
        identity = choices.get(pocket)
        if not identity:
            continue
        if identity in retired:
            raise ValueError(f"Pocket {pocket}: assembly is declared replaced; choose the replacement identity")
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


def inspect_bank(
    program: ProgramOperations,
    bank: ToolBank,
    record: BankRecord | None,
    custody: ToolCustodyStore,
    profiles: Sequence[ProfileRecord],
    endpoint: str = "",
    *,
    machine_id: str | None = None,
) -> list[BankRow]:
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
    retired = {e["assembly_id"] for e in events if e["kind"] == "replacement"}
    rows: list[BankRow] = []
    for pocket, tool in bank.slots:
        binding = bindings.get(pocket)
        assembly = custody.assembly(binding["assembly_id"]) if binding else None
        issues = []
        profile = designs.get(assembly["profile_id"]) if assembly else None
        if assembly and assembly["id"] in retired:
            issues.append("Physical assembly is declared replaced; reconcile this bank with its replacement identity")
        definition_current = bool(
            binding
            and assembly
            and profile
            and assembly["id"] not in retired
            and assembly["revision_id"] == binding["revision_id"]
            and design_fingerprint(profile) == binding["design_fingerprint"]
        )
        if assembly is None:
            issues.append("Choose a physical assembly")
        elif profile is None:
            issues.append("Linked cutter design is missing")
        elif binding and (
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
            and assembly
            and placement
            and placement["assembly_id"] == assembly["id"]
            and placement.get("revision_id") == assembly["revision_id"]
        )
        controller_applicable = [
            e
            for e in reports
            if placement_matches
            and placement is not None
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
                "placement_at": placement["at"] if placement_matches and placement is not None else None,
                "issues": issues,
            }
        )
    return rows


class BankReviewStore:
    """Atomic local preparations with stale-writer rejection; invalid originals stay intact."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/tool-bank-reviews.json")
        self.error: str | None = None
        try:
            self.records = self._read()
        except (OSError, ValueError) as exc:
            self.records, self.error = {}, str(exc)

    def _read(self) -> dict[str, BankRecord]:
        if not self.path.exists():
            return {}
        with self.path.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("Bank preparations exceed the size limit; original preserved")
        data = json.loads(raw)
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

    def get(self, program_hash: str, machine_id: str, bank_index: int) -> BankRecord | None:
        return copy.deepcopy(self.records.get(bank_key(program_hash, machine_id, bank_index)))

    def reload(self) -> None:
        try:
            self.records, self.error = self._read(), None
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    def save(self, record: BankRecord, expected_revision: str | None = None) -> None:
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
            current = {**current, record["id"]: record}
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
