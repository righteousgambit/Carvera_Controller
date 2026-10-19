"""Atomic local preference replacement with a retained-file revision check."""

from __future__ import annotations

import os
import stat
import tempfile
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
