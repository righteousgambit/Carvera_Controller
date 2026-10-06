"""Independently verify packaged controller source against an exact frozen archive.

Never installs, launches or connects. Caller supplies revision and archive hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from scripts.install_verified_macos import validate_manifest, verify_bundle

MAX_SOURCE_FILE_BYTES = 32 * 1024**2
MAX_SOURCE_TOTAL_BYTES = 128 * 1024**2
MAX_SOURCE_FILES = 5000


def archive_sources(archive: Path, version: str) -> dict[str, bytes]:
    expected: dict[str, bytes] = {}
    total = 0
    with tarfile.open(archive) as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Archive contains unsafe source path")
            if not path.parts or path.parts[0] != "carveracontroller" or member.isdir():
                continue
            if not member.isfile() or member.size > MAX_SOURCE_FILE_BYTES:
                raise ValueError("Controller archive member must be bounded regular source")
            total += member.size
            if total > MAX_SOURCE_TOTAL_BYTES or len(expected) >= MAX_SOURCE_FILES:
                raise ValueError("Controller archive exceeds total source budget")
            name = str(path.relative_to("carveracontroller"))
            if name in expected:
                raise ValueError("Duplicate controller archive member")
            stream = tar.extractfile(member)
            if stream is None:
                raise ValueError("Missing archive member bytes")
            expected[name] = stream.read()
    if not expected or "__version__.py" not in expected:
        raise ValueError("Archive contains no controller package")
    expected["__version__.py"] = f"__version__ = {version!r}\n".encode()
    with tempfile.TemporaryDirectory(prefix="carvera-source-verify-") as folder:
        po, mo = Path(folder) / "translation.po", Path(folder) / "translation.mo"
        for name, content in list(expected.items()):
            if name.endswith(".po"):
                po.write_bytes(content)
                subprocess.run(["msgfmt", "-o", str(mo), str(po)], check=True)
                expected[str(PurePosixPath(name).with_suffix(".mo"))] = mo.read_bytes()
    return expected


def verify(root: Path, revision: str, archive_sha256: str) -> dict[str, object]:
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("Exact lowercase source revision required")
    validate_manifest({"source.tar": archive_sha256})
    receipt_path = root / "built-verification.json"
    if receipt_path.exists():
        raise ValueError("Verification receipt exists; inspect prior result instead of overwriting")
    request = json.loads((root / "build-request.json").read_text())
    archive = root / "source.tar"
    if request.get("source_revision") != revision or request.get("source_archive_sha256") != archive_sha256:
        raise ValueError("Build request differs from supplied source identity")
    if hashlib.sha256(archive.read_bytes()).hexdigest() != archive_sha256:
        raise ValueError("Frozen source archive hash mismatch")
    expected = archive_sources(archive, request["version"])
    manifest = validate_manifest(json.loads((root / "artifact/source-manifest.json").read_text()))
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in expected.items()}
    if hashes != manifest:
        raise ValueError("Build manifest differs from independently read frozen archive")
    bundle = root / "artifact/dist/carveracontroller.app"
    verify_bundle(bundle, manifest, request["version"])
    receipt: dict[str, object] = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source_revision": revision,
        "version": request["version"],
        "bundle": str(bundle),
        "files": len(expected),
        "mismatches": [],
        "strict_signature_verified": True,
        "signature_exit": 0,
        "source_archive_sha256": archive_sha256,
        "installed": False,
        "method": "Frozen archive bytes plus explicit version and independently compiled gettext; package hashes, bundle identity and strict signature",
    }
    with receipt_path.open("x") as output:
        json.dump(receipt, output, indent=2)
        output.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--archive-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.root.resolve(), args.source_revision, args.archive_sha256), indent=2))


if __name__ == "__main__":
    main()
