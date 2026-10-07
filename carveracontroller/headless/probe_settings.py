"""Fixed-key reported SD probe settings from bounded original receive windows.

This is independently implemented from the pinned firmware's output grammar.
It does not authenticate firmware, attribute every received byte to a command,
or establish the ATC handler's active TLO correction.
"""

from __future__ import annotations

import base64
import hashlib
import math
import re

from .telemetry import STATES, parse_diagnostics, parse_status

VERSION = "carvera.persisted_probe_settings.v1"
GRAMMAR = "carvera.configurator.sd_probe_settings.2fd69ee.v1"
FIRMWARE_SOURCE = "2fd69ee0542e75f1ad0561e93317308c32ebe863"
CONFIGURATOR_SHA256 = "c23d9923f97e1ba34b25c21f4c9f6ce0e16c8f4fc491d69ebbb6dec0b405b6c1"
KEYS = ("zprobe.probe_tip_diameter", "zprobe.three_axis_probe_tlo_correction")
READ_COMMANDS = tuple(f"config-get sd {key}" for key in KEYS)
MAX_RESPONSE = 4096
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
ACK = re.compile(r"ok(?: [A-Za-z@][A-Za-z0-9@]*:[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?: /[+-]?(?:\d+(?:\.\d*)?|\.\d+))?)*\Z")
WINDOW_FIELDS = {
    "version",
    "connection_id",
    "scope",
    "original_bytes_base64",
    "sha256",
    "byte_count",
    "budget_bytes",
    "original_bytes_retained",
    "planned_command_bytes_base64",
    "sendall_completed",
    "delivery_verified",
    "may_include_interleaved_or_unattributed_bytes",
    "complete_controller_response_verified",
    "firmware_identity_verified",
    "measurement_interpretation_available",
    "physical_accuracy_verified",
    "execution_authorized",
}
FALSE_FLAGS = (
    "delivery_verified",
    "complete_controller_response_verified",
    "firmware_identity_verified",
    "measurement_interpretation_available",
    "physical_accuracy_verified",
    "execution_authorized",
)


class ProbeSettingsReadRefused(ValueError):
    """Original earlier read receipts remain with the private caller on refusal."""


def parse_receipt(receipt: dict, key: str, connection_id: str) -> dict:
    if key not in KEYS or not isinstance(receipt, dict):
        raise ProbeSettingsReadRefused("probe_settings_receipt_invalid")
    command = f"config-get sd {key}"
    if (
        receipt.get("command") != command
        or receipt.get("wire_commands") != [command, "M105"]
        or receipt.get("outcome") != "controller_acknowledged"
        or receipt.get("connection_id") != connection_id
        or receipt.get("motion_completed") is not False
    ):
        raise ProbeSettingsReadRefused("probe_settings_receipt_binding_changed")
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
        or not 0 < window["byte_count"] <= MAX_RESPONSE
        or type(window.get("budget_bytes")) is not int
        or window["budget_bytes"] != 65536
    ):
        raise ProbeSettingsReadRefused("probe_settings_original_window_required")
    try:
        raw = base64.b64decode(window["original_bytes_base64"], validate=True)
        planned = base64.b64decode(window["planned_command_bytes_base64"], validate=True)
        text = raw.decode("ascii")
    except (ValueError, TypeError, UnicodeDecodeError) as error:
        raise ProbeSettingsReadRefused("probe_settings_original_window_invalid") from error
    if (
        base64.b64encode(raw).decode("ascii") != window["original_bytes_base64"]
        or len(raw) != window["byte_count"]
        or hashlib.sha256(raw).hexdigest() != window["sha256"]
        or planned != f"{command}\nM105\n".encode("ascii")
        or not text.endswith("\n")
    ):
        raise ProbeSettingsReadRefused("probe_settings_original_window_changed")
    matches: list[dict[str, str | float | None]] = []
    for original in text.splitlines(keepends=True):
        if not original.endswith("\n"):
            raise ProbeSettingsReadRefused("probe_settings_partial_response")
        line = original[:-1].removesuffix("\r")
        if any(ord(char) < 32 or ord(char) > 126 for char in line):
            raise ProbeSettingsReadRefused("probe_settings_response_control_character")
        if line == f"sd: {key} is not in config":
            matches.append({"state": "missing", "value_mm": None, "original_numeric_token": None})
        elif line.startswith(f"sd: {key} is set to "):
            token = line[len(f"sd: {key} is set to ") :]
            if not NUMBER.fullmatch(token):
                raise ProbeSettingsReadRefused("probe_settings_numeric_grammar")
            value = float(token)
            if not math.isfinite(value) or abs(value) > 500 or key == KEYS[0] and value <= 0:
                raise ProbeSettingsReadRefused("probe_settings_numeric_range")
            matches.append({"state": "reported", "value_mm": value, "original_numeric_token": token})
        elif not line or ACK.fullmatch(line):
            continue
        elif line.startswith("<"):
            try:
                status = parse_status(line)
                if status.get("state") not in STATES:
                    raise ValueError("unknown status state")
            except (ValueError, OverflowError) as error:
                raise ProbeSettingsReadRefused("probe_settings_invalid_interleaved_status") from error
        elif line.startswith("{"):
            try:
                diagnostic = parse_diagnostics(line)
                fields = diagnostic["raw_fields"]
                if not fields or set(fields) - {"S", "G", "R", "V", "P", "E", "I", "A"}:
                    raise ValueError("unknown diagnostic fields")
            except (ValueError, OverflowError) as error:
                raise ProbeSettingsReadRefused("probe_settings_invalid_interleaved_diagnostics") from error
        else:
            raise ProbeSettingsReadRefused("probe_settings_unrecognized_response")
    if len(matches) != 1:
        raise ProbeSettingsReadRefused("probe_settings_response_membership")
    return matches[0]


def read_settings(link, receipts: list[dict]) -> dict:
    before = link.snapshot()
    connection_id = before.get("connection_id")
    if (
        before.get("connected") is not True
        or not isinstance(connection_id, str)
        or not connection_id
        or before.get("transfer_active") is not False
        or before.get("unknown_outcome") is not False
    ):
        raise ProbeSettingsReadRefused("probe_settings_settled_connection_required")
    values = {}
    for key, command in zip(KEYS, READ_COMMANDS):
        receipt = link.command(command, read_only=True, timeout=10)
        receipts.append(receipt)
        values[key] = parse_receipt(receipt, key, connection_id)
        after = link.snapshot()
        if (
            after.get("connected") is not True
            or after.get("connection_id") != connection_id
            or after.get("transfer_active") is not False
            or after.get("unknown_outcome") is not False
        ):
            raise ProbeSettingsReadRefused("probe_settings_connection_changed")
    return {
        "schema_version": VERSION,
        "source_grammar": GRAMMAR,
        "grammar_firmware_revision": FIRMWARE_SOURCE,
        "grammar_configurator_sha256": CONFIGURATOR_SHA256,
        "connection_id": connection_id,
        "reported_source": "sd",
        "settings": values,
        "command_receipts": receipts,
        "active_settings_verified": False,
        "persistence_verified": False,
        "firmware_identity_verified": False,
        "physical_accuracy_verified": False,
        "execution_authorized": False,
    }
