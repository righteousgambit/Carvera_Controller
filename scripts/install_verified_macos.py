"""Install a verified existing controller update while retaining recovery/forensics.

No app launch, permissions, operator data, controller connection or motion.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def validate_manifest(record):
    if not isinstance(record, dict) or not record:
        raise ValueError("Nonempty source manifest required")
    for name, digest in record.items():
        if not isinstance(name, str) or "\\" in name:
            raise ValueError("Manifest requires relative POSIX paths")
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or path.as_posix() != name:
            raise ValueError("Manifest path must be canonical and contained")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Manifest requires lowercase SHA-256 digests")
    return record


def verify_bundle(bundle, manifest, version=None):
    package = bundle / "Contents/Resources/carveracontroller"
    for name, digest in manifest.items():
        path = package / name
        if not path.resolve().is_relative_to(package.resolve()):
            raise ValueError("Manifest member escapes packaged source")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Packaged source mismatch: {name}")
    info = plistlib.loads((bundle / "Contents/Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != "carveracontroller":
        raise ValueError("Unexpected bundle identity")
    if version is not None:
        if info.get("CFBundleShortVersionString") != version.split("-", 1)[0]:
            raise ValueError("Unexpected bundle version")
        if (package / "__version__.py").read_text() != f"__version__ = {version!r}\n":
            raise ValueError("Unexpected application source version")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)


def storage_preflight(bundle, target_parent, reserve=1024**3):
    if reserve <= 0:
        raise ValueError("Installation reserve must be positive")
    if not target_parent.is_dir():
        raise ValueError("Installation parent must exist")
    # Counting dereferenced files may overestimate symlink storage; retaining the
    # conservative estimate avoids underbudgeting a copied/signature-checked app.
    required = sum(path.stat().st_size for path in bundle.rglob("*") if path.is_file()) + reserve
    available = shutil.disk_usage(target_parent).free
    if available < required:
        raise ValueError(f"Installation requires {required} free bytes including reserve; {available} available")
    return {"required_bytes": required, "available_bytes": available, "reserve_bytes": reserve}


def install(root, target, recovery, staging, failed):
    if (root / "superseded-do-not-install.json").exists():
        raise ValueError("Build is explicitly superseded; preserve its evidence and use the replacement source")
    paths = [target, recovery, staging, failed]
    if len({path.resolve() for path in paths}) != 4 or any(path.parent != target.parent for path in paths):
        raise ValueError("Installation, recovery, staging and failure paths must be distinct siblings")
    if any(path.suffix != ".app" for path in paths) or not target.is_dir():
        raise ValueError("An existing application update target and .app sibling paths are required")
    if any(path.exists() or path.is_symlink() for path in (recovery, staging, failed)):
        raise ValueError("Recovery/staging/failure destinations already exist; preserve them")
    request = json.loads((root / "build-request.json").read_text())
    prior = json.loads((root / "built-verification.json").read_text())
    bundle = Path(prior["bundle"])
    if prior["mismatches"] or prior["signature_exit"] != 0 or prior["source_revision"] != request["source_revision"]:
        raise ValueError("Built-verification receipt does not match requested source")
    if prior["version"] != request["version"]:
        raise ValueError("Built-verification receipt does not match requested version")
    manifest = validate_manifest(json.loads((root / "artifact/source-manifest.json").read_text()))
    verify_bundle(bundle, manifest, request["version"])
    processes = subprocess.check_output(["ps", "-axo", "command"], text=True).splitlines()
    if any(line.lstrip().startswith(str(target / "Contents/MacOS/")) for line in processes):
        raise ValueError("Quit the installed application before updating")
    old_info = plistlib.loads((target / "Contents/Info.plist").read_bytes())
    if old_info.get("CFBundleIdentifier") != "carveracontroller":
        raise ValueError("Existing target is not the controller")
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(target)], check=True)
    capacity = storage_preflight(bundle, target.parent)
    receipt = {
        "source_revision": request["source_revision"],
        "version": request["version"],
        "capacity": capacity,
        "installed": str(target),
        "recovery": str(recovery),
        "staging": str(staging),
        "failed": str(failed),
        "files": len(manifest),
        "native_workflow": "unverified",
    }
    receipt_path = root / "artifact-verification.json"
    if receipt_path.exists():
        raise ValueError("Installation receipt already exists; inspect the completed attempt")
    moved_old = False
    try:
        subprocess.run(["ditto", str(bundle), str(staging)], check=True)
        verify_bundle(staging, manifest, request["version"])
        target.rename(recovery)
        moved_old = True
        staging.rename(target)
        verify_bundle(target, manifest, request["version"])
    except Exception as exc:
        receipt.update(status="failed", error=type(exc).__name__, recovery_restored=False)
        if moved_old:
            if target.exists():
                target.rename(failed)
            recovery.rename(target)
            subprocess.run(["codesign", "--verify", "--deep", "--strict", str(target)], check=True)
            receipt["recovery_restored"] = True
        receipt["verified_at"] = datetime.now(timezone.utc).isoformat()
        receipt_path.write_text(json.dumps(receipt, indent=2))
        raise
    receipt.update(
        status="installed", mismatches=[], signature_exit=0, verified_at=datetime.now(timezone.utc).isoformat()
    )
    receipt_path.write_text(json.dumps(receipt, indent=2))
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("root", "target", "recovery", "staging", "failed"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    result = install(*(getattr(args, name).resolve() for name in ("root", "target", "recovery", "staging", "failed")))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
