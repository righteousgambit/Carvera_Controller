from dataclasses import FrozenInstanceError

import pytest

from carveracontroller.headless.atc_offset import AtcOffsetObservation, AtcOffsetRead
from tests.unit.test_headless_job_run import model, version
from tests.unit.test_tool_exchange import response, state
from tests.unit.test_tool_measurement import context

LINE = b"tool:1 ref:-10.000 cur:-31.479 offset:-21.491\nok\n"


def read():
    identity = {"session_id": "child", "connection_id": "wire", "model": model(), "version": version()}
    return AtcOffsetRead.create("child", "wire", context(), identity, state(), 10)


def test_original_query_values_and_reference_are_separate_from_full_robot_compensation():
    ticket = read()
    assert ticket.authorize("child", "wire", context(), state(), 40) == {
        "operation": "observe.query",
        "parameters": {"query": "M499"},
    }
    plan = ticket.plan
    plan["commands"].append("M493.3 Z0")
    assert ticket.plan["commands"] == ["M499"]
    with pytest.raises(FrozenInstanceError):
        ticket.target = 2
    result = ticket.accept(response(ticket, LINE))
    assert result["atc_offset_mm"] == -21.491 and result["current_mz_mm"] == -31.479
    assert result["reference_mz_mm"] == -10
    assert result["reported_resolution_mm"] == 0.001
    for flag in (
        "applied_robot_offset_verified",
        "physical_accuracy_verified",
        "command_attribution_verified",
        "firmware_authenticated",
    ):
        assert result[flag] is False
    assert result["ipc"]["original_ipc_bytes_base64"] and result["command_window_sha256"]


@pytest.mark.parametrize(
    "text",
    [
        b"ok\n",
        LINE + LINE,
        LINE.replace(b"tool:1", b"tool:2"),
        LINE.replace(b"ref:-10.000", b"ref:nan"),
        LINE.replace(b"offset:-21.491", b"offset:1001.000"),
        LINE.replace(b"cur:-31.479", b"cur:-31.4790"),
        LINE.replace(b"\n", b"\r", 1),
        LINE[:-1],
        LINE + b"ERROR: failed\n",
        LINE + b"Unknown\n",
        b"Tool:1 ref:-10.000 cur:-31.479 offset:-21.491\nok\n",
    ],
)
def test_incomplete_ambiguous_conflicting_or_non_source_query_refuses(text):
    with pytest.raises(ValueError):
        read().accept(response(read(), text))


@pytest.mark.parametrize("change", ["raw", "hash", "plan", "motion", "connection", "wire"])
def test_original_query_custody_cannot_be_substituted(change):
    reply = response(read(), LINE)
    if change == "raw":
        object.__setattr__(reply, "original_line", reply.original_line + b" ")
    elif change == "hash":
        object.__setattr__(reply, "response_sha256", "0" * 64)
    else:

        def mutate(envelope):
            r = envelope["result"]
            if change == "plan":
                r["plan"]["commands"] = ["M493.4"]
            elif change == "motion":
                r["motion_completed"] = True
            elif change == "connection":
                r["command_receipts"][0]["connection_id"] = "other"
            else:
                r["command_receipts"][0]["wire_commands"] = ["M499", "M105"]

        reply = response(read(), LINE, mutate)
    with pytest.raises(ValueError):
        read().accept(reply)


@pytest.mark.parametrize(
    "change",
    [
        "session",
        "connection",
        "profile",
        "context",
        "tool",
        "spindle",
        "position",
        "stale",
        "unknown",
        "expiry",
        "clock",
    ],
)
def test_final_admission_rechecks_owner_context_fresh_state_and_deadline(change):
    ticket, ctx, snapshot, session, connection, now = read(), context(), state(), "child", "wire", 11
    status = snapshot["last_machine_snapshot"]["status"]
    if change == "session":
        session = "replacement"
    elif change == "connection":
        connection = "replacement"
    elif change == "profile":
        ctx["profile"]["model"] = "CA1"
    elif change == "context":
        ctx["assembly"]["revision_id"] = "changed"
    elif change == "tool":
        status["tool"] = 2
    elif change == "spindle":
        status["spindle_target_rpm"] = 12000
    elif change == "position":
        status["machine_position"]["x"] = 100
    elif change == "stale":
        snapshot["last_machine_snapshot_age_s"] = 5
    elif change == "unknown":
        snapshot["last_machine_snapshot"]["unknown_outcome"] = True
    elif change == "expiry":
        now = 40.001
    else:
        now = float("nan")
    with pytest.raises(ValueError):
        ticket.authorize(session, connection, ctx, snapshot, now)


def test_receipt_is_immutable_and_only_fresh_on_exact_profile_connection_and_tool():
    receipt = AtcOffsetObservation.retained(read(), response(read(), LINE), context()["profile"])
    value = receipt.receipt
    value["atc_offset_mm"] = 500
    assert receipt.receipt["atc_offset_mm"] == -21.491
    assert receipt.fresh_for(("child", "wire"), context()["profile"], 1, 11.8)
    for owner, profile, tool, clock in [
        (("child", "new"), context()["profile"], 1, 11.1),
        (("child", "wire"), {"model": "CA1"}, 1, 11.1),
        (("child", "wire"), context()["profile"], 2, 11.1),
        (("child", "wire"), context()["profile"], 1, 11.801),
        (("child", "wire"), context()["profile"], 1, 10.9),
        (("child", "wire"), context()["profile"], 1, float("nan")),
    ]:
        assert not receipt.fresh_for(owner, profile, tool, clock)


@pytest.mark.parametrize("change", ["probe", "identity", "model", "clock"])
def test_unsupported_identity_probe_and_unknown_query_clock_are_refused(change):
    ctx, snapshot = context(), state()
    identity = {"session_id": "child", "connection_id": "wire", "model": model(), "version": version()}
    now = 10
    if change == "probe":
        ctx["target"] = snapshot["last_machine_snapshot"]["status"]["tool"] = 0
    elif change == "identity":
        identity["version"]["reported_version"] = "unknown"
    elif change == "model":
        identity["model"]["reported_model"] = "CA1"
    else:
        now = float("inf")
    with pytest.raises(ValueError):
        AtcOffsetRead.create("child", "wire", ctx, identity, snapshot, now)


def test_retained_tool_observation_cannot_relabel_expired_query_as_fresh():
    from carveracontroller.desktop_tool_observation import ToolObservation

    receipt = AtcOffsetObservation.retained(read(), response(read(), LINE), context()["profile"])
    observation = ToolObservation(True, tool=1, current=True, atc_offset=receipt)
    row = {"controller_tool": 1, "controller_applicable": []}
    assert "independent fresh M499" in observation.compare_offset(row, 11.5)["detail"]
    assert "independent fresh M499" not in observation.compare_offset(row, 11.801)["detail"]
    assert (
        "independent fresh M499"
        not in observation.compare_offset({"controller_tool": 2, "controller_applicable": []}, 11.5)["detail"]
    )
    assert observation.compare_offset(row, 11.5)["reported_mm"] is None
    assert observation.pose is None
