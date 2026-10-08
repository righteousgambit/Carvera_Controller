"""Presentation-only assembly separation in nominal machine millimetres."""

from math import isfinite
from typing import cast

DIRECTIONS = {
    "fixed": (-2, 0, 1),
    "carriage": (-2, 0, 1),
    "fixture": (0, 0, 1),
    "workholding": (0, 0, 2),
    "stock": (0, 0, 3),
    "repeat_stock": (0, 0, 3),
    "atc": (2, 0, 1),
    "spindle": (2, 0, 3),
    "cutter": (2, 0, 3),
}


def validate_explosion(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Exploded separation must be between 0 and 100 mm")
    number = cast(float, value)
    if not 0 <= number <= 100 or not isfinite(number):
        raise ValueError("Exploded separation must be between 0 and 100 mm")
    return float(number)


def explosion_offset(group: str, distance: float, mode: str) -> tuple[float, float, float]:
    distance = validate_explosion(distance)
    if mode != "Preview":
        return (0.0, 0.0, 0.0)
    x, y, z = DIRECTIONS.get(group, (0, 0, 0))
    return x * distance, y * distance, z * distance
