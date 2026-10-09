"""Installation preflight precedes mutations; swap failure restores recovery."""

import hashlib
import importlib.util
import json
import plistlib
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "installer", Path(__file__).parents[2] / "scripts/install_verified_macos.py"
)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def test_superseded_build_is_rejected_before_any_application_or_signature_operation(tmp_path, monkeypatch):
    from unittest.mock import Mock

    root = tmp_path / "build"
    root.mkdir()
    (root / "superseded-do-not-install.json").write_text('{"reason": "replacement source required"}')
    run = Mock()
    monkeypatch.setattr(installer.subprocess, "run", run)
    paths = [tmp_path / f"{name}.app" for name in ("target", "recovery", "staging", "failed")]
    with pytest.raises(ValueError, match="explicitly superseded"):
        installer.install(root, *paths)
    run.assert_not_called()
    assert all(not path.exists() for path in paths)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../b", "a//b", "a\\b"])
def test_manifest_path_containment(name):
    with pytest.raises(ValueError):
        installer.validate_manifest({name: "a" * 64})


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "build"
    bundle = root / "artifact/dist/source.app"
    bundle.mkdir(parents=True)
    (bundle / "bytes").write_bytes(b"new")
    (bundle / "Contents/MacOS").mkdir(parents=True)
    (bundle / "Contents/MacOS/carveracontroller").write_bytes(b"worker")
    target = tmp_path / "controller.app"
    (target / "Contents").mkdir(parents=True)
    (target / "bytes").write_bytes(b"old")
    (target / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "carveracontroller"}))
    (root / "build-request.json").write_text(
        json.dumps({"version": "2.1.0-DESKTOP182", "source_revision": "abc", "source_archive_sha256": "a" * 64})
    )
    (root / "built-verification.json").write_text(
        json.dumps(
            {
                "version": "2.1.0-DESKTOP182",
                "source_revision": "abc",
                "bundle": str(bundle),
                "signature_exit": 0,
                "mismatches": [],
            }
        )
    )
    (root / "artifact-worker-verification.json").write_text(
        json.dumps(
            {
                "version": "2.1.0-DESKTOP182",
                "source_revision": "abc",
                "source_archive_sha256": "a" * 64,
                "executable_sha256": hashlib.sha256(b"worker").hexdigest(),
                "probe": {"exit": 0, "stdin_retained": True, "file_created": False, "elapsed_s": 0.2},
            }
        )
    )
    (root / "artifact/source-manifest.json").write_text(json.dumps({"bytes": hashlib.sha256(b"new").hexdigest()}))
    monkeypatch.setattr(installer, "verify_bundle", lambda *_: None)
    monkeypatch.setattr(installer.subprocess, "check_output", lambda *_args, **_kw: "")

    def run(args, **_kw):
        if args[0] == "ditto":
            shutil.copytree(args[1], args[2])

    monkeypatch.setattr(installer.subprocess, "run", run)
    monkeypatch.setattr(installer.shutil, "disk_usage", lambda _: SimpleNamespace(free=2 * 1024**3))
    return root, target, tmp_path / "recovery.app", tmp_path / "staging.app", tmp_path / "failed.app"


