import hashlib
import json
import sys
from pathlib import Path

import pytest

from scripts.verify_artifact_worker import probe


@pytest.mark.parametrize("mutation", [None, "changed", "layout", "escape"])
def test_verifier_probes_exact_dedicated_helper_not_desktop_entry(tmp_path, monkeypatch, mutation):
    from unittest.mock import Mock

    from carveracontroller.machine.artifact_fs import macos_worker_executable
    from scripts import verify_artifact_worker as verifier

    bundle = tmp_path / "artifact/dist/carveracontroller.app"
    desktop = bundle / "Contents/MacOS/carveracontroller"
    desktop.parent.mkdir(parents=True)
    desktop.write_bytes(b"desktop executable")
    helper = macos_worker_executable(bundle)
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"dedicated executable")
    request = {
        "source_revision": "a" * 40,
        "source_archive_sha256": "b" * 64,
        "version": "2.1.0-TEST",
        "artifact_worker_layout": "dedicated-v1",
    }
    prior = {
        **request,
        "mismatches": [],
        "strict_signature_verified": True,
        "signature_exit": 0,
        "worker_executable_sha256": hashlib.sha256(helper.read_bytes()).hexdigest(),
    }
    if mutation == "changed":
        helper.write_bytes(b"changed executable")
    elif mutation == "layout":
        prior["artifact_worker_layout"] = None
    elif mutation == "escape":
        outside = tmp_path / "outside"
        outside.write_bytes(helper.read_bytes())
        helper.unlink()
        helper.symlink_to(outside)
    (tmp_path / "build-request.json").write_text(json.dumps(request))
    (tmp_path / "built-verification.json").write_text(json.dumps(prior))
    (tmp_path / "artifact/source-manifest.json").write_text(json.dumps({"file.py": "c" * 64}))
    monkeypatch.setattr(verifier, "verify_bundle", lambda *_: None)
    run = Mock(return_value={"elapsed_s": 0.2, "exit": 0, "stdin_retained": True, "file_created": False})
    monkeypatch.setattr(verifier, "probe", run)
    if mutation is None:
        receipt = verifier.verify(tmp_path)
        run.assert_called_once_with([str(helper)])
        assert receipt["worker_executable_relative"] == str(helper.relative_to(bundle))
        assert receipt["executable_sha256"] == hashlib.sha256(desktop.read_bytes()).hexdigest()
    else:
        with pytest.raises(ValueError, match="worker|Worker"):
            verifier.verify(tmp_path)
        run.assert_not_called()
        assert not (tmp_path / "artifact-worker-verification.json").exists()


def test_actual_worker_answers_and_exits_with_retained_writer():
    worker = Path(__file__).parents[2] / "carveracontroller/machine/artifact_fs.py"
    result = probe([sys.executable, str(worker)])
    assert result["exit"] == 0 and result["stdin_retained"] and not result["file_created"]


def test_eof_dependent_worker_fails_bounded_probe():
    code = 'import sys; sys.stdin.buffer.read(); print(\'{"result": {}, "error": null}\')'
    with pytest.raises(ValueError, match="stdin remained open"):
        probe([sys.executable, "-c", code], timeout=0.2)


@pytest.mark.parametrize("code", ["print('invalid')", "print('{}')", "raise SystemExit(1)", "print('x'*70000)"])
def test_bad_response_never_becomes_package_proof(code):
    with pytest.raises((ValueError, UnicodeDecodeError)):
        probe([sys.executable, "-c", code])
