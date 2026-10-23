"""Standalone bounded filesystem protocol; no parent process or desktop imports."""

from __future__ import annotations

import json
import os
import stat as stat_types
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

MAX_RESPONSE = 4 * 1024 * 1024
MAX_ITEMS = 20000
PROGRAM_EXTENSIONS = frozenset({".cnc", ".nc", ".gcode", ".tap", ".ngc"})
PLACES_MAX_BYTES = 1024 * 1024
RECENT_LIMIT = 25
FAVORITE_LIMIT = 100


class ArtifactRequest(TypedDict, total=False):
    operation: str
    path: str
    save: bool
    suffixes: Sequence[str]
    create: bool
    fallback: str | None
    base: str
    navigate: bool
    initial_candidates: Sequence[str] | None
    collection: str | None
    places_path: str


class _ArtifactMetadata(TypedDict):
    name: str
    path: str
    is_dir: bool
    size: int
    modified: float


class ArtifactEntry(_ArtifactMetadata, total=False):
    available: bool


class ProgramPlacesSnapshot(TypedDict):
    recent: list[str]
    favorites: list[str]
    error: str | None


class ArtifactResult(TypedDict, total=False):
    path: str
    filename: str | None
    entries: list[ArtifactEntry]
    selected: ArtifactEntry | None
    message: str | None
    places: ProgramPlacesSnapshot


def program_reference(value: object) -> str:
    """Shared lexical reference contract; this standalone worker imports no app code."""
    if not isinstance(value, (str, os.PathLike)):
        raise ValueError("Invalid local program reference")
    value = os.fspath(value)
    if not isinstance(value, str) or not value or len(value) > 4096 or "\0" in value:
        raise ValueError("Invalid local program reference")
    path = Path(value)
    if not path.is_absolute() or path.suffix.casefold() not in PROGRAM_EXTENSIONS:
        raise ValueError("Program references require an absolute supported program path")
    return os.path.normpath(value)


def parse_program_places(
    data: object, recent_limit: int = RECENT_LIMIT, favorite_limit: int = FAVORITE_LIMIT
) -> tuple[list[str], list[str]]:
    if not isinstance(data, dict) or set(data) != {"schema_version", "recent", "favorites"}:
        raise ValueError("Invalid program-reference document")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported program-reference schema")
    result: list[list[str]] = []
    for name, limit in (("recent", recent_limit), ("favorites", favorite_limit)):
        values = data[name]
        if not isinstance(values, list) or len(values) > limit:
            raise ValueError(f"Invalid {name} program references")
        normalized = [program_reference(value) for value in values]
        if len(set(normalized)) != len(normalized):
            raise ValueError(f"Duplicate {name} program references")
        result.append(normalized)
    return result[0], result[1]


def read_program_places(
    path: Path,
    max_bytes: int = PLACES_MAX_BYTES,
    recent_limit: int = RECENT_LIMIT,
    favorite_limit: int = FAVORITE_LIMIT,
) -> tuple[list[str], list[str]]:
    if not path.exists():
        return [], []
    with path.open("rb") as stream:
        raw = stream.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise ValueError("Program references exceed 1 MiB")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
        raise ValueError("Invalid program-reference document") from None
    return parse_program_places(data, recent_limit, favorite_limit)


def _valid_path(value: object) -> bool:
    return isinstance(value, str) and bool(value) and "\0" not in value and len(value) <= 16384


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
    if operation == "program-list":
        if set(value) != {"operation", "path", "base", "navigate", "initial_candidates", "collection", "places_path"}:
            raise ValueError("Invalid program-list request fields")
        base, places_path = value["base"], value["places_path"]
        initial, collection = value["initial_candidates"], value["collection"]
        if (
            not _valid_path(base)
            or not Path(base).is_absolute()
            or not _valid_path(places_path)
            or not Path(places_path).is_absolute()
            or type(value["navigate"]) is not bool
            or collection not in (None, "recent", "favorites")
            or initial is not None
            and (
                not isinstance(initial, (tuple, list))
                or not 1 <= len(initial) <= 3
                or any(not _valid_path(item) for item in initial)
            )
        ):
            raise ValueError("Invalid program-list request")
        return {
            "operation": operation,
            "path": path,
            "base": base,
            "navigate": value["navigate"],
            "initial_candidates": initial,
            "collection": collection,
            "places_path": places_path,
        }
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
    if operation == "program-list":
        return _program_list(request)
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


def _program_path(path: str, base: str) -> Path:
    candidate = Path(path).expanduser()
    return (candidate if candidate.is_absolute() else Path(base) / candidate).absolute()


def _program_entry(path: Path, stat: os.stat_result, is_dir: bool, available: bool = True) -> ArtifactEntry:
    return {
        "name": path.name,
        "path": str(path),
        "is_dir": is_dir,
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "available": available,
    }


def _program_list(request: ArtifactRequest) -> ArtifactResult:
    places: ProgramPlacesSnapshot = {"recent": [], "favorites": [], "error": None}
    try:
        places["recent"], places["favorites"] = read_program_places(Path(request["places_path"]))
    except (OSError, ValueError) as error:
        places["error"] = str(error)
    try:
        candidate = _program_path(request["path"], request["base"])
        initial = request["initial_candidates"]
        if initial:
            for hint in initial:
                candidate = _program_path(hint, request["base"])
                try:
                    if stat_types.S_ISDIR(candidate.stat().st_mode):
                        break
                except (FileNotFoundError, NotADirectoryError):
                    continue
                except OSError:
                    break  # An unreadable saved folder retains its own error.
    except (OSError, ValueError, RuntimeError) as error:
        raise ValueError(f"Cannot read path: {error}") from None
    selected: ArtifactEntry | None = None
    message = None
    entries: list[ArtifactEntry] = []
    collection = request["collection"]
    if collection:
        if places["error"]:
            message = f"Program shortcuts unavailable: {places['error']}"
        else:
            references = places["recent"] if collection == "recent" else places["favorites"]
            for reference in references:
                item = Path(reference)
                try:
                    stat = item.stat()
                    entries.append(_program_entry(item, stat, False, item.is_file()))
                except OSError:
                    entries.append(
                        {
                            "name": item.name,
                            "path": reference,
                            "is_dir": False,
                            "size": 0,
                            "modified": 0.0,
                            "available": False,
                        }
                    )
    else:
        try:
            if request["navigate"] and candidate.is_file():
                if candidate.suffix.casefold() in PROGRAM_EXTENSIONS:
                    selected = _program_entry(candidate, candidate.stat(), False)
                else:
                    message = f"Unsupported program file: {Path(request['path']).name}"
                candidate = candidate.parent
            with os.scandir(candidate) as children:
                for index, child in enumerate(children):
                    if index >= MAX_ITEMS:
                        raise ValueError("Folder has more than 20,000 items; enter a narrower folder")
                    if child.name.startswith("."):
                        continue
                    try:
                        stat, is_dir = child.stat(), child.is_dir()
                        if is_dir or Path(child.name).suffix.casefold() in PROGRAM_EXTENSIONS:
                            try:
                                child.name.encode("utf-8")
                            except UnicodeEncodeError:
                                raise ValueError("Folder contains an unsupported filename") from None
                            entries.append(_program_entry(Path(child.path), stat, is_dir))
                    except OSError:
                        continue
            entries.sort(key=lambda item: (not item["is_dir"], item["name"].casefold(), item["name"]))
        except (OSError, ValueError) as error:
            entries, selected, message = [], None, f"Cannot read folder: {error}"
    return {"path": str(candidate), "entries": entries, "selected": selected, "message": message, "places": places}


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
