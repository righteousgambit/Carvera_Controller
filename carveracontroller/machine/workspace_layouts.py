"""Bounded named presentation layouts. No machine setup or execution state."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import TypedDict

from carveracontroller.machine.simulation_bookmarks import BookmarkView, validate_view


class LayoutRecord(TypedDict):
    name: str
    media_share: float
    camera_visible: bool
    section: str
    task: str | None
    scroll: float | None
    view: BookmarkView


def validate_layout(value: object) -> LayoutRecord:
    fields = {"name", "media_share", "camera_visible", "section", "task", "scroll", "view"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Invalid workspace layout fields")
    name = value["name"]
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 80:
        raise ValueError("Enter a layout name of 1–80 characters")
    share = value["media_share"]
    if type(share) not in (int, float) or not math.isfinite(share) or not 0.25 <= share <= 0.75:
        raise ValueError("Media share must be between 25% and 75%")
    if type(value["camera_visible"]) is not bool:
        raise ValueError("Camera visibility must be boolean")
    if not isinstance(value["section"], str) or not value["section"] or len(value["section"]) > 80:
        raise ValueError("Invalid workbench section")
    if value["task"] is not None and (
        not isinstance(value["task"], str) or not value["task"] or len(value["task"]) > 80
    ):
        raise ValueError("Invalid workbench task")
    scroll = value["scroll"]
    if value["task"] is None:
        if scroll is not None:
            raise ValueError("Reading position requires a task")
    elif type(scroll) not in (int, float) or not math.isfinite(scroll) or not 0 <= scroll <= 1:
        raise ValueError("Reading position must be between zero and one")
    return {
        "camera_visible": value["camera_visible"],
        "section": value["section"],
        "task": value["task"],
        "scroll": value["scroll"],
        "name": name.strip(),
        "media_share": float(share),
        "view": validate_view(value["view"]),
    }


class WorkspaceLayouts:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/workspace-layouts.json")
        self.records: list[LayoutRecord] = []
        self.load_error: str | None = None
        try:
            if self.path.exists():
                self.records = read_layout_file(self.path)
        except (ValueError, TypeError, OSError) as exc:
            self.load_error = str(exc)

    def save(self, record: object) -> None:
        record = validate_layout(record)
        self._write([r for r in self.records if r["name"] != record["name"]] + [record])

    def delete(self, name: str) -> None:
        if name not in {r["name"] for r in self.records}:
            raise ValueError("Select a saved layout")
        self._write([r for r in self.records if r["name"] != name])

    def export_file(self, path: Path | str) -> str:
        if self.load_error:
            raise ValueError("Repair the layout library before exporting: " + self.load_error)
        records = [validate_layout(r) for r in self.records]
        raw = json.dumps({"schema": 1, "layouts": records}, allow_nan=False, indent=2).encode()
        if len(raw) > 256 * 1024 or len(records) > 50:
            raise ValueError("Layout export exceeds library limits")
        path = Path(path)
        with path.open("xb") as stream:
            stream.write(raw)
        if read_layout_file(path) != records or path.read_bytes() != raw:
            raise OSError("Layout export readback mismatch")
        return hashlib.sha256(raw).hexdigest()

    def import_file(self, path: Path | str) -> int:
        incoming = read_layout_file(path)
        existing = {r["name"]: r for r in self.records}
        conflicts = [r["name"] for r in incoming if r["name"] in existing and r != existing[r["name"]]]
        if conflicts:
            raise ValueError("Layout names conflict; rename before importing: " + ", ".join(conflicts))
        added = [r for r in incoming if r["name"] not in existing]
        self._write(self.records + added)
        return len(added)

    def _write(self, records: list[LayoutRecord]) -> None:
        if self.load_error:
            raise ValueError("Repair the layout library before saving: " + self.load_error)
        if len(records) > 50:
            raise ValueError("Keep at most 50 layouts")
        raw = json.dumps({"schema": 1, "layouts": records}, allow_nan=False, indent=2).encode()
        if len(raw) > 256 * 1024:
            raise ValueError("Workspace layouts exceed 256 KiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(raw)
            os.replace(temporary, self.path)
            if self.path.read_bytes() != raw:
                raise OSError("Layout save readback mismatch")
            self.records = copy.deepcopy(records)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def read_layout_file(path: Path | str) -> list[LayoutRecord]:
    with Path(path).open("rb") as stream:
        raw = stream.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ValueError("Workspace layouts exceed 256 KiB")
    data = json.loads(raw)
    if (
        not isinstance(data, dict)
        or set(data) != {"schema", "layouts"}
        or type(data["schema"]) is not int
        or data["schema"] != 1
    ):
        raise ValueError("Unsupported workspace layout library")
    items = data["layouts"]
    if not isinstance(items, list) or len(items) > 50:
        raise ValueError("Keep at most 50 layouts")
    records = [validate_layout(item) for item in items]
    if len({r["name"] for r in records}) != len(records):
        raise ValueError("Layout names must be unique")
    return records
