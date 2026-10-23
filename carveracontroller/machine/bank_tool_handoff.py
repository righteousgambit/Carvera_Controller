"""Frozen bank intent for a fixed-rack review; never physical tool identification."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, cast

from .assembly_preview import assembly_definition, design_fingerprint
from .desktop_profiles import ProfileRecord
from .program_operations import ProgramOperations, ToolBank
from .tool_bank_review import BankRecord, validate_record
from .tool_custody import ToolCustodyStore


@dataclass(frozen=True)
class BankToolHandoff:
    """Canonical immutable identity; returned dictionaries are detached copies."""

    serialized: str

    def context(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.serialized))


def capture_handoff(
    program: ProgramOperations,
    bank: ToolBank,
    machine: Mapping[str, Any],
    record: BankRecord | None,
    saved: BankRecord | None,
    choices: Mapping[int, str],
    custody: ToolCustodyStore,
    profiles: Sequence[ProfileRecord],
    pocket: int,
) -> BankToolHandoff:
    """Resolve a saved logical-tool/physical-pocket declaration without changing either."""
    if record is None or saved is None or validate_record(record) != validate_record(saved):
        raise ValueError("Save the current bank preparation before opening its exchange review")
    if (
        record["program_hash"] != program.file_hash
        or record["machine_id"] != machine.get("id")
        or record["bank_index"] != bank.index
        or (record["start_line"], record["end_line"]) != (bank.start_line, bank.end_line)
    ):
        raise ValueError("Saved preparation belongs to a different program, machine or bank")
    if type(pocket) is not int or not 1 <= pocket <= 6:
        raise ValueError("Choose a fixed rack pocket T1–T6")
    binding = next((b for b in record["bindings"] if b["pocket"] == pocket), None)
    if binding is None or (pocket, binding["tool"]) not in bank.slots or choices.get(pocket) != binding["assembly_id"]:
        raise ValueError("Save the selected pocket's assembly before reviewing its exchange")
    if any(e["kind"] == "replacement" and e["assembly_id"] == binding["assembly_id"] for e in custody.events):
        raise ValueError("The selected assembly was replaced; review and save this bank again")
    assembly = custody.assembly(binding["assembly_id"])
    profile = next((p for p in profiles if assembly and p["id"] == assembly["profile_id"]), None)
    if (
        assembly is None
        or profile is None
        or assembly["revision_id"] != binding["revision_id"]
        or design_fingerprint(profile) != binding["design_fingerprint"]
    ):
        raise ValueError("Assembly or cutter design changed; review and save this bank again")
    definition = assembly_definition(assembly, profile, pocket)
    tool = asdict(definition)
    tool["tool_type"] = definition.tool_type.value
    context = {
        "program_hash": program.file_hash,
        "machine_profile": copy.deepcopy(dict(machine)),
        "bank_index": bank.index,
        "source_range": [bank.start_line, bank.end_line],
        "preparation_id": record["id"],
        "preparation_revision": record["revision"],
        "logical_tool": binding["tool"],
        "controller_tool": pocket,
        "assembly_id": assembly["id"],
        "assembly_revision": assembly["revision_id"],
        "design_fingerprint": binding["design_fingerprint"],
        "assembly": copy.deepcopy(assembly),
        "declared_tool_mm": tool,
    }
    return BankToolHandoff(json.dumps(context, sort_keys=True, allow_nan=False))


def handoff_label(context: Mapping[str, Any]) -> str:
    return (
        f"Bank {context['bank_index']} · Program T{context['logical_tool']} · "
        f"Controller T{context['controller_tool']}\n{context['assembly']['name']}"
    )
