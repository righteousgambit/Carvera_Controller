"""Expiring fixed-pocket exchange reviews and original acknowledgment checks.

A library assignment is a declaration. Reported tool numbers neither identify
the physical cutter nor establish its length, clearance or completed motion.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, cast

from ..machine.backend_live_report import finite
from ..machine.desktop_control_owner import reported_state
from ..machine.probe_settings_workflow import canonical, fingerprint
from .client import Response
from .job_identity import original_command_window, supported_identity
from .operations import compile_operation
from .probe_settings import ACK
from .probe_settings_receipts import ipc_record
from .telemetry import parse_diagnostics, parse_status

REPORT_FIELDS = (
    "machine_model",
    "features",
    "tool",
    "tool_offset_reported",
    "machine_position",
    "work_position",
    "linear_units",
    "reported_units",
    "active_wcs",
    "rotation_degrees",
    "absolute_mode",
    "feed_override_percent",
    "spindle_override_percent",
)


def idle_report(state: dict[str, Any], connection: str) -> dict[str, Any]:
    snapshot = state.get("last_machine_snapshot") or {}
    status = snapshot.get("status") or {}
    diagnostic = snapshot.get("diagnostics") or {}
    age, cached = finite(snapshot.get("diagnostics_age_ms")), finite(state.get("last_machine_snapshot_age_s"))
    features = finite(status.get("features"))
    if (
        state.get("ready") is not True
        or state.get("running") is not True
        or snapshot.get("connected") is not True
        or snapshot.get("connection_id") != connection
        or snapshot.get("unknown_outcome") is not False
        or snapshot.get("transfer_active") is not False
        or reported_state(state) != "Idle"
        or status.get("is_playing") is not False
        or any(type(status.get(k)) not in (int, float) or status[k] != 0 for k in ("spindle_rpm", "spindle_target_rpm"))
        or diagnostic.get("spindle_enabled") is not False
        or age is None
        or cached is None
        or not math.isfinite(age + cached * 1000)
        or not 0 <= age + cached * 1000 <= 3000
        or type(status.get("tool")) not in (int, float)
        or status["tool"] not in range(7)
        or features is None
        or not features.is_integer()
        or not 0 <= features <= 255
        or not int(features) & 4
        or finite(status.get("machine_model")) != 1
        or status.get("linear_units") != "mm"
        or any(
            finite((status.get(frame) or {}).get(axis)) is None
            for frame in ("machine_position", "work_position")
            for axis in ("x", "y", "z")
        )
    ):
        raise ValueError("Exchange requires current C1 ATC status: Idle, no job, stopped spindle and known tool")
    return status


@dataclass(frozen=True)
class ToolExchangeReview:
    session_id: str
    connection_id: str
    context_sha256: str
    reports_sha256: str
    created_at: float
    target: int
    plan_json: str

    @classmethod
    def create(
        cls,
        session: str,
        connection: str,
        context: dict[str, Any],
        identity: dict[str, Any],
        state: dict[str, Any],
        now: float,
    ) -> ToolExchangeReview:
        status = idle_report(state, connection)
        target = context.get("target")
        if type(target) is not int or not 1 <= target <= 6:
            raise ValueError("Choose one declared fixed rack pocket T1–T6")
        if status["tool"] == target:
            raise ValueError("That tool is already reported in the spindle; no exchange is needed")
        if (
            (identity.get("session_id"), identity.get("connection_id")) != (session, connection)
            or not supported_identity(identity.get("model", {}), identity.get("version", {}), status)
            or context.get("profile", {}).get("model") != "C1"
        ):
            raise ValueError("Read the supported C1 / Community 2.1.0c identity on this connection first")
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError("Review clock unavailable")
        return cls(
            session,
            connection,
            fingerprint(context),
            fingerprint({k: status.get(k) for k in REPORT_FIELDS}),
            now,
            target,
            canonical(compile_operation("tool.change", {"tool": target})),
        )

    @property
    def plan(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.plan_json))

    def authorize(
        self, session: str, connection: str, context: dict[str, Any], state: dict[str, Any], now: float
    ) -> dict[str, Any]:
        status = idle_report(state, connection)
        if (session, connection, fingerprint(context)) != (self.session_id, self.connection_id, self.context_sha256):
            raise ValueError("Machine, preview toolset or selected cutter changed; review again")
        if fingerprint({k: status.get(k) for k in REPORT_FIELDS}) != self.reports_sha256:
            raise ValueError("Reported position, coordinates, tool or overrides changed after review")
        if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now - self.created_at <= 30:
            raise ValueError("Tool exchange review expired; review again")
        return {"operation": "tool.change", "parameters": {"tool": self.target}}

    def accept(self, response: Response) -> dict[str, Any]:
        retained = ipc_record(response)
        result = response.envelope.get("result")
        if (
            response.envelope.get("ok") is not True
            or not isinstance(result, dict)
            or (
                result.get("outcome") != "controller_acknowledged"
                or result.get("motion_completed") is not False
                or fingerprint(result.get("plan")) != fingerprint(self.plan)
            )
        ):
            raise ValueError("Tool exchange response is refused, uncertain or differs from the reviewed plan")
        receipts = result.get("command_receipts")
        command = self.plan["commands"][0]
        if not isinstance(receipts, list) or len(receipts) != 1 or not isinstance(receipts[0], dict):
            raise ValueError("Exchange requires one original command receipt")
        receipt = receipts[0]
        if (
            receipt.get("command") != command
            or receipt.get("wire_commands") != [command]
            or receipt.get("connection_id") != self.connection_id
            or receipt.get("outcome") != "controller_acknowledged"
            or receipt.get("motion_completed") is not False
        ):
            raise ValueError("Exchange receipt differs from its command or connection")
        text, _window = original_command_window(receipt, command, self.connection_id, shell_barrier=False)
        acknowledgments = 0
        for original in text.splitlines(keepends=True):
            line = original[:-1].removesuffix("\r")
            if not original.endswith("\n") or any(ord(c) < 32 or ord(c) > 126 for c in line):
                raise ValueError("Incomplete or invalid exchange response bytes")
            if ACK.fullmatch(line):
                acknowledgments += 1
            elif (
                not line
                or line.startswith("<")
                and parse_status(line)["state"]
                or line.startswith("{")
                and parse_diagnostics(line)["raw_fields"]
            ):
                continue
            else:
                # Firmware may emit tool-change progress text. Preserve it but
                # do not use an unrecognized sentence as proof of completion.
                if line.lower().startswith(("error", "alarm")):
                    raise ValueError("Controller reported exchange failure")
        if acknowledgments != 1:
            raise ValueError("Exchange acknowledgment is missing or duplicated")
        return retained

    def target_reported(self, state: dict[str, Any], now: float, acknowledged_at: float | None) -> bool:
        if type(now) not in (int, float) or not math.isfinite(now) or finite(acknowledged_at) is None:
            return False
        assert acknowledged_at is not None
        try:
            status = idle_report(state, self.connection_id)
        except ValueError:
            return False
        snapshot = state["last_machine_snapshot"]
        age = finite(snapshot.get("status_age_ms"))
        cached = finite(state.get("last_machine_snapshot_age_s"))
        return (
            age is not None
            and cached is not None
            and math.isfinite(age + cached * 1000)
            and 0 <= age + cached * 1000 <= 3000
            and now - cached - age / 1000 > acknowledged_at
            and status["tool"] == self.target
        )
