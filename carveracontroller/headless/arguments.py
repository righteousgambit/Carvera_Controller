"""Shared wire argument validation, before ownership or transport mutation."""

from __future__ import annotations

import math

MAX_FILE = 8 * 1024 * 1024


def command_line(value: object) -> None:
    if not isinstance(value, str) or not 0 < len(value) <= 120:
        raise ValueError("Command must be non-empty ASCII of at most 120 bytes")
    if any(ord(char) < 32 or ord(char) > 126 for char in value):
        raise ValueError("A command contains exactly one printable ASCII line")


def deadline(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value <= 300
        or not math.isfinite(value)
    ):
        raise ValueError("A finite numeric deadline above zero and at most 300 seconds is required")


def read_only_flag(value: object) -> None:
    if type(value) is not bool:
        raise ValueError("Read-only classification must be an explicit boolean")


def transfer_data(value: object) -> None:
    if not isinstance(value, bytes) or len(value) > MAX_FILE:
        raise ValueError("Transfer data must be bytes within the file size limit")
