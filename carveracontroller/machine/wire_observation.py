"""Pure original wire field parsing shared by backend observations and archives."""

from __future__ import annotations

import math


def wire_fields(text: str, left: str, right: str, state: bool = False) -> tuple[str | None, dict[str, list[float]]]:
    if not text.startswith(left) or not text.endswith(right) or len(text) > 8192:
        raise ValueError("Malformed or oversized observation")
    parts = text[1:-1].split("|")
    token = parts.pop(0) if state else None
    fields: dict[str, list[float]] = {}
    for part in parts:
        key, sep, value = part.partition(":")
        if not sep or not key or key in fields or len(value.split(",")) > 16:
            raise ValueError("Malformed or duplicate observation field")
        numbers = [float(v) for v in value.split(",")]
        if not numbers or not all(math.isfinite(v) for v in numbers):
            raise ValueError("Non-finite observation field")
        fields[key] = numbers
    return token, fields
