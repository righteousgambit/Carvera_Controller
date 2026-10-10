"""Closed-solid occupancy between continuous surface-contact intervals.

Separation classifies every connected boundary shell in both solids;
containment stops at its first witness. With no boundary crossing, occupancy
cannot change. Surface enclosures remain possible contact, never discarded.
"""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from carveracontroller.addons.manufacturing_simulation.stock_solid import (
    SolidBudget,
    SolidBudgetExceeded,
    TriangleSolid,
)
from carveracontroller.machine.surface_motion import (
    Point,
    QPoint,
    SurfaceBudget,
    SurfaceContact,
    SurfaceMesh,
    mesh_contacts,
    qpoint,
)


@dataclass(frozen=True)
class OccupancyInterval:
    lower: Fraction
    upper: Fraction
    lower_closed: bool
    upper_closed: bool
    state: Literal["contained", "separated"]
    sample: Fraction
    contained_side: Literal["first", "second"] | None = None
    witness_triangle: int | None = None
    witness_point: QPoint | None = None


@dataclass(frozen=True)
class SolidPairReview:
    contacts: tuple[SurfaceContact, ...]
    intervals: tuple[OccupancyInterval, ...]
    gap: str = ""


def separated_intervals(hits: Sequence[SurfaceContact]) -> tuple[tuple[Fraction, Fraction, bool, bool], ...]:
    """Complement of closed possible-contact ranges in [0,1]."""
    merged: list[tuple[Fraction, Fraction]] = []
    for hit in sorted(hits, key=lambda c: (c.lower, c.upper)):
        lo, hi = hit.lower, hit.upper
        if not 0 <= lo <= hi <= 1:
            raise ValueError("Invalid closed surface contact interval")
        if merged and lo <= merged[-1][1]:
            merged[-1] = merged[-1][0], max(merged[-1][1], hi)
        else:
            merged.append((lo, hi))
    if not merged:
        return ((Fraction(0), Fraction(1), True, True),)
    result = []
    cursor = Fraction(0)
    left_closed = True
    for lo, hi in merged:
        if cursor < lo:
            result.append((cursor, lo, left_closed, False))
        cursor = hi
        left_closed = False
    if cursor < 1:
        result.append((cursor, Fraction(1), False, True))
    return tuple(result)


def review_solid_pair(
    first: SurfaceMesh,
    second: SurfaceMesh,
    shift: Point,
    delta: Point,
    *,
    position_error_mm: float = 0.0,
    surface_budget: SurfaceBudget | None = None,
    budget: SolidBudget | None = None,
    cache: MutableMapping[int, TriangleSolid | str] | None = None,
) -> SolidPairReview:
    budget = budget or SolidBudget(cancelled=surface_budget.cancelled if surface_budget is not None else None)
    cache = {} if cache is None else cache
    qs, qd = qpoint(shift), qpoint(delta)
    hits = mesh_contacts(first, second, shift, delta, position_error_mm=position_error_mm, budget=surface_budget)
    spans = separated_intervals(hits)
    if not spans:
        return SolidPairReview(hits, ())  # Surface enclosures already cover the pair.
    solids = []
    for label, mesh in (("first", first), ("second", second)):
        key = id(mesh)
        if key not in cache:
            try:
                cache[key] = TriangleSolid.validate(mesh.triangles, budget=budget)
            except SolidBudgetExceeded:
                raise
            except ValueError as exc:
                cache[key] = str(exc)[:250]
        value = cache[key]
        if isinstance(value, str):
            return SolidPairReview(hits, (), f"{label} solid unavailable: {value}")
        solids.append(value)
    result = []
    for lo, hi, left_closed, right_closed in spans:
        sample = (lo + hi) / 2
        relative = tuple(qs[a] + sample * qd[a] for a in range(3))
        witness = None
        try:
            for side, solid, container, sign in (
                ("first", solids[0], solids[1], 1),
                ("second", solids[1], solids[0], -1),
            ):
                for triangle, point in solid.representatives:
                    query = tuple(Fraction(point[a]) + sign * relative[a] for a in range(3))
                    state = container.classify(query, budget=budget)
                    if state == "boundary":
                        raise ValueError("Shell witness reaches a boundary outside the surface enclosure")
                    if state == "inside":
                        witness = (side, triangle, point)
                        break
                if witness:
                    break
        except SolidBudgetExceeded:
            raise
        except ValueError as exc:
            return SolidPairReview(hits, (), "Solid classification unavailable: " + str(exc)[:250])
        if witness:
            side, triangle, point = witness
            result.append(
                OccupancyInterval(
                    lo,
                    hi,
                    left_closed,
                    right_closed,
                    "contained",
                    sample,
                    "first" if side == "first" else "second",
                    triangle,
                    qpoint(point),
                )
            )
        else:
            result.append(OccupancyInterval(lo, hi, left_closed, right_closed, "separated", sample))
    return SolidPairReview(hits, tuple(result))
