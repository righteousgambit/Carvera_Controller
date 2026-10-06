"""Conservative swept geometry and explicit registration evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite, radians, sqrt, tan


@dataclass(frozen=True)
class Vec3:
    x: float
    y: float
    z: float

    def __post_init__(self):
        if not all(isfinite(v) for v in self.tuple):
            raise ValueError("Coordinates must be finite millimetres")

    @property
    def tuple(self):
        return (self.x, self.y, self.z)

    def __add__(self, other):
        return Vec3(*(a + b for a, b in zip(self.tuple, other.tuple)))

    def __sub__(self, other):
        return Vec3(*(a - b for a, b in zip(self.tuple, other.tuple)))

    def scaled(self, scale):
        return Vec3(*(a * scale for a in self.tuple))

    @property
    def length(self):
        return sqrt(sum(a * a for a in self.tuple))


@dataclass(frozen=True)
class AABB:
    minimum: Vec3
    maximum: Vec3

    def __post_init__(self):
        if any(a >= b for a, b in zip(self.minimum.tuple, self.maximum.tuple)):
            raise ValueError("Bounds need positive extent on every axis")

    def intersects(self, other):
        return all(
            a <= d and c <= b
            for a, b, c, d in zip(self.minimum.tuple, self.maximum.tuple, other.minimum.tuple, other.maximum.tuple)
        )

    def contains(self, other):
        return all(
            a <= c and d <= b
            for a, b, c, d in zip(self.minimum.tuple, self.maximum.tuple, other.minimum.tuple, other.maximum.tuple)
        )

    @property
    def volume_mm3(self):
        extents = self.maximum - self.minimum
        return extents.x * extents.y * extents.z


@dataclass(frozen=True)
class AxialEnvelope:
    """Conservative rotating body section, heights measured from the tool tip."""

    component: str
    low_mm: float
    high_mm: float
    radius_mm: float
    source: str = "declared dimensions"

    def __post_init__(self):
        if self.component not in ("cutter", "shank", "holder"):
            raise ValueError("Unknown assembly component")
        if not all(isfinite(v) for v in (self.low_mm, self.high_mm, self.radius_mm)):
            raise ValueError("Envelope dimensions must be finite")
        if self.low_mm < 0 or self.high_mm <= self.low_mm or self.radius_mm <= 0:
            raise ValueError("Envelope needs positive radius and ordered tip-relative heights")


@dataclass(frozen=True)
class ToolGeometry:
    diameter_mm: float
    flute_length_mm: float
    shank_diameter_mm: float
    overall_length_mm: float
    holder_diameter_mm: float = 0
    holder_length_mm: float = 0
    shape: str = "flat"
    corner_radius_mm: float = 0
    tip_angle_deg: float = 118
    taper_angle_deg: float = 45
    tip_diameter_mm: float = 0
    noncutting_sections: tuple[AxialEnvelope, ...] = ()
    clearance_notes: tuple[str, ...] = ()

    def __post_init__(self):
        values = (
            self.diameter_mm,
            self.flute_length_mm,
            self.shank_diameter_mm,
            self.overall_length_mm,
            self.holder_diameter_mm,
            self.holder_length_mm,
        )
        if not all(isfinite(v) for v in values) or min(values[:4]) <= 0 or min(values[4:]) < 0:
            raise ValueError("Tool dimensions must be finite and positive")
        if self.overall_length_mm < self.flute_length_mm:
            raise ValueError("Overall length must contain cutting length")
        if self.shape not in ("flat", "ball", "bull", "drill", "tapered", "chamfer", "engraving", "threadmill"):
            raise ValueError("Unsupported cutting shape")
        extra = (self.corner_radius_mm, self.tip_angle_deg, self.taper_angle_deg, self.tip_diameter_mm)
        if not all(isfinite(v) for v in extra):
            raise ValueError("Axial profile dimensions must be finite")
        if not 0 <= self.corner_radius_mm <= self.diameter_mm / 2:
            raise ValueError("Corner radius must lie within cutting radius")
        if not 0 <= self.tip_diameter_mm <= self.diameter_mm:
            raise ValueError("Tip diameter must lie within cutting diameter")
        if not 0 < self.tip_angle_deg < 180 or not 0 < self.taper_angle_deg < 90:
            raise ValueError("Tip included angle and taper per-side angle are invalid")
        if self.shape == "bull" and (self.corner_radius_mm <= 0 or self.flute_length_mm < self.corner_radius_mm):
            raise ValueError("Bull nose needs positive corner radius contained in flute length")
        if self.shape == "ball" and self.flute_length_mm < self.diameter_mm / 2:
            raise ValueError("Ball flute length must contain hemisphere")
        if len(self.noncutting_sections) > 256 or any(
            not isinstance(section, AxialEnvelope) or section.component == "cutter"
            for section in self.noncutting_sections
        ):
            raise ValueError("Non-cutting envelope needs bounded shank/holder sections")
        if any(s.component == "shank" and s.low_mm < self.flute_length_mm for s in self.noncutting_sections):
            raise ValueError("Non-cutting cutter body must start above cutting length")

    @property
    def stock_model_note(self):
        if self.shape == "threadmill":
            return "Threadmill outside-diameter envelope only; thread grooves and individual teeth unresolved"
        return "Rotational axial cutting envelope; material removal classified at voxel centers"

    @property
    def profile_breaks_mm(self):
        """Axial piece boundaries from tooltip to top of cutting envelope."""
        radius = self.diameter_mm / 2
        values = [0.0, self.flute_length_mm]
        if self.shape == "ball":
            values.append(radius)
        elif self.shape == "bull":
            values.append(self.corner_radius_mm)
        elif self.shape == "drill":
            values.append(radius / tan(radians(self.tip_angle_deg / 2)))
        elif self.shape in ("tapered", "chamfer", "engraving"):
            rounded = self.corner_radius_mm if self.shape == "tapered" else 0
            tip_radius = rounded if rounded else self.tip_diameter_mm / 2
            if rounded:
                values.append(rounded)
            values.append(rounded + (radius - tip_radius) / tan(radians(self.taper_angle_deg)))
        return tuple(sorted({v for v in values if 0 <= v <= self.flute_length_mm}))

    def axial_radius(self, height_mm):
        """Radius of the rotational cutting envelope at axial tooltip height.

        Taper angles are per side; drill tip angles are included. Thread mills
        describe the swept outside-diameter envelope, not individual teeth or
        thread groove material removal. A tapered tool with corner_radius_mm
        has a ball tip followed by its cone, capped at declared diameter.
        """
        if not isfinite(height_mm):
            raise ValueError("Axial height must be finite")
        if not 0 <= height_mm <= self.flute_length_mm:
            return 0.0
        radius = self.diameter_mm / 2
        if self.shape == "ball" and height_mm < radius:
            return sqrt(max(0, radius * radius - (height_mm - radius) ** 2))
        if self.shape == "bull" and height_mm < self.corner_radius_mm:
            corner = self.corner_radius_mm
            return radius - corner + sqrt(max(0, corner * corner - (height_mm - corner) ** 2))
        if self.shape == "drill":
            return min(radius, height_mm * tan(radians(self.tip_angle_deg / 2)))
        if self.shape in ("tapered", "chamfer", "engraving"):
            rounded = self.corner_radius_mm if self.shape == "tapered" else 0
            if rounded and height_mm < rounded:
                return sqrt(max(0, rounded * rounded - (height_mm - rounded) ** 2))
            tip_radius = rounded if rounded else self.tip_diameter_mm / 2
            return min(radius, tip_radius + (height_mm - rounded) * tan(radians(self.taper_angle_deg)))
        return radius


@dataclass(frozen=True)
class SweptTool:
    start: Vec3
    end: Vec3
    tool: ToolGeometry
    axis: Vec3 = field(default_factory=lambda: Vec3(0, 0, 1))

    def __post_init__(self):
        if abs(self.axis.length - 1) > 1e-8:
            raise ValueError("Tool axis must be a unit vector")
        object.__setattr__(self, "axis", self.axis.scaled(1 / self.axis.length))

    def sections(self):
        t = self.tool
        specs = [AxialEnvelope("cutter", 0, t.flute_length_mm, t.diameter_mm / 2)]
        specs.extend(t.noncutting_sections)
        modeled = {s.component for s in t.noncutting_sections}
        if "shank" not in modeled and t.overall_length_mm > t.flute_length_mm:
            specs.append(AxialEnvelope("shank", t.flute_length_mm, t.overall_length_mm, t.shank_diameter_mm / 2))
        if "holder" not in modeled and t.holder_diameter_mm and t.holder_length_mm:
            specs.append(
                AxialEnvelope(
                    "holder", t.overall_length_mm, t.overall_length_mm + t.holder_length_mm, t.holder_diameter_mm / 2
                )
            )
        return tuple(specs)

    def section_bounds(self, section):
        points = [p + self.axis.scaled(h) for p in (self.start, self.end) for h in (section.low_mm, section.high_mm)]
        radial = [section.radius_mm * sqrt(max(0, 1 - a * a)) for a in self.axis.tuple]
        minimum = Vec3(*(min(p.tuple[i] for p in points) - radial[i] for i in range(3)))
        maximum = Vec3(*(max(p.tuple[i] for p in points) + radial[i] for i in range(3)))
        return AABB(minimum, maximum)

    def component_bounds(self):
        """Enclose every translating cylinder position including arbitrary axis.

        Bounds are deliberately conservative. They cannot miss a swept collision
        but may report candidates at bounding-box corners that need narrow phase.
        """
        return tuple((s.component, self.section_bounds(s)) for s in self.sections())

    def intersects_section(self, section, obstacle):
        """Continuous cylinder/box test; tilted sections use support distance bounds.

        Restrict time by axial overlap, then minimize the piecewise quadratic
        distance from the translating XY center to the obstacle rectangle.
        No temporal sampling can skip a contact between the endpoints.
        """
        if not self.section_bounds(section).intersects(obstacle):
            return False
        if self.axis.tuple != (0, 0, 1):
            from .convex_clearance import cylinder_box_clearance

            lower, _upper, _fraction, _method, _cost = cylinder_box_clearance(self, section, obstacle, 1e-5)
            return lower <= 0  # Never discard unresolved contact/near-contact intervals.
        lo, hi = 0.0, 1.0
        dz = self.end.z - self.start.z
        zlo = obstacle.minimum.z - section.high_mm
        zhi = obstacle.maximum.z - section.low_mm
        if dz == 0:
            if not zlo <= self.start.z <= zhi:
                return False
        else:
            first, last = sorted(((zlo - self.start.z) / dz, (zhi - self.start.z) / dz))
            lo, hi = max(lo, first), min(hi, last)
            if lo > hi:
                return False
        breaks = {lo, hi}
        coordinates = tuple(
            zip(self.start.tuple[:2], self.end.tuple[:2], obstacle.minimum.tuple[:2], obstacle.maximum.tuple[:2])
        )
        for start, end, lower, upper in coordinates:
            if end != start:
                for edge in (lower, upper):
                    t = (edge - start) / (end - start)
                    if lo < t < hi:
                        breaks.add(t)

        def distance_squared(t):
            return sum(
                max(lower - (start + (end - start) * t), 0, (start + (end - start) * t) - upper) ** 2
                for start, end, lower, upper in coordinates
            )

        times = sorted(breaks)
        minimum = min(distance_squared(t) for t in times)
        for a, b in zip(times, times[1:]):
            middle = (a + b) / 2
            slope_squared = linear = 0.0
            for start, end, lower, upper in coordinates:
                delta = end - start
                value = start + delta * middle
                edge = lower if value < lower else upper if value > upper else None
                if edge is not None:
                    slope_squared += delta * delta
                    linear += (start - edge) * delta
            if slope_squared:
                minimum = min(minimum, distance_squared(max(a, min(b, -linear / slope_squared))))
        return minimum <= section.radius_mm**2 + 1e-12


@dataclass(frozen=True)
class CollisionObstacle:
    name: str
    bounds: AABB
    kind: str = "fixture"


@dataclass(frozen=True)
class CollisionContact:
    component: str
    obstacle: str
    sections: tuple[AxialEnvelope, ...]
    obstacle_bounds: AABB
    method: str


@dataclass(frozen=True)
class CollisionResult:
    candidates: tuple[tuple[str, str], ...]
    registration_confirmed: bool
    geometry_complete: bool
    method: str = "continuous +Z radial envelopes versus obstacle bounds; fixed tilted axes use support-plane bounds; changing orientation is unsupported"
    contacts: tuple[CollisionContact, ...] = ()

    @property
    def status(self):
        if self.candidates:
            return "potential_collision"
        if not self.registration_confirmed or not self.geometry_complete:
            return "unknown"
        return "clear_conservative_bounds"

    @property
    def qualified(self):
        # Broad-volume simulation never constitutes physical qualification.
        return False


@dataclass
class CollisionScene:
    obstacles: tuple[CollisionObstacle, ...] = ()
    stock: AABB | None = None
    allowed_cut_region: AABB | None = None
    registration_confirmed: bool = False
    geometry_complete: bool = False

    def check_sweep(self, sweep: SweptTool, cutting=True, *, residual_stock=None, cancelled=None):
        hits = []
        contacts = {}

        def record(section, name, obstacle):
            key = (section.component, name)
            hits.append(key)
            contacts.setdefault(key, (obstacle, []))[1].append(section)

        for section in sweep.sections():
            component, bounds = section.component, sweep.section_bounds(section)
            for obstacle in self.obstacles:
                if sweep.intersects_section(section, obstacle.bounds):
                    record(section, obstacle.name, obstacle.bounds)
            if self.stock and sweep.intersects_section(section, self.stock):
                if component != "cutter" or not cutting:
                    if residual_stock is None:
                        record(section, "stock", self.stock)
                elif not self.allowed_cut_region or not self.allowed_cut_region.contains(bounds):
                    record(section, "outside allowed cut region", self.stock)
        method = (
            "continuous vertical cylinder versus box"
            if sweep.axis.tuple == (0, 0, 1)
            else "continuous fixed-axis convex envelope; zero lower bound candidate"
        )
        details = tuple(
            CollisionContact(component, name, tuple(sections), obstacle, method)
            for (component, name), (obstacle, sections) in contacts.items()
        )
        if residual_stock is not None:
            details += residual_stock.collision_contacts(sweep, cutting=cutting, cancelled=cancelled)
            hits.extend((contact.component, contact.obstacle) for contact in details)
        return CollisionResult(
            tuple(dict.fromkeys(hits)), self.registration_confirmed, self.geometry_complete, contacts=details
        )
