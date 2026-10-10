#!/usr/bin/env python3
"""Prepare two reviewable service files; never install, connect or restart."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from carveracontroller.machine.camera_origin_patch import MAX_ORIGIN_BYTES, prepare_origin


def prepare(source: Path, output: Path) -> dict[str, object]:
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_ORIGIN_BYTES:
        raise ValueError("Select a bounded regular copy of the reviewed origin source")
    with source.open("rb") as stream:
        original = stream.read(MAX_ORIGIN_BYTES + 1)
    patched = prepare_origin(original)
    support = Path(__file__).resolve().parents[1] / "carveracontroller/machine/camera_origin.py"
    payloads = {"viewer.py": patched, "camera_origin.py": support.read_bytes()}
    # An existing output refuses rather than overwriting any previous attempt.
    output.mkdir(parents=False, exist_ok=False)
    hashes = {}
    for name, data in payloads.items():
        path = output / name
        with path.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != data:
            raise ValueError("Prepared origin file failed readback")
        hashes[name] = hashlib.sha256(data).hexdigest()
    report: dict[str, object] = {
        "schema": 1,
        "original_sha256": hashlib.sha256(original).hexdigest(),
        "files": hashes,
        "action": "Prepared and read back local source only; no service/configuration/CNC mutation",
        "frame_timestamp_basis": "jpeg-assembled",
        "open_gates": [
            "live source revalidation before deployment",
            "origin deployment",
            "clock/exposure qualification",
        ],
    }
    data = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    manifest = output / "prepared-origin.json"
    with manifest.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if manifest.read_bytes() != data:
        raise ValueError("Prepared origin receipt failed readback")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.output), indent=2))
