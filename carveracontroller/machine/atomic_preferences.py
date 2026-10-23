"""Atomic local preference replacement with a retained-file revision check."""

from __future__ import annotations

import io
import os
import stat
import tempfile
from collections.abc import Mapping
from configparser import ConfigParser
from pathlib import Path

MAX_CONFIG_BYTES = 4 * 1024 * 1024


def preference_bytes(path: Path) -> bytes | None:
    if path.is_symlink():
        raise ValueError("Preference target must not be a symbolic link")
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_CONFIG_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(data) > MAX_CONFIG_BYTES:
        raise ValueError("Preference file exceeds the 4 MB budget")
    return data


def replace_preferences(path: Path, expected: bytes | None, content: bytes) -> None:
    """No visible write before replace; no fallible operation after commit.

    The revision check detects intervening writes; it is not a cross-process
    compare-and-swap or a claim of crash durability after power loss.
    """
    if len(content) > MAX_CONFIG_BYTES:
        raise ValueError("Preference file exceeds the 4 MB budget")
    if preference_bytes(path) != expected:
        raise ValueError("Preferences changed during job publication; import again")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".carvera-preferences-", delete=False) as stream:
            temporary = Path(stream.name)
            if path.exists():
                os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if preference_bytes(path) != expected:
            raise ValueError("Preferences changed during job publication; import again")
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def merge_preference_updates(expected: bytes | None, baseline: bytes, updates: Mapping[str, str]) -> bytes:
    """Update only job-owned options; preserve unrelated retained file values.

    Existing file data is authoritative even when the in-memory UI cache is
    older. A missing file is explicitly seeded from the current application.
    Invalid or oversized input is refused before any visible file write.
    """
    raw = baseline if expected is None else expected
    if len(raw) > MAX_CONFIG_BYTES:
        raise ValueError("Preference file exceeds the 4 MB budget")
    parser = ConfigParser(interpolation=None)
    parser.read_string(raw.decode("utf-8"))
    if not parser.has_section("carvera"):
        parser.add_section("carvera")
    for key, value in updates.items():
        parser.set("carvera", key, value)
    stream = io.StringIO()
    parser.write(stream)
    encoded = stream.getvalue().encode("utf-8")
    if len(encoded) > MAX_CONFIG_BYTES:
        raise ValueError("Preference file exceeds the 4 MB budget")
    return encoded
