"""Conservative exact directional bounds for complete rotating cylinders."""

from __future__ import annotations

from fractions import Fraction as F
from math import isqrt

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.machine.rotating_surface import dimensions
from carveracontroller.machine.surface_directions import DIRECTIONS, DirectionBounds


def _radial_norm_upper(x: int, y: int) -> F:
    """Exact square root or an outward rational upper bound, never rounded float."""
    square = x * x + y * y
    root = isqrt(square)
    if root * root == square:
        return F(root)
    scale = 1 << 32
    return F(isqrt(square * scale * scale) + 1, scale)


_RADIAL_NORMS = tuple(_radial_norm_upper(x, y) for x, y, _z in DIRECTIONS)


def section_projections(section: AxialEnvelope, error: float) -> DirectionBounds:
    """Enclose the entire padded section in every retained fixed direction.

    A cylinder's support is radius*sqrt(nx^2+ny^2) plus its complete axial
    interval. Outward rational norms preserve tangency and shaped sections'
    enclosing cylinders. These bounds reject candidates; they certify no hit.
    """
    low, high, radius = dimensions(section, error)
    return tuple(
        (min(z * low, z * high) - norm * radius, max(z * low, z * high) + norm * radius)
        for (_x, _y, z), norm in zip(DIRECTIONS, _RADIAL_NORMS)
    )
