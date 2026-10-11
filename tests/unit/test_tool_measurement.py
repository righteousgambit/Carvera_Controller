import copy
from dataclasses import FrozenInstanceError

import pytest

from carveracontroller.headless.tool_measurement import ToolMeasurementReview, projection
from tests.unit.test_headless_job_run import model, version
from tests.unit.test_tool_exchange import response, state

REPORT = """------------------ Measurements--------------------
TLO value from measurement 1: -21.482
TLO value from measurement 2: -21.479
TLO value from measurement 3: -21.491
------------------ Results------------------------------
Using TLO value from measurement 2: -21.479
Max delta: 0.012
Lowest cutting edge: 2, Highest cutting edge: 3
-----------------------------------------------------------
"""


def context():
    return {
        "target": 1,
        "repeats": 3,
        "tool_kind": "cutter",
        "installed_kind_asserted": True,
        "profile": {"model": "C1"},
        "assembly": {"id": "physical", "revision_id": "one"},
    }


def review():
    identity = {"session_id": "child", "connection_id": "wire", "model": model(), "version": version()}
    return ToolMeasurementReview.create("child", "wire", context(), identity, state(), 10)


def test_review_is_frozen_and_byte_qualified_printed_using_is_not_applied_offset():
    ticket = review()
    with pytest.raises(FrozenInstanceError):
        ticket.target = 2
    assert ticket.authorize("child", "wire", context(), state(), 40)["parameters"] == {
        "repeats": 3,
        "tool_kind": "cutter",
    }
    accepted = ticket.accept(response(ticket, (REPORT + "ok\n").encode()), 100)
    calibration = accepted["calibration"]
    assert calibration["report"]["measurements"] == [-21.482, -21.479, -21.491]
    assert calibration["report"]["applied"] is None
    assert calibration["printed_using_mm"] == -21.479
    assert calibration["printed_using_is_applied_tlo"] is False
    assert accepted["ipc"]["original_ipc_bytes_base64"] and accepted["command_window_sha256"]
    assert accepted["motion_completed"] is False
    assert not ticket.target_reported(state(), 11.1, 11)
    assert ticket.target_reported(state(), 12, 11)


@pytest.mark.parametrize(
    "change",
    [
        "assembly",
        "kind",
        "assertion",
        "repeats",
        "target",
        "profile",
        "session",
        "connection",
        "expired",
        "clock",
        "tool",
        "spindle",
        "stale",
        "position",
        "transfer",
        "unknown",
    ],
)
def test_changed_context_or_freshness_refuses_measurement(change):
    ticket, ctx, snapshot = review(), context(), state()
    session, connection, now = "child", "wire", 11
    status = snapshot["last_machine_snapshot"]["status"]
    if change == "assembly":
        ctx["assembly"]["revision_id"] = "new"
    elif change == "kind":
        ctx["tool_kind"] = "probe"
    elif change == "assertion":
        ctx["installed_kind_asserted"] = False
    elif change == "repeats":
        ctx["repeats"] = 4
    elif change == "target":
        ctx["target"] = 2
    elif change == "profile":
        ctx["profile"]["name"] = "new"
    elif change == "session":
        session = "new"
    elif change == "connection":
        connection = "new"
    elif change == "expired":
        now = 40.001
    elif change == "clock":
        now = float("nan")
    elif change == "tool":
        status["tool"] = 2
    elif change == "spindle":
        status["spindle_target_rpm"] = 12000
    elif change == "stale":
        snapshot["last_machine_snapshot_age_s"] = 5
    elif change == "position":
        status["machine_position"]["x"] = 6
    elif change == "transfer":
        snapshot["last_machine_snapshot"]["transfer_active"] = True
    else:
        snapshot["last_machine_snapshot"]["unknown_outcome"] = True
    with pytest.raises(ValueError):
        ticket.authorize(session, connection, ctx, snapshot, now)


@pytest.mark.parametrize(
    "text",
    [
        REPORT.replace("measurement 2: -21.479", "measurement 1: -21.479"),
        REPORT.replace("Using TLO value from measurement 2: -21.479", "Using TLO value from measurement 3: -21.491"),
        REPORT.replace("Max delta: 0.012", "Max delta: 0.090"),
        REPORT.replace("Highest cutting edge: 3", "Highest cutting edge: 2"),
        REPORT.replace("TLO value from measurement 1: -21.482", "TLO value from measurement 1: nan"),
        REPORT.replace("\nTLO value", "\rTLO value", 1),
        REPORT + REPORT,
        REPORT.replace("-----------------------------------------------------------\n", ""),
        REPORT + "ERROR: calibration failed\n",
        REPORT + "ok\n",
    ],
)
def test_partial_duplicate_conflicting_or_control_output_never_imports(text):
    ticket = review()
    with pytest.raises(ValueError):
        ticket.accept(response(ticket, (text + "ok\n").encode()), 100)


@pytest.mark.parametrize("change", ["hash", "raw", "connection", "plan", "motion", "wire"])
def test_original_ack_custody_is_required(change):
    def mutate(envelope):
        result = envelope["result"]
        receipt = result["command_receipts"][0]
        if change == "hash":
            receipt["controller_receive_evidence"]["sha256"] = "new"
        elif change == "raw":
            receipt["controller_receive_evidence"]["original_bytes_retained"] = False
        elif change == "connection":
            receipt["connection_id"] = "new"
        elif change == "plan":
            result["plan"]["commands"] = ["M491 R4"]
        elif change == "motion":
            result["motion_completed"] = True
        else:
            receipt["wire_commands"] = ["M491 R3", "M105"]

    with pytest.raises(ValueError):
        review().accept(response(review(), (REPORT + "ok\n").encode(), mutate), 100)


def test_single_pass_and_ack_without_samples_do_not_manufacture_calibration():
    ctx = context()
    ctx["repeats"] = 1
    identity = {"session_id": "child", "connection_id": "wire", "model": model(), "version": version()}
    ticket = ToolMeasurementReview.create("child", "wire", ctx, identity, state(), 10)
    assert ticket.accept(response(ticket), 100)["calibration"] is None
    assert projection(["Tool length calibrated"], 1, 100) is None
    with pytest.raises(ValueError):
        projection(REPORT.splitlines(), 1, 100)
