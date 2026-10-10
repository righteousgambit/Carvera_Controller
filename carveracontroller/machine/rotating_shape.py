"""Declared spherical/conical cutting profiles, with exact full-chord witnesses.

The cutting envelope is rotational, not an individual flute or thread tooth.
Quadratic minima on a bounded three-variable polytope are found on every face:
vertices and feasible stationary points of all independent active sets. Singular
stationary faces have a flat direction reaching a lower face, also enumerated.
No temporal sampling, tessellation or numerical optimizer is involved.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction as F
from itertools import combinations
from math import isfinite
from typing import Literal

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope, ToolGeometry
from carveracontroller.machine.surface_motion import Point, QPoint, Triangle, dot, qpoint, sub


@dataclass(frozen=True)
class RotatingShape(AxialEnvelope):
    primitive: Literal["sphere", "cone"] = "sphere"
    low_radius_mm: float = 0.0
    center_mm: float = 0.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.component != "cutter" or self.primitive not in ("sphere", "cone"):
            raise ValueError("Shaped rotation requires a spherical or conical cutting section")
        if any(
            type(v) not in (int, float) or not isfinite(v) or abs(v) > 10000
            for v in (self.low_mm, self.high_mm, self.radius_mm, self.low_radius_mm, self.center_mm)
        ):
            raise ValueError("Shaped cutting dimensions must be finite bounded numbers")
        if self.primitive == "sphere":
            if self.low_radius_mm != 0 or not (
                self.center_mm - self.radius_mm <= self.low_mm < self.high_mm <= self.center_mm + self.radius_mm
            ):
                raise ValueError("Spherical cutting section must retain its axial center and caps")
        elif self.center_mm != 0 or not 0 <= self.low_radius_mm < self.radius_mm:
            raise ValueError("Conical cutting section needs increasing endpoint radii and no sphere center")


def cutting_sections(tool: ToolGeometry) -> tuple[AxialEnvelope, ...]:
    """Profile parameters are declared nominal dimensions, not measured geometry."""
    radius, high = tool.diameter_mm / 2, tool.flute_length_mm
    note = f"declared {tool.shape} rotational cutting profile"
    sections: list[AxialEnvelope] = []
    bottom = 0.0
    rounded = radius if tool.shape == "ball" else tool.corner_radius_mm if tool.shape == "tapered" else 0.0
    if rounded:
        stop = min(rounded, high)
        sections.append(RotatingShape("cutter", 0, stop, rounded, note, "sphere", 0, rounded))
        bottom = stop
    if tool.shape in ("drill", "tapered", "chamfer", "engraving"):
        stop = next((v for v in tool.profile_breaks_mm if v > bottom), high)
        low_radius = tool.axial_radius(bottom)
        upper_radius = tool.axial_radius(stop)
        if upper_radius > low_radius:
            sections.append(RotatingShape("cutter", bottom, stop, upper_radius, note, "cone", low_radius))
            bottom = stop
    if bottom < high:
        sections.append(AxialEnvelope("cutter", bottom, high, radius, note))
    # Bull corners and thread teeth retain the published outside-radius method.
    if tool.shape in ("flat", "bull", "threadmill"):
        return (AxialEnvelope("cutter", 0, high, radius),)
    return tuple(sections)


def _linear(matrix: Sequence[Sequence[F]], rhs: Sequence[F]) -> tuple[F, ...] | None:
    n = len(rhs)
    rows = [list(row) + [value] for row, value in zip(matrix, rhs)]
    for col in range(n):
        pivot = next((i for i in range(col, n) if rows[i][col]), None)
        if pivot is None:
            return None
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [value / divisor for value in rows[col]]
        for i in range(n):
            if i != col:
                factor = rows[i][col]
                rows[i] = [a - factor * b for a, b in zip(rows[i], rows[col])]
    return tuple(row[-1] for row in rows)


def _minimum(
    terms: Sequence[tuple[F, QPoint, F]],
    constraints: Sequence[tuple[QPoint, F]],
    cancelled: Callable[[], bool],
) -> QPoint | None:
    h = [[sum((sign * a[i] * a[j] for sign, a, _b in terms), F(0)) for j in range(3)] for i in range(3)]
    g = [sum((sign * a[i] * b for sign, a, b in terms), F(0)) for i in range(3)]
    best: tuple[F, QPoint] | None = None
    for count in range(4):
        for active in combinations(constraints, count):
            if cancelled():
                raise InterruptedError("Shaped rotating query cancelled; no partial report")
            if count == 3:
                solution = _linear([a for a, _b in active], [b for _a, b in active])
            else:
                matrix = [h[i] + [a[i] for a, _b in active] for i in range(3)]
                matrix.extend([list(a) + [F(0)] * count for a, _b in active])
                solution = _linear(matrix, [-v for v in g] + [b for _a, b in active])
            if solution is None:
                continue
            p: QPoint = solution[0], solution[1], solution[2]
            if any(dot(a, p) > b for a, b in constraints):
                continue
            value = sum((sign * (dot(a, p) + b) ** 2 for sign, a, b in terms), F(0))
            if best is None or value < best[0]:
                best = value, p
    return best[1] if best is not None and best[0] <= 0 else None


def shape_contact(
    section: RotatingShape,
    triangle: Triangle,
    shift: Point,
    delta: Point,
    error: float,
    cancelled: Callable[[], bool],
) -> tuple[F, QPoint, tuple[F, F, F], F] | None:
    """Return a feasible exact witness, not entry time or a tool boundary point."""
    a, b, c = (qpoint(p) for p in triangle)
    e, f = sub(b, a), sub(c, a)
    start, speed = qpoint(shift), qpoint(delta)
    axes: tuple[QPoint, ...] = tuple((e[j], f[j], -speed[j]) for j in range(3))
    offsets = sub(a, start)
    pad, zero = F(error), (F(0), F(0), F(0))
    low, high, radius = F(section.low_mm) - pad, F(section.high_mm) + pad, F(section.radius_mm) + 2 * pad
    pieces: list[tuple[F, F, list[tuple[F, QPoint, F]]]] = []
    radial = [(F(1), axes[j], offsets[j]) for j in range(2)]
    if section.primitive == "sphere":
        pieces.append((low, high, radial + [(F(1), axes[2], offsets[2] - F(section.center_mm)), (F(-1), zero, radius)]))
    else:
        slope = (F(section.radius_mm) - F(section.low_radius_mm)) / (F(section.high_mm) - F(section.low_mm))
        cone_high = F(section.high_mm) - pad
        radius_axis: QPoint = slope * axes[2][0], slope * axes[2][1], slope * axes[2][2]
        radius_offset = F(section.low_radius_mm) + 2 * pad + slope * (offsets[2] - low)
        pieces.append((low, cone_high, radial + [(F(-1), radius_axis, radius_offset)]))
        if pad:
            pieces.append((cone_high, high, radial + [(F(-1), zero, radius)]))
    for bottom, top, terms in pieces:
        constraints: tuple[tuple[QPoint, F], ...] = (
            ((F(-1), F(0), F(0)), F(0)),
            ((F(0), F(-1), F(0)), F(0)),
            ((F(1), F(1), F(0)), F(1)),
            ((F(0), F(0), F(-1)), F(0)),
            ((F(0), F(0), F(1)), F(1)),
            (axes[2], top - offsets[2]),
            ((-axes[2][0], -axes[2][1], -axes[2][2]), offsets[2] - bottom),
        )
        p = _minimum(terms, constraints, cancelled)
        if p is not None:
            u, v, t = p
            point: QPoint = (a[0] + u * e[0] + v * f[0], a[1] + u * e[1] + v * f[1], a[2] + u * e[2] + v * f[2])
            distance = sum(((dot(axes[j], p) + offsets[j]) ** 2 for j in range(2)), F(0))
            return t, point, (1 - u - v, u, v), distance
    return None
