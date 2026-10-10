"""Original static triangle SAT on one exact integer grid, without rounding."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from fractions import Fraction

from carveracontroller.addons.manufacturing_simulation.solid_separation import IPoint, cross, dot, sub

QPoint = tuple[Fraction, Fraction, Fraction]


def static_contact(first: Sequence[QPoint], second: Sequence[QPoint], shift: QPoint, padding: Fraction) -> bool:
    """Same complete static projection family and L1 allowance as rational SAT.

    Inputs come from validated binary64/int coordinates and error. A common
    power-of-two scale embeds every value exactly. Axes of different polynomial
    degree multiply both sides of their inequality by the same positive factor.
    No geometric repair, normalization, tolerance or additional culling axes.
    """
    values = (*first, *second, shift)
    scale = max(padding.denominator, *(v.denominator for p in values for v in p))
    if scale & (scale - 1) or any(scale % v.denominator for p in values for v in p) or scale % padding.denominator:
        raise ValueError("Static surface predicate requires exact dyadic inputs")

    def point(row: QPoint) -> IPoint:
        return (
            row[0].numerator * (scale // row[0].denominator),
            row[1].numerator * (scale // row[1].denominator),
            row[2].numerator * (scale // row[2].denominator),
        )

    a, b = tuple(point(p) for p in first), tuple(point(p) for p in second)
    start = point(shift)
    allowance_scale = padding.numerator * (scale // padding.denominator)

    def axes() -> Iterable[IPoint]:
        yield 1, 0, 0
        yield 0, 1, 0
        yield 0, 0, 1
        ea, eb = ([sub(row[(i + 1) % 3], row[i]) for i in range(3)] for row in (a, b))
        na, nb = cross(ea[0], ea[1]), cross(eb[0], eb[1])
        yield na
        yield nb
        for u in ea:
            for v in eb:
                yield cross(u, v)
        for normal in (na, nb):
            for edge in ea + eb:
                yield cross(normal, edge)

    for axis in axes():
        if not any(axis):
            continue
        pa, pb = [dot(p, axis) for p in a], [dot(p, axis) for p in b]
        allowance = allowance_scale * sum(abs(v) for v in axis)
        offset = dot(start, axis)
        if min(pb) - max(pa) - allowance - offset > 0 or max(pb) - min(pa) + allowance - offset < 0:
            return False
    return True
