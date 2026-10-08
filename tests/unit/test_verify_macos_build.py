import hashlib
import io
import json
import plistlib
import subprocess
import sys
import tarfile

import pytest

from scripts import verify_macos_build as verifier


def fixture(tmp_path, translation=False, worker=False):
    root = tmp_path / "build"
    root.mkdir()
    archive = root / "source.tar"
    sources = {"__version__.py": b"old version", "controller.py": b"print('frozen')\n"}
    if worker:
        sources["machine/artifact_fs.py"] = b"worker source\n"
    if translation:
        sources["locales/en/LC_MESSAGES/controller.po"] = (
            b'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\nmsgid "Hello"\nmsgstr "Hi"\n'
        )
    with tarfile.open(archive, "w") as tar:
        for name, data in sources.items():
            member = tarfile.TarInfo("carveracontroller/" + name)
            member.size = len(data)
            tar.addfile(member, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    revision = "a" * 40
    version = "2.1.0-DESKTOP219"
    request = {"source_revision": revision, "source_archive_sha256": digest, "version": version}
    (root / "build-request.json").write_text(json.dumps(request))
    expected = verifier.archive_sources(archive, version)
    bundle = root / "artifact/dist/carveracontroller.app"
    package = bundle / "Contents/Resources/carveracontroller"
    package.mkdir(parents=True)
    for name, data in expected.items():
        (package / name).parent.mkdir(parents=True, exist_ok=True)
        (package / name).write_bytes(data)
    (bundle / "Contents/Info.plist").write_bytes(
        plistlib.dumps({"CFBundleIdentifier": "carveracontroller", "CFBundleShortVersionString": "2.1.0"})
    )
    (root / "artifact/source-manifest.json").write_text(
        json.dumps({n: hashlib.sha256(d).hexdigest() for n, d in expected.items()})
    )
    return root, revision, digest


@pytest.mark.parametrize("mutation", [None, "missing", "escape", "source", "layout"])
def test_dedicated_helper_is_bound_to_frozen_source_before_receipt(tmp_path, monkeypatch, mutation):
    from carveracontroller.machine.artifact_fs import macos_worker_executable

    root, revision, digest = fixture(tmp_path, worker=True)
    bundle = root / "artifact/dist/carveracontroller.app"
    helper = macos_worker_executable(bundle)
    helper.parent.mkdir(parents=True)
    helper.write_bytes(b"compiled worker")
    worker_source = helper.parent.parent / "Resources/worker-source.py"
    worker_source.parent.mkdir()
    worker_source.write_bytes(b"worker source\n")
    request_path = root / "build-request.json"
    request = json.loads(request_path.read_text())
    request["artifact_worker_layout"] = "wrong" if mutation == "layout" else "dedicated-v1"
    request_path.write_text(json.dumps(request))
    monkeypatch.setattr(verifier, "verify_bundle", lambda *_: None)
    if mutation == "missing":
        helper.unlink()
    elif mutation == "escape":
        outside = tmp_path / "outside"
        outside.write_bytes(helper.read_bytes())
        helper.unlink()
        helper.symlink_to(outside)
    elif mutation == "source":
        worker_source.write_bytes(b"wrong source")
    if mutation is None:
        result = verifier.verify(root, revision, digest)
        assert result["worker_executable_sha256"] == hashlib.sha256(helper.read_bytes()).hexdigest()
    else:
        with pytest.raises(ValueError, match="worker"):
            verifier.verify(root, revision, digest)
        assert not (root / "built-verification.json").exists()


def test_verifier_uses_archive_not_mutable_checkout_and_receipt_is_exclusive(tmp_path, monkeypatch):
    root, revision, digest = fixture(tmp_path)
    (root / "checkout").mkdir()
    (root / "checkout/controller.py").write_text("untrusted checkout")
    monkeypatch.setattr(verifier, "verify_bundle", lambda *_: None)
    result = verifier.verify(root, revision, digest)
    assert result["files"] == 2 and result["source_archive_sha256"] == digest and result["installed"] is False
    with pytest.raises(ValueError, match="receipt exists"):
        verifier.verify(root, revision, digest)


@pytest.mark.parametrize("mutation", ["archive", "request", "manifest", "package"])
def test_corruption_refuses_receipt_without_modifying_build(tmp_path, monkeypatch, mutation):
    root, revision, digest = fixture(tmp_path)
    monkeypatch.setattr(verifier.subprocess, "run", lambda *_args, **_kwargs: None)
    if mutation == "archive":
        (root / "source.tar").write_bytes(b"wrong bytes")
    elif mutation == "request":
        request = json.loads((root / "build-request.json").read_text())
        request["source_revision"] = "b" * 40
        (root / "build-request.json").write_text(json.dumps(request))
    elif mutation == "manifest":
        (root / "artifact/source-manifest.json").write_text(json.dumps({"controller.py": "0" * 64}))
    else:
        (root / "artifact/dist/carveracontroller.app/Contents/Resources/carveracontroller/controller.py").write_bytes(
            b"corrupt"
        )
    with pytest.raises(ValueError):
        verifier.verify(root, revision, digest)
    assert not (root / "built-verification.json").exists()
    assert (root / "source.tar").exists()


@pytest.mark.parametrize(
    "name,kind", [("carveracontroller/../escape.py", "file"), ("carveracontroller/file.py", "link")]
)
def test_archive_paths_and_nonregular_controller_source_reject(tmp_path, name, kind):
    archive = tmp_path / "bad.tar"
    with tarfile.open(archive, "w") as tar:
        member = tarfile.TarInfo(name)
        if kind == "link":
            member.type = tarfile.SYMTYPE
            member.linkname = "/outside"
        tar.addfile(member)
    with pytest.raises(ValueError):
        verifier.archive_sources(archive, "2.1.0-DESKTOP219")


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires native macOS signature verification")
def test_real_signed_fixture_bundle_passes_independent_archive_verification(tmp_path):
    root, revision, digest = fixture(tmp_path, translation=True)
    bundle = root / "artifact/dist/carveracontroller.app"
    subprocess.run(["codesign", "--force", "--sign", "-", str(bundle)], check=True)
    result = verifier.verify(root, revision, digest)
    assert result["strict_signature_verified"] and result["signature_exit"] == 0
    assert result["files"] == 4
    compiled = bundle / "Contents/Resources/carveracontroller/locales/en/LC_MESSAGES/controller.mo"
    assert b"Hi" in compiled.read_bytes()


def test_bundled_unicode_font_fits_independent_archive_budget(tmp_path):
    from pathlib import Path

    font = Path(__file__).resolve().parents[2] / "carveracontroller/ARIALUNI.ttf"
    archive = tmp_path / "font.tar"
    with tarfile.open(archive, "w") as tar:
        tar.add(font, arcname="carveracontroller/ARIALUNI.ttf")
        member = tarfile.TarInfo("carveracontroller/__version__.py")
        member.size = 3
        tar.addfile(member, io.BytesIO(b"old"))
    expected = verifier.archive_sources(archive, "2.1.0-DESKTOP220")
    assert hashlib.sha256(expected["ARIALUNI.ttf"]).hexdigest() == hashlib.sha256(font.read_bytes()).hexdigest()


@pytest.mark.parametrize("limit", ["file", "total", "count"])
def test_source_budget_rejects_before_unbounded_payload_read(tmp_path, monkeypatch, limit):
    archive = tmp_path / "bounded.tar"
    with tarfile.open(archive, "w") as tar:
        for i in range(3):
            member = tarfile.TarInfo(f"carveracontroller/source{i}.py")
            member.size = 4
            tar.addfile(member, io.BytesIO(b"data"))
    if limit == "file":
        monkeypatch.setattr(verifier, "MAX_SOURCE_FILE_BYTES", 3)
    elif limit == "total":
        monkeypatch.setattr(verifier, "MAX_SOURCE_TOTAL_BYTES", 7)
    else:
        monkeypatch.setattr(verifier, "MAX_SOURCE_FILES", 1)
    with pytest.raises(ValueError, match="bounded|budget"):
        verifier.archive_sources(archive, "2.1.0-DESKTOP220")