def test_capacity_refusal_preserves_target_before_copy(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(installer.shutil, "disk_usage", lambda _: SimpleNamespace(free=1))
    with pytest.raises(ValueError, match="free bytes"):
        installer.install(*paths)
    assert (paths[1] / "bytes").read_bytes() == b"old"
    assert not paths[2].exists() and not paths[3].exists()


def test_post_swap_failure_restores_old_and_preserves_failed(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)

    def verify(bundle, *_):
        if bundle == paths[1]:
            raise ValueError("Injected post-swap mismatch")

    monkeypatch.setattr(installer, "verify_bundle", verify)
    with pytest.raises(ValueError, match="post-swap"):
        installer.install(*paths)
    assert (paths[1] / "bytes").read_bytes() == b"old"
    assert (paths[4] / "bytes").read_bytes() == b"new"
    receipt = json.loads((paths[0] / "artifact-verification.json").read_text())
    assert receipt["status"] == "failed" and receipt["recovery_restored"] is True


def test_success_retains_recovery_and_refuses_second_attempt(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)
    receipt = installer.install(*paths)
    assert receipt["status"] == "installed"
    assert (paths[1] / "bytes").read_bytes() == b"new"
    assert (paths[2] / "bytes").read_bytes() == b"old"
    with pytest.raises(ValueError, match="already exist"):
        installer.install(*paths)


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "missing",
        "changed",
        "escape",
        "receipt_path",
        "layout",
        "attempt_missing",
        "attempt_changed",
        "attempt_failure",
        "attempt_bundle",
        "attempt_deadline",
        "attempt_identity",
    ],
)
@pytest.mark.parametrize("layout", ["dedicated-v1", "dedicated-v2", "dedicated-v3"])
def test_dedicated_worker_identity_is_checked_before_application_copy(tmp_path, monkeypatch, mutation, layout):
    from carveracontroller.machine.artifact_fs import macos_worker_executable

    paths = fixture(tmp_path, monkeypatch)
    bundle = paths[0] / "artifact/dist/source.app"
    worker = macos_worker_executable(bundle)
    worker.parent.mkdir(parents=True)
    worker.write_bytes(b"dedicated worker")
    request_path = paths[0] / "build-request.json"
    request = json.loads(request_path.read_text())
    request["artifact_worker_layout"] = layout
    request_path.write_text(json.dumps(request))
    receipt_path = paths[0] / "artifact-worker-verification.json"
    receipt = json.loads(receipt_path.read_text())
    receipt.update(
        artifact_worker_layout=layout,
        worker_executable_relative=str(worker.relative_to(bundle)),
        worker_executable_sha256=hashlib.sha256(worker.read_bytes()).hexdigest(),
    )
    attempt_path = paths[0] / "artifact-worker-attempt.json"
    attempt = {
        **{key: value for key, value in receipt.items() if key != "probe"},
        "protocol": "first-probe-v1",
        "timeout_s": 4.0,
        "bundle": str(bundle.resolve()),
    }
    if mutation == "attempt_bundle":
        attempt["bundle"] = str(tmp_path / "other.app")
    elif mutation == "attempt_deadline":
        attempt["timeout_s"] = 30
    elif mutation == "attempt_identity":
        attempt["worker_executable_sha256"] = "a" * 64
    attempt_path.write_text(json.dumps(attempt))
    receipt["attempt_sha256"] = hashlib.sha256(attempt_path.read_bytes()).hexdigest()
    if mutation == "attempt_missing":
        attempt_path.unlink()
    elif mutation == "attempt_changed":
        attempt_path.write_text(json.dumps({**attempt, "changed": True}))
    elif mutation == "attempt_failure":
        (paths[0] / "artifact-worker-failure.json").write_text('{"status":"failed"}')
    if mutation == "missing":
        worker.unlink()
    elif mutation == "changed":
        worker.write_bytes(b"changed")
    elif mutation == "escape":
        outside = tmp_path / "outside"
        outside.write_bytes(worker.read_bytes())
        worker.unlink()
        worker.symlink_to(outside)
    elif mutation == "receipt_path":
        receipt["worker_executable_relative"] = "Contents/MacOS/carveracontroller"
    elif mutation == "layout":
        receipt["artifact_worker_layout"] = None
    receipt_path.write_text(json.dumps(receipt))
    if mutation is None:
        assert installer.install(*paths)["status"] == "installed"
    else:
        with pytest.raises(ValueError, match="worker"):
            installer.install(*paths)
        assert (paths[1] / "bytes").read_bytes() == b"old"
        assert all(not path.exists() for path in paths[2:])


def test_running_controller_prevents_copy(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        installer.subprocess, "check_output", lambda *_args, **_kw: str(paths[1] / "Contents/MacOS/controller")
    )
    with pytest.raises(ValueError, match="Quit"):
        installer.install(*paths)
    assert not paths[3].exists()


def test_pre_swap_failure_preserves_existing_bundle(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)

    def verify(bundle, *_):
        if bundle == paths[3]:
            raise ValueError("Injected staging mismatch")

    monkeypatch.setattr(installer, "verify_bundle", verify)
    with pytest.raises(ValueError, match="staging"):
        installer.install(*paths)
    assert (paths[1] / "bytes").read_bytes() == b"old"
    assert (paths[3] / "bytes").read_bytes() == b"new"
    assert not paths[2].exists()


def test_receipt_identity_mismatch_prevents_copy(tmp_path, monkeypatch):
    paths = fixture(tmp_path, monkeypatch)
    request = json.loads((paths[0] / "build-request.json").read_text())
    request["source_revision"] = "different"
    (paths[0] / "build-request.json").write_text(json.dumps(request))
    with pytest.raises(ValueError, match="requested source"):
        installer.install(*paths)
    assert not paths[3].exists()


def test_actual_verifier_rejects_manifest_symlink_escape(tmp_path):
    bundle = tmp_path / "verify.app"
    package = bundle / "Contents/Resources/carveracontroller"
    package.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.write_bytes(b"escaped")
    (package / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="escapes"):
        installer.verify_bundle(bundle, {"link": hashlib.sha256(b"escaped").hexdigest()})


@pytest.mark.parametrize(
    "mutation",
    ["missing", "revision", "archive", "version", "executable", "failure", "eof", "created", "unbounded", "nan"],
)
def test_worker_proof_refusal_preserves_installed_app(tmp_path, monkeypatch, mutation):
    paths = fixture(tmp_path, monkeypatch)
    receipt_path = paths[0] / "artifact-worker-verification.json"
    receipt = json.loads(receipt_path.read_text())
    if mutation == "missing":
        receipt_path.unlink()
    else:
        if mutation in ("revision", "archive", "version"):
            receipt[
                {"revision": "source_revision", "archive": "source_archive_sha256", "version": "version"}[mutation]
            ] = "different"
        elif mutation == "executable":
            (paths[0] / "artifact/dist/source.app/Contents/MacOS/carveracontroller").write_bytes(b"changed")
        elif mutation == "failure":
            receipt["probe"]["exit"] = 1
        elif mutation == "eof":
            receipt["probe"]["stdin_retained"] = False
        elif mutation == "created":
            receipt["probe"]["file_created"] = True
        elif mutation == "unbounded":
            receipt["probe"]["elapsed_s"] = 5
        else:
            receipt["probe"]["elapsed_s"] = float("nan")
        receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match="worker"):
        installer.install(*paths)
    assert (paths[1] / "bytes").read_bytes() == b"old"
    assert all(not path.exists() for path in paths[2:])
