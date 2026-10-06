"""Private supervised JSON-lines child. No HTTP listener and no credentials.

The gateway owns approval, identity, leases and its durable operation journal.
This child owns the sole CNC connection and reports each command outcome. A
single executor preserves command order; realtime requests can interrupt an
in-flight motion without waiting behind its acknowledgement.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import logging
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

from . import RUNTIME_VERSION
from .link import MAX_FILE, CarveraLink, ControllerRejected, OutcomeUnknown
from .operations import catalog, compile_operation
from .probe_settings import ProbeSettingsReadRefused, read_settings
from .probe_settings_application import ProbeSettingsApplicationRefused, apply_settings, strict_application_request

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=2222)
    options = parser.parse_args()
    address = ipaddress.ip_address(options.host)
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8")
    if address.version != 4 or not any(address in ipaddress.ip_network(value) for value in networks):
        parser.error("A private IPv4 CNC address is required")
    if options.port != 2222 and not address.is_loopback:
        parser.error("The supported CNC port is 2222")
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    output_lock = threading.Lock()

    def emit(value: dict) -> None:
        with output_lock:
            sys.stdout.write(json.dumps(value, allow_nan=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()

    link = CarveraLink(options.host, options.port, on_event=emit)
    closing = threading.Event()
    pending_slots = threading.BoundedSemaphore(16)

    def run(request: dict) -> None:
        request_id = request["id"]
        method, params = request["method"], request.get("params", {})
        receipts = []
        try:
            if closing.is_set():
                raise RuntimeError("Supervisor is closing")
            if (
                method in ("connect", "disconnect", "snapshot", "cancel_transfer", "catalog", "probe_profile_read")
                and params
            ):
                raise ValueError("This method takes no parameters")
            if method == "connect":
                link.connect()
                result = link.snapshot()
            elif method == "disconnect":
                link.close()
                result = link.snapshot()
            elif method == "snapshot":
                result = link.snapshot()
            elif method == "reconcile":
                if set(params) != {"connection_id"}:
                    raise ValueError("Reconciliation needs the exact connection identity")
                result = link.acknowledge_unknown_outcome(params["connection_id"])
            elif method == "probe_profile_read":
                result = read_settings(link, receipts)
            elif method == "probe_profile_apply":
                result = apply_settings(link, params, receipts)
            elif method == "catalog":
                result = catalog()
            elif method in ("compile", "operation"):
                if set(params) != {"operation", "parameters"}:
                    raise ValueError("A named operation and exact parameters are required")
                plan = compile_operation(params["operation"], params["parameters"])
                if method == "compile":
                    result = plan
                elif plan["realtime"]:
                    result = link.realtime(plan["realtime"])
                else:
                    for command in plan["commands"]:
                        receipts.append(link.command(command, timeout=180, read_only=plan["read_only"]))
                    result = {
                        "outcome": "controller_acknowledged",
                        "motion_completed": False,
                        "plan": plan,
                        "command_receipts": receipts,
                        "snapshot": link.snapshot(),
                    }
            elif method == "command":
                if set(params) - {"command", "timeout", "read_only"}:
                    raise ValueError("Unknown command parameter")
                result = link.command(**params)
            elif method == "realtime":
                if set(params) != {"action"}:
                    raise ValueError("Realtime request needs one named action")
                result = link.realtime(params["action"])
            elif method in ("upload", "download"):
                if set(params) - {"path", "data_base64", "timeout"}:
                    raise ValueError("Unknown transfer parameter")
                encoded = params.get("data_base64", "")
                if not isinstance(encoded, str) or len(encoded) > MAX_FILE * 4 // 3 + 4:
                    raise ValueError("Invalid transfer size")
                data = base64.b64decode(encoded, validate=True)
                result = link.transfer(method, params["path"], data, timeout=params.get("timeout", 120))
                received = result.pop("data", None)
                if received is not None:
                    result["data_base64"] = base64.b64encode(received).decode("ascii")
            else:
                link.cancel_transfer()
                result = {"outcome": "cancel_requested"}
            emit({"id": request_id, "ok": True, "result": result})
        except ProbeSettingsApplicationRefused:
            emit(
                {
                    "id": request_id,
                    "ok": False,
                    "error": "probe_settings_application_refused",
                    "completed_command_receipts": receipts,
                }
            )
        except ProbeSettingsReadRefused:
            emit(
                {
                    "id": request_id,
                    "ok": False,
                    "error": "probe_settings_read_refused",
                    "completed_command_receipts": receipts,
                }
            )
        except ControllerRejected as error:
            emit(
                {
                    "id": request_id,
                    "ok": False,
                    "error": "controller_rejected",
                    "receipt": error.receipt,
                    "completed_command_receipts": receipts,
                }
            )
        except OutcomeUnknown as error:
            emit(
                {
                    "id": request_id,
                    "ok": False,
                    "error": "unknown_outcome",
                    "receipt": error.receipt,
                    "completed_command_receipts": receipts,
                }
            )
        except Exception as error:
            # Exceptions may contain filesystem/network data. The parent gets
            # a typed error code, not an arbitrary exception string.
            result = {"id": request_id, "ok": False, "error": type(error).__name__}
            if method == "probe_profile_apply":
                result["completed_command_receipts"] = receipts
            emit(result)

    emit(
        {
            "event": "ready",
            "runtime_version": RUNTIME_VERSION,
            "protocol": "smoothie",
            "connection_owned": False,
            "license": "GPL-2.0-only",
        }
    )
    seen: set[str] = set()

    def queued_run(request: dict) -> None:
        try:
            run(request)
        finally:
            pending_slots.release()

    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="carvera-commands") as executor:
        try:
            while True:
                line = sys.stdin.buffer.readline(MAX_REQUEST + 1)
                if not line:
                    break
                if len(line) > MAX_REQUEST or not line.endswith(b"\n"):
                    raise ValueError("Oversized or unterminated request")
                request = json.loads(line)
                if isinstance(request, dict) and request.get("method") == "probe_profile_apply":
                    request = strict_application_request(line)
                if not isinstance(request, dict) or set(request) - {"id", "method", "params"}:
                    raise ValueError("Invalid request envelope")
                request_id = request.get("id")
                if not isinstance(request_id, str) or not ID.fullmatch(request_id) or request_id in seen:
                    raise ValueError("Invalid or duplicate request identity")
                if len(seen) >= 100000:
                    raise ValueError("Runtime request budget exhausted")
                seen.add(request_id)
                if request.get("method") not in METHODS or not isinstance(request.get("params", {}), dict):
                    emit({"id": request_id, "ok": False, "error": "invalid_method"})
                    continue
                urgent_operation = request["method"] == "operation" and request.get("params", {}).get("operation") in (
                    "machine.hold",
                    "machine.abort",
                    "machine.jog_cancel",
                )
                if (
                    request["method"] in ("realtime", "snapshot", "cancel_transfer", "catalog", "compile")
                    or urgent_operation
                ):
                    run(request)
                elif not pending_slots.acquire(blocking=False):
                    emit({"id": request_id, "ok": False, "error": "queue_full"})
                else:
                    executor.submit(queued_run, request)
        except (ValueError, UnicodeError):
            emit({"event": "protocol_error", "error": "invalid_request"})
        finally:
            closing.set()
            link.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
