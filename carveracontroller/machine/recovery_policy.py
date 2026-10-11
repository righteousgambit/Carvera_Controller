"""Evidence required before executing an approach into a partially cut job.

Preview remains available. Operator verification is scoped to exact program,
line, boot and coordinate/tool state; it is not physical position telemetry.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any


def recovery_scope(program_hash: str | None, start_line: int, context: dict[str, Any]) -> str:
    keys = (
        "firmware_boot_id",
        "wcs",
        "tool",
        "tlo",
        "work_offset",
        "machine_filename",
        "machine_position",
        "work_position",
        "rotation",
        "modes",
        "assembly_id",
        "assembly_revision_id",
        "seat_revision",
        "assignment_id",
        "connection_generation",
        "connection_address",
    )
    state = {key: context.get(key) for key in keys}
    return hashlib.sha256(
        json.dumps(
            {"program_hash": program_hash, "start_line": start_line, "state": state}, sort_keys=True, allow_nan=False
        ).encode()
    ).hexdigest()


@dataclass(frozen=True)
class RecoveryVerification:
    scope: str
    position_verified: bool
    origin_verified: bool
    tool_offset_verified: bool
    clearance_verified: bool
    clearance_machine_z_mm: float
    operator_note: str
    program_verified: bool = False

    def __post_init__(self) -> None:
        checks = (
            self.position_verified,
            self.origin_verified,
            self.tool_offset_verified,
            self.clearance_verified,
            self.program_verified,
        )
        if any(type(value) is not bool for value in checks):
            raise ValueError("recovery verification fields must be explicit booleans")
        if type(self.clearance_machine_z_mm) not in (int, float) or not math.isfinite(self.clearance_machine_z_mm):
            raise ValueError("verified machine clearance Z must be finite")
        if not isinstance(self.scope, str) or not re.fullmatch(r"[0-9a-f]{64}", self.scope):
            raise ValueError("recovery requires an exact verification scope")
        if not isinstance(self.operator_note, str) or not self.operator_note.strip():
            raise ValueError("recovery requires an operator verification note")


def assess_recovery(
    program_hash: str | None,
    start_line: int,
    context: dict[str, Any],
    verification: RecoveryVerification | None = None,
) -> dict[str, Any]:
    blockers = []
    if not isinstance(program_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", program_hash):
        blockers.append("exact program hash unavailable")
    if type(start_line) is not int or start_line < 1:
        blockers.append("recovery line must be positive")

    def finite_number(value: Any) -> bool:
        return type(value) in (int, float) and math.isfinite(value)

    for key, low, high in (("wcs", 0, 8), ("tool", 1, 999999), ("firmware_boot_id", 1, 2**32 - 1)):
        value = context.get(key)
        if (
            not isinstance(value, (int, float))
            or not finite_number(value)
            or value != int(value)
            or not low <= value <= high
        ):
            blockers.append(f"valid current {key} identity required")
    for key in ("tlo", "rotation"):
        if not finite_number(context.get(key)):
            blockers.append(f"finite current {key} required")
    for key in ("machine_position", "work_position", "work_offset"):
        values = context.get(key)
        if not isinstance(values, (list, tuple)) or len(values) < 3 or any(not finite_number(v) for v in values):
            blockers.append(f"finite current {key} required")
    modes = context.get("modes")
    if (
        not isinstance(modes, (list, tuple))
        or len(modes) != 4
        or any(not finite_number(v) for v in modes)
        or modes[2] not in (0, 1)
        or modes[3] not in (0, 1)
    ):
        blockers.append("explicit live unit and distance modes required")
    filename = context.get("machine_filename")
    if not isinstance(filename, str) or not filename.strip() or any(c in filename for c in "\r\n\0"):
        blockers.append("exact machine filename required")
    if context.get("halt_reason") != 0 or type(context.get("halt_reason")) not in (int, float):
        blockers.append("known clear halt state required")
    if context.get("state") != "Idle":
        blockers.append("fresh idle state required")
    if context.get("telemetry_stale") is not False:
        blockers.append("fresh telemetry required")
    inputs = context.get("raw_inputs")
    if isinstance(inputs, dict):
        for name in ("x_motor_alarm", "y_motor_alarm", "z_motor_alarm", "spindle_alarm", "estop"):
            if inputs.get(name) is True:
                blockers.append("asserted " + name)
        if inputs.get("cover") is False:
            blockers.append("cover open")
    try:
        scope = recovery_scope(program_hash, start_line, context)
    except (TypeError, ValueError):
        scope = None
        blockers.append("invalid recovery state")
    if verification is None or verification.scope != scope:
        blockers.append("verify position, work origin, tool offset and clearance for this recovery scope")
    else:
        for key in (
            "position_verified",
            "origin_verified",
            "tool_offset_verified",
            "clearance_verified",
            "program_verified",
        ):
            if not getattr(verification, key):
                blockers.append(key.replace("_", " "))
    return {
        "allowed": not blockers,
        "scope": scope,
        "blockers": blockers,
        "start_line": start_line,
        "program_hash": program_hash,
        "clearance_machine_z_mm": verification.clearance_machine_z_mm if verification else None,
        "position_evidence": "operator verification; firmware position derives from issued steps",
    }
