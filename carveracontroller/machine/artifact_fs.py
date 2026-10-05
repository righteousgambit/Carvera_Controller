"""Isolated, bounded local artifact metadata service. No controller or Kivy imports."""

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

MAX_RESPONSE = 4 * 1024 * 1024
MAX_ITEMS = 20000
_slots = threading.BoundedSemaphore(2)
_retired = []
_retired_lock = threading.Lock()


def _acquire_slot(deadline, cancelled):
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


def execute(request):
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
    entries = []
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


def worker_main():
    # Windowed frozen apps may replace sys.stdin/stdout with None. The parent
    # explicitly supplies pipes, so use their inherited descriptors directly.
    source = os.fdopen(0, "rb", closefd=False)
    destination = os.fdopen(1, "wb", closefd=False)
    try:
        raw = source.read(65537)
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


def filesystem_request(request, *, cancelled=lambda: False, timeout=4.0, command=None):
    """Called on a desktop worker, with child cancellation and wall-clock deadline.

    Frozen entry point dispatches before application imports. Source runs this file
    directly, avoiding package/UI initialization. Metadata never executes commands.
    """
    if command is None:
        command = (
            [sys.executable, "--artifact-fs-worker"]
            if getattr(sys, "frozen", False)
            else [sys.executable, str(Path(__file__).absolute())]
        )
    payload = json.dumps(request, allow_nan=False).encode("utf-8")
    if len(payload) > 65536:
        raise ValueError("Filesystem request exceeds limit")
    if cancelled():
        raise ValueError("Filesystem request cancelled")
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
        response = json.loads(output)
        if response["error"]:
            raise ValueError(response["error"])
        return response["result"]
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
