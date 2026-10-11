"""Validate probe results against retained IPC bytes and controller windows."""

from __future__ import annotations

import base64
import hashlib
from typing import Any, Callable, cast

from carveracontroller.machine.probe_settings_workflow import expected_settings, strict_json

from .client import Response
from .probe_settings import CONFIGURATOR_SHA256, FIRMWARE_SOURCE, GRAMMAR, KEYS, VERSION, parse_receipt
from .probe_settings_application import CONFIG_VALUE_SHA256, compile_application
from .probe_settings_application import VERSION as APPLICATION_VERSION

FLAGS = (
    "active_settings_verified",
    "persistence_verified",
    "firmware_identity_verified",
    "physical_accuracy_verified",
    "execution_authorized",
)


def require(condition: object) -> None:
    if not condition:
        raise ValueError("Probe result differs from its original receipts")


def ipc_record(response: Response) -> dict[str, Any]:
    raw = response.original_line
    require(isinstance(raw, bytes) and len(raw) <= 4 * 1024 * 1024 and raw.endswith(b"\n"))
    assert raw is not None
    require(hashlib.sha256(raw).hexdigest() == response.response_sha256)
    envelope = strict_json(raw)
    require(envelope == response.envelope)
    return {
        "original_ipc_bytes_base64": base64.b64encode(raw).decode(),
        "response_sha256": response.response_sha256,
        "request_sha256": response.request_sha256,
        "received_at_s": response.received_at_s,
        "elapsed_ms": response.elapsed_ms,
        "envelope": envelope,
    }


def validate_read(value: Any, connection: str) -> dict[str, Any]:
    require(
        isinstance(value, dict)
        and set(value)
        == {
            "schema_version",
            "source_grammar",
            "grammar_firmware_revision",
            "grammar_configurator_sha256",
            "connection_id",
            "reported_source",
            "settings",
            "command_receipts",
            *FLAGS,
        }
    )
    require(
        value["schema_version"] == VERSION
        and value["source_grammar"] == GRAMMAR
        and value["grammar_firmware_revision"] == FIRMWARE_SOURCE
        and value["grammar_configurator_sha256"] == CONFIGURATOR_SHA256
        and value["connection_id"] == connection
        and value["reported_source"] == "sd"
    )
    require(all(value[flag] is False for flag in FLAGS))
    receipts = value["command_receipts"]
    require(isinstance(receipts, list) and len(receipts) == 2)
    settings = expected_settings(value["settings"])
    require(settings == {key: parse_receipt(receipt, key, connection) for key, receipt in zip(KEYS, receipts)})
    return settings


def validate_apply(value: Any, params: dict[str, Any]) -> None:
    # The pinned producer is dynamically typed; the adapter keeps its closed
    # request contract without changing producer behavior or command semantics.
    compile_plan = cast(Callable[[dict[str, Any]], dict[str, Any]], compile_application)
    plan = compile_plan(params)
    require(
        isinstance(value, dict)
        and set(value)
        == {
            "schema_version",
            "outcome",
            "connection_id",
            "plan",
            "grammar_config_value_sha256",
            "before",
            "write_command_receipts",
            "after",
            "command_receipts",
            "sd_readback_matches_requested",
            "automatic_rollback_performed",
            *FLAGS,
        }
    )
    connection = plan["connection_id"]
    require(
        value["schema_version"] == APPLICATION_VERSION
        and value["outcome"] == "reported_sd_values_match"
        and value["connection_id"] == connection
        and value["plan"] == plan
        and value["grammar_config_value_sha256"] == CONFIG_VALUE_SHA256
    )
    require(
        value["sd_readback_matches_requested"] is True
        and value["automatic_rollback_performed"] is False
        and all(value[flag] is False for flag in FLAGS)
    )
    require(validate_read(value["before"], connection) == plan["expected_settings"])
    after = validate_read(value["after"], connection)
    writes = value["write_command_receipts"]
    require(isinstance(writes, list) and len(writes) == 2)
    for key, receipt in zip(KEYS, writes):
        parsed = parse_receipt(receipt, key, connection, write_token=plan["settings"][key])
        require(after[key] == parsed)
    require(
        value["command_receipts"] == value["before"]["command_receipts"] + writes + value["after"]["command_receipts"]
    )
