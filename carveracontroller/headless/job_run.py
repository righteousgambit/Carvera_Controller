"""Reviewed backend job lifecycle; reported setup is not physical qualification."""

from __future__ import annotations

import copy
import math
from typing import Any
from uuid import uuid4

from ..machine.desktop_control_owner import reported_state
from ..machine.setup_readiness import GROUPS, SetupEvidenceStore, fingerprint
from .client import Response
from .job_file import JobFile, context_digest
from .job_identity import original_command_window, supported_identity
from .operations import compile_operation
from .probe_settings import ACK


def require_setup(context: dict[str, Any], now_utc: float) -> None:
    if type(now_utc) not in (int, float) or not math.isfinite(now_utc):
        raise ValueError("Setup evidence needs a finite current UTC time")
    items = context.get("evidence")
    if not isinstance(items, list) or len(items) != len(GROUPS):
        raise ValueError("Review all four setup evidence groups before a machine run")
    by_key = {item.get("key"): item for item in items if isinstance(item, dict)}
    if set(by_key) != set(GROUPS):
        raise ValueError("Setup evidence groups are missing or duplicated")
    for key in GROUPS:
        item = by_key[key]
        receipt = SetupEvidenceStore.validate(item.get("receipt"))
        if (
            item.get("state") != "measured"
            or context.get("present", {}).get(key) is not True
            or receipt["machine_id"] != context.get("machine_id")
            or receipt["group"] != key
            or receipt["fingerprint"] != fingerprint(context.get("setup", {}).get(key))
            or not receipt["measured_at"] <= now_utc < receipt["expires_at"]
        ):
            raise ValueError("Setup measurements are missing, changed or expired")


