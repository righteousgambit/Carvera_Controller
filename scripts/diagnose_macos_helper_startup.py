"""Sample a fresh signing identity without retrying a failed package qualification.

Only a copy of the failed native helper is re-signed. Its __text section must be
unchanged. The original package/first-attempt receipts are read-only. Sampling
can perturb timing, and a fresh signature does not prove a cold OS cache. This
diagnostic never creates an installation or worker-qualification receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import plistlib
import selectors
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from carveracontroller.machine.artifact_startup import STARTUP_STAGES


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_digest(path: Path) -> str:
    """Check actual thin Mach-O machine instructions independently of signing."""
    data = path.read_bytes()
    if len(data) > 8 * 1024 * 1024 or data[:4] != b"\xcf\xfa\xed\xfe":
        raise ValueError("Diagnostic requires the bounded thin 64-bit native helper")
    if len(data) < 32:
        raise ValueError("Truncated native helper")
    count, size = struct.unpack_from("<II", data, 16)
    end, offset = 32 + size, 32
    if count > 4096 or end > len(data):
        raise ValueError("Invalid native load commands")
    for _ in range(count):
        if offset + 8 > end:
            raise ValueError("Truncated native load command")
        command, length = struct.unpack_from("<II", data, offset)
        if length < 8 or offset + length > end:
            raise ValueError("Invalid native load command extent")
        if command == 0x19:
            if length < 72:
                raise ValueError("Truncated native segment")
            sections = struct.unpack_from("<I", data, offset + 64)[0]
            if 72 + sections * 80 > length:
                raise ValueError("Invalid native section table")
            for index in range(sections):
                section = offset + 72 + index * 80
                if (
                    data[section : section + 16].rstrip(b"\0") == b"__text"
                    and data[section + 16 : section + 32].rstrip(b"\0") == b"__TEXT"
                ):
                    length = struct.unpack_from("<Q", data, section + 40)[0]
                    start = struct.unpack_from("<I", data, section + 48)[0]
                    if not length or start + length > len(data):
                        raise ValueError("Invalid native instruction extent")
                    return hashlib.sha256(data[start : start + length]).hexdigest()
        offset += length
    raise ValueError("Native helper has no instruction section")


def observe(
    worker: Path, output: Path, *, timeout: float = 15, sample_after: float = 1, request_after: float = 0
) -> dict[str, object]:
    if not 0 < sample_after < timeout <= 20:
        raise ValueError("Diagnostic timing must satisfy 0 < sample_after < timeout <=20 seconds")
    if not 0 <= request_after < timeout:
        raise ValueError("Diagnostic input delay must fit the observation window")
    started = time.monotonic()
    candidate = output / "must-not-be-created.json"
    child = subprocess.Popen(
        [str(worker)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CARVERA_ARTIFACT_STARTUP_TRACE": "1"},
    )
    sampler = None
    response, error_lines = bytearray(), bytearray()
    stages = []
    stderr_bytes = 0
    result: dict[str, object] = {
        "child_pid": child.pid,
        "launch_elapsed_s": time.monotonic() - started,
        "sample_requested": False,
        "qualification": "NOT_ATTEMPTED",
        "request_withheld_s": request_after,
        "request_sent": False,
    }
    assert child.stdin is not None and child.stdout is not None and child.stderr is not None
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            selector.register(child.stderr, selectors.EVENT_READ)
            while selector.get_map() or child.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed >= timeout:
                    result["timed_out"] = True
                    break
                if not result["request_sent"] and elapsed >= request_after:
                    child.stdin.write(
                        json.dumps({"operation": "check", "path": str(candidate), "save": True}).encode() + b"\n"
                    )
                    child.stdin.flush()
                    result.update(request_sent=True, request_sent_elapsed_s=time.monotonic() - started)
                if sampler is None and elapsed >= sample_after and child.poll() is None:
                    result["sample_requested"] = True
                    result["sample_started_elapsed_s"] = elapsed
                    # One owned child only. Stack sampling is diagnostic and can
                    # perturb its scheduling; never use this as a timing gate.
                    with (output / "sample-tool.log").open("xb") as log:
                        sampler = subprocess.Popen(
                            [
                                "/usr/bin/sample",
                                str(child.pid),
                                "2",
                                "10",
                                "-mayDie",
                                "-file",
                                str(output / "process-sample.txt"),
                            ],
                            stdout=log,
                            stderr=subprocess.STDOUT,
                        )
                    result.update(sample_pid=sampler.pid, sample_launch_elapsed_s=time.monotonic() - started - elapsed)
                for key, _ in selector.select(min(0.05, timeout - elapsed)):
                    chunk = os.read(key.fd, 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                    elif key.fileobj is child.stdout:
                        response.extend(chunk)
                        if len(response) > 65536:
                            raise ValueError("Diagnostic response exceeds budget")
                    else:
                        stderr_bytes += len(chunk)
                        error_lines.extend(chunk)
                        if stderr_bytes > 4096:
                            raise ValueError("Diagnostic startup channel exceeds budget")
                        while b"\n" in error_lines:
                            line, _, tail = error_lines.partition(b"\n")
                            error_lines = bytearray(tail)
                            for stage in STARTUP_STAGES:
                                if line == ("CARVERA_STARTUP " + stage).encode() and not any(
                                    row["stage"] == stage for row in stages
                                ):
                                    stages.append({"stage": stage, "observed_elapsed_s": time.monotonic() - started})
        result.update(
            elapsed_s=time.monotonic() - started,
            startup_stages=stages,
            response_bytes=len(response),
            exit_observed=child.poll(),
            file_created=candidate.exists(),
        )
        result["valid_check_response"] = bool(response) and json.loads(response) == {"result": {}, "error": None}
    except Exception as error:
        result.update(
            error_type=type(error).__name__,
            error=str(error),
            elapsed_s=time.monotonic() - started,
            startup_stages=stages,
            response_bytes=len(response),
            exit_observed=child.poll(),
        )
    finally:
        if child.poll() is None:
            result["kill_requested"] = True
            child.kill()
        try:
            child.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            pass
        for stream in (child.stdin, child.stdout, child.stderr):
            try:
                stream.close()
            except OSError:
                pass
        result.update(cleanup_exit=child.poll(), stderr_bytes=stderr_bytes)
        if sampler is not None:
            try:
                sampler.wait(timeout=5)
            except subprocess.TimeoutExpired:
                sampler.kill()
                try:
                    sampler.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
            result["sample_exit"] = sampler.poll()
        sample = output / "process-sample.txt"
        result["sample_captured"] = sample.is_file() and sample.stat().st_size > 0
    return result


def diagnose(root: Path, output: Path, *, sample_after: float = 1, request_after: float = 0) -> dict[str, object]:
    if not 0 < sample_after < 15:
        raise ValueError("Sampling must start after launch and before the15-second observation deadline")
    if not 0 <= request_after < 15:
        raise ValueError("Diagnostic input delay must fit the15-second observation window")
    root, output = root.resolve(), output.resolve()
    if root.is_relative_to(output) or output.is_relative_to(root):
        raise ValueError("Diagnostic and failed-package roots must be separate")
    failure_path, attempt_path = root / "artifact-worker-failure.json", root / "artifact-worker-attempt.json"
    failure = json.loads(failure_path.read_text())
    originals = {path.name: digest(path) for path in (failure_path, attempt_path)}
    if failure.get("attempt_sha256") != originals[attempt_path.name]:
        raise ValueError("First failure no longer matches its immutable attempt")
    if failure.get("status") != "failed" or failure.get("installed") is not False:
        raise ValueError("A retained failed, uninstalled first qualification is required")
    bundle = root / "artifact/dist/carveracontroller.app"
    worker = bundle / failure["worker_executable_relative"]
    if not worker.resolve().is_relative_to(bundle) or worker.parent.name != "MacOS":
        raise ValueError("Unexpected failed-helper location")
    helper = worker.parent.parent.parent
    if not helper.name.endswith(".app") or any(p.is_symlink() for p in helper.rglob("*")):
        raise ValueError("Diagnostic requires a contained native helper app")
    if digest(worker) != failure["worker_executable_sha256"]:
        raise ValueError("Original helper differs from first-failure identity")
    output.mkdir(parents=True, exist_ok=False)
    identity = "dev.carvera.artifact-worker.diagnostic." + uuid4().hex
    request = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "DIAGNOSTIC ONLY; no qualification or install",
        "original_root": str(root),
        "original_receipt_sha256": originals,
        "original_worker_sha256": digest(worker),
        "original_text_sha256": text_digest(worker),
        "diagnostic_identifier": identity,
        "harness_sha256": digest(Path(__file__)),
        "sample_after_s": sample_after,
        "request_withheld_s": request_after,
        "stage_names": list(STARTUP_STAGES),
        "limitations": "Fresh signature identity, not proof of cold OS cache; sampling can perturb timing",
    }
    (output / "diagnostic-request.json").write_text(json.dumps(request, indent=2) + "\n")
    (output / "harness-source.py").write_bytes(Path(__file__).read_bytes())
    copied = output / "diagnostic.app/Contents/Helpers" / helper.name
    copied.parent.mkdir(parents=True)
    shutil.copytree(helper, copied)
    plist = copied / "Contents/Info.plist"
    info = plistlib.loads(plist.read_bytes())
    info["CFBundleIdentifier"] = identity
    plist.write_bytes(plistlib.dumps(info))
    subprocess.run(
        ["/usr/bin/codesign", "--force", "--sign", "-", str(copied)],
        check=True,
        timeout=60,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--deep", "--strict", str(copied)],
        check=True,
        timeout=60,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    diagnostic_worker = copied / "Contents/MacOS" / worker.name
    if text_digest(diagnostic_worker) != request["original_text_sha256"]:
        raise ValueError("Diagnostic changed native instructions")
    observed = observe(diagnostic_worker, output, sample_after=sample_after, request_after=request_after)
    result = {
        **request,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "diagnostic_worker_sha256": digest(diagnostic_worker),
        "original_receipts_unchanged": all(digest(root / name) == expected for name, expected in originals.items()),
        "original_worker_unchanged": digest(worker) == request["original_worker_sha256"],
        "observation": observed,
        "qualification": "NOT_ATTEMPTED; original package remains FAILED and uninstalled",
    }
    sample = output / "process-sample.txt"
    if sample.exists():
        result["sample_sha256"] = digest(sample)
    tool_log = output / "sample-tool.log"
    if tool_log.exists():
        result["sample_tool_log_sha256"] = digest(tool_log)
    (output / "diagnostic-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-after", type=float, default=1)
    parser.add_argument(
        "--request-after",
        type=float,
        default=0,
        help="Diagnostic only: keep stdin open without a request to retain the child for sampling",
    )
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("macOS is required")
    print(
        json.dumps(
            diagnose(args.root, args.output, sample_after=args.sample_after, request_after=args.request_after), indent=2
        )
    )
