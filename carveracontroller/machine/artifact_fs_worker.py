"""Standalone bounded filesystem protocol; no parent process or desktop imports."""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

MAX_RESPONSE = 4 * 1024 * 1024
MAX_ITEMS = 20000


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


if __name__ == "__main__":
    worker_main()
