"""Nominal ball-probe geometry. No transport, offsets, or inferred registration."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from carveracontroller.machine.scene_interaction import SurfaceHit, Vec3, dot, ray, subtract, vector


@dataclass(frozen=True)
class SurfaceMeasurementPlan:
    reference: SurfaceHit
    outward_normal: Vec3
    direction: Vec3
    tip_radius_mm: float
    approach_mm: Vec3
    contact_center_mm: Vec3
    search_limit_mm: Vec3
    retract_mm: Vec3

    def normal_deviation_mm(self, measured_center_mm: Sequence[float]) -> float:
        """Signed local-plane deviation, assuming a compensated ball-center receipt.

        A trigger position or unregistered coordinate is not a ball-center receipt.
        This calculation does not validate that prerequisite or correct lobing.
        """
        return dot(subtract(vector(measured_center_mm), self.contact_center_mm), self.outward_normal)


def plan_surface_measurement(
    reference: SurfaceHit,
    *,
    tip_diameter_mm: float,
    clearance_mm: float,
    overtravel_mm: float,
    direction: Sequence[float] | None = None,
    flip: bool = False,
) -> SurfaceMeasurementPlan:
    """Plan in the untranslated nominal component machine frame.

    Winding is explicitly operator-selectable, never assumed to mean outward.
    Clearance is measured along the approach axis. Adjacent surfaces, holder
    clearance, machine limits and physical registration need separate review.
    """
    if not isinstance(reference, SurfaceHit):
        raise ValueError("Select a nominal surface first")
    if reference.component == "cutter":
        raise ValueError("Select stock or workholding geometry, not the moving cutter")
    for name, value in (("Tip diameter", tip_diameter_mm), ("Clearance", clearance_mm), ("Overtravel", overtravel_mm)):
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    _, normal = ray((0, 0, 0), reference.normal)
    normal = vector([(-1 if flip else 1) * v for v in normal])
    resolved_direction = vector([-v for v in normal]) if direction is None else ray((0, 0, 0), direction)[1]
    if dot(resolved_direction, normal) >= -1e-6:
        raise ValueError("Approach must move into the selected outward surface normal")
    radius = tip_diameter_mm / 2
    point = vector(reference.component_point_mm)
    contact = vector([point[i] + normal[i] * radius for i in range(3)])
    approach = vector([contact[i] - resolved_direction[i] * clearance_mm for i in range(3)])
    limit = vector([contact[i] + resolved_direction[i] * overtravel_mm for i in range(3)])
    if not all(math.isfinite(v) for p in (contact, approach, limit) for v in p):
        raise ValueError("Probe geometry exceeds finite coordinate range")
    return SurfaceMeasurementPlan(reference, normal, resolved_direction, radius, approach, contact, limit, approach)
