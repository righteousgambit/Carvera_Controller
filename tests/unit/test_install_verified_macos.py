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


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../b", "a//b", "a\\b"])
def test_manifest_path_containment(name):
    with pytest.raises(ValueError):
        installer.validate_manifest({name: "a" * 64})


def fixture(tmp_path, monkeypatch):
    root = tmp_path / "build"
    bundle = root / "artifact/dist/source.app"
    bundle.mkdir(parents=True)
    (bundle / "bytes").write_bytes(b"new")
    target = tmp_path / "controller.app"
    (target / "Contents").mkdir(parents=True)
    (target / "bytes").write_bytes(b"old")
    (target / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": "carveracontroller"}))
    (root / "build-request.json").write_text(json.dumps({"version": "2.1.0-DESKTOP182", "source_revision": "abc"}))
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
