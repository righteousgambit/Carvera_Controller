"""Nominal ball-probe geometry. No transport, offsets, or inferred registration."""

import math
from dataclasses import dataclass

from carveracontroller.machine.scene_interaction import SurfaceHit, dot, ray, subtract, vector


@dataclass(frozen=True)
class SurfaceMeasurementPlan:
    reference: SurfaceHit
    outward_normal: tuple
    direction: tuple
    tip_radius_mm: float
    approach_mm: tuple
    contact_center_mm: tuple
    search_limit_mm: tuple
    retract_mm: tuple

    def normal_deviation_mm(self, measured_center_mm):
        """Signed local-plane deviation, assuming a compensated ball-center receipt.

        A trigger position or unregistered coordinate is not a ball-center receipt.
        This calculation does not validate that prerequisite or correct lobing.
        """
        return dot(subtract(vector(measured_center_mm), self.contact_center_mm), self.outward_normal)


def plan_surface_measurement(reference, *, tip_diameter_mm, clearance_mm, overtravel_mm, direction=None, flip=False):
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
    normal = tuple((-1 if flip else 1) * v for v in normal)
    direction = tuple(-v for v in normal) if direction is None else ray((0, 0, 0), direction)[1]
    if dot(direction, normal) >= -1e-6:
        raise ValueError("Approach must move into the selected outward surface normal")
    radius = tip_diameter_mm / 2
    point = vector(reference.component_point_mm)
    contact = tuple(point[i] + normal[i] * radius for i in range(3))
    approach = tuple(contact[i] - direction[i] * clearance_mm for i in range(3))
    limit = tuple(contact[i] + direction[i] * overtravel_mm for i in range(3))
    if not all(math.isfinite(v) for p in (contact, approach, limit) for v in p):
        raise ValueError("Probe geometry exceeds finite coordinate range")
    return SurfaceMeasurementPlan(reference, normal, direction, radius, approach, contact, limit, approach)
