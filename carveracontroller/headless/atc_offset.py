"""Reported ATC M499 values, independent of raw status units and Robot compensation."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, cast

from ..machine.probe_settings_workflow import canonical, fingerprint
from .client import Response
from .job_identity import SOURCE, original_command_window, supported_identity
from .operations import compile_operation
from .probe_settings import ACK
from .probe_settings_receipts import ipc_record
from .telemetry import parse_diagnostics, parse_status
from .tool_exchange import REPORT_FIELDS, idle_report

NUMBER = r"(-?[0-9]{1,4}\.[0-9]{3})"
LINE = re.compile(r"tool:([1-6]) ref:" + NUMBER + " cur:" + NUMBER + " offset:" + NUMBER + r"\Z")


@dataclass(frozen=True)
class AtcOffsetRead:
    session_id: str
    connection_id: str
    context_sha256: str
    reports_sha256: str
    created_at: float
    target: int

    @property
    def plan(self) -> dict[str, Any]:
        return compile_operation("observe.query", {"query": "M499"})

    @classmethod
    def create(
        cls,
        session: str,
        connection: str,
        context: dict[str, Any],
        identity: dict[str, Any],
        state: dict[str, Any],
        now: float,
    ) -> AtcOffsetRead:
        status = idle_report(state, connection)
        target = context.get("target")
        if type(target) is not int or not 1 <= target <= 6 or target != status["tool"]:
            raise ValueError("Select the current reported cutter T1–T6 for ATC offset readback")
        if (
            (identity.get("session_id"), identity.get("connection_id")) != (session, connection)
            or not supported_identity(identity.get("model", {}), identity.get("version", {}), status)
            or context.get("profile", {}).get("model") != "C1"
        ):
            raise ValueError("Read this connection's supported C1 / Community 2.1.0c identity first")
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError("Offset read clock unavailable")
        return cls(
            session,
            connection,
            fingerprint(context),
            fingerprint({k: status.get(k) for k in REPORT_FIELDS}),
            now,
            target,
        )

    def authorize(
        self, session: str, connection: str, context: dict[str, Any], state: dict[str, Any], now: float
    ) -> dict[str, Any]:
        status = idle_report(state, connection)
        if (session, connection, fingerprint(context), fingerprint({k: status.get(k) for k in REPORT_FIELDS})) != (
            self.session_id,
            self.connection_id,
            self.context_sha256,
            self.reports_sha256,
        ):
            raise ValueError("Offset read owner, tooling, setup or reported state changed")
        if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now - self.created_at <= 30:
            raise ValueError("Offset read admission expired")
        return {"operation": "observe.query", "parameters": {"query": "M499"}}

    def accept(self, response: Response) -> dict[str, Any]:
        ipc = ipc_record(response)
        result = response.envelope.get("result")
        if (
            response.envelope.get("ok") is not True
            or not isinstance(result, dict)
            or result.get("outcome") != "controller_acknowledged"
            or result.get("motion_completed") is not False
            or fingerprint(result.get("plan")) != fingerprint(self.plan)
        ):
            raise ValueError("Offset response differs from its read-only query")
        receipts = result.get("command_receipts")
        if not isinstance(receipts, list) or len(receipts) != 1 or not isinstance(receipts[0], dict):
            raise ValueError("Offset read needs one original command receipt")
        receipt = receipts[0]
        if (
            receipt.get("command"),
            receipt.get("wire_commands"),
            receipt.get("connection_id"),
            receipt.get("outcome"),
            receipt.get("motion_completed"),
        ) != ("M499", ["M499"], self.connection_id, "controller_acknowledged", False):
            raise ValueError("Offset command or connection differs")
        text, window = original_command_window(receipt, "M499", self.connection_id, shell_barrier=False)
        found, acknowledgments = [], 0
        for original in text.splitlines(keepends=True):
            line = original[:-1].removesuffix("\r")
            if not original.endswith("\n") or any(ord(c) < 32 or ord(c) > 126 for c in line):
                raise ValueError("Partial or control-byte offset report")
            match = LINE.fullmatch(line)
            if match:
                found.append(match.groups())
            elif ACK.fullmatch(line):
                acknowledgments += 1
            elif (
                not line
                or line.startswith("<")
                and parse_status(line).get("state")
                or line.startswith("{")
                and parse_diagnostics(line).get("raw_fields")
            ):
                continue
            else:
                raise ValueError("Unrecognized or conflicting offset output")
        if len(found) != 1 or acknowledgments != 1 or int(found[0][0]) != self.target:
            raise ValueError("Missing, duplicate, unacknowledged or different-tool offset report")
        reference, current, offset = (float(v) for v in found[0][1:])
        if any(abs(v) > 1000 for v in (reference, current, offset)):
            raise ValueError("ATC offset values exceed this source contract's bounds")
        return {
            "tool": self.target,
            "reference_mz_mm": reference,
            "current_mz_mm": current,
            "atc_offset_mm": offset,
            "reported_resolution_mm": 0.001,
            "reference": "ATCHandler tool_offset and reference_tool_mz; not nominal stickout or full Robot compensation",
            "source_grammar_revision": SOURCE,
            "firmware_authenticated": False,
            "physical_accuracy_verified": False,
            "applied_robot_offset_verified": False,
            "command_attribution_verified": False,
            "ipc": ipc,
            "command_window_sha256": window["sha256"],
        }


@dataclass(frozen=True)
class AtcOffsetObservation:
    session_id: str
    connection_id: str
    profile_sha256: str
    received_at_s: float
    receipt_json: str

    @classmethod
    def retained(cls, ticket: AtcOffsetRead, response: Response, profile: dict[str, Any]) -> AtcOffsetObservation:
        value = ticket.accept(response)
        if (
            response.received_at_s is None
            or type(response.received_at_s) not in (int, float)
            or not math.isfinite(response.received_at_s)
            or response.received_at_s < 0
        ):
            raise ValueError("Offset receipt clock unavailable")
        return cls(
            ticket.session_id, ticket.connection_id, fingerprint(profile), response.received_at_s, canonical(value)
        )

    @property
    def receipt(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.receipt_json))

    def fresh(self, now: float) -> bool:
        return (
            type(now) in (int, float) and math.isfinite(now) and self.received_at_s <= now <= self.received_at_s + 0.8
        )

    def fresh_for(
        self, owner: tuple[str | None, str | None], profile: dict[str, Any], tool: int | None, now: float
    ) -> bool:
        return (
            owner == (self.session_id, self.connection_id)
            and fingerprint(profile) == self.profile_sha256
            and type(tool) is int
            and tool == self.receipt["tool"]
            and self.fresh(now)
        )
