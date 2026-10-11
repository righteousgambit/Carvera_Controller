import base64
import copy

import pytest

from carveracontroller.headless.client import Response
from carveracontroller.headless.job_file import JobFile, context_digest
from carveracontroller.headless.job_identity import reported_identity, supported_identity
from carveracontroller.headless.job_run import JobRun
from carveracontroller.headless.operations import compile_operation
from carveracontroller.headless.telemetry import parse_status
from carveracontroller.headless.wire_evidence import ReceiveWindow
from carveracontroller.machine.setup_readiness import GROUPS, fingerprint


def query_result(query, text, connection="wire"):
    window = ReceiveWindow()
    window.append(text)
    receipt = {
        "command": query,
        "connection_id": connection,
        "outcome": "controller_acknowledged",
        "motion_completed": False,
        "wire_commands": [query, "M105"],
        "controller_receive_evidence": window.evidence(connection, f"{query}\nM105\n".encode(), True),
    }
    return {
        "plan": compile_operation("observe.query", {"query": query}),
        "outcome": "controller_acknowledged",
        "motion_completed": False,
        "command_receipts": [receipt],
    }


def model():
    return reported_identity(query_result("model", b"model = C1, 1, 4, 1\nok\n"), "model", "wire")


def version():
    return reported_identity(query_result("version", b"version = 2.1.0c\nok\n"), "version", "wire")


def context():
    snapshots = {key: {"group": key} for key in GROUPS}
    return {
        "machine_id": "machine",
        "profile": {"id": "machine", "model": "C1"},
        "setup": snapshots,
        "present": dict.fromkeys(GROUPS, True),
        "evidence": [
            {
                "key": key,
                "state": "measured",
                "receipt": {
                    "machine_id": "machine",
                    "group": key,
                    "fingerprint": fingerprint(snapshots[key]),
                    "source": "operator",
                    "method": "native fixture",
                    "measured_at": 50,
                    "expires_at": 1000,
                },
            }
            for key in GROUPS
        ],
    }


def state(mode="Idle", playing=0):
    status = parse_status(f"<{mode}|MPos:1,2,3|WPos:4,5,6|C:1,4,0,1|S:0,0,100|T:1,12|G:0|P:0,0,0,{playing}>")
    return {
        "ready": True,
        "running": True,
        "last_machine_snapshot_age_s": 0.1,
        "last_machine_snapshot": {
            "connection_id": "wire",
            "connected": True,
            "unknown_outcome": False,
            "transfer_active": False,
            "status_age_ms": 100,
            "status": status,
        },
    }


def ticket(ctx=None):
    ctx = context() if ctx is None else ctx
    file = JobFile("/tmp/program.nc", b"G21\nG90\nM5\n", context_digest(ctx), "child", "wire")
    file.phase = "reviewed"
    file.launch_plan = compile_operation("job.start", {"path": file.remote_path})
    identity = {"model": model(), "version": version(), "session_id": "child", "connection_id": "wire"}
    return JobRun(file, ctx, identity, state(), 10, 100)


def acknowledgment(run, operation):
    plan = compile_operation(operation, {"path": run.file.remote_path} if operation == "job.start" else {})
    command = plan["commands"][0]
    window = ReceiveWindow()
    window.append(b"ok\n")
    receipt = {
        "wire_commands": [command, "M105"],
        "controller_receive_evidence": window.evidence("wire", f"{command}\nM105\n".encode(), True),
        "command": command,
        "connection_id": "wire",
        "outcome": "controller_acknowledged",
        "motion_completed": False,
    }
    return Response(
        {
            "id": operation,
            "ok": True,
            "result": {
                "outcome": "controller_acknowledged",
                "motion_completed": False,
                "plan": plan,
                "command_receipts": [receipt],
            },
        },
        "request-hash",
        "response-hash",
        1,
        3,
    )


