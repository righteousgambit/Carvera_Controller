"""Closed two-key SD update producer. The external supervisor owns admission.

Fresh original reads precede any write. Partial writes are not rolled back or
retried. Reported SD matches cannot establish active ATC TLO or physical accuracy.
"""

from __future__ import annotations

import copy
import json
import math
import re

from .probe_settings import KEYS, NUMBER, parse_receipt, read_settings

VERSION = "carvera.probe_settings_application.v1"
CONFIG_VALUE_SHA256 = "cbe3c6a5e101622585a0c73badf006bfdf65d562d906722083a563483183b0b3"
CONNECTION = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")


class ProbeSettingsApplicationRefused(ValueError):
    """Keep all prior command receipts; a refusal never rolls back a write."""


def require(value):
    if not value:
        raise ProbeSettingsApplicationRefused("probe_settings_application_refused")


def closed(value, keys):
    require(isinstance(value, dict) and set(value) == set(keys))


def token(value, key):
    # Pinned ConfigValue.h stores at most 19 characters plus the terminator.
    require(isinstance(value, str) and 0 < len(value) < 20 and NUMBER.fullmatch(value))
    number = float(value)
    require(math.isfinite(number) and abs(number) <= 500 and (key != KEYS[0] or number > 0))
    return number


def compile_application(params):
    closed(params, ("schema_version", "connection_id", "expected_settings", "settings"))
    require(params["schema_version"] == VERSION)
    require(isinstance(params["connection_id"], str) and CONNECTION.fullmatch(params["connection_id"]))
    closed(params["expected_settings"], KEYS)
    closed(params["settings"], KEYS)
    for key in KEYS:
        setting = params["expected_settings"][key]
        closed(setting, ("state", "value_mm", "original_numeric_token"))
        if setting["state"] == "missing":
            require(setting["value_mm"] is None and setting["original_numeric_token"] is None)
        else:
            require(setting["state"] == "reported" and type(setting["value_mm"]) in (int, float))
            require(setting["value_mm"] == token(setting["original_numeric_token"], key))
        token(params["settings"][key], key)
    require(
        any(
            params["expected_settings"][key]["state"] != "reported"
            or params["expected_settings"][key]["original_numeric_token"] != params["settings"][key]
            for key in KEYS
        )
    )
    return copy.deepcopy(params)


def strict_application_request(raw):
    require(isinstance(raw, bytes) and len(raw) <= 8192 and raw.endswith(b"\n"))

    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result)
            result[key] = value
        return result

    def constant(_value):
        raise ProbeSettingsApplicationRefused("nonfinite_private_request")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    closed(value, ("id", "method", "params"))
    require(value["method"] == "probe_profile_apply")
    compile_application(value["params"])
    return value


def settled(link, connection):
    snapshot = link.snapshot()
    status, diagnostic = snapshot.get("status") or {}, snapshot.get("diagnostics") or {}
    require(snapshot.get("connected") is True and snapshot.get("connection_id") == connection)
    require(snapshot.get("transfer_active") is False and snapshot.get("unknown_outcome") is False)
    for field, limit in (("status_age_ms", 2000), ("diagnostics_age_ms", 3000)):
        age = snapshot.get(field)
        require(type(age) in (int, float) and math.isfinite(age) and 0 <= age <= limit)
    require(status.get("state") == "Idle" and status.get("is_playing") is False)
    require(type(status.get("spindle_rpm")) in (int, float) and status["spindle_rpm"] == 0)
    require(type(status.get("spindle_target_rpm")) in (int, float) and status["spindle_target_rpm"] == 0)
    require(diagnostic.get("spindle_enabled") is False)


def original_read(link, receipts):
    phase = []
    try:
        return copy.deepcopy(read_settings(link, phase))
    finally:
        receipts.extend(phase)


def apply_settings(link, params, receipts):
    plan = compile_application(params)
    connection = plan["connection_id"]
    settled(link, connection)
    before = original_read(link, receipts)
    require(before["connection_id"] == connection and before["settings"] == plan["expected_settings"])
    settled(link, connection)
    writes = []
    for key in KEYS:
        settled(link, connection)
        requested = plan["settings"][key]
        receipt = link.command(f"config-set sd {key} {requested}", timeout=10, read_only=False)
        receipts.append(receipt)
        # Require the exact pinned firmware success line, not merely M105's ok.
        parse_receipt(receipt, key, connection, write_token=requested)
        writes.append(copy.deepcopy(receipt))
        settled(link, connection)
    after = original_read(link, receipts)
    settled(link, connection)
    require(after["connection_id"] == connection)
    for key in KEYS:
        require(
            after["settings"][key]
            == {
                "state": "reported",
                "value_mm": token(plan["settings"][key], key),
                "original_numeric_token": plan["settings"][key],
            }
        )
    return {
        "schema_version": VERSION,
        "outcome": "reported_sd_values_match",
        "connection_id": connection,
        "plan": plan,
        "grammar_config_value_sha256": CONFIG_VALUE_SHA256,
        "before": before,
        "write_command_receipts": writes,
        "after": after,
        "command_receipts": copy.deepcopy(receipts),
        "sd_readback_matches_requested": True,
        "automatic_rollback_performed": False,
        "active_settings_verified": False,
        "persistence_verified": False,
        "firmware_identity_verified": False,
        "physical_accuracy_verified": False,
        "execution_authorized": False,
    }
