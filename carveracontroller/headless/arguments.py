"""Shared wire argument validation, before ownership or transport mutation."""

from __future__ import annotations

import math
import re

MAX_FILE = 8 * 1024 * 1024
FILE_PATH = re.compile(r"/sd/gcodes/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]{1,80}\Z")


def remote_path(value: str) -> str:
    """Validate requests without importing transport code.

    Temporarily mirrors link.remote_path across the protected producer boundary.
    Parity tests preserve behavior until that owner can consolidate the validator.
    """
    if not isinstance(value, str) or not FILE_PATH.fullmatch(value) or ".." in value or len(value) > 110:
        raise ValueError("Only bounded, unambiguous paths beneath /sd/gcodes are accepted")
    return value


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