def test_reported_identity_comes_from_original_receipts_without_authentication_claim():
    assert supported_identity(model(), version(), state()["last_machine_snapshot"]["status"])
    assert model()["authenticated"] is False and version()["authenticated"] is False
    assert not supported_identity({**model(), "model_code": 0}, version(), state()["last_machine_snapshot"]["status"])
    assert not supported_identity(
        model(), {**version(), "reported_version": "2.2.0"}, state()["last_machine_snapshot"]["status"]
    )


@pytest.mark.parametrize(
    "raw",
    [
        b"version = 2.1.0c\nversion = 2.1.0c\nok\n",
        b"version = 2.1.0c\nERROR: mismatch\nok\n",
        b"version = 2.1.0c\nok\nok\n",
        b"version = 2.1.0c\nok",
        b"version = 2.1.0c\nother prose\nok\n",
    ],
)
def test_mixed_duplicate_partial_or_conflicting_original_identity_refuses(raw):
    with pytest.raises(ValueError):
        reported_identity(query_result("version", raw), "version", "wire")


@pytest.mark.parametrize("change", ["hash", "planned", "connection", "custody", "physical", "normalized"])
def test_identity_original_custody_and_bound_query_are_required(change):
    result = query_result("model", b"model = C1, 1, 4, 1\nok\n")
    receipt = result["command_receipts"][0]
    window = receipt["controller_receive_evidence"]
    if change == "hash":
        window["sha256"] = "changed"
    elif change == "planned":
        window["planned_command_bytes_base64"] = base64.b64encode(b"version\nM105\n").decode()
    elif change == "connection":
        receipt["connection_id"] = "replacement"
    elif change == "custody":
        window["original_bytes_retained"] = False
    elif change == "physical":
        window["physical_accuracy_verified"] = True
    else:
        del receipt["controller_receive_evidence"]
    with pytest.raises(ValueError):
        reported_identity(result, "model", "wire")


def test_review_start_acknowledgment_observed_play_pause_resume_cancel_and_settled_are_distinct():
    run = ticket()
    params = run.authorize("job.start", "child", state(), context(), 11, 100)
    assert params["parameters"]["path"] == run.file.remote_path and run.phase == "start_pending"
    run.accept("job.start", acknowledgment(run, "job.start"))
    assert run.phase == "start_acknowledged" and run.record()["motion_completed"] is False
    run.observe(state())
    assert run.phase == "start_acknowledged"
    run.observe(state("Run", 1))
    assert run.phase == "playing_reported"
    run.authorize("job.pause", "child", state("Run", 1), context(), 12, 100)
    run.accept("job.pause", acknowledgment(run, "job.pause"))
    run.observe(state("Pause", 1))
    assert run.phase == "paused_reported"
    run.authorize("job.resume", "child", state("Pause", 1), context(), 13, 100)
    run.accept("job.resume", acknowledgment(run, "job.resume"))
    run.observe(state("Run", 1))
    run.authorize("job.cancel", "child", state("Run", 1), context(), 14, 100)
    run.accept("job.cancel", acknowledgment(run, "job.cancel"))
    run.observe(state())
    assert run.phase == "settled_reported" and run.record()["physical_setup_verified"] is False


@pytest.mark.parametrize(
    "change",
    [
        "context",
        "expired_review",
        "expired_measurement",
        "connection",
        "child",
        "stale",
        "unknown",
        "position",
        "wcs",
        "tool",
        "playing",
        "rpm",
    ],
)
def test_start_refuses_changed_expired_or_unresolved_admission_without_mutating_to_pending(change):
    run = ticket()
    ctx, report, session, now, utc = context(), state(), "child", 11, 100
    status = report["last_machine_snapshot"]["status"]
    if change == "context":
        ctx["setup"]["stock"] = {"changed": True}
    elif change == "expired_review":
        now = 41
    elif change == "expired_measurement":
        utc = 1000
    elif change == "connection":
        report["last_machine_snapshot"]["connection_id"] = "new"
    elif change == "child":
        session = "new"
    elif change == "stale":
        report["last_machine_snapshot_age_s"] = 2
    elif change == "unknown":
        report["last_machine_snapshot"]["unknown_outcome"] = True
    elif change == "position":
        status["machine_position"]["x"] = 999
    elif change == "wcs":
        status["active_wcs"] = 2
    elif change == "tool":
        status["tool"] = 2
    elif change == "playing":
        status["is_playing"] = True
    else:
        status["spindle_rpm"] = 1000
    with pytest.raises(ValueError):
        run.authorize("job.start", session, report, ctx, now, utc)
    assert run.phase == "review"


