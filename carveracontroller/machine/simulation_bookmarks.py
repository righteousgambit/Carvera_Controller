"""Revision-bound local preview bookmarks; no machine transport or actuation."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tempfile
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

VIEW_FIELDS = (
    "m_xRot",
    "m_yRot",
    "m_xRotTarget",
    "m_yRotTarget",
    "m_zoom",
    "m_xPan",
    "m_yPan",
    "m_distance",
    "m_xLookAt",
    "m_yLookAt",
    "m_zLookAt",
)
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class BookmarkView(TypedDict):
    m_xRot: float
    m_yRot: float
    m_xRotTarget: float
    m_yRotTarget: float
    m_zoom: float
    m_xPan: float
    m_yPan: float
    m_distance: float
    m_xLookAt: float
    m_yLookAt: float
    m_zLookAt: float
    orthographic: bool


class BookmarkRecord(TypedDict):
    id: str
    name: str
    profile_id: str
    program_hash: str
    setup_hash: str
    line: int
    source: str
    tool: int | None
    view: BookmarkView
    created_at: str


def revision_hash(value: object) -> str:
    """Canonical metadata identity. Reject nonfinite or non-JSON state."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


def validate_view(view: object) -> BookmarkView:
    if not isinstance(view, Mapping) or set(view) != {*VIEW_FIELDS, "orthographic"}:
        raise ValueError("Bookmark view fields are invalid")
    numbers: dict[str, float] = {}
    for key in VIEW_FIELDS:
        value = view[key]
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or abs(value) > 1e7
            or not math.isfinite(value)
        ):
            raise ValueError("Bookmark view must contain finite bounded values")
        if key in ("m_zoom", "m_distance") and value <= 0:
            raise ValueError("Bookmark zoom and distance must be positive")
        numbers[key] = float(value)
    if type(view["orthographic"]) is not bool:
        raise ValueError("Bookmark projection must be boolean")
    return BookmarkView(
        m_xRot=numbers["m_xRot"],
        m_yRot=numbers["m_yRot"],
        m_xRotTarget=numbers["m_xRotTarget"],
        m_yRotTarget=numbers["m_yRotTarget"],
        m_zoom=numbers["m_zoom"],
        m_xPan=numbers["m_xPan"],
        m_yPan=numbers["m_yPan"],
        m_distance=numbers["m_distance"],
        m_xLookAt=numbers["m_xLookAt"],
        m_yLookAt=numbers["m_yLookAt"],
        m_zLookAt=numbers["m_zLookAt"],
        orthographic=view["orthographic"],
    )


