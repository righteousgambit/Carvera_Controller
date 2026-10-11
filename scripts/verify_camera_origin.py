#!/usr/bin/env python3
"""Check the live camera timing protocol and preserve a bounded local receipt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from carveracontroller.machine.camera_origin_verification import verify_origin
from carveracontroller.machine.webcam import DEFAULT_CAMERA_URL


def preserve_receipt(report: dict[str, object], output: Path) -> None:
    data = (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    with output.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    if output.read_bytes() != data:
        raise ValueError("Live origin receipt failed readback")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default=DEFAULT_CAMERA_URL)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    report = verify_origin(args.url, args.samples)
    preserve_receipt(report, args.output)
    print(
        json.dumps(
            {key: report[key] for key in ("protocol_qualified", "gap", "source_sha256", "physical_exposure_qualified")},
            indent=2,
        )
    )
    raise SystemExit(0 if report["protocol_qualified"] else 2)
