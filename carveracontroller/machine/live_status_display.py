"""Current packet values for live displays, in explicitly normalized units.

An older global CNC value must never fill a missing field in a newer packet.
Freshness here concerns report arrival; it does not establish sensor acquisition
latency or independent physical position/feed measurement.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


def _number(value: Any) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except (OverflowError, ValueError):
        return None


def _position(value: Any) -> tuple[float, ...] | None:
    if not isinstance(value, (list, tuple)) or not 3 <= len(value) <= 5:
        return None
    values = tuple(_number(item) for item in value)
    if any(item is None for item in values):
        return None
    return tuple(float(item) for item in values if item is not None)


@dataclass(frozen=True)
class LiveStatusDisplay:
    fresh: bool = False
    spindle_rpm: float | None = None
    spindle_target_rpm: float | None = None
    feed_mm_min: float | None = None
    feed_override_percent: float | None = None
    tool: int | None = None
    tool_offset_mm: float | None = None
    machine_position: tuple[float, ...] | None = None
    work_position: tuple[float, ...] | None = None
    wcs: int | None = None


def live_status_display(context: Mapping[str, Any], *, connected: bool, reacquiring: bool = False) -> LiveStatusDisplay:
    age = _number(context.get("arrival_age_s"))
    if not connected or reacquiring or age is None or not 0 <= age <= 0.8:
        return LiveStatusDisplay()
    raw = context.get("raw_fields")
    validity = context.get("field_validity")
    raw = raw if isinstance(raw, Mapping) else {}
    validity = validity if isinstance(validity, Mapping) else {}

    def field(key: str, index: int = 0) -> float | None:
        values = raw.get(key)
        return _number(values[index]) if isinstance(values, (list, tuple)) and len(values) > index else None

    def nonnegative(value: float | None) -> float | None:
        return value if value is not None and value >= 0 else None

    spindle_valid = validity.get("spindle_status") is not False
    tool_valid = validity.get("tool_status") is not False and "T" in raw
    tool = _number(context.get("tool")) if tool_valid else None
    tool_number = int(tool) if tool is not None and tool.is_integer() and tool >= -1 else None
    wcs = _number(context.get("wcs"))
    # These positions/feeds are already converted by the production packet
    # context. Requiring its unit identity prevents labelling raw inch values mm.
    units_known = context.get("status_linear_unit") in ("mm", "inch")
    return LiveStatusDisplay(
        fresh=True,
        spindle_rpm=nonnegative(field("S")) if spindle_valid else None,
        spindle_target_rpm=nonnegative(field("S", 1)) if spindle_valid else None,
        feed_mm_min=nonnegative(_number(context.get("planner_feed_mm_min"))) if units_known and "F" in raw else None,
        feed_override_percent=field("F", 2),
        tool=tool_number,
        tool_offset_mm=_number(context.get("tlo")) if tool_number is not None else None,
        machine_position=_position(context.get("machine_position")) if units_known and "MPos" in raw else None,
        work_position=_position(context.get("work_position")) if units_known and "WPos" in raw else None,
        wcs=int(wcs) if wcs is not None and wcs.is_integer() and 0 <= wcs <= 8 and "G" in raw else None,
    )
