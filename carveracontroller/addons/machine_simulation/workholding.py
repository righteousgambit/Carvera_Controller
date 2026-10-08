"""Shared workholding placement for CAD rendering and editor projections."""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .profile import MachineProfile

Point = tuple[float, float, float]
Envelope = tuple[tuple[Point, ...], bool]


def placed_point(
    point: Sequence[float],
    pivot: Sequence[float],
    offset: Sequence[float],
    cosine: float,
    sine: float,
    jaw: float = 0,
) -> Point:
    x, y, z = point
    x, y = x - pivot[0], y - pivot[1] + jaw
    return (
        x * cosine - y * sine + pivot[0] + offset[0],
        x * sine + y * cosine + pivot[1] + offset[1],
        z + offset[2],
    )


def component_envelopes(profile: MachineProfile | None) -> tuple[tuple[Envelope, ...], Point]:
    """Capture nominal component bounds once, retaining actual movable roles."""
    if profile is None:
        return (), (0, 0, 0)
    pivot = profile.workholding_pivot_mm
    result = []
    for component in profile.components:
        if component["group"] != "workholding":
            continue
        values = component["vertices"]
        low = tuple(min(values[i::10]) for i in range(3))
        high = tuple(max(values[i::10]) for i in range(3))
        corners = tuple((x, y, z) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2]))
        movable = component.get("workholding_role", component.get("role")) == "movable"
        result.append((corners, movable))
    return tuple(result), pivot


def projected_envelopes(
    envelopes: Sequence[Envelope],
    pivot: Sequence[float],
    offset: Sequence[float],
    angle: float,
    jaw: float,
) -> tuple[Envelope, ...]:
    """Return placed corners relative to the source CAD pivot, in millimeters."""
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return tuple(
        (
            tuple(
                relative_point(placed_point(point, pivot, offset, cosine, sine, jaw if movable else 0), pivot)
                for point in corners
            ),
            movable,
        )
        for corners, movable in envelopes
    )


def relative_point(point: Point, pivot: Sequence[float]) -> Point:
    return point[0] - pivot[0], point[1] - pivot[1], point[2] - pivot[2]
