import hashlib
import io
import json
import plistlib
import subprocess
import sys
import tarfile

import pytest

from scripts import verify_macos_build as verifier


def fixture(tmp_path, translation=False):
    root = tmp_path / "build"
    root.mkdir()
    archive = root / "source.tar"
    sources = {"__version__.py": b"old version", "controller.py": b"print('frozen')\n"}
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