class BookmarkStore:
    MAX_BYTES = 2 * 1024 * 1024
    MAX_ITEMS = 500
    FIELDS = {"id", "name", "profile_id", "program_hash", "setup_hash", "line", "source", "tool", "view", "created_at"}

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/simulation-bookmarks.json")
        self.items: list[BookmarkRecord] = []
        self.load_error: str | None = None
        self._disk_hash: str | None = None
        try:
            raw = self._read_bytes()
            if raw is not None:
                self._disk_hash = hashlib.sha256(raw).hexdigest()
                data = json.loads(raw, object_pairs_hook=self._unique)
                if (
                    not isinstance(data, dict)
                    or set(data) != {"schema", "bookmarks"}
                    or type(data["schema"]) is not int
                    or data["schema"] != 1
                ):
                    raise ValueError("Unsupported bookmark document")
                self.items = self._validate_items(data["bookmarks"])
        except (OSError, ValueError, TypeError, RecursionError) as exc:
            self.load_error = str(exc)

    def _read_bytes(self) -> bytes | None:
        if not self.path.exists():
            return None
        with self.path.open("rb") as stream:
            raw = stream.read(self.MAX_BYTES + 1)
        if len(raw) > self.MAX_BYTES:
            raise ValueError("Bookmark library exceeds 2 MiB")
        return raw

    @staticmethod
    def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate bookmark field")
            result[key] = value
        return result

    @classmethod
    def _validate_items(cls, items: object) -> list[BookmarkRecord]:
        if not isinstance(items, list) or len(items) > cls.MAX_ITEMS:
            raise ValueError("Bookmark limit is 500")
        result: list[BookmarkRecord] = []
        ids: set[str] = set()
        for item in items:
            if not isinstance(item, dict) or set(item) != cls.FIELDS:
                raise ValueError("Invalid bookmark fields")
            item = copy.deepcopy(item)
            for key, limit in (("id", 36), ("name", 100), ("profile_id", 160), ("source", 16384), ("created_at", 64)):
                if (
                    not isinstance(item[key], str)
                    or (key != "source" and not item[key].strip())
                    or len(item[key]) > limit
                ):
                    raise ValueError(f"Invalid bookmark {key}")
            uuid.UUID(item["id"])
            datetime.fromisoformat(item["created_at"])
            if item["id"] in ids:
                raise ValueError("Duplicate bookmark identity")
            ids.add(item["id"])
            for key in ("program_hash", "setup_hash"):
                if not isinstance(item[key], str) or not DIGEST.fullmatch(item[key]):
                    raise ValueError("Invalid bookmark revision")
            if type(item["line"]) is not int or item["line"] < 1:
                raise ValueError("Bookmark requires a one-based line")
            if item["tool"] is not None and (type(item["tool"]) is not int or not 0 <= item["tool"] <= 99999):
                raise ValueError("Invalid bookmark tool")
            result.append(
                BookmarkRecord(
                    id=item["id"],
                    name=item["name"],
                    profile_id=item["profile_id"],
                    program_hash=item["program_hash"],
                    setup_hash=item["setup_hash"],
                    line=item["line"],
                    source=item["source"],
                    tool=item["tool"],
                    view=validate_view(item["view"]),
                    created_at=item["created_at"],
                )
            )
        return result

    def _commit(self, items: object) -> None:
        if self.load_error:
            raise ValueError(f"Repair bookmark library before saving: {self.load_error}")
        current = self._read_bytes()
        current_hash = hashlib.sha256(current).hexdigest() if current is not None else None
        if current_hash != self._disk_hash:
            raise ValueError("Bookmark library changed elsewhere; reopen before saving")
        items = self._validate_items(items)
        payload = json.dumps({"schema": 1, "bookmarks": items}, indent=2, allow_nan=False).encode()
        if len(payload) > self.MAX_BYTES:
            raise ValueError("Bookmark library exceeds 2 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".bookmarks-")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
        if self._read_bytes() != payload:
            raise OSError("Bookmark library readback differs; reopen before saving again")
        self.items = items
        self._disk_hash = hashlib.sha256(payload).hexdigest()

    def add(
        self,
        *,
        name: str,
        profile_id: str,
        program_hash: str,
        setup_hash: str,
        line: int,
        source: str,
        tool: int | None,
        view: Mapping[str, object],
    ) -> BookmarkRecord:
        item = {
            "id": str(uuid.uuid4()),
            "name": name.strip(),
            "profile_id": profile_id,
            "program_hash": program_hash,
            "setup_hash": setup_hash,
            "line": line,
            "source": source,
            "tool": tool,
            "view": validate_view(view),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._commit([*self.items, item])
        return copy.deepcopy(self.items[-1])

    def delete(self, identity: str) -> None:
        if not any(item["id"] == identity for item in self.items):
            raise ValueError("Bookmark no longer exists")
        self._commit([item for item in self.items if item["id"] != identity])

    @staticmethod
    def mismatch(item: BookmarkRecord, *, profile_id: str, program_hash: str, setup_hash: str) -> str | None:
        if item["profile_id"] != profile_id:
            return "Different machine profile"
        if item["program_hash"] != program_hash:
            return "Program revision changed"
        if item["setup_hash"] != setup_hash:
            return "Setup or tool geometry changed"
        return None
