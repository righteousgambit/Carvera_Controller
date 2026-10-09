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

from carveracontroller.machine.artifact_fs import macos_worker_executable
from scripts.install_verified_macos import validate_manifest, verify_bundle

STARTUP_STAGES = (
    "main_entered",
    "request_read",
    "request_parsed",
    "request_executed",
    "response_encoded",
    "response_written",
)


class WorkerProbeError(ValueError):
    """A failed first attempt with bounded, content-free transport observations."""

    def __init__(self, message: str, observations: dict[str, object]) -> None:
        super().__init__(message)
        self.observations = observations


def probe(command: Sequence[str], timeout: float = 4.0) -> dict[str, object]:
    if not 0 < timeout <= 30:
        raise ValueError("Probe timeout must be positive and at most 30 seconds")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="carvera-worker-probe-") as directory:
        candidate = Path(directory) / "must-not-be-created.json"
        request = {"operation": "check", "path": str(candidate), "save": True}
        child = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "CARVERA_ARTIFACT_STARTUP_TRACE": "1"},
        )
        launch_elapsed = time.monotonic() - started
        assert child.stdin is not None and child.stdout is not None and child.stderr is not None
        output = bytearray()
        eof = False
        request_sent = False
        first_response_elapsed = None
        stdout_eof_elapsed = None
        stderr_eof = False
        stderr_bytes = 0
        stderr_buffer = bytearray()
        startup_stages: list[dict[str, object]] = []
        seen_stages: set[str] = set()
        try:
            child.stdin.write(json.dumps(request).encode() + b"\n")
            child.stdin.flush()  # Keep open until the child answers AND exits.
            request_sent = True
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                selector.register(child.stderr, selectors.EVENT_READ)
                while not eof or not stderr_eof or child.poll() is None:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        raise ValueError("Filesystem worker did not answer and exit while stdin remained open")
                    for key, _mask in selector.select(min(remaining, 0.05)):
                        stream = key.fileobj
                        chunk = os.read(key.fd, 65536)
                        if stream is child.stderr:
                            if not chunk:
                                stderr_eof = True
                                selector.unregister(child.stderr)
                                continue
                            stderr_bytes += len(chunk)
                            if stderr_bytes > 4096:
                                raise ValueError("Filesystem startup diagnostics exceed probe limit")
                            stderr_buffer.extend(chunk)
                            while b"\n" in stderr_buffer:
                                line, _, rest = stderr_buffer.partition(b"\n")
                                stderr_buffer = bytearray(rest)
                                for stage in STARTUP_STAGES:
                                    if (
                                        line == ("CARVERA_STARTUP " + stage).encode("ascii")
                                        and stage not in seen_stages
                                    ):
                                        seen_stages.add(stage)
                                        startup_stages.append(
                                            {"stage": stage, "observed_elapsed_s": time.monotonic() - started}
                                        )
                            continue
                        if not chunk:
                            eof = True
                            stdout_eof_elapsed = time.monotonic() - started
                            selector.unregister(child.stdout)
                        else:
                            if first_response_elapsed is None:
                                first_response_elapsed = time.monotonic() - started
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
                "launch_elapsed_s": launch_elapsed,
                "first_response_elapsed_s": first_response_elapsed,
                "stdout_eof_elapsed_s": stdout_eof_elapsed,
                "child_pid": child.pid,
                "startup_stages": startup_stages,
                "stderr_bytes": stderr_bytes,
            }
        except (ValueError, OSError) as error:
            # Never retain request paths, response payloads or raw process stderr.
            # A response without exit differs from a worker that never answered;
            # neither is a passing qualification and neither permits a retry.
            raise WorkerProbeError(
                str(error),
                {
                    "elapsed_s": time.monotonic() - started,
                    "launch_elapsed_s": launch_elapsed,
                    "request_sent": request_sent,
                    "response_bytes": len(output),
                    "first_response_elapsed_s": first_response_elapsed,
                    "stdout_eof": eof,
                    "stdout_eof_elapsed_s": stdout_eof_elapsed,
                    "exit_observed": child.poll(),
                    "child_pid": child.pid,
                    "startup_stages": startup_stages,
                    "stderr_bytes": stderr_bytes,
                },
            ) from error
        finally:
            if child.poll() is None:
                child.kill()
            try:
                child.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass  # Do not turn a failed bounded probe into an indefinite wait.
            child.stdin.close()
            child.stdout.close()
            child.stderr.close()


def verify(root: Path) -> dict[str, object]:
    destination = root / "artifact-worker-verification.json"
    attempt_path = root / "artifact-worker-attempt.json"
    if destination.exists():
        raise ValueError("Worker verification receipt exists; preserve it")
    if attempt_path.exists() or (root / "artifact-worker-failure.json").exists():
        raise ValueError(
            "Worker qualification already attempted; preserve first-attempt evidence. Use a separate diagnostic."
        )
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
    layout = request.get("artifact_worker_layout")
    if layout != prior.get("artifact_worker_layout") or layout not in (
        None,
        "dedicated-v1",
        "dedicated-v2",
        "dedicated-v3",
    ):
        raise ValueError("Filesystem worker layout differs from package verification")
    worker = (
        macos_worker_executable(bundle) if layout in ("dedicated-v1", "dedicated-v2", "dedicated-v3") else executable
    )
    if not worker.is_file() or not worker.resolve().is_relative_to(bundle.resolve()):
        raise ValueError("Filesystem worker missing or outside verified bundle")
    worker_sha256 = hashlib.sha256(worker.read_bytes()).hexdigest()
    if layout in ("dedicated-v1", "dedicated-v2", "dedicated-v3") and worker_sha256 != prior.get(
        "worker_executable_sha256"
    ):
        raise ValueError("Dedicated worker differs from package verification")
    identity = {
        **{key: request[key] for key in ("source_revision", "source_archive_sha256", "version")},
        "executable_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "artifact_worker_layout": layout,
        "worker_executable_relative": str(worker.relative_to(bundle)),
        "worker_executable_sha256": worker_sha256,
    }
    attempt = {
        **identity,
        "protocol": "first-probe-v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "timeout_s": 4.0,
        "bundle": str(bundle.resolve()),
    }
    # Claim the attempt before launch, atomically. Failure, interruption or a
    # concurrent verifier must never turn a later warm probe into first proof.
    with attempt_path.open("x") as output:
        json.dump(attempt, output, indent=2)
        output.write("\n")
    attempt_sha256 = hashlib.sha256(attempt_path.read_bytes()).hexdigest()
    started = time.monotonic()
    try:
        result = probe(
            [str(worker)]
            if layout in ("dedicated-v1", "dedicated-v2", "dedicated-v3")
            else [str(executable), "--artifact-fs-worker"]
        )
    except Exception as error:
        failure = {
            **identity,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "attempt_sha256": attempt_sha256,
            "elapsed_s": time.monotonic() - started,
            "error_type": type(error).__name__,
            "error": str(error),
            "status": "failed",
            "installed": False,
            "transport_observations": error.observations if isinstance(error, WorkerProbeError) else None,
        }
        with (root / "artifact-worker-failure.json").open("x") as output:
            json.dump(failure, output, indent=2)
            output.write("\n")
        raise
    receipt = {
        **identity,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "attempt_sha256": attempt_sha256,
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
