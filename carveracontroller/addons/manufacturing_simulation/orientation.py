"""Fixed right-handed stock orientation: extrinsic X, then Y, then Z."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from math import cos, isfinite, radians, sin

Point = tuple[float, float, float]


@dataclass(frozen=True)
class StockOrientation:
    degrees: Point = (0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        try:
            valid = (
                isinstance(self.degrees, (tuple, list))
                and len(self.degrees) == 3
                and all(type(v) in (int, float) and isfinite(v) for v in self.degrees)
            )
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("Stock rotation requires three finite orientation angles in degrees")
        object.__setattr__(self, "degrees", tuple((v + 180) % 360 - 180 for v in self.degrees))

    @classmethod
    def from_z_tilt(cls, z: float, tilt: Sequence[float]) -> StockOrientation:
        if not isinstance(tilt, (tuple, list)) or len(tilt) != 2:
            raise ValueError("Stock tilt requires X and Y angles in degrees")
        return cls((tilt[0], tilt[1], z))

    @cached_property
    def matrix(self) -> tuple[Point, Point, Point]:
        x, y, z = (radians(v) for v in self.degrees)
        cx, sx, cy, sy, cz, sz = cos(x), sin(x), cos(y), sin(y), cos(z), sin(z)
        return (
            (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
            (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
            (-sy, cy * sx, cy * cx),
        )

    def apply(self, point: Sequence[float], *, inverse: bool = False) -> Point:
        if len(point) != 3:
            raise ValueError("Stock orientation requires XYZ coordinates")
        rows = self.matrix
        if inverse:
            result = tuple(sum(rows[j][i] * point[j] for j in range(3)) for i in range(3))
        else:
            result = tuple(sum(row[i] * point[i] for i in range(3)) for row in rows)
        return result[0], result[1], result[2]