class JobRun:
    def __init__(
        self,
        file: JobFile,
        context: dict[str, Any],
        identity: dict[str, Any],
        state: dict[str, Any],
        now: float,
        now_utc: float,
    ) -> None:
        if file.phase != "reviewed" or context_digest(file.launch_plan) != context_digest(
            compile_operation("job.start", {"path": file.remote_path})
        ):
            raise ValueError("Verify the controller bytes and review the exact start command first")
        if not file.matches(file.session_id, file.connection_id, context):
            raise ValueError("The reviewed file context changed")
        require_setup(context, now_utc)
        snapshot = state.get("last_machine_snapshot") or {}
        if not supported_identity(identity.get("model", {}), identity.get("version", {}), snapshot.get("status") or {}):
            raise ValueError("The actual reported model/version does not support this backend job dialect")
        if identity.get("session_id") != file.session_id or identity.get("connection_id") != file.connection_id:
            raise ValueError("Identity readback belongs to another backend connection")
        if context.get("profile", {}).get("model") != "C1":
            raise ValueError("The selected machine profile differs from the reported C1")
        self.file, self.identity = file, copy.deepcopy(identity)
        self.review_id = uuid4().hex
        self.reviewed_at = now
        self.review_reports = copy.deepcopy(
            {
                key: snapshot["status"].get(key)
                for key in (
                    "machine_position",
                    "work_position",
                    "active_wcs",
                    "linear_units",
                    "reported_units",
                    "absolute_mode",
                    "rotation_degrees",
                    "tool",
                    "tool_offset_reported",
                    "feed_override_percent",
                    "spindle_override_percent",
                )
            }
        )
        self.approved_at: float | None = None
        self.phase = "review"
        self.saw_playing = False
        self.receipts: list[dict[str, Any]] = []
        self.last_observation: dict[str, Any] | None = None
        self._require_connection(state)
        self._require_idle(state)

    def _require_connection(self, state: dict[str, Any]) -> None:
        snapshot = state.get("last_machine_snapshot") or {}
        if (
            state.get("ready") is not True
            or state.get("running") is not True
            or snapshot.get("connection_id") != self.file.connection_id
            or snapshot.get("connected") is not True
            or snapshot.get("unknown_outcome") is not False
            or snapshot.get("transfer_active") is not False
            or reported_state(state) is None
        ):
            raise ValueError("The retained job needs its current unambiguous backend connection and fresh status")

    def _require_idle(self, state: dict[str, Any]) -> None:
        status = state["last_machine_snapshot"].get("status") or {}
        if (
            reported_state(state) != "Idle"
            or status.get("is_playing") is not False
            or type(status.get("spindle_rpm")) not in (int, float)
            or status["spindle_rpm"] != 0
            or type(status.get("spindle_target_rpm")) not in (int, float)
            or status["spindle_target_rpm"] != 0
            or status.get("linear_units") != "mm"
            or type(status.get("active_wcs")) not in (int, float)
            or status.get("active_wcs") not in range(9)
        ):
            raise ValueError("Run review requires fresh Idle, no playing job, zero spindle and known coordinates")
        for frame in ("machine_position", "work_position"):
            values = status.get(frame) or {}
            if any(
                type(values.get(axis)) not in (int, float) or not math.isfinite(values[axis])
                for axis in ("x", "y", "z")
            ):
                raise ValueError("Run review requires complete reported XYZ coordinates")

    def authorize(
        self, operation: str, session: str, state: dict[str, Any], context: dict[str, Any], now: float, now_utc: float
    ) -> dict[str, Any]:
        self._require_connection(state)
        status = state["last_machine_snapshot"].get("status") or {}
        if session != self.file.session_id:
            raise ValueError("The job belongs to another private child")
        if operation in ("job.start", "job.resume"):
            if not self.file.matches(session, self.file.connection_id, context):
                raise ValueError("Program, profile or setup changed after run review")
            require_setup(context, now_utc)
            if not supported_identity(self.identity["model"], self.identity["version"], status):
                raise ValueError("Reported machine identity changed")
        if operation == "job.start":
            if self.phase != "review" or not 0 <= now - self.reviewed_at <= 30:
                raise ValueError("Run review is expired or already submitted; review again")
            self._require_idle(state)
            if {key: status.get(key) for key in self.review_reports} != self.review_reports:
                raise ValueError("Reported position, coordinates, tooling or overrides changed after review")
            self.approved_at = now
        elif operation == "job.pause":
            if (
                self.phase not in ("playing_reported", "resume_acknowledged")
                or reported_state(state) != "Run"
                or status.get("is_playing") is not True
            ):
                raise ValueError("Pause requires this retained job to be reported playing")
        elif operation == "job.resume":
            if (
                self.phase != "paused_reported"
                or reported_state(state) != "Pause"
                or status.get("is_playing") is not True
            ):
                raise ValueError("Resume requires this retained suspended job and unchanged review context")
        elif operation == "job.cancel":
            if (
                self.phase in ("review", "settled_reported", "unresolved")
                or self.phase.endswith("_pending")
                or reported_state(state) not in ("Run", "Pause", "Hold", "Wait", "Tool")
                or status.get("is_playing") is not True
            ):
                raise ValueError("Cancel requires the retained job to be reported active")
        else:
            raise ValueError("Unknown job lifecycle action")
        self.pending_previous_phase = self.phase
        self.phase = operation.removeprefix("job.") + "_pending"
        return {
            "operation": operation,
            "parameters": {"path": self.file.remote_path} if operation == "job.start" else {},
        }

    def accept(self, operation: str, response: Response) -> None:
        if self.phase != operation.removeprefix("job.") + "_pending":
            raise ValueError("Unexpected or repeated job response")
        params = {"path": self.file.remote_path} if operation == "job.start" else {}
        expected = compile_operation(operation, params)
        result = response.envelope.get("result")
        receipt = {
            "operation": operation,
            "request_id": response.envelope.get("id"),
            "request_sha256": response.request_sha256,
            "response_sha256": response.response_sha256,
            "response": copy.deepcopy(response.envelope),
            "outcome": "unverified_response",
        }
        self.receipts.append(receipt)
        self.phase = "unresolved"
        if (
            not isinstance(result, dict)
            or response.envelope.get("ok") is not True
            or result.get("outcome") != "controller_acknowledged"
            or result.get("motion_completed") is not False
            or context_digest(result.get("plan")) != context_digest(expected)
        ):
            receipt["error"] = response.envelope.get("error")
            raise ValueError("The backend job response is refused, unresolved or differs from the approved plan")
        commands = result.get("command_receipts")
        if (
            not isinstance(commands, list)
            or len(commands) != 1
            or not isinstance(commands[0], dict)
            or commands[0].get("command") != expected["commands"][0]
            or commands[0].get("connection_id") != self.file.connection_id
            or commands[0].get("outcome") != "controller_acknowledged"
            or commands[0].get("motion_completed") is not False
        ):
            raise ValueError("The job command acknowledgment does not match its connection or command")
        command = expected["commands"][0]
        if commands[0].get("wire_commands") != [command, "M105"]:
            raise ValueError("The original wire commands differ from the reviewed operation")
        text, _window = original_command_window(commands[0], command, self.file.connection_id)
        lines = [line.removesuffix("\r") for line in text.split("\n")[:-1]]
        if (
            sum(bool(ACK.fullmatch(line)) for line in lines) != 1
            or any(any(ord(char) < 32 or ord(char) > 126 for char in line) for line in lines)
            or any(line.lower().startswith(("error", "alarm")) for line in lines)
        ):
            raise ValueError("The original acknowledgment is incomplete, duplicated or conflicting")
        receipt["outcome"] = "controller_acknowledged_motion_unconfirmed"
        receipt["command_receipt"] = commands[0]
        self.phase = operation.removeprefix("job.") + "_acknowledged"

    def observe(self, state: dict[str, Any]) -> None:
        if (
            self.phase == "review"
            or self.phase.endswith("_pending")
            or self.phase in ("unresolved", "settled_reported")
        ):
            return
        try:
            self._require_connection(state)
        except ValueError:
            return
        status = state["last_machine_snapshot"].get("status") or {}
        mode = reported_state(state)
        # A still-fresh cached report from before this command must not erase
        # its acknowledgment or pretend the requested transition was observed.
        if self.phase == "pause_acknowledged" and mode != "Pause":
            return
        if self.phase == "resume_acknowledged" and mode != "Run":
            return
        if self.phase == "cancel_acknowledged" and status.get("is_playing") is True:
            return
        self.last_observation = copy.deepcopy(state["last_machine_snapshot"])
        if status.get("is_playing") is True:
            self.saw_playing = True
            if reported_state(state) == "Run":
                self.phase = "playing_reported"
            elif reported_state(state) == "Pause":
                self.phase = "paused_reported"
        elif self.saw_playing and status.get("is_playing") is False:
            try:
                self._require_idle(state)
            except ValueError:
                return
            self.phase = "settled_reported"

    def record(self) -> dict[str, Any]:
        return {
            "schema_version": "carvera.job_run.v1",
            "review_id": self.review_id,
            "file_sha256": self.file.sha256,
            "context_sha256": self.file.context_sha256,
            "backend_session_id": self.file.session_id,
            "connection_id": self.file.connection_id,
            "reported_identity": self.identity,
            "review_reports": self.review_reports,
            "reviewed_at_s": self.reviewed_at,
            "operator_approved_at_s": self.approved_at,
            "phase": self.phase,
            "saw_playing": self.saw_playing,
            "last_observation": self.last_observation,
            "receipts": self.receipts,
            "physical_setup_verified": False,
            "motion_completed": False,
        }
