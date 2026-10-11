"""Startup sampling cannot become a qualification retry or alter failed evidence."""

import hashlib
import json
import plistlib
import struct
from pathlib import Path

import pytest

from scripts import diagnose_macos_helper_startup as diagnostic


def native_bytes():
    header = struct.pack("<8I", 0xFEEDFACF, 0x100000C, 0, 2, 1, 152, 0, 0)
    segment = struct.pack("<II16s4Q4I", 0x19, 152, b"__TEXT", 0, 4096, 0, 188, 7, 5, 1, 0)
    section = struct.pack("<16s16s2Q8I", b"__text", b"__TEXT", 0, 4, 184, 0, 0, 0, 0, 0, 0, 0)
    return header + segment + section + b"code"


def test_instruction_identity_ignores_signature_bytes_and_refuses_corrupt_extents(tmp_path):
    path = tmp_path / "helper"
    path.write_bytes(native_bytes() + b"old-signature")
    original = diagnostic.text_digest(path)
    path.write_bytes(native_bytes() + b"new-signature")
    assert diagnostic.text_digest(path) == original == hashlib.sha256(b"code").hexdigest()
    data = bytearray(native_bytes())
    struct.pack_into("<Q", data, 144, 1000)
    path.write_bytes(data)
    with pytest.raises(ValueError, match="instruction extent"):
        diagnostic.text_digest(path)


@pytest.fixture
def failed_package(tmp_path):
    root = tmp_path / "failed-package"
    relative = "Contents/Helpers/carvera-artifact-worker.app/Contents/MacOS/carvera-artifact-worker"
    worker = root / "artifact/dist/carveracontroller.app" / relative
    worker.parent.mkdir(parents=True)
    worker.write_bytes(native_bytes())
    plist = worker.parent.parent / "Info.plist"
    plist.write_bytes(plistlib.dumps({"CFBundleIdentifier": "dev.carvera.artifact-worker"}))
    (root / "artifact-worker-attempt.json").write_text('{"first":true}\n')
    failure = {
        "status": "failed",
        "installed": False,
        "worker_executable_relative": relative,
        "worker_executable_sha256": diagnostic.digest(worker),
        "attempt_sha256": diagnostic.digest(root / "artifact-worker-attempt.json"),
    }
    (root / "artifact-worker-failure.json").write_text(json.dumps(failure))
    return root, worker


def test_fresh_diagnostic_changes_only_copy_and_cannot_be_reused_or_qualified(failed_package, tmp_path, monkeypatch):
    root, worker = failed_package
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    calls = []

    def sign(command, **kwargs):
        calls.append(command)
        if "--force" in command:
            copied = Path(command[-1]) / "Contents/MacOS" / worker.name
            copied.write_bytes(copied.read_bytes() + b"fresh-signature")

    monkeypatch.setattr(diagnostic.subprocess, "run", sign)
    observed = []

    def observe(path, output, **kwargs):
        assert path != worker and path.is_relative_to(output)
        assert diagnostic.digest(path) != diagnostic.digest(worker)
        assert kwargs == {"sample_after": 1, "request_after": 0}
        observed.append(path)
        return {"qualification": "NOT_ATTEMPTED", "valid_check_response": True}

    monkeypatch.setattr(diagnostic, "observe", observe)
    out = tmp_path / "diagnostic"
    result = diagnostic.diagnose(root, out)
    assert result["original_receipts_unchanged"] and result["original_worker_unchanged"]
    assert result["qualification"].startswith("NOT_ATTEMPTED")
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
    assert len(calls) == 2 and len(observed) == 1
    assert calls[0][1:4] == ["--force", "--sign", "-"]
    assert not (out / "artifact-worker-verification.json").exists()
    assert not (out / "build-request.json").exists()
    from scripts.install_verified_macos import worker_preflight

    with pytest.raises(ValueError, match="verification required"):
        worker_preflight(out, out / "diagnostic.app", {})
    with pytest.raises(FileExistsError):
        diagnostic.diagnose(root, out)
    assert len(observed) == 1


