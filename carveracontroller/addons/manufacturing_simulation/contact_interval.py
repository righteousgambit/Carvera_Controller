"""Continuous contact interval for a translating vertical cylinder and a box.

Axial overlap bounds time first. Rectangle-edge crossings divide XY distance
into at most five quadratic pieces. Solving each piece localizes entry/exit
without temporal sampling. This concerns declared envelopes, not real surfaces.
"""

from __future__ import annotations

from math import sqrt

from .geometry import AABB, AxialEnvelope, SweptTool


def vertical_contact_interval(sweep: SweptTool, section: AxialEnvelope, obstacle: AABB) -> tuple[float, float] | None:
    if sweep.axis.tuple != (0, 0, 1):
        raise ValueError("Contact localization requires a fixed +Z cylinder")
    if any(
        abs(value) > 1e9
        for value in (
            *sweep.start.tuple,
            *sweep.end.tuple,
            *obstacle.minimum.tuple,
            *obstacle.maximum.tuple,
            section.high_mm,
            section.radius_mm,
        )
    ):
        raise ValueError("Contact localization coordinates exceed the bounded millimetre domain")
    if not sweep.section_bounds(section).intersects(obstacle):
        return None
    lo, hi = 0.0, 1.0
    dz = sweep.end.z - sweep.start.z
    zlo = obstacle.minimum.z - section.high_mm - sweep.start.z
    zhi = obstacle.maximum.z - section.low_mm - sweep.start.z
    if dz == 0:
        if not zlo <= 0 <= zhi:
            return None
    else:
        first, last = sorted((zlo / dz, zhi / dz))
        lo, hi = max(lo, first), min(hi, last)
        if lo > hi:
            return None
    # Subtract the start before arithmetic so a large translated origin does
    # not enter squared coefficients or the quadratic root calculation.
    coordinates = tuple(
        (end - start, lower - start, upper - start)
        for start, end, lower, upper in zip(
            sweep.start.tuple[:2], sweep.end.tuple[:2], obstacle.minimum.tuple[:2], obstacle.maximum.tuple[:2]
        )
    )
    breaks = {lo, hi}
    for delta, lower, upper in coordinates:
        if delta:
            for edge in (lower, upper):
                t = edge / delta
                if lo < t < hi:
                    breaks.add(t)
    times = sorted(breaks)
    intervals = []
    # The single-point axial overlap still has to satisfy the radial condition.
    pieces = tuple(zip(times, times[1:])) or ((lo, hi),)
    for a, b in pieces:
        middle = (a + b) / 2
        offsets = []
        for delta, lower, upper in coordinates:
            value = delta * middle
            nearest_edge = lower if value < lower else upper if value > upper else None
            if nearest_edge is not None:
                offsets.append((delta * a - nearest_edge, delta))
        slope = sum(delta * delta for _offset, delta in offsets)
        if slope == 0:
            if sum(offset * offset for offset, _delta in offsets) <= section.radius_mm**2 + 1e-12:
                intervals.append((a, b))
            continue
        vertex = -sum(offset * delta for offset, delta in offsets) / slope
        minimum = sum((offset + delta * vertex) ** 2 for offset, delta in offsets)
        remainder = section.radius_mm**2 - minimum
        if remainder < -1e-12:
            continue
        radius_time = sqrt(max(0.0, remainder) / slope)
        first, last = max(a, a + vertex - radius_time), min(b, a + vertex + radius_time)
        if first <= last:
            intervals.append((first, last))
    return (min(first for first, _last in intervals), max(last for _first, last in intervals)) if intervals else None
