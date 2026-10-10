"""Connection-local, lossless observations for Community firmware 2.1.0c.

Field meanings are pinned to Carvera_Community_Firmware feab653, Kernel.cpp,
Endstops.cpp and ZProbe.cpp. Missing fields are never filled from older reports.
Pin values are reported firmware input values, not a certified safety decision.
"""

from __future__ import annotations

import math

AXES = ("x", "y", "z", "a", "b")
STATES = frozenset(("Idle", "Run", "Home", "Hold", "Pause", "Wait", "Tool", "Alarm", "Sleep"))


def _fields(text: str, left: str, right: str, state: bool = False) -> tuple[str | None, dict[str, list[float]]]:
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


def _value(fields: dict[str, list[float]], key: str, index: int = 0) -> float | None:
    values = fields.get(key, [])
    return values[index] if len(values) > index else None


def _input(fields: dict[str, list[float]], key: str, index: int = 0) -> bool | None:
    value = _value(fields, key, index)
    return bool(value) if value in (0, 1) else None


def parse_status(text: str) -> dict:
    state, fields = _fields(text, "<", ">", state=True)
    inches = _input(fields, "C", 2)
    scale = 25.4 if inches is True else 1.0 if inches is False else None

    def position(key: str) -> dict[str, float | None]:
        values = fields.get(key, [])
        return {
            axis: (values[i] * scale if i < 3 and scale is not None else values[i] if i >= 3 else None)
            if i < len(values)
            else None
            for i, axis in enumerate(AXES)
        }

    feed = _value(fields, "F")
    return {
        "state": state if state in STATES else "Unknown",
        "reported_state": state,
        "machine_position": position("MPos"),
        "work_position": position("WPos"),
        "linear_units": "mm" if scale is not None else None,
        "rotary_units": "degrees",
        "reported_units": "inches" if inches is True else "mm" if inches is False else None,
        "absolute_mode": _input(fields, "C", 3),
        "machine_model": _value(fields, "C"),
        "features": _value(fields, "C", 1),
        "active_wcs": _value(fields, "G"),
        "rotation_degrees": _value(fields, "R"),
        "feed_mm_per_min": feed * scale if feed is not None and scale is not None else None,
        "feed_override_percent": _value(fields, "F", 2),
        "spindle_rpm": _value(fields, "S"),
        "spindle_target_rpm": _value(fields, "S", 1),
        "spindle_override_percent": _value(fields, "S", 2),
        "tool": _value(fields, "T"),
        "tool_offset_reported": _value(fields, "T", 1),
        "tool_offset_units": "firmware-reported",  # do not infer conversion from coordinate mode
        "target_tool": _value(fields, "T", 2),
        "target_collet": _value(fields, "T", 3),
        "played_lines": _value(fields, "P"),
        "progress_percent": _value(fields, "P", 1),
        "elapsed_seconds": _value(fields, "P", 2),
        "is_playing": _input(fields, "P", 3),
        "halt_reason": _value(fields, "H"),
        "raw_fields": fields,
        "raw": text,
    }


def parse_diagnostics(text: str) -> dict:
    _, fields = _fields(text, "{", "}")
    return {
        "spindle_enabled": _input(fields, "S"),
        "light_on": _input(fields, "G"),
        "air_on": _input(fields, "R"),
        "vacuum_on": _input(fields, "V"),
        "vacuum_power": _value(fields, "V", 1),
        "probe_triggered": _input(fields, "P"),
        "setter_triggered": _input(fields, "P", 1),
        "cover_input": _input(fields, "E", 5),
        "stop_input": _input(fields, "I"),
        "atc_input": _input(fields, "A"),
        "tool_sensor_input": _input(fields, "A", 1),
        "limits_reported": fields.get("E"),
        "raw_fields": fields,
        "raw": text,
    }
