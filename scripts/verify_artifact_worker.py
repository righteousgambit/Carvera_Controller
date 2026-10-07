"""Exercise the packaged filesystem worker without GUI, controller or operator writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import selectors
import subprocess
import tempfile
import time
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from scripts.install_verified_macos import validate_manifest, verify_bundle


def probe(command: Sequence[str], timeout: float = 4.0) -> dict[str, object]:
    if not 0 < timeout <= 30:
        raise ValueError("Probe timeout must be positive and at most 30 seconds")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="carvera-worker-probe-") as directory:
        candidate = Path(directory) / "must-not-be-created.json"
        request = {"operation": "check", "path": str(candidate), "save": True}
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        assert child.stdin is not None and child.stdout is not None
        try:
            child.stdin.write(json.dumps(request).encode() + b"\n")
            child.stdin.flush()  # Keep open until the child answers AND exits.
            output = bytearray()
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                eof = False
                while not eof or child.poll() is None:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise ValueError("Filesystem worker did not answer and exit while stdin remained open")
                    for _key, _mask in selector.select(min(remaining, 0.05)):
                        chunk = os.read(child.stdout.fileno(), 65536)
                        if not chunk:
                            eof = True
                            selector.unregister(child.stdout)
                        else:
                            output.extend(chunk)
                            if len(output) > 65536:
                                raise ValueError("Filesystem check response exceeds probe limit")
            if child.returncode != 0 or json.loads(output) != {"result": {}, "error": None}:
                raise ValueError("Filesystem worker returned an invalid check response")
            if candidate.exists():
                raise ValueError("Filesystem check unexpectedly created a file")
            return {
                "elapsed_s": time.monotonic() - started,
                "exit": child.returncode,
                "stdin_retained": True,
                "file_created": False,
            }
        finally:
            if child.poll() is None:
                child.kill()
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass  # Do not turn a failed bounded probe into an indefinite wait.
            child.stdin.close()
            child.stdout.close()


def verify(root: Path) -> dict[str, object]:
    destination = root / "artifact-worker-verification.json"
    if destination.exists():
        raise ValueError("Worker verification receipt exists; preserve it")
    request = json.loads((root / "build-request.json").read_text())
    prior = json.loads((root / "built-verification.json").read_text())
    for key in ("source_revision", "source_archive_sha256", "version"):
        if request[key] != prior[key]:
            raise ValueError("Package verification identity mismatch")
    if prior["mismatches"] or not prior["strict_signature_verified"] or prior["signature_exit"]:
        raise ValueError("Successful independent package verification required")
    bundle = root / "artifact/dist/carveracontroller.app"
    manifest = validate_manifest(json.loads((root / "artifact/source-manifest.json").read_text()))
    verify_bundle(bundle, manifest, request["version"])
    executable = bundle / "Contents/MacOS/carveracontroller"
    result = probe([str(executable), "--artifact-fs-worker"])
    receipt = {
        **{key: request[key] for key in ("source_revision", "source_archive_sha256", "version")},
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "method": "Verified bundled executable; bounded framed file check while retaining stdin until worker exit",
        "probe": result,
        "limitations": "CLI worker behavior only; GUI launch environment, picker interaction and native export remain separate gates",
        "installed": False,
    }
    with destination.open("x") as output:
        json.dump(receipt, output, indent=2)
        output.write("\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().root), indent=2))
