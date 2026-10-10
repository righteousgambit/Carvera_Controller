"""Unambiguous JSON request envelopes and closed method parameter contracts.

Parsing refuses duplicates at every object depth and all nonfinite numbers.
Validation does not dispatch, authorize, coerce arguments or modify a plan.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, NoReturn, TypedDict

from .arguments import MAX_FILE, command_line, deadline, read_only_flag
from .link import remote_path

MAX_REQUEST = 12 * 1024 * 1024
ID = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
METHODS = frozenset(
    (
        "connect",
        "disconnect",
        "snapshot",
        "command",
        "realtime",
        "upload",
        "download",
        "cancel_transfer",
        "catalog",
        "compile",
        "operation",
        "reconcile",
        "probe_profile_read",
        "probe_profile_apply",
    )
)
REALTIME_ACTIONS = frozenset(("status", "feed_hold", "cycle_resume", "software_abort", "jog_cancel", "jog_keepalive"))


class Request(TypedDict):
    id: str
    method: str
    params: dict[str, Any]


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate request field")
        result[key] = value
    return result


def _constant(_value: str) -> NoReturn:
    raise ValueError("Nonfinite request number")


def _float(value: str) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Nonfinite request number")
    return result


def decode_record(raw: bytes, limit: int = MAX_REQUEST) -> object:
    if not isinstance(raw, bytes) or len(raw) > limit or not raw.endswith(b"\n"):
        raise ValueError("Oversized or unterminated request")
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant, parse_float=_float)
    except RecursionError:
        raise ValueError("Request nesting exceeds the parser limit") from None


def decode_request(raw: bytes) -> Request:
    value = decode_record(raw)
    if not isinstance(value, dict) or set(value) - {"id", "method", "params"}:
        raise ValueError("Invalid request envelope")
    request_id, method, params = value.get("id"), value.get("method"), value.get("params", {})
    if not isinstance(request_id, str) or not ID.fullmatch(request_id):
        raise ValueError("Invalid request identity")
    if not isinstance(method, str) or not isinstance(params, dict):
        raise ValueError("Invalid request method or parameters")
    return {"id": request_id, "method": method, "params": params}


def _keys(params: dict[str, Any], required: set[str], optional: set[str] | None = None) -> None:
    if not required.issubset(params) or set(params) - required - (optional or set()):
        raise ValueError("Method parameters do not match the closed contract")


def validate_parameters(method: str, params: dict[str, Any]) -> None:
    if not isinstance(method, str) or method not in METHODS or not isinstance(params, dict):
        raise ValueError("Unknown method or invalid parameters")
    if method in ("connect", "disconnect", "snapshot", "cancel_transfer", "catalog", "probe_profile_read"):
        _keys(params, set())
    elif method == "command":
        _keys(params, {"command"}, {"timeout", "read_only"})
        command_line(params["command"])
        deadline(params.get("timeout", 10))
        read_only_flag(params.get("read_only", False))
    elif method == "realtime":
        _keys(params, {"action"})
        if not isinstance(params["action"], str) or params["action"] not in REALTIME_ACTIONS:
            raise ValueError("Unknown realtime action")
    elif method in ("upload", "download"):
        _keys(params, {"path"}, {"data_base64", "timeout"})
        remote_path(params["path"])
        deadline(params.get("timeout", 120))
        data = params.get("data_base64", "")
        if not isinstance(data, str) or len(data) > MAX_FILE * 4 // 3 + 4:
            raise ValueError("Invalid encoded transfer size")
        if method == "download" and data:
            raise ValueError("Download takes no outgoing payload")
    elif method in ("compile", "operation"):
        _keys(params, {"operation", "parameters"})
        if not isinstance(params["operation"], str) or not isinstance(params["parameters"], dict):
            raise ValueError("Operation needs a name and parameter object")
    elif method == "reconcile":
        _keys(params, {"connection_id"})
        if not isinstance(params["connection_id"], str) or not ID.fullmatch(params["connection_id"]):
            raise ValueError("Reconciliation needs an exact connection identity")
    elif method == "probe_profile_apply":
        # The two-key application producer owns its deeper pinned contract.
        _keys(params, {"schema_version", "connection_id", "expected_settings", "settings"})
    else:
        raise ValueError("Method parameter contract is not implemented")
