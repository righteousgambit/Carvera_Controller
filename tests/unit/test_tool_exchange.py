import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from carveracontroller.headless.client import Response
from carveracontroller.headless.tool_exchange import ToolExchangeReview
from carveracontroller.headless.wire_evidence import ReceiveWindow
from tests.unit.test_headless_job_run import model, version
from tests.unit.test_headless_job_run import state as job_state


def state():
    value = job_state()
    value["last_machine_snapshot"].update({"diagnostics_age_ms": 10, "diagnostics": {"spindle_enabled": False}})
    return value


def context():
    return {"target": 2, "profile": {"model": "C1", "name": "Bench"}, "declared_tool_mm": {"diameter": 6.35}}


def review():
    identity = {"session_id": "child", "connection_id": "wire", "model": model(), "version": version()}
    return ToolExchangeReview.create("child", "wire", context(), identity, state(), 10)


def response(ticket, text=b"ok\n", change=None):
    command = ticket.plan["commands"][0]
    window = ReceiveWindow()
    window.append(text)
    envelope = {
        "id": "exchange",
        "ok": True,
        "result": {
            "plan": ticket.plan,
            "outcome": "controller_acknowledged",
            "motion_completed": False,
            "command_receipts": [
                {
                    "command": command,
                    "wire_commands": [command],
                    "connection_id": "wire",
                    "outcome": "controller_acknowledged",
                    "motion_completed": False,
                    "controller_receive_evidence": window.evidence("wire", f"{command}\n".encode(), True),
                }
            ],
        },
    }
    if change:
        change(envelope)
    raw = json.dumps(envelope).encode() + b"\n"
    return Response(envelope, "request", hashlib.sha256(raw).hexdigest(), 11, 1, raw)


def test_fixed_pocket_review_frozen_exact_context_original_ack_and_distinct_later_report():
    ticket = review()
    with pytest.raises(FrozenInstanceError):
        ticket.target = 3
    changed_plan = ticket.plan
    changed_plan["commands"] = ["M6 T4"]
    assert ticket.plan["commands"] == ["M6 T2"]
    assert ticket.authorize("child", "wire", context(), state(), 40)["parameters"] == {"tool": 2}
    retained = ticket.accept(response(ticket))
    assert retained["original_ipc_bytes_base64"]
    assert not ticket.target_reported(state(), 12, 11)
    current = state()
    current["last_machine_snapshot"]["status"]["tool"] = 2
    assert ticket.target_reported(current, 12, 11)
    assert not ticket.target_reported(current, 11.1, 11)
    assert not ticket.target_reported(current, 12, float("inf"))


@pytest.mark.parametrize(
    "change",
    [
        "target",
        "profile",
        "cutter",
        "connection",
        "session",
        "expired",
        "clock",
        "tool",
        "position",
        "model",
        "features",
        "spindle",
        "diagnostic",
        "stale",
        "transfer",
        "unknown",
        "playing",
        "partial",
    ],
)
def test_changed_or_unavailable_review_refuses_request(change):
    ticket, ctx, snapshot, session, connection, now = review(), context(), state(), "child", "wire", 11
    status = snapshot["last_machine_snapshot"]["status"]
    if change == "target":
        ctx["target"] = 3
    elif change == "profile":
        ctx["profile"]["name"] = "Different"
    elif change == "cutter":
        ctx["declared_tool_mm"]["diameter"] = 3
    elif change == "connection":
        connection = "replacement"
    elif change == "session":
        session = "replacement"
    elif change == "expired":
        now = 40.1
    elif change == "clock":
        now = float("nan")
    elif change == "tool":
        status["tool"] = 3
    elif change == "position":
        status["machine_position"]["x"] = 4
    elif change == "model":
        status["machine_model"] = 2
    elif change == "features":
        status["features"] = 6
    elif change == "spindle":
        status["spindle_target_rpm"] = 12000
    elif change == "diagnostic":
        snapshot["last_machine_snapshot"]["diagnostics"]["spindle_enabled"] = True
    elif change == "stale":
        snapshot["last_machine_snapshot_age_s"] = 1
    elif change in ("transfer", "unknown"):
        snapshot["last_machine_snapshot"]["transfer_active" if change == "transfer" else "unknown_outcome"] = True
    elif change == "partial":
        status["machine_position"]["z"] = None
    else:
        status["is_playing"] = True
    with pytest.raises(ValueError):
        ticket.authorize(session, connection, ctx, snapshot, now)


@pytest.mark.parametrize("target", [-1, 0, 1, 7, 100, True, 2.0, "2"])
def test_no_probe_manual_or_current_pocket_exchange(target):
    identity = {"session_id": "child", "connection_id": "wire", "model": model(), "version": version()}
    with pytest.raises(ValueError):
        ToolExchangeReview.create("child", "wire", {**context(), "target": target}, identity, state(), 10)


@pytest.mark.parametrize("text", [b"ok\nok\n", b"ok", b"ERROR: jam\nok\n", b"alarm: stop\nok\n", b"ok\n\x00\n"])
def test_ambiguous_failed_or_partial_original_ack_is_not_accepted(text):
    ticket = review()
    with pytest.raises(ValueError):
        ticket.accept(response(ticket, text))


def test_changed_ipc_plan_connection_or_controller_window_is_refused():
    ticket = review()
    good = response(ticket)
    forged = copy.deepcopy(good.envelope)
    forged["result"]["motion_completed"] = True
    with pytest.raises(ValueError):
        ticket.accept(replace(good, envelope=forged))
    for field, value in (("command", "M6 T4"), ("connection_id", "other")):
        changed = response(
            ticket,
            change=lambda envelope, field=field, value=value: envelope["result"]["command_receipts"][0].update(
                {field: value}
            ),
        )
        with pytest.raises(ValueError):
            ticket.accept(changed)
    altered = response(ticket, change=lambda envelope: envelope["result"].update({"plan": {"commands": ["M6 T4"]}}))
    with pytest.raises(ValueError):
        ticket.accept(altered)
