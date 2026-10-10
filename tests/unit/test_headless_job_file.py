import base64
import hashlib
from dataclasses import FrozenInstanceError

import pytest

from carveracontroller.headless.client import Response
from carveracontroller.headless.job_file import JobFile, context_digest
from carveracontroller.headless.operations import compile_operation


def job():
    return JobFile("/tmp/program.nc", b"G21\r\nG90\nM5\n", context_digest({"setup": 1}), "child", "wire")


def reply(file, action, **changes):
    result = {
        "outcome": "transfer_acknowledged",
        "direction": action,
        "path": file.remote_path,
        "size": len(file.data),
        "sha256": file.sha256,
        "md5": hashlib.md5(file.data).hexdigest(),
        "completion": f"Info: {action} success: {file.remote_path}.",
        "readback_verified": False,
    }
    if action == "download":
        result["data_base64"] = base64.b64encode(file.data).decode()
    result.update(changes)
    return Response({"id": "request", "ok": True, "result": result}, "request-hash", "reply-hash", 1, 3)


def uploaded():
    file = job()
    params = file.begin("upload")
    assert base64.b64decode(params["data_base64"]) == file.data
    file.accept("upload", reply(file, "upload"))
    return file


def test_exact_bytes_independent_readback_and_closed_launch_plan_are_separate_gates():
    file = uploaded()
    assert file.phase == "uploaded" and file.launch_plan is None
    assert file.remote_path == f"/sd/gcodes/job-{hashlib.sha256(file.data).hexdigest()}.nc"
    with pytest.raises(ValueError):
        file.begin("compile")
    file.begin("download")
    file.accept("download", reply(file, "download"))
    assert file.phase == "verified" and file.receipts[-1]["outcome"] == "exact_bytes_readback_verified"
    params = file.begin("compile")
    assert params == {"operation": "job.start", "parameters": {"path": file.remote_path}}
    plan = compile_operation(params["operation"], params["parameters"])
    file.accept("compile", Response({"id": "compile", "ok": True, "result": plan}, "a", "b", 1, 3))
    assert file.phase == "reviewed" and file.launch_plan == plan
    assert file.record()["execution_admitted"] is False and file.record()["motion_completed"] is False
    assert file.receipts[-1]["outcome"] == "plan_compiled_only"


@pytest.mark.parametrize(
    "changes",
    [
        {"path": "/sd/gcodes/other.nc"},
        {"sha256": "wrong"},
        {"size": True},
        {"size": 2},
        {"md5": "wrong"},
        {"direction": "download"},
        {"readback_verified": True},
        {"outcome": "sent_unacknowledged"},
        {"completion": "Info: upload success: /sd/gcodes/other.nc."},
    ],
)
def test_wrong_transfer_receipt_is_retained_unresolved_and_never_replayed(changes):
    file = job()
    file.begin("upload")
    with pytest.raises(ValueError):
        file.accept("upload", reply(file, "upload", **changes))
    assert file.phase == "unresolved" and len(file.receipts) == 1
    with pytest.raises(ValueError):
        file.begin("upload")
    with pytest.raises(ValueError):
        file.begin("download")


@pytest.mark.parametrize("encoded", ["***", "", base64.b64encode(b"changed bytes").decode(), None])
def test_download_metadata_never_substitutes_for_the_actual_returned_bytes(encoded):
    file = uploaded()
    file.begin("download")
    with pytest.raises(ValueError):
        file.accept("download", reply(file, "download", data_base64=encoded))
    assert file.phase == "unresolved"


def test_source_is_immutable_and_context_or_child_replacement_invalidates_binding():
    file = job()
    with pytest.raises(FrozenInstanceError):
        file.program.data = b"different"
    assert file.matches("child", "wire", {"setup": 1})
    assert not file.matches("child-new", "wire", {"setup": 1})
    assert not file.matches("child", "wire-new", {"setup": 1})
    assert not file.matches("child", "wire", {"setup": 2})


@pytest.mark.parametrize("data", [b"", b"G21\0", b"\xff", b"x" * (8 * 1024 * 1024 + 1)])
def test_file_bounds_and_encoding_are_enforced_before_any_machine_submission(data):
    with pytest.raises((ValueError, UnicodeError)):
        JobFile("/tmp/program.nc", data, context_digest({}), "child", "wire")


def test_refusal_and_transport_loss_never_imply_verification():
    file = job()
    file.begin("upload")
    with pytest.raises(ValueError):
        file.accept("upload", Response({"id": "x", "ok": False, "error": {"code": "unknown_outcome"}}, "a", "b", 1, 1))
    assert file.receipts[-1]["error"] == {"code": "unknown_outcome"}
    other = job()
    other.begin("upload")
    other.fail("upload", ConnectionError("lost"))
    assert other.phase == "unresolved" and other.receipts[-1]["error_type"] == "ConnectionError"


@pytest.mark.parametrize(
    "change",
    [{"commands": ["play /sd/gcodes/other.nc"]}, {"profile_id": "other"}, {"read_only": True}, {"motion_completed": 0}],
)
def test_review_requires_the_exact_typed_closed_plan(change):
    file = uploaded()
    file.begin("download")
    file.accept("download", reply(file, "download"))
    params = file.begin("compile")
    plan = compile_operation(params["operation"], params["parameters"])
    plan.update(change)
    with pytest.raises(ValueError):
        file.accept("compile", Response({"id": "compile", "ok": True, "result": plan}, "a", "b", 1, 3))
    assert file.phase == "unresolved" and file.launch_plan is None
