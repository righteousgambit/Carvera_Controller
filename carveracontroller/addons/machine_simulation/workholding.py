"""Shared workholding placement for CAD rendering and editor projections."""

import math


def placed_point(point, pivot, offset, cosine, sine, jaw=0):
    x, y, z = point
    x, y = x - pivot[0], y - pivot[1] + jaw
    return (
        x * cosine - y * sine + pivot[0] + offset[0],
        x * sine + y * cosine + pivot[1] + offset[1],
        z + offset[2],
    )


def component_envelopes(profile):
    """Capture nominal component bounds once, retaining actual movable roles."""
    if profile is None:
        return (), (0, 0, 0)
    pivot = tuple(profile.workholding.get("pivot_mm", profile.workholding.get("cad_translation_mm", (0, 0, 0))))
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


def projected_envelopes(envelopes, pivot, offset, angle, jaw):
    """Return placed corners relative to the source CAD pivot, in millimeters."""
    cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    return tuple(
        (
            tuple(
                tuple(
                    value - pivot[i]
                    for i, value in enumerate(placed_point(point, pivot, offset, cosine, sine, jaw if movable else 0))
                )
                for point in corners
            ),
            movable,
        )
        for corners, movable in envelopes
    )