@pytest.mark.parametrize("change", ["nested", "worker", "attempt"])
def test_changed_identity_or_original_package_destination_refused(failed_package, tmp_path, change):
    root, worker = failed_package
    output = tmp_path / "diagnostic"
    if change == "nested":
        output = root / "diagnostic"
    elif change == "worker":
        worker.write_bytes(b"changed")
    else:
        (root / "artifact-worker-attempt.json").write_text("changed")
    with pytest.raises(ValueError):
        diagnostic.diagnose(root, output)
    assert not output.exists()


def shell(tmp_path, source):
    path = tmp_path / "fixture-helper"
    path.write_text("#!/bin/sh\n" + source)
    path.chmod(0o700)
    return path


def test_observation_retains_writer_and_only_fixed_stages(tmp_path):
    worker = shell(
        tmp_path,
        "read line\nprintf 'private-diagnostic-value\\nCARVERA_STARTUP main_entered\\n' >&2\nprintf '{\"result\":{},\"error\":null}'\n",
    )
    result = diagnostic.observe(worker, tmp_path, timeout=20, sample_after=19)
    assert result["valid_check_response"] and result["request_sent"]
    assert result["cleanup_exit"] == 0 and not result["file_created"]
    assert [s["stage"] for s in result["startup_stages"]] == ["main_entered"]
    assert "private-diagnostic-value" not in json.dumps(result)
    assert result["qualification"] == "NOT_ATTEMPTED"


def test_sampler_targets_owned_child_and_timeout_retains_evidence(tmp_path, monkeypatch):
    worker = shell(tmp_path, "read line\nprintf 'CARVERA_STARTUP main_entered\\n' >&2\nread another_line\n")
    original = diagnostic.subprocess.Popen
    samplers = []

    def popen(command, **kwargs):
        if command[0] == "/usr/bin/sample":
            samplers.append(command)
            return original(["/usr/bin/true"], **kwargs)
        return original(command, **kwargs)

    monkeypatch.setattr(diagnostic.subprocess, "Popen", popen)
    result = diagnostic.observe(worker, tmp_path, timeout=3, sample_after=0.01)
    assert result["timed_out"] and result["kill_requested"]
    assert result["sample_requested"] and result["sample_exit"] == 0
    assert samplers[0][1] == str(result["child_pid"])
    assert "-mayDie" in samplers[0]
    assert result["cleanup_exit"] is not None
    assert result["response_bytes"] == 0 and result["qualification"] == "NOT_ATTEMPTED"
    assert not result["sample_captured"]  # Tool exit0 alone is not a captured stack.
    assert (tmp_path / "sample-tool.log").exists()


def test_shared_stage_tokens_match_native_source():
    native = (Path(__file__).parents[2] / "carveracontroller/machine/artifact_fs_worker_macos.m").read_text()
    for stage in diagnostic.STARTUP_STAGES:
        assert 'startupStage("CARVERA_STARTUP ' + stage + '\\n");' in native


def test_diagnostic_input_delay_is_explicit_and_not_a_qualification(tmp_path):
    worker = shell(
        tmp_path,
        "printf 'CARVERA_STARTUP main_entered\\n' >&2\nread line\nprintf 'CARVERA_STARTUP request_read\\n' >&2\nprintf '{\"result\":{},\"error\":null}'\n",
    )
    result = diagnostic.observe(worker, tmp_path, timeout=10, sample_after=9, request_after=0.25)
    assert result["request_withheld_s"] == 0.25 and result["request_sent_elapsed_s"] >= 0.25
    assert result["valid_check_response"] and result["cleanup_exit"] == 0
    assert result["qualification"] == "NOT_ATTEMPTED"
    read = next(row for row in result["startup_stages"] if row["stage"] == "request_read")
    assert read["observed_elapsed_s"] >= 0.25
