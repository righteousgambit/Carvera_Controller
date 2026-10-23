"""Bounded local program references; never a controller transfer or run record."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from weakref import WeakValueDictionary

from carveracontroller.machine.artifact_fs_worker import (
    FAVORITE_LIMIT,
    PLACES_MAX_BYTES,
    PROGRAM_EXTENSIONS,
    RECENT_LIMIT,
    program_reference,
    read_program_places,
)

EXTENSIONS = PROGRAM_EXTENSIONS


class _StoreWriter:
    def __init__(self) -> None:
        self.lock = threading.Lock()


_writers: WeakValueDictionary[str, _StoreWriter] = WeakValueDictionary()
_writers_lock = threading.Lock()


@contextmanager
def _serialize_update(path: Path) -> Iterator[None]:
    # Resolve parent aliases only when a worker actually mutates the store;
    # ProgramPlaces(load=False) must not inspect possibly unavailable storage.
    # The destination name, unlike its inode or final symlink target, is stable
    # across first creation and atomic replacement. This is in-process only.
    try:
        identity = os.path.normcase(str(path.parent.resolve() / path.name))
    except RuntimeError as exc:
        raise OSError(str(exc))
    if sys.platform == "darwin":
        # macOS volumes commonly alias both case and Unicode composition.
        # Conservatively share locks for these spellings even on a volume
        # where they are distinct files; their actual data paths stay separate.
        identity = unicodedata.normalize("NFC", unicodedata.normalize("NFD", identity).casefold())
    with _writers_lock:
        writer = _writers.get(identity)
        if writer is None:
            writer = _StoreWriter()
            _writers[identity] = writer
    # Retain the strong reference while waiting and through exact readback.
    # Idle keys leave no registry entry; unrelated keys never wait here.
    with writer.lock:
        yield


class ProgramPlaces:
    MAX_BYTES = PLACES_MAX_BYTES
    RECENT_LIMIT = RECENT_LIMIT
    FAVORITE_LIMIT = FAVORITE_LIMIT

    def __init__(self, path: str | os.PathLike[str] | None = None, *, load: bool = True) -> None:
        self.path = Path(path or Path.home() / ".carvera/program-places.json")
        self.recent: list[str] = []
        self.favorites: list[str] = []
        self.error: str | None = None
        if not load:
            return
        try:
            self.recent, self.favorites = self._read()
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    @staticmethod
    def reference(value: object) -> str:
        return program_reference(value)

    def _read(self) -> tuple[list[str], list[str]]:
        return read_program_places(self.path, self.MAX_BYTES, self.RECENT_LIMIT, self.FAVORITE_LIMIT)

    def reload(self) -> None:
        try:
            recent, favorites = self._read()
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            raise
        self.recent, self.favorites, self.error = recent, favorites, None

    def _save(self, recent: list[str], favorites: list[str]) -> None:
        raw = json.dumps({"schema_version": 1, "recent": recent, "favorites": favorites}, indent=2) + "\n"
        if len(raw.encode()) > self.MAX_BYTES:
            raise ValueError("Program references exceed 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, suffix=".tmp", delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
        if self.path.read_text() != raw:
            raise OSError("Program-reference readback differs")
        self.recent, self.favorites, self.error = recent, favorites, None

    def record_recent(self, path: object) -> None:
        reference = self.reference(path)
        with _serialize_update(self.path):
            recent, favorites = self._read()
            self._save([reference] + [item for item in recent if item != reference][: self.RECENT_LIMIT - 1], favorites)

    def toggle_favorite(self, path: object) -> None:
        reference = self.reference(path)
        with _serialize_update(self.path):
            recent, favorites = self._read()
            if reference in favorites:
                favorites.remove(reference)
            elif len(favorites) >= self.FAVORITE_LIMIT:
                raise ValueError("Favorite limit is 100; remove a favorite before adding another")
            else:
                favorites.append(reference)
            self._save(recent, favorites)
