"""Connection-bound reported model/version from original command windows.

Grammar: Community feab653def96a959e695049a4f828aeddbcd5547
SimpleShell.cpp model_command/version_command. Reported strings are not signed
firmware attestation, and do not prove physical setup or completed motion.
"""

from __future__ import annotations

import base64
import hashlib
import re
from typing import Any

from .job_file import context_digest
from .operations import compile_operation
from .probe_settings import ACK, FALSE_FLAGS, WINDOW_FIELDS
from .telemetry import STATES, parse_diagnostics, parse_status

SOURCE = "feab653def96a959e695049a4f828aeddbcd5547"
MODEL = re.compile(r"model = (C1|CA1), ([0-9]{1,3}), ([0-9]{1,3}), ([0-9]{1,10})\Z")
VERSION = re.compile(r"version = ([A-Za-z0-9][A-Za-z0-9_.+-]{0,79})\Z")


def original_command_window(receipt: dict[str, Any], command: str, connection_id: str) -> tuple[str, dict[str, Any]]:
    window = receipt.get("controller_receive_evidence")
    if (
        not isinstance(window, dict)
        or set(window) != WINDOW_FIELDS
        or window.get("version") != "carvera.controller_receive_window.v1"
        or window.get("scope") != "pending_command_socket_recv_calls"
        or window.get("connection_id") != connection_id
        or window.get("original_bytes_retained") is not True
        or window.get("sendall_completed") is not True
        or window.get("may_include_interleaved_or_unattributed_bytes") is not True
        or any(window.get(flag) is not False for flag in FALSE_FLAGS)
        or type(window.get("byte_count")) is not int
        or not 0 < window["byte_count"] <= 4096
        or type(window.get("budget_bytes")) is not int
        or window["budget_bytes"] != 65536
    ):
        raise ValueError("Command requires its bounded original receive window")
    try:
        raw = base64.b64decode(window["original_bytes_base64"], validate=True)
        planned = base64.b64decode(window["planned_command_bytes_base64"], validate=True)
        text = raw.decode("ascii")
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("Invalid command window encoding") from None
    if (
        len(raw) != window["byte_count"]
        or hashlib.sha256(raw).hexdigest() != window.get("sha256")
        or planned != f"{command}\nM105\n".encode()
        or not text.endswith("\n")
    ):
        raise ValueError("Command window hash, size or planned bytes changed")
    return text, window


def reported_identity(result: dict[str, Any], query: str, connection_id: str) -> dict[str, Any]:
    expected = compile_operation("observe.query", {"query": query})
    if query not in ("model", "version") or (
        result.get("outcome") != "controller_acknowledged"
        or result.get("motion_completed") is not False
        or context_digest(result.get("plan")) != context_digest(expected)
    ):
        raise ValueError("Identity response does not match the read-only query")
    receipts = result.get("command_receipts")
    if not isinstance(receipts, list) or len(receipts) != 1 or not isinstance(receipts[0], dict):
        raise ValueError("Identity requires one original command receipt")
    receipt = receipts[0]
    if (
        receipt.get("command") != query
        or receipt.get("wire_commands") != [query, "M105"]
        or receipt.get("connection_id") != connection_id
        or receipt.get("outcome") != "controller_acknowledged"
        or receipt.get("motion_completed") is not False
    ):
        raise ValueError("Identity command receipt belongs to another query or connection")
    text, window = original_command_window(receipt, query, connection_id)
    matches = []
    acknowledgments = 0
    for original in text.splitlines(keepends=True):
        line = original[:-1].removesuffix("\r")
        if not original.endswith("\n") or any(ord(char) < 32 or ord(char) > 126 for char in line):
            raise ValueError("Identity response contains partial or control bytes")
        match = (MODEL if query == "model" else VERSION).fullmatch(line)
        if match:
            matches.append(match.groups())
        elif ACK.fullmatch(line):
            acknowledgments += 1
        elif (
            not line
            or line.startswith("<")
            and parse_status(line)["state"] in STATES
            or line.startswith("{")
            and parse_diagnostics(line)["raw_fields"]
        ):
            continue
        else:
            raise ValueError("Identity response contains unrecognized or conflicting text")
    if len(matches) != 1 or acknowledgments != 1:
        raise ValueError("Identity response is missing, duplicated or unacknowledged")
    tokens = matches[0]
    if query == "version":
        return {
            "reported_version": tokens[0],
            "source_sha": SOURCE,
            "window_sha256": window["sha256"],
            "authenticated": False,
        }
    model, code, features, probe = tokens
    if int(features) > 255 or int(probe) > 4294967295:
        raise ValueError("Reported identity numeric fields exceed their bounds")
    return {
        "reported_model": model,
        "model_code": int(code),
        "features": int(features),
        "probe_address": int(probe),
        "source_sha": SOURCE,
        "window_sha256": window["sha256"],
        "authenticated": False,
    }


def supported_identity(model: dict[str, Any], version: dict[str, Any], status: dict[str, Any]) -> bool:
    return (
        model.get("reported_model") == "C1"
        and type(model.get("model_code")) is int
        and model.get("model_code") == 1
        and model.get("source_sha") == SOURCE
        and version.get("source_sha") == SOURCE
        and version.get("reported_version") == "2.1.0c"
        and model.get("authenticated") is False
        and version.get("authenticated") is False
        and type(model.get("features")) is int
        and type(status.get("machine_model")) in (int, float)
        and status.get("machine_model") == model["model_code"]
        and status.get("features") == model.get("features")
    )
