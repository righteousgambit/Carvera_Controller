"""Build the experimental controller without changing checkout version files.

Preserve the normal controller bundle identity for an in-place app update.
This builds and signs an artifact only; it never installs or connects it.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def packaging_environment(output, temporary=None):
    """Keep packaging hooks out of the operator's Kivy configuration/logs."""
    environment = os.environ.copy()
    environment.update(
        KIVY_HOME=str(Path(output).resolve() / "packaging-kivy"),
        KIVY_NO_FILELOG="1",
        KIVY_LOG_MODE="MIXED",
    )
    if temporary is not None:
        environment["TMPDIR"] = str(Path(temporary).resolve())
    return environment


def storage_preflight(output, minimum_bytes=1024**3):
    """Check build and temporary volumes before staging or invoking packagers."""
    if minimum_bytes <= 0:
        raise ValueError("Storage reserve must be positive")
    roots = []
    for target in (Path(output).resolve(), Path(tempfile.gettempdir()).resolve()):
        while not target.exists():
            target = target.parent
        if not target.is_dir():
            raise ValueError(f"Build storage path is not a directory: {target}")
        roots.append(target)
    for root in roots:
        free = shutil.disk_usage(root).free
        if free < minimum_bytes:
            raise ValueError(
                f"Insufficient free storage at {root}: {free / 1024**3:.2f} GiB available; {minimum_bytes / 1024**3:.2f} GiB reserve required. Choose another output volume and free temporary storage before building."
            )


def dependency_preflight():
    """Resolve packaging dependencies before staging or modifying output."""
    missing = [name for name in ("PyInstaller", "kivy", "PIL") if importlib.util.find_spec(name) is None]
    if missing:
        raise ValueError(
            f"Packaging runtime {sys.executable} is missing {', '.join(missing)}. "
            "Use the prepared build interpreter and dependency path before staging."
        )

    missing_tools = [name for name in ("msgfmt", "codesign") if shutil.which(name) is None]
    if missing_tools:
        raise ValueError(
            f"Packaging shell is missing {', '.join(missing_tools)}. "
            "Include the prepared Homebrew/vendor tool directories in PATH before building."
        )


def build_locations(output, scratch):
    """Separate optional scratch packaging/signing from archive publication."""
    output = Path(output).resolve()
    if scratch is None:
        return output, output
    scratch = Path(scratch).resolve()
    if scratch == output or scratch in output.parents or output in scratch.parents:
        raise ValueError("Scratch and archive paths must be separate, non-nested directories")
    if scratch.exists() or output.exists():
        raise ValueError("Scratch mode requires fresh scratch and archive paths; existing evidence is retained")
    return output, scratch


def artifact_tree(root):
    """Identity of deliverable files, directories, modes and symbolic links."""
    result = {}
    for name in ("source", "dist", "source-manifest.json"):
        target = Path(root) / name
        if not target.exists():
            raise ValueError(f"Missing build deliverable: {name}")
        paths = [target]
        if target.is_dir():
            for directory, folders, files in os.walk(target, followlinks=False):
                paths.extend(Path(directory) / item for item in folders + files)
        for path in paths:
            key = str(path.relative_to(root))
            mode = path.lstat().st_mode & 0o7777
            if path.is_symlink():
                result[key] = ["link", mode, os.readlink(path)]
            elif path.is_file():
                result[key] = ["file", mode, hashlib.sha256(path.read_bytes()).hexdigest()]
            elif path.is_dir():
                result[key] = ["directory", mode]
            else:
                raise ValueError(f"Unsupported build member: {key}")
    return result


