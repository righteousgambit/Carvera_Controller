"""Evidence required before executing an approach into a partially cut job.

Preview remains available. Operator verification is scoped to exact program,
line, boot and coordinate/tool state; it is not physical position telemetry.
"""

import hashlib
import json
import math
from dataclasses import dataclass


def recovery_scope(program_hash, start_line, context):
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

    def __post_init__(self):
        checks = (
            self.position_verified,
            self.origin_verified,
            self.tool_offset_verified,
            self.clearance_verified,
            self.program_verified,
        )
        if any(type(value) is not bool for value in checks):
            raise ValueError("recovery verification fields must be explicit booleans")
        if not isinstance(self.clearance_machine_z_mm, (int, float)) or not math.isfinite(self.clearance_machine_z_mm):
            raise ValueError("verified machine clearance Z must be finite")
        if not isinstance(self.operator_note, str) or not self.operator_note.strip():
            raise ValueError("recovery requires an operator verification note")


def assess_recovery(program_hash, start_line, context, verification=None):
    blockers = []
    if not program_hash:
        blockers.append("exact program hash unavailable")
    if not isinstance(start_line, int) or start_line < 1:
        blockers.append("recovery line must be positive")
    for key in ("wcs", "tool", "tlo", "work_offset"):
        if context.get(key) is None:
            blockers.append(f"current {key} unavailable")
    for key in ("machine_position", "work_position"):
        values = context.get(key)
        if (
            not isinstance(values, (list, tuple))
            or len(values) < 3
            or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in values[:3])
        ):
            blockers.append(f"finite current {key} required")
    if context.get("halt_reason") not in (None, 0) or context.get("state") == "Alarm":
        blockers.append("machine still halted or alarmed")
    if context.get("state") != "Idle":
        blockers.append("fresh idle state required")
    if context.get("telemetry_stale", True):
        blockers.append("fresh telemetry required")
    if context.get("firmware_boot_id") is None:
        blockers.append("verified firmware boot identity unavailable")
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
