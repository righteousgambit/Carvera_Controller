"""Complete declared rotating-section/mesh queries with shared review budgets."""

from __future__ import annotations

from collections.abc import MutableMapping, Sequence
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Literal

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.manufacturing_simulation.stock_solid import (
    SolidBudget,
    SolidBudgetExceeded,
    SolidRowReuse,
    TriangleSolid,
)
from carveracontroller.machine.rotating_directions import section_projections
from carveracontroller.machine.rotating_shape import RotatingShape
from carveracontroller.machine.rotating_surface import box_candidate, dimensions, triangle_contact
from carveracontroller.machine.surface_directions import overlap_interval, project
from carveracontroller.machine.surface_motion import Point, QPoint, SurfaceBudget, SurfaceMesh, qpoint


@dataclass(frozen=True)
class RotatingSectionReview:
    section_index: int
    state: Literal["possible_contact", "contained", "separated", "unavailable"]
    sample: F = F(1, 2)
    witness_point: QPoint | None = None
    witness_triangle: int | None = None
    other_section_index: int | None = None
    radial_distance_squared: F | None = None
    barycentric: tuple[F, F, F] | None = None
    reason: str = ""


def cylinder_pair(
    first: AxialEnvelope, second: AxialEnvelope, shift: QPoint, delta: QPoint, error: float, upper_time: F = F(1)
) -> tuple[F, QPoint, F] | None:
    """Exact continuous existence for parallel declared +Z cylinders."""
    if type(upper_time) is not F or not 0 <= upper_time <= 1:
        raise ValueError("Rotating time prefix must be an exact fraction in [0, 1]")
    low, high, radius = dimensions(first, error)
    other_low, other_high, other_radius = dimensions(second)
    lower, upper = other_low - high - shift[2], other_high - low - shift[2]
    lo, hi = F(0), upper_time
    if delta[2]:
        a, b = lower / delta[2], upper / delta[2]
        lo, hi = max(lo, min(a, b)), min(hi, max(a, b))
        if lo > hi:
            return None
    elif not lower <= 0 <= upper:
        return None
    denominator = delta[0] ** 2 + delta[1] ** 2
    time = max(lo, min(hi, -(shift[0] * delta[0] + shift[1] * delta[1]) / denominator)) if denominator else lo
    center = tuple(shift[j] + time * delta[j] for j in range(3))
    distance = center[0] ** 2 + center[1] ** 2
    if distance > (radius + other_radius) ** 2:
        return None
    # A point on the center line, weighted by the two radii, belongs to both
    # disks. The midpoint of their complete axial overlap belongs to both caps.
    ratio = other_radius / (radius + other_radius)
    point: QPoint = (
        center[0] * ratio,
        center[1] * ratio,
        (max(center[2] + low, other_low) + min(center[2] + high, other_high)) / 2,
    )
    return time, point, distance


