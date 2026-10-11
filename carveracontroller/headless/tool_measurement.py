"""Expiring M491 reviews and qualified-versus-normalized calibration output.

Pinned Community output prints its highest sample as 'Using', but the setter
saves its lowest sample. The printed Using value is never an applied-TLO receipt.
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, cast

from ..machine.backend_live_report import finite
from ..machine.probe_settings_workflow import canonical, fingerprint, strict_json
from ..machine.tool_history import TloReport
from .client import Response
from .job_identity import SOURCE, original_command_window, supported_identity
from .operations import compile_operation
from .probe_settings import ACK
from .probe_settings_receipts import ipc_record
from .tool_exchange import REPORT_FIELDS, idle_report

HEAD = "------------------ Measurements--------------------"
RESULTS = "------------------ Results------------------------------"
END = "-----------------------------------------------------------"
NUMBER = r"(-?[0-9]{1,4}\.[0-9]{3})"
SAMPLE = re.compile(r"TLO value from measurement ([1-5]): " + NUMBER + r"\Z")
USING = re.compile(r"Using TLO value from measurement ([1-5]): " + NUMBER + r"\Z")
DELTA = re.compile(r"Max delta: " + NUMBER + r"\Z")
EDGES = re.compile(r"Lowest cutting edge: ([1-5]), Highest cutting edge: ([1-5])\Z")


def projection(lines: list[str], repeats: int, utc: float) -> dict[str, Any] | None:
    """Closed repeat-block grammar; parsed numbers alone do not qualify custody."""
    if type(repeats) is not int or not 1 <= repeats <= 5 or not math.isfinite(utc) or utc <= 0:
        raise ValueError("Invalid measurement count or receipt time")
    starts = [i for i, line in enumerate(lines) if line == HEAD]
    if not starts:
        if any(line.startswith(("TLO value", "Using TLO", "Max delta:", "Lowest cutting edge:")) for line in lines):
            raise ValueError("Calibration block lacks its original boundary")
        return None
    if repeats == 1 or len(starts) != 1:
        raise ValueError("Unexpected or duplicate calibration block")
    block = lines[starts[0] : starts[0] + repeats + 6]
    if len(block) != repeats + 6 or block[-1] != END or block[repeats + 1] != RESULTS:
        raise ValueError("Incomplete or changed calibration block")
    values = []
    for index, line in enumerate(block[1 : repeats + 1], 1):
        match = SAMPLE.fullmatch(line)
        if match is None or int(match[1]) != index:
            raise ValueError("Calibration samples are missing, duplicated or reordered")
        values.append(float(match[2]))
    using, delta, edges = USING.fullmatch(block[-4]), DELTA.fullmatch(block[-3]), EDGES.fullmatch(block[-2])
    if using is None or delta is None or edges is None or not 1 <= int(using[1]) <= repeats:
        raise ValueError("Calibration result grammar differs")
    reported_using, spread = float(using[2]), float(delta[1])
    if (
        reported_using != values[int(using[1]) - 1]
        or reported_using != max(values)
        or spread < 0
        or abs(spread - (max(values) - min(values))) > 0.0011
        or any(not 1 <= int(v) <= repeats for v in edges.groups())
        or any(abs(v) > 1000 for v in values)
        or int(edges[1]) != int(using[1])
        or values[int(edges[2]) - 1] != min(values)
    ):
        raise ValueError("Calibration sample and result values conflict")
    remaining = lines[: starts[0]] + lines[starts[0] + repeats + 6 :]
    if any(
        line == HEAD or SAMPLE.fullmatch(line) or USING.fullmatch(line) or DELTA.fullmatch(line) for line in remaining
    ):
        raise ValueError("Additional calibration values outside the block")
    return {
        "report": TloReport(tuple(values), spread, None, utc).to_dict(),
        "printed_using_mm": reported_using,
        "printed_using_is_applied_tlo": False,
        "source_grammar_revision": SOURCE,
        "reference": "probe machine Z minus configured reference_tool_mz; not nominal stickout",
        "units_under_source_contract": "mm",
        "physical_accuracy_verified": False,
        "firmware_authenticated": False,
    }


@dataclass(frozen=True)
class ToolMeasurementReview:
    session_id: str
    connection_id: str
    context_sha256: str
    reports_sha256: str
    created_at: float
    target: int
    repeats: int
    tool_kind: str
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
    ) -> ToolMeasurementReview:
        status = idle_report(state, connection)
        target, repeats, kind = context.get("target"), context.get("repeats"), context.get("tool_kind")
        if (
            type(target) is not int
            or target != status["tool"]
            or not 0 <= target <= 6
            or type(repeats) is not int
            or not 1 <= repeats <= 5
            or kind != ("probe" if target == 0 else "cutter")
            or context.get("installed_kind_asserted") is not True
        ):
            raise ValueError("Confirm the installed probe/cutter kind and current reported T0–T6 before measurement")
        if (
            (identity.get("session_id"), identity.get("connection_id")) != (session, connection)
            or not supported_identity(identity.get("model", {}), identity.get("version", {}), status)
            or context.get("profile", {}).get("model") != "C1"
        ):
            raise ValueError("Read this connection's supported C1 / Community 2.1.0c identity first")
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError("Review clock unavailable")
        return cls(
            session,
            connection,
            fingerprint(context),
            fingerprint({k: status.get(k) for k in REPORT_FIELDS}),
            now,
            target,
            repeats,
            kind,
            canonical(compile_operation("tool.measure", {"repeats": repeats, "tool_kind": kind})),
        )

    @property
    def plan(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.plan_json))

    def authorize(
        self, session: str, connection: str, context: dict[str, Any], state: dict[str, Any], now: float
    ) -> dict[str, Any]:
        status = idle_report(state, connection)
        if (session, connection, fingerprint(context)) != (self.session_id, self.connection_id, self.context_sha256):
            raise ValueError("Machine, installed-kind assertion, assembly or repeat count changed; review again")
        if fingerprint({k: status.get(k) for k in REPORT_FIELDS}) != self.reports_sha256:
            raise ValueError("Reported tool, position or coordinate context changed after review")
        if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now - self.created_at <= 30:
            raise ValueError("Measurement review expired")
        return {"operation": "tool.measure", "parameters": {"repeats": self.repeats, "tool_kind": self.tool_kind}}

    def accept(self, response: Response, utc: float) -> dict[str, Any]:
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
            raise ValueError("Measurement response differs from its reviewed operation")
        receipts = result.get("command_receipts")
        if not isinstance(receipts, list) or len(receipts) != 1 or not isinstance(receipts[0], dict):
            raise ValueError("Measurement needs one original command receipt")
        receipt, command = receipts[0], self.plan["commands"][0]
        if (
            receipt.get("command") != command
            or receipt.get("wire_commands") != [command]
            or receipt.get("connection_id") != self.connection_id
            or receipt.get("outcome") != "controller_acknowledged"
            or receipt.get("motion_completed") is not False
        ):
            raise ValueError("Measurement receipt command or connection differs")
        text, window = original_command_window(receipt, command, self.connection_id, shell_barrier=False)
        original_lines = text.splitlines(keepends=True)
        if any(not line.endswith("\n") for line in original_lines):
            raise ValueError("Partial measurement output line")
        lines = [line[:-1].removesuffix("\r") for line in original_lines]
        if any(any(ord(c) < 32 or ord(c) > 126 for c in line) for line in lines):
            raise ValueError("Invalid measurement response characters")
        if sum(bool(ACK.fullmatch(line)) for line in lines) != 1 or any(
            line.lower().startswith(("error", "alarm", "halted")) for line in lines
        ):
            raise ValueError("Measurement response is unacknowledged or reports failure")
        return {
            "ipc": retained,
            "command_window_sha256": window["sha256"],
            "calibration": projection(lines, self.repeats, utc),
            "motion_completed": False,
        }

    def normalized_output(self, batch: dict[str, Any], after: int) -> list[dict[str, Any]]:
        """Original IPC is auditable; normalized/truncated firmware text stays unqualified."""
        if (
            type(after) is not int
            or after < 0
            or batch.get("session_id") != self.session_id
            or type(batch.get("lost_receipts")) is not int
            or batch.get("lost_receipts") != 0
        ):
            raise ValueError("Measurement output owner changed or bounded receipts were lost")
        rows = batch.get("receipts")
        if not isinstance(rows, list) or len(rows) > 256:
            raise ValueError("Invalid output receipt batch")
        for sequence, row in enumerate(rows, after + 1):
            if (
                not isinstance(row, dict)
                or type(row.get("sequence")) is not int
                or row.get("sequence") != sequence
                or row.get("connection_id") != self.connection_id
                or (
                    row.get("controller_original_bytes_retained") is not False
                    or row.get("normalized_by_backend") is not True
                    or row.get("command_attribution_verified") is not False
                )
            ):
                raise ValueError("Output receipt connection, sequence or provenance differs")
            try:
                raw = base64.b64decode(row["original_ipc_bytes_base64"], validate=True)
                event = strict_json(raw)
            except (KeyError, TypeError, ValueError):
                raise ValueError("Invalid original output IPC") from None
            if (
                len(raw) > 65536
                or not raw.endswith(b"\n")
                or hashlib.sha256(raw).hexdigest() != row.get("ipc_sha256")
                or event != {"event": "unsolicited_response", "text": row.get("text")}
            ):
                raise ValueError("Output projection differs from its original IPC bytes")
            text = row.get("text")
            if (
                not isinstance(text, str)
                or len(text) > 512
                or type(row.get("text_may_be_truncated")) is not bool
                or row["text_may_be_truncated"] != (len(text) == 512)
                or any(finite(row.get(k)) is None or row[k] < 0 for k in ("received_at_s", "received_utc_s"))
            ):
                raise ValueError("Output receipt clock, text bound or truncation flag differs")
        if batch.get("latest_sequence") != after + len(rows):
            raise ValueError("Output receipt cursor differs")
        return rows

    def target_reported(self, state: dict[str, Any], now: float, after: float | None) -> bool:
        if finite(now) is None or finite(after) is None:
            return False
        assert after is not None
        try:
            status = idle_report(state, self.connection_id)
        except ValueError:
            return False
        age = finite(state["last_machine_snapshot"].get("status_age_ms"))
        cached = finite(state.get("last_machine_snapshot_age_s"))
        return bool(
            age is not None
            and cached is not None
            and 0 <= age + cached * 1000 <= 3000
            and now - cached - age / 1000 > after
            and status["tool"] == self.target
        )
