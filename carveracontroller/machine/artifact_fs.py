"""Isolated, bounded local artifact metadata service. No controller or Kivy imports."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from math import isfinite
from pathlib import Path
from typing import TypedDict

MAX_RESPONSE = 4 * 1024 * 1024
MAX_ITEMS = 20000
MACOS_WORKER_DIRECTORY = "carvera-artifact-worker"
_slots = threading.BoundedSemaphore(2)
_retired: list[subprocess.Popen[bytes]] = []
_retired_lock = threading.Lock()


def macos_worker_executable(bundle: Path) -> Path:
    return (
        bundle
        / "Contents"
        / "Helpers"
        / (MACOS_WORKER_DIRECTORY + ".app")
        / "Contents"
        / "MacOS"
        / MACOS_WORKER_DIRECTORY
    )


def worker_command() -> list[str]:
    if not getattr(sys, "frozen", False):
        return [sys.executable, str(Path(__file__).absolute())]
    if sys.platform != "darwin":
        return [sys.executable, "--artifact-fs-worker"]
    bundle = Path(sys.executable).absolute().parents[2]
    helper = macos_worker_executable(bundle)
    if not helper.is_file() or not helper.resolve().is_relative_to(bundle.resolve()):
        raise ValueError("The bundled filesystem helper is unavailable. Repair the application installation.")
    return [str(helper)]


class ArtifactRequest(TypedDict, total=False):
    operation: str
    path: str
    save: bool
    suffixes: Sequence[str]
    create: bool
    fallback: str | None


class ArtifactEntry(TypedDict):
    name: str
    path: str
    is_dir: bool
    size: int
    modified: float


class ArtifactResult(TypedDict, total=False):
    path: str
    filename: str | None
    entries: list[ArtifactEntry]


def validate_request(value: object) -> ArtifactRequest:
    if not isinstance(value, dict):
        raise ValueError("Invalid filesystem request")
    operation, path = value.get("operation"), value.get("path")
    if not isinstance(path, str) or not path or "\0" in path or len(path) > 16384:
        raise ValueError("Filesystem request needs a valid path")
    if operation == "check":
        if set(value) != {"operation", "path", "save"} or type(value.get("save")) is not bool:
            raise ValueError("Invalid file-check request")
        return {"operation": "check", "path": path, "save": value["save"]}
    if operation != "list":
        raise ValueError("Unsupported filesystem operation")
    if set(value) - {"operation", "path", "suffixes", "create", "fallback"}:
        raise ValueError("Unsupported folder-list request fields")
    suffixes = value.get("suffixes")
    create, fallback = value.get("create", False), value.get("fallback")
    if (
        not isinstance(suffixes, (tuple, list))
        or len(suffixes) > 128
        or any(not isinstance(item, str) or len(item) > 256 or "\0" in item for item in suffixes)
        or type(create) is not bool
        or fallback is not None
        and (not isinstance(fallback, str) or not fallback or len(fallback) > 16384 or "\0" in fallback)
    ):
        raise ValueError("Invalid folder-list request")
    return {
        "operation": "list",
        "path": path,
        "suffixes": tuple(item.casefold() for item in suffixes),
        "create": create,
        "fallback": fallback,
    }


def _invalid_response() -> ValueError:
    return ValueError("Filesystem helper returned invalid metadata. Retry the folder or choose another location.")


def _name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\0" in value
        or value in (".", "..")
        or Path(value).name != value
    ):
        raise _invalid_response()
    return value


def validate_response(value: object, request: ArtifactRequest) -> ArtifactResult:
    if not isinstance(value, dict) or set(value) != {"result", "error"}:
        raise _invalid_response()
    error, result = value["error"], value["result"]
    if error is not None:
        if not isinstance(error, str) or not error or len(error) > 16384 or result is not None:
            raise _invalid_response()
        raise ValueError(error)
    if request["operation"] == "check":
        if not isinstance(result, dict) or result:
            raise _invalid_response()
        return {}
    if not isinstance(result, dict) or set(result) != {"path", "filename", "entries"}:
        raise _invalid_response()
    path, filename, rows = result["path"], result["filename"], result["entries"]
    if not isinstance(path, str) or not path or len(path) > 16384 or "\0" in path or not Path(path).is_absolute():
        raise _invalid_response()
    if filename is not None:
        filename = _name(filename)
    if not isinstance(rows, list) or len(rows) > MAX_ITEMS:
        raise _invalid_response()
    entries: list[ArtifactEntry] = []
    names: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "path", "is_dir", "size", "modified"}:
            raise _invalid_response()
        name = _name(row["name"])
        entry_path, is_dir, size, modified = row["path"], row["is_dir"], row["size"], row["modified"]
        if (
            name in names
            or not isinstance(entry_path, str)
            or "\0" in entry_path
            or Path(entry_path) != Path(path) / name
            or type(is_dir) is not bool
            or type(size) is not int
            or not 0 <= size <= 2**63 - 1
            or isinstance(modified, bool)
            or not isinstance(modified, (int, float))
        ):
            raise _invalid_response()
        try:
            timestamp = float(modified)
        except (ValueError, OverflowError):
            raise _invalid_response() from None
        if not isfinite(timestamp) or not is_dir and not name.casefold().endswith(tuple(request["suffixes"])):
            raise _invalid_response()
        names.add(name)
        entries.append({"name": name, "path": entry_path, "is_dir": is_dir, "size": size, "modified": timestamp})
    return {"path": path, "filename": filename, "entries": entries}


def _acquire_slot(deadline: float, cancelled: Callable[[], bool]) -> None:
    # Killing cannot immediately reap a kernel-blocked process. Retain its slot
    # until it exits so repeated navigation cannot accumulate unlimited helpers.
    # A replacement request waits on this same worker rather than requiring the
    # operator to retry a transient cancellation/reaping race.
    while True:
        if cancelled():
            raise ValueError("Filesystem request cancelled")
        with _retired_lock:
            for process in list(_retired):
                if process.poll() is not None:
                    _retired.remove(process)
                    _slots.release()
            retiring = bool(_retired)
        if _slots.acquire(blocking=False):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if retiring:
                raise ValueError("Filesystem helpers are still stopping. Retry after storage recovers.")
            raise ValueError("Filesystem service busy. Retry or choose another location.")
        time.sleep(min(remaining, 0.05))


def execute(request: ArtifactRequest) -> ArtifactResult:
    request = validate_request(request)
    operation = request["operation"]
    candidate = Path(request["path"]).expanduser()
    if operation == "check":
        if request["save"] and candidate.exists():
            raise ValueError("That file already exists. Choose a new name to preserve it.")
        if not request["save"] and not candidate.is_file():
            raise ValueError("Choose an existing file.")
        return {}
    if operation != "list":
        raise ValueError("Unsupported filesystem operation")
    if request.get("create"):
        candidate.mkdir(parents=True, exist_ok=True)
    filename = None
    if candidate.is_file():
        filename, candidate = candidate.name, candidate.parent
    if not candidate.is_dir():
        fallback = request.get("fallback")
        if fallback is None:
            raise ValueError("That folder is unavailable. Enter an existing folder or file path.")
        candidate = Path(fallback).expanduser()
    candidate = candidate.resolve(strict=True)
    suffixes = tuple(value.casefold() for value in request["suffixes"])
    entries: list[ArtifactEntry] = []
    with os.scandir(candidate) as children:
        for index, child in enumerate(children):
            if index >= MAX_ITEMS:
                raise ValueError("Folder has more than 20,000 items; enter a narrower folder")
            if child.name.startswith("."):
                continue
            try:
                is_dir = child.is_dir()
                if not is_dir and not child.name.casefold().endswith(suffixes):
                    continue
                stat = child.stat()
                entries.append(
                    {
                        "name": child.name,
                        "path": child.path,
                        "is_dir": is_dir,
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )
            except OSError:
                continue
    entries.sort(key=lambda item: (not item["is_dir"], item["name"].casefold()))
    return {"path": str(candidate), "filename": filename, "entries": entries}


def worker_main() -> None:
    # Windowed frozen apps may replace sys.stdin/stdout with None. The parent
    # explicitly supplies pipes, so use their inherited descriptors directly.
    source = os.fdopen(0, "rb", closefd=False)
    destination = os.fdopen(1, "wb", closefd=False)
    try:
        # One bounded JSON line is a complete request. Do not require EOF:
        # inherited writers in a GUI process can otherwise hold the helper open.
        # Legacy callers that close stdin after unframed JSON remain supported.
        raw = source.readline(65538)
        if raw.endswith(b"\n"):
            raw = raw[:-1]
        if len(raw) > 65536:
            raise ValueError("Filesystem request exceeds limit")
        result = {"result": execute(json.loads(raw)), "error": None}
        payload = json.dumps(result, allow_nan=False).encode("utf-8")
        if len(payload) > MAX_RESPONSE:
            raise ValueError("Folder metadata exceeds limit; enter a narrower folder")
    except Exception as error:
        payload = json.dumps({"result": None, "error": str(error)}, allow_nan=False).encode("utf-8")
    destination.write(payload)
    destination.flush()


def filesystem_request(
    request: ArtifactRequest,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    timeout: float = 4.0,
    command: Sequence[str] | None = None,
) -> ArtifactResult:
    """Called on a desktop worker, with child cancellation and wall-clock deadline.

    macOS uses its dedicated bundled helper. Other frozen platforms retain their
    early worker entry point. Source runs this file without package/UI imports.
    """
    request = validate_request(request)
    if command is None:
        command = worker_command()
    encoded = json.dumps(request, allow_nan=False).encode("utf-8")
    if len(encoded) > 65536:
        raise ValueError("Filesystem request exceeds limit")
    encoded += b"\n"
    if cancelled():
        raise ValueError("Filesystem request cancelled")
    payload: bytes | None = encoded
    deadline = time.monotonic() + timeout
    _acquire_slot(deadline, cancelled)
    try:
        if cancelled():
            raise ValueError("Filesystem request cancelled")
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    except Exception:
        _slots.release()
        raise
    try:
        while True:
            if cancelled():
                raise ValueError("Filesystem request cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Folder check timed out. Retry or choose another location.")
            try:
                output, _ = process.communicate(input=payload, timeout=min(remaining, 0.05))
                break
            except subprocess.TimeoutExpired:
                payload = None
        if process.returncode:
            raise ValueError("Filesystem helper exited before completing the request")
        if len(output) > MAX_RESPONSE:
            raise ValueError("Filesystem response exceeds limit")
        if cancelled():
            raise ValueError("Filesystem request cancelled")
        try:
            decoded = json.loads(output)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _invalid_response() from None
        return validate_response(decoded, request)
    finally:
        if process.poll() is None:
            process.kill()
        # A kernel-blocked helper can delay reaping. Never wait indefinitely.
        try:
            process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            with _retired_lock:
                _retired.append(process)
        else:
            _slots.release()
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                pipe.close()


if __name__ == "__main__":
    worker_main()
