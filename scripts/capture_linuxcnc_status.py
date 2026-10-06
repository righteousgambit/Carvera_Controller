"""Capture bounded, read-only NML status on the LinuxCNC host.

Run with that host's LinuxCNC Python environment. Output is created exclusively;
existing evidence is never overwritten. No command or HAL writer is opened.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from carveracontroller.machine.linuxcnc_status import LinuxCNCStatusReader


def capture(reader, output, samples, interval, *, clock=time.monotonic, sleep=time.sleep):
    if type(samples) is not int or not 1 <= samples <= 10000:
        raise ValueError("samples must be 1..10000")
    if type(interval) not in (float, int) or not 0.02 <= interval <= 60:
        raise ValueError("interval must be 0.02..60 seconds")
    with Path(output).open("x", encoding="utf-8") as stream:
        identity = None
        for index in range(samples):
            try:
                observation = reader.poll(clock())
                config = Path(observation.ini_filename)
                digest = hashlib.sha256(config.read_bytes()).hexdigest()
                current = (str(config), digest)
                if identity is not None and current != identity:
                    raise ValueError("LinuxCNC INI changed during capture; start a new session")
                identity = current
                record = {
                    "record": "observation",
                    "captured_at_utc": datetime.now(timezone.utc).isoformat(),
                    "ini_sha256": digest,
                    "status": observation.to_dict(),
                    "transitions": [asdict(change) for change in reader.transitions],
                    "scope": "NML sample; INI hash excludes included HAL/other configuration files",
                }
            except Exception as exc:
                stream.write(json.dumps({"record": "failure", "sample": index, "error": str(exc)}) + "\n")
                stream.flush()
                raise
            stream.write(json.dumps(record, allow_nan=False) + "\n")
            stream.flush()
            if index + 1 < samples:
                sleep(interval)
        stream.write(json.dumps({"record": "complete", "samples": samples, "execution_available": False}) + "\n")
        stream.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--machine-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()
    capture(LinuxCNCStatusReader.connect_local(args.machine_id), args.output, args.samples, args.interval)


if __name__ == "__main__":
    main()
