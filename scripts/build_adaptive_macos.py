"""Build the experimental controller without changing checkout version files.

Preserve the normal controller bundle identity for an in-place app update.
This builds and signs an artifact only; it never installs or connects it.
"""

import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def packaging_environment(output):
    """Keep packaging hooks out of the operator's Kivy configuration/logs."""
    environment = os.environ.copy()
    environment.update(
        KIVY_HOME=str(Path(output).resolve() / "packaging-kivy"),
        KIVY_NO_FILELOG="1",
        KIVY_LOG_MODE="MIXED",
    )
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="2.1.0-DESKTOP1")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("macOS is required")
    repo = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    stage = output / "source"
    try:
        storage_preflight(output)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    output.mkdir(parents=True, exist_ok=True)
    for folder in ("carveracontroller", "assets"):
        shutil.copytree(
            repo / folder, stage / folder, dirs_exist_ok=True, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
    (stage / "carveracontroller/__version__.py").write_text(f"__version__ = {args.version!r}\n")
    for po in (stage / "carveracontroller/locales").rglob("*.po"):
        subprocess.run(["msgfmt", "-o", str(po.with_suffix(".mo")), str(po)], check=True)
    package = stage / "carveracontroller"
    manifest = {
        str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in package.rglob("*")
        if p.is_file()
    }
    (output / "source-manifest.json").write_text(json.dumps(manifest, indent=2))
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
            str(output / "dist"),
            "--workpath",
            str(output / "build"),
            "--specpath",
            str(output),
        ],
        cwd=stage,
        env=packaging_environment(output),
        check=True,
    )
    bundle = output / "dist/carveracontroller.app"
    plist = bundle / "Contents/Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info["CFBundleShortVersionString"] = args.version.split("-", 1)[0]
    info["NSLocalNetworkUsageDescription"] = "Connect to your Carvera CNC and receive telemetry on your local network."
    plist.write_bytes(plistlib.dumps(info))
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(bundle)], check=True)
    subprocess.run(["codesign", "--verify", "--deep", "--strict", str(bundle)], check=True)
    print(bundle)


if __name__ == "__main__":
    main()