def archive_signed_build(scratch, output, version):
    """Copy an exact signed candidate; retain scratch and any failed archive.

    This proves archive identity/signature only. Independent source-to-package
    verification and installed/native qualification remain separate gates.
    """
    scratch, output = Path(scratch).resolve(), Path(output).resolve()
    if scratch == output or scratch in output.parents or output in scratch.parents:
        raise ValueError("Scratch and archive paths must be separate, non-nested directories")
    bundle = Path("dist/carveracontroller.app")
    verify = lambda root: subprocess.run(["codesign", "--verify", "--deep", "--strict", str(root / bundle)], check=True)
    verify(scratch)
    expected = artifact_tree(scratch)
    output.mkdir(parents=True, exist_ok=False)
    try:
        for name in ("source", "dist"):
            shutil.copytree(scratch / name, output / name, symlinks=True)
        shutil.copy2(scratch / "source-manifest.json", output / "source-manifest.json")
        if artifact_tree(scratch) != expected or artifact_tree(output) != expected:
            raise ValueError("Build archive identity mismatch; scratch and failed archive retained")
        verify(output)
        receipt = {
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "version": version,
            "scratch": str(scratch),
            "archive": str(output),
            "members": len(expected),
            "identity_mismatches": [],
            "artifact_tree_sha256": hashlib.sha256(json.dumps(expected, sort_keys=True).encode()).hexdigest(),
            "strict_signature_verified": True,
            "scratch_retained": True,
            "source_to_package_verification": "OPEN independent gate",
            "installed": False,
        }
        (output / "build-archive-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    except Exception as exc:
        (output / "build-archive-failure.json").write_text(
            json.dumps(
                {
                    "observed_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(exc),
                    "scratch_retained": str(scratch),
                    "installed": False,
                },
                indent=2,
            )
            + "\n"
        )
        raise
    return output / bundle


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="2.1.0-DESKTOP1")
    parser.add_argument(
        "--scratch-root",
        type=Path,
        help="Fresh fast-storage workspace for staging/packaging/signing; --output is the retained archive",
    )
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("macOS is required")
    repo = Path(__file__).resolve().parent.parent
    try:
        output, working = build_locations(args.output, args.scratch_root)
        storage_preflight(output)
        if working != output:
            storage_preflight(working)
        dependency_preflight()
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    working.mkdir(parents=True, exist_ok=args.scratch_root is None)
    temporary = working / "temporary" if args.scratch_root is not None else None
    if temporary is not None:
        temporary.mkdir()
    environment = packaging_environment(working, temporary)
    stage = working / "source"
    for folder in ("carveracontroller", "assets"):
        shutil.copytree(
            repo / folder, stage / folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
    (stage / "carveracontroller/__version__.py").write_text(f"__version__ = {args.version!r}\n")
    for po in (stage / "carveracontroller/locales").rglob("*.po"):
        subprocess.run(["msgfmt", "-o", str(po.with_suffix(".mo")), str(po)], check=True, env=environment)
    package = stage / "carveracontroller"
    manifest = {
        str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in package.rglob("*")
        if p.is_file()
    }
    (working / "source-manifest.json").write_text(json.dumps(manifest, indent=2))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(package / "__main__.py"),
            "--name",
            "carveracontroller",
            "--windowed",
            "--noconfirm",
            "--log-level",
            "WARN",
            "--noupx",
            # Setuptools' vendored jaraco runtime imports this namespace on
            # Python <3.12; automatic analysis can miss the vendored alias.
            *(["--hidden-import", "backports.tarfile"] if sys.version_info < (3, 12) else []),
            "--paths",
            str(stage),
            "--add-data",
            f"{package}:carveracontroller",
            "--add-binary",
            f"{stage}/assets/packaging/hidapi/macos/{platform.machine()}/libhidapi.dylib:.",
            "--icon",
            str(stage / "assets/packaging/icon-src.icns"),
            "--osx-bundle-identifier",
            "carveracontroller",
            "--distpath",
            str(working / "dist"),
            "--workpath",
            str(working / "build"),
            "--specpath",
            str(working),
        ],
        cwd=stage,
        env=environment,
        check=True,
    )
    bundle = working / "dist/carveracontroller.app"
    plist = bundle / "Contents/Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info["CFBundleShortVersionString"] = args.version.split("-", 1)[0]
    info["NSLocalNetworkUsageDescription"] = "Connect to your Carvera CNC and receive telemetry on your local network."
    plist.write_bytes(plistlib.dumps(info))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True, env=environment)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True, env=environment)
    if working != output:
        bundle = archive_signed_build(working, output, args.version)
    print(bundle)


if __name__ == "__main__":
    main()