def test_same_review_cannot_start_twice_and_unresolved_response_cannot_resume():
    run = ticket()
    run.authorize("job.start", "child", state(), context(), 11, 100)
    with pytest.raises(ValueError):
        run.authorize("job.start", "child", state(), context(), 11, 100)
    wrong = copy.deepcopy(acknowledgment(run, "job.start"))
    wrong.envelope["result"]["command_receipts"][0]["connection_id"] = "other"
    with pytest.raises(ValueError):
        run.accept("job.start", wrong)
    assert run.phase == "unresolved"
    with pytest.raises(ValueError):
        run.authorize("job.resume", "child", state("Pause", 1), context(), 12, 100)


@pytest.mark.parametrize("change", ["window_hash", "planned", "missing_original", "duplicate_ack", "bool_plan"])
def test_run_ack_requires_original_bound_bytes_and_exact_typed_plan(change):
    run = ticket()
    run.authorize("job.start", "child", state(), context(), 11, 100)
    response = acknowledgment(run, "job.start")
    receipt = response.envelope["result"]["command_receipts"][0]
    if change == "window_hash":
        receipt["controller_receive_evidence"]["sha256"] = "changed"
    elif change == "planned":
        receipt["controller_receive_evidence"]["planned_command_bytes_base64"] = base64.b64encode(
            b"abort\nM105\n"
        ).decode()
    elif change == "missing_original":
        del receipt["controller_receive_evidence"]
    elif change == "duplicate_ack":
        window = ReceiveWindow()
        window.append(b"ok\nok\n")
        command = receipt["command"]
        receipt["controller_receive_evidence"] = window.evidence("wire", f"{command}\nM105\n".encode(), True)
    else:
        response.envelope["result"]["plan"]["motion_completed"] = 0
    with pytest.raises(ValueError):
        run.accept("job.start", response)
    assert run.phase == "unresolved"


def test_cached_pretransition_status_does_not_erase_pause_resume_or_cancel_acknowledgment():
    run = ticket()
    run.authorize("job.start", "child", state(), context(), 11, 100)
    run.accept("job.start", acknowledgment(run, "job.start"))
    run.observe(state("Run", 1))
    run.authorize("job.pause", "child", state("Run", 1), context(), 12, 100)
    run.accept("job.pause", acknowledgment(run, "job.pause"))
    run.observe(state("Run", 1))
    assert run.phase == "pause_acknowledged"
    run.observe(state("Pause", 1))
    run.authorize("job.resume", "child", state("Pause", 1), context(), 13, 100)
    run.accept("job.resume", acknowledgment(run, "job.resume"))
    run.observe(state("Pause", 1))
    assert run.phase == "resume_acknowledged"
    run.observe(state("Run", 1))
    run.authorize("job.cancel", "child", state("Run", 1), context(), 14, 100)
    with pytest.raises(ValueError):
        run.authorize("job.cancel", "child", state("Run", 1), context(), 14, 100)
    run.accept("job.cancel", acknowledgment(run, "job.cancel"))
    run.observe(state("Run", 1))
    assert run.phase == "cancel_acknowledged"
    run.observe(state())
    assert run.phase == "settled_reported"


@pytest.mark.parametrize("index", range(9))
def test_reported_wcs_supports_actual_zero_based_g54_through_g59_3(index):
    run = ticket()
    snapshot = state()
    snapshot["last_machine_snapshot"]["status"]["active_wcs"] = index
    run._require_idle(snapshot)
