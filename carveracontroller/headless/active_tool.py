"""Fixed stopped-cell ATC report, independently derived from pinned firmware.

The reported active offset is not a six-pocket table or proof of calibration.
In particular, repeated tool probing can leave cur different from the lowest
cutting-edge value used by offset; do not infer offset from cur minus ref.
"""

import base64
import hashlib
import math
import re

from .probe_settings import ACK, FALSE_FLAGS, WINDOW_FIELDS
from .telemetry import STATES, parse_diagnostics, parse_status

VERSION = "carvera.reported_active_tool.v1"
GRAMMAR = "carvera.atc.reported_active_tool.2fd69ee.v1"
FIRMWARE = "2fd69ee0542e75f1ad0561e93317308c32ebe863"
ATC_SHA256 = "03e44c114cd32f49b3685e3b46f09f535c14edad0969ee7a5aa5b77ab37bf441"
COMMANDS = ("M499.1", "M493.4", "M499.1")
FALSE = (
    "active_offsets_authenticated",
    "six_pocket_table_verified",
    "firmware_identity_verified",
    "physical_accuracy_verified",
    "execution_authorized",
)
N = r"-?(?:0|[1-9]\d*)\.\d{3}"
TOOL = re.compile(r"tool:(-1|0|[1-9]\d{0,5}) ref:(" + N + r") cur:(" + N + r") offset:(" + N + r")\Z")
PAIR = re.compile(r"current tool offset \[(" + N + r")\] , reference tool offset \[(" + N + r")\]\Z")
XYZ = r"X\[(" + N + r")\] Y\[(" + N + r")\] Z\[(" + N + r")\]"
ONEOFF = re.compile(r"one-off tool setter position offsets: " + XYZ + r"\Z")
SETTER = re.compile(r"(Tool setter position \(MCS\)|using default Tool setter position): " + XYZ + r"\Z")


class ActiveToolReadRefused(ValueError):
    """Earlier original command receipts remain available to the supervisor."""


def require(condition):
    if not condition:
        raise ActiveToolReadRefused("active_tool_original_invalid")


def numbers(tokens):
    require(all(math.isfinite(float(t)) and abs(float(t)) <= 10000 for t in tokens))
    return list(tokens)


def interpret(raw, command):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 4096 and raw.endswith(b"\n"))
    try:
        text = raw.decode("ascii")
    except UnicodeError:
        raise ActiveToolReadRefused("active_tool_original_invalid") from None
    lines = []
    ack = False
    for segment in text.splitlines(keepends=True):
        require(segment.endswith("\n"))
        line = segment[:-1].removesuffix("\r")
        require(all(32 <= ord(c) <= 126 for c in line))
        if not line:
            continue
        if ACK.fullmatch(line):
            ack = True
        elif line.startswith("<"):
            require(parse_status(line).get("state") in STATES)
        elif line.startswith("{"):
            fields = parse_diagnostics(line)["raw_fields"]
            require(bool(fields) and not set(fields) - {"S", "G", "R", "V", "P", "E", "I", "A"})
        else:
            lines.append(line)
    require(ack)
    if command == "M499.1":
        require(len(lines) == 1)
        match = TOOL.fullmatch(lines[0])
        require(match is not None)
        tool, ref, cur, offset = match.groups()
        numbers((ref, cur, offset))
        return {
            "tool_id": int(tool),
            "original_tool_token": tool,
            "reference_mm_token": ref,
            "current_mm_token": cur,
            "offset_mm_token": offset,
        }
    require(command == "M493.4" and len(lines) == 3)
    pair, oneoff, setter = PAIR.fullmatch(lines[0]), ONEOFF.fullmatch(lines[1]), SETTER.fullmatch(lines[2])
    require(pair is not None and setter is not None)
    require(oneoff is not None or lines[1] == "no one-off tool setter position offsets configured")
    cur, ref = numbers(pair.groups())
    return {
        "current_mm_token": cur,
        "reference_mm_token": ref,
        "oneoff_mm_tokens": numbers(oneoff.groups()) if oneoff else None,
        "setter_kind": "configured" if setter.group(1).startswith("Tool") else "default",
        "setter_mcs_mm_tokens": numbers(setter.groups()[1:]),
    }


def parse_receipt(receipt, command, connection):
    require(receipt.get("command") == command and receipt.get("wire_commands") == [command])
    require(
        receipt.get("outcome") == "controller_acknowledged"
        and receipt.get("motion_completed") is False
        and receipt.get("connection_id") == connection
    )
    w = receipt.get("controller_receive_evidence")
    require(isinstance(w, dict) and set(w) == WINDOW_FIELDS)
    require(
        w["version"] == "carvera.controller_receive_window.v1"
        and w["scope"] == "pending_command_socket_recv_calls"
        and w["connection_id"] == connection
    )
    require(
        w["original_bytes_retained"] is True
        and w["sendall_completed"] is True
        and w["may_include_interleaved_or_unattributed_bytes"] is True
    )
    require(all(w[k] is False for k in FALSE_FLAGS))
    require(
        type(w["byte_count"]) is int
        and 0 < w["byte_count"] <= 4096
        and type(w["budget_bytes"]) is int
        and w["budget_bytes"] == 65536
    )
    try:
        raw = base64.b64decode(w["original_bytes_base64"], validate=True)
        planned = base64.b64decode(w["planned_command_bytes_base64"], validate=True)
    except (ValueError, TypeError):
        raise ActiveToolReadRefused("active_tool_original_invalid") from None
    require(
        len(raw) == w["byte_count"]
        and hashlib.sha256(raw).hexdigest() == w["sha256"]
        and planned == (command + "\n").encode()
    )
    return interpret(raw, command)


def read_active_tool(link, receipts):
    before = link.snapshot()
    connection = before.get("connection_id")

    def settled(value):
        require(
            value.get("connected") is True
            and isinstance(connection, str)
            and bool(connection)
            and value.get("connection_id") == connection
            and value.get("transfer_active") is False
            and value.get("unknown_outcome") is False
        )

        for key, limit in (("status_age_ms", 2000), ("diagnostics_age_ms", 3000)):
            require(type(value.get(key)) in (int, float) and math.isfinite(value[key]) and 0 <= value[key] <= limit)
        status, diagnostics = value.get("status"), value.get("diagnostics")
        require(isinstance(status, dict) and isinstance(diagnostics, dict))
        require(all(type(status.get(k)) in (int, float) for k in ("spindle_rpm", "spindle_target_rpm")))
        require(
            status.get("state") == "Idle"
            and status.get("is_playing") is False
            and status.get("spindle_rpm") == 0
            and status.get("spindle_target_rpm") == 0
            and diagnostics.get("spindle_enabled") is False
        )

    settled(before)
    reports = []
    for command in COMMANDS:
        receipt = link.command(command, read_only=True, timeout=10)
        receipts.append(receipt)
        reports.append(parse_receipt(receipt, command, connection))
        settled(link.snapshot())
    first, detail, last = reports
    require(first == last and all(first[k] == detail[k] for k in ("current_mm_token", "reference_mm_token")))
    return {
        "schema_version": VERSION,
        "source_grammar": GRAMMAR,
        "grammar_firmware_revision": FIRMWARE,
        "grammar_atc_sha256": ATC_SHA256,
        "connection_id": connection,
        "reported": first,
        "setter": detail,
        "command_receipts": receipts,
        **dict.fromkeys(FALSE, False),
    }
