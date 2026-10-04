"""Bounded byte identity for local converted CAD, independent of UI and hardware."""

import hashlib
from pathlib import Path


def read_asset_bytes(path, limit):
    source = Path(path).expanduser()
    with source.open("rb") as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("CAD asset exceeds size limit")
    return raw


def asset_digest(path, limit=24 * 1024 * 1024):
    return hashlib.sha256(read_asset_bytes(path, limit)).hexdigest() if path else ""
