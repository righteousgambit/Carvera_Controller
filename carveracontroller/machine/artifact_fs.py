"""Isolated, bounded local artifact metadata service. No controller or Kivy imports."""

from __future__ import annotations

import base64
import binascii
import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Sequence
from math import isfinite
from pathlib import Path

from carveracontroller.machine.artifact_fs_worker import (
    MAX_ITEMS as MAX_ITEMS,
)
from carveracontroller.machine.artifact_fs_worker import (
    MAX_RESPONSE as MAX_RESPONSE,
)
from carveracontroller.machine.artifact_fs_worker import PROGRAM_EXTENSIONS, PROGRAM_MAX_BYTES, parse_program_places
from carveracontroller.machine.artifact_fs_worker import (
    ArtifactEntry as ArtifactEntry,
)
from carveracontroller.machine.artifact_fs_worker import (
    ArtifactRequest as ArtifactRequest,
)
from carveracontroller.machine.artifact_fs_worker import (
    ArtifactResult as ArtifactResult,
)
from carveracontroller.machine.artifact_fs_worker import (
    execute as execute,
)
from carveracontroller.machine.artifact_fs_worker import (
    validate_request as validate_request,
)
from carveracontroller.machine.artifact_fs_worker import (
    worker_main as worker_main,
)

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
        return [sys.executable, str(Path(__file__).with_name("artifact_fs_worker.py").absolute())]
    if sys.platform != "darwin":
        return [sys.executable, "--artifact-fs-worker"]
    bundle = Path(sys.executable).absolute().parents[2]
    helper = macos_worker_executable(bundle)
    if not helper.is_file() or not helper.resolve().is_relative_to(bundle.resolve()):
        raise ValueError("The bundled filesystem helper is unavailable. Repair the application installation.")
    return [str(helper)]


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
    if request["operation"] == "program-list":
        return _program_response(result, request)
    if request["operation"] == "program-read":
        if not isinstance(result, dict) or set(result) != {"path", "content_b64"}:
            raise _invalid_response()
        path, encoded = result["path"], result["content_b64"]
        if path != request["path"] or not isinstance(encoded, str) or len(encoded) > ((PROGRAM_MAX_BYTES + 2) // 3) * 4:
            raise _invalid_response()
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise _invalid_response() from None
        if len(content) > PROGRAM_MAX_BYTES or base64.b64encode(content).decode("ascii") != encoded:
            raise _invalid_response()
        return {"path": path, "content_b64": encoded}
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


def _response_path(value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 16384 or "\0" in value or not Path(value).is_absolute():
        raise _invalid_response()
    return value


def _message(value: object) -> str | None:
    if value is not None and (not isinstance(value, str) or not value or len(value) > 16384 or "\0" in value):
        raise _invalid_response()
    return value


def _program_row(value: object) -> ArtifactEntry:
    if not isinstance(value, dict) or set(value) != {"name", "path", "is_dir", "size", "modified", "available"}:
        raise _invalid_response()
    name, path = _name(value["name"]), _response_path(value["path"])
    is_dir, size, modified, available = value["is_dir"], value["size"], value["modified"], value["available"]
    if (
        Path(path).name != name
        or type(is_dir) is not bool
        or type(available) is not bool
        or type(size) is not int
        or not 0 <= size <= 2**63 - 1
        or isinstance(modified, bool)
        or not isinstance(modified, (int, float))
        or not is_dir
        and Path(name).suffix.casefold() not in PROGRAM_EXTENSIONS
    ):
        raise _invalid_response()
    try:
        timestamp = float(modified)
    except (ValueError, OverflowError):
        raise _invalid_response() from None
    if not isfinite(timestamp):
        raise _invalid_response()
    return {"name": name, "path": path, "is_dir": is_dir, "size": size, "modified": timestamp, "available": available}


def _program_response(result: object, request: ArtifactRequest) -> ArtifactResult:
    if not isinstance(result, dict) or set(result) != {"path", "entries", "selected", "message", "places"}:
        raise _invalid_response()
    path, message = _response_path(result["path"]), _message(result["message"])
    places = result["places"]
    if not isinstance(places, dict) or set(places) != {"recent", "favorites", "error"}:
        raise _invalid_response()
    error = _message(places["error"])
    try:
        recent, favorites = parse_program_places(
            {"schema_version": 1, "recent": places["recent"], "favorites": places["favorites"]}
        )
    except ValueError:
        raise _invalid_response() from None
    if recent != places["recent"] or favorites != places["favorites"] or error and (recent or favorites):
        raise _invalid_response()
    rows = result["entries"]
    if not isinstance(rows, list) or len(rows) > MAX_ITEMS:
        raise _invalid_response()
    entries = [_program_row(row) for row in rows]
    selected = None if result["selected"] is None else _program_row(result["selected"])
    collection = request["collection"]
    if collection:
        references = recent if collection == "recent" else favorites
        if (
            selected is not None
            or [row["path"] for row in entries] != references
            or any(row["is_dir"] for row in entries)
        ):
            raise _invalid_response()
        if error and message != f"Program shortcuts unavailable: {error}":
            raise _invalid_response()
    else:
        names = [row["name"] for row in entries]
        if len(set(names)) != len(names) or any(
            Path(row["path"]) != Path(path) / row["name"] or row["name"].startswith(".") or not row["available"]
            for row in entries
        ):
            raise _invalid_response()
        if selected is not None and (
            not request["navigate"]
            or selected["is_dir"]
            or not selected["available"]
            or Path(selected["path"]) != Path(path) / selected["name"]
            or not _requested_program(selected["path"], request)
        ):
            raise _invalid_response()
    return {
        "path": path,
        "entries": entries,
        "selected": selected,
        "message": message,
        "places": {"recent": recent, "favorites": favorites, "error": error},
    }


def _requested_program(path: str, request: ArtifactRequest) -> bool:
    # Selection comes from a separate stat. Hidden files, filesystem spelling
    # aliases and disappearance during enumeration can omit it from the rows.
    requested = Path(request["path"])
    if requested.parts and requested.parts[0].startswith("~"):
        # Home lookup belongs to the deadline-bound child. Bind the complete
        # explicit tail here without repeating a potentially blocking user lookup.
        tail = requested.parts[1:]
        return bool(tail) and Path(path).parts[-len(tail) :] == tail
    expected = requested if requested.is_absolute() else Path(request["base"]) / requested
    return Path(path) == expected


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


def filesystem_request(
    request: ArtifactRequest,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    timeout: float = 4.0,
    command: Sequence[str] | None = None,
) -> ArtifactResult:
    """Called on a desktop worker, with child cancellation and wall-clock deadline.

    macOS uses its dedicated bundled helper. Other frozen platforms retain their
    early worker entry point. Source runs the standalone protocol without package/UI imports.
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
                if request["operation"] == "program-read":
                    raise ValueError("Program read timed out. Retry or select another program.")
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


def read_program_bytes(
    path: str | os.PathLike[str], *, cancelled: Callable[[], bool] = lambda: False, timeout: float = 4.0
) -> bytes:
    """Capture at most 1 MiB in the cancellable helper; parsing belongs to the caller."""
    result = filesystem_request(
        {"operation": "program-read", "path": os.fspath(path)}, cancelled=cancelled, timeout=timeout
    )
    return base64.b64decode(result["content_b64"], validate=True)


if __name__ == "__main__":
    worker_main()
