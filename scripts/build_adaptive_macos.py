"""Build the experimental controller without changing checkout version files.

Preserve the normal controller bundle identity for an in-place app update.
This builds and signs an artifact only; it never installs or connects it.
"""

import argparse
import hashlib
import json
import platform
import plistlib
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="2.0.0-ADAPTIVE1")
    args = parser.parse_args()
    if platform.system() != "Darwin":
        parser.error("macOS is required")
    repo = Path(__file__).resolve().parent.parent
    output = args.output.resolve()
    stage = output / "source"
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
