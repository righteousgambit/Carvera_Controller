"""Bounded byte identity for local converted CAD, independent of UI and hardware."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from os import PathLike
from pathlib import Path


def read_asset_bytes(path: str | PathLike[str], limit: int) -> bytes:
    source = Path(path).expanduser()
    with source.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("CAD asset exceeds size limit")
    return raw


def asset_digest(
    path: str | PathLike[str] | None,
    limit: int = 24 * 1024 * 1024,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> str:
    if cancelled is None:
        return hashlib.sha256(read_asset_bytes(path, limit)).hexdigest() if path else ""
    digest, count = hashlib.sha256(), 0
    if cancelled():
        raise InterruptedError("CAD verification cancelled")
    if not path:
        return ""
    with Path(path).expanduser().open("rb") as stream:
        while True:
            if cancelled():
                raise InterruptedError("CAD verification cancelled")
            chunk = stream.read(min(65536, limit + 1 - count))
            count += len(chunk)
            if count > limit:
                raise ValueError("CAD asset exceeds size limit")
            if not chunk:
                break
            digest.update(chunk)
    if cancelled():
        raise InterruptedError("CAD verification cancelled")
    return digest.hexdigest()
