"""Bounded byte identity for local converted CAD, independent of UI and hardware."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from os import PathLike
from pathlib import Path


def read_asset_bytes(path: str | PathLike[str], limit: int, *, cancelled: Callable[[], bool] | None = None) -> bytes:
    if cancelled is not None and cancelled():
        raise InterruptedError("CAD read cancelled")
    source = Path(path).expanduser()
    with source.open("rb") as stream:
        if cancelled is None:
            raw = stream.read(limit + 1)
        else:
            chunks, count = [], 0
            while True:
                if cancelled():
                    raise InterruptedError("CAD read cancelled")
                chunk = stream.read(min(65536, limit + 1 - count))
                count += len(chunk)
                if count > limit:
                    raise ValueError("CAD asset exceeds size limit")
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
            if cancelled():
                raise InterruptedError("CAD read cancelled")
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
