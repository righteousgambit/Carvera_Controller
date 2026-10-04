"""Bounded local program references; never a controller transfer or run record."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

EXTENSIONS = frozenset({".cnc", ".nc", ".gcode", ".tap", ".ngc"})


class ProgramPlaces:
    MAX_BYTES = 1024 * 1024
    RECENT_LIMIT = 25
    FAVORITE_LIMIT = 100

    def __init__(self, path=None, *, load=True):
        self.path = Path(path or Path.home() / ".carvera/program-places.json")
        self.recent, self.favorites, self.error = [], [], None
        if not load:
            return
        try:
            self.recent, self.favorites = self._read()
        except (OSError, ValueError) as exc:
            self.error = str(exc)

    @staticmethod
    def reference(value):
        if not isinstance(value, (str, os.PathLike)):
            raise ValueError("Invalid local program reference")
        value = os.fspath(value)
        if not isinstance(value, str) or not value or len(value) > 4096 or "\x00" in value:
            raise ValueError("Invalid local program reference")
        path = Path(value)
        if not path.is_absolute() or path.suffix.casefold() not in EXTENSIONS:
            raise ValueError("Program references require an absolute supported program path")
        # Normalize traversal without resolving symlinks or changing user-facing mounts.
        return os.path.normpath(value)

    def _read(self):
        if not self.path.exists():
            return [], []
        if self.path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Program references exceed 1 MiB")
        data = json.loads(self.path.read_text())
        if not isinstance(data, dict) or set(data) != {"schema_version", "recent", "favorites"}:
            raise ValueError("Invalid program-reference document")
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError("Unsupported program-reference schema")
        result = []
        for name, limit in (("recent", self.RECENT_LIMIT), ("favorites", self.FAVORITE_LIMIT)):
            values = data[name]
            if not isinstance(values, list) or len(values) > limit:
                raise ValueError(f"Invalid {name} program references")
            normalized = [self.reference(value) for value in values]
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"Duplicate {name} program references")
            result.append(normalized)
        return tuple(result)

    def reload(self):
        try:
            recent, favorites = self._read()
        except (OSError, ValueError) as exc:
            self.error = str(exc)
            raise
        self.recent, self.favorites, self.error = recent, favorites, None

    def _save(self, recent, favorites):
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

    def record_recent(self, path):
        path = self.reference(path)
        recent, favorites = self._read()
        self._save([path] + [item for item in recent if item != path][: self.RECENT_LIMIT - 1], favorites)

    def toggle_favorite(self, path):
        path = self.reference(path)
        recent, favorites = self._read()
        if path in favorites:
            favorites.remove(path)
        elif len(favorites) >= self.FAVORITE_LIMIT:
            raise ValueError("Favorite limit is 100; remove a favorite before adding another")
        else:
            favorites.append(path)
        self._save(recent, favorites)