def review_rotating_pair(
    sections: Sequence[AxialEnvelope],
    shift: Point,
    delta: Point,
    *,
    mesh: SurfaceMesh | None = None,
    other_sections: Sequence[AxialEnvelope] = (),
    position_error_mm: float = 0.0,
    surface_budget: SurfaceBudget,
    solid_budget: SolidBudget,
    cache: MutableMapping[int, TriangleSolid | str],
    row_cache: SolidRowReuse | None = None,
    directional_bounds: bool = False,
    upper_time: F = F(1),
) -> tuple[RotatingSectionReview, ...]:
    if type(upper_time) is not F or not 0 <= upper_time <= 1:
        raise ValueError("Rotating time prefix must be an exact fraction in [0, 1]")
    if type(directional_bounds) is not bool:
        raise ValueError("Rotating directional bounds require an explicit boolean mode")
    if not 1 <= len(sections) <= 257 or (mesh is None) == (not other_sections):
        raise ValueError("Rotating pair requires complete sections and exactly one mesh or rotating assembly")
    if len(other_sections) > 257:
        raise ValueError("Rotating assembly exceeds complete section budget")
    for section in (*sections, *other_sections):
        dimensions(section, position_error_mm)
    start, speed = qpoint(shift), qpoint(delta)
    shifts, speeds = project(start), project(speed)
    results = []
    for index, section in enumerate(sections):
        found = None
        if mesh is None:
            for other_index, other in enumerate(other_sections):
                surface_budget.consume("pairs")
                hit = cylinder_pair(section, other, start, speed, position_error_mm, upper_time)
                if hit is not None:
                    time, point, distance = hit
                    found = RotatingSectionReview(
                        index,
                        "possible_contact",
                        time,
                        point,
                        other_section_index=other_index,
                        radial_distance_squared=distance,
                        reason="Assembly pair uses enclosing cylinders for shaped sections"
                        if isinstance(section, RotatingShape) or isinstance(other, RotatingShape)
                        else "",
                    )
                    break
            if found is None:
                found = RotatingSectionReview(index, "separated")
        else:
            projections = section_projections(section, position_error_mm) if directional_bounds else ()
            pending = [mesh.root]
            while pending and found is None:
                node = pending.pop()
                surface_budget.consume("nodes")
                if not box_candidate(section, node.bounds, start, speed, position_error_mm, upper_time):
                    continue
                if (
                    projections
                    and node.projections
                    and overlap_interval(projections, node.projections, shifts, speeds, F(0), (F(0), upper_time))
                    is None
                ):
                    continue
                if node.children:
                    pending.extend(node.children)
                    continue
                for triangle in node.ids:
                    surface_budget.consume("pairs")
                    triangle_hit = triangle_contact(
                        section,
                        mesh.triangles[triangle],
                        shift,
                        delta,
                        position_error_mm=position_error_mm,
                        cancelled=surface_budget.cancelled,
                        upper_time=upper_time,
                    )
                    if triangle_hit is not None:
                        found = RotatingSectionReview(
                            index,
                            "possible_contact",
                            triangle_hit.sample,
                            triangle_hit.point,
                            triangle,
                            radial_distance_squared=triangle_hit.radial_distance_squared,
                            barycentric=triangle_hit.barycentric,
                        )
                        break
            if found is None:
                # No surface of the complete obstacle enters this cylinder at
                # any time. A connected translating cylinder can only change
                # solid occupancy by reaching a boundary. A center witness is
                # therefore sufficient after complete closed-solid admission.
                key = id(mesh)
                if key not in cache:
                    try:
                        cache[key] = TriangleSolid.validate(mesh.triangles, budget=solid_budget)
                    except SolidBudgetExceeded:
                        raise
                    except ValueError as exc:
                        cache[key] = str(exc)[:250]
                solid = cache[key]
                if isinstance(solid, str):
                    found = RotatingSectionReview(
                        index, "unavailable", reason="Complete surface separation; obstacle solid unavailable: " + solid
                    )
                else:
                    low, high, _radius = dimensions(section, position_error_mm)
                    center: QPoint = (
                        start[0] + upper_time * speed[0] / 2,
                        start[1] + upper_time * speed[1] / 2,
                        start[2] + upper_time * speed[2] / 2 + (low + high) / 2,
                    )
                    state = solid.classify(center, budget=solid_budget, row_cache=row_cache)
                    if state == "boundary":
                        found = RotatingSectionReview(
                            index,
                            "unavailable",
                            reason="Cylinder center reaches obstacle boundary outside the surface query",
                        )
                    else:
                        found = RotatingSectionReview(
                            index,
                            "contained" if state == "inside" else "separated",
                            sample=upper_time / 2,
                            witness_point=center if state == "inside" else None,
                        )
        if found.state == "possible_contact":
            surface_budget.consume("contacts")
        results.append(found)
    if surface_budget.cancelled():
        raise InterruptedError("Rotating pair review cancelled; no partial report")
    return tuple(results)
