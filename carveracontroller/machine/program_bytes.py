"""Bind disk bytes to a reviewed textual preview before a later local effect."""

from __future__ import annotations

import hashlib
from pathlib import Path

MAX_PROGRAM_BYTES = 64 * 1024 * 1024


def preview_digest(data: bytes) -> str:
    """Match the UTF-8/universal-newline text consumed by the program loader."""
    text = data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_program_bytes(
    path: str | Path, *, expected_preview: str | None = None, maximum: int = MAX_PROGRAM_BYTES
) -> bytes:
    """Read once, bound memory and verify those same returned bytes when reviewed.

    An absent expected identity permits explicitly selected, unreviewed files;
    it never establishes a relationship to a displayed preview or machine file.
    Callers must retain the returned bytes rather than reopen the source path.
    """
    if type(maximum) is not int or not 0 < maximum <= MAX_PROGRAM_BYTES:
        raise ValueError("Invalid program byte budget")
    with Path(path).open("rb") as stream:
        data = stream.read(maximum + 1)
    if len(data) > maximum:
        raise ValueError(f"Program exceeds the {maximum // (1024 * 1024)} MB byte budget")
    if expected_preview is not None:
        if (
            not isinstance(expected_preview, str)
            or len(expected_preview) != 64
            or any(c not in "0123456789abcdef" for c in expected_preview)
        ):
            raise ValueError("Invalid reviewed program identity")
        if preview_digest(data) != expected_preview:
            raise ValueError("Program bytes differ from the reviewed preview; reload and review the changed program")
    return data


def selected_preview_identity(
    local_path: str, remote_path: str, loaded_key: str | None, loaded_digest: str | None
) -> str | None:
    """A digest belongs to the selection only after that file's load completed."""
    selected_key = remote_path or local_path
    return loaded_digest if selected_key and loaded_key == selected_key else None
