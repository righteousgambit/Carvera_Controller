"""Bounded byte identity for local converted CAD, independent of UI and hardware."""

from __future__ import annotations

import hashlib
from os import PathLike
from pathlib import Path


def read_asset_bytes(path: str | PathLike[str], limit: int) -> bytes:
    source = Path(path).expanduser()
    with source.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("CAD asset exceeds size limit")
    return raw


def asset_digest(path: str | PathLike[str] | None, limit: int = 24 * 1024 * 1024) -> str:
    return hashlib.sha256(read_asset_bytes(path, limit)).hexdigest() if path else ""
