"""Measured surface maps and polygon facing, without device or UI dependencies.

Heights are work coordinates, not a compensation command. Generated programs are
previews requiring travel, workholding, datum and tool qualification before use.
"""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any

Point = tuple[float, float]
Polygon = tuple[Point, ...]


def _number(value: float) -> float:
    result = float(value)
    if not math.isfinite(result) or abs(result) > 100000:
        raise ValueError("Coordinate must be finite and bounded")
    return result


def _polygon(points: Any) -> Polygon:
    result = tuple((_number(p[0]), _number(p[1])) for p in points)
    if (
        not 3 <= len(result) <= 1000
        or abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(result, result[1:] + result[:1]))) < 1e-9
    ):
        raise ValueError("Polygon must have between 3 and 1000 vertices and nonzero area")
    for i, (a, b) in enumerate(zip(result, result[1:] + result[:1])):
        for j, (c, d) in enumerate(zip(result, result[1:] + result[:1])):
            if j <= i + 1 or (i == 0 and j == len(result) - 1):
                continue
            if _crosses(a, b, c, d):
                raise ValueError("Self-intersecting polygon")
    return result


def _cross(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _crosses(a: Point, b: Point, c: Point, d: Point) -> bool:
    return _cross(a, b, c) * _cross(a, b, d) < -1e-12 and _cross(c, d, a) * _cross(c, d, b) < -1e-12


def contains(polygon: Polygon, point: Point) -> bool:
    """Boundary-inclusive even/odd polygon membership."""
    x, y = point
    inside = False
    for a, b in zip(polygon, polygon[1:] + polygon[:1]):
        if (
            abs(_cross(a, b, point)) < 1e-8
            and min(a[0], b[0]) - 1e-8 <= x <= max(a[0], b[0]) + 1e-8
            and min(a[1], b[1]) - 1e-8 <= y <= max(a[1], b[1]) + 1e-8
        ):
            return True
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


@dataclass(frozen=True)
class HeightSample:
    x_mm: float
    y_mm: float
    z_mm: float
    source: str
    observed_at: str
    uncertainty_mm: float = 0.0

    def __post_init__(self) -> None:
        for name in ("x_mm", "y_mm", "z_mm", "uncertainty_mm"):
            object.__setattr__(self, name, _number(getattr(self, name)))
        if self.uncertainty_mm < 0 or not self.source or not self.observed_at:
            raise ValueError("Measurement requires source, timestamp and nonnegative uncertainty")


@dataclass(frozen=True)
class HeightEstimate:
    """Uncertainty bounds sample repeat/instrument errors, not unknown surface curvature."""

    z_mm: float
    uncertainty_mm: float
    kind: str
    supporting_samples: tuple[HeightSample, ...]


@dataclass
class HeightMap:
    boundary: Polygon
    samples: list[HeightSample] = field(default_factory=list)
    exclusions: tuple[Polygon, ...] = ()
    max_gap_mm: float = 20.0
    wcs: str = "G54"

    def __post_init__(self) -> None:
        self.boundary = _polygon(self.boundary)
        self.exclusions = tuple(_polygon(p) for p in self.exclusions)
        if not 0 < _number(self.max_gap_mm) <= 10000 or self.wcs not in {f"G{i}" for i in range(54, 60)}:
            raise ValueError("Invalid map gap or work coordinate system")
        if len(self.samples) > 10000:
            raise ValueError("Too many height samples")

    def _allowed(self, p: Point) -> bool:
        return contains(self.boundary, p) and not any(contains(e, p) for e in self.exclusions)

    def query(self, x_mm: float, y_mm: float) -> HeightEstimate | None:
        p = (_number(x_mm), _number(y_mm))
        if not self._allowed(p):
            return None
        near = sorted(
            (
                s
                for s in self.samples
                if self._allowed((s.x_mm, s.y_mm)) and math.dist(p, (s.x_mm, s.y_mm)) <= self.max_gap_mm
            ),
            key=lambda s: math.dist(p, (s.x_mm, s.y_mm)),
        )
        exact = [s for s in near if math.dist(p, (s.x_mm, s.y_mm)) < 1e-8]
        if exact:
            mean = sum(s.z_mm for s in exact) / len(exact)
            # Repeat spread does not disappear by averaging an unqualified probe.
            uncertainty = max(abs(s.z_mm - mean) + s.uncertainty_mm for s in exact)
            return HeightEstimate(mean, uncertainty, "measured", tuple(exact))
        groups: dict[Point, list[HeightSample]] = {}
        for measurement in near:
            groups.setdefault((measurement.x_mm, measurement.y_mm), []).append(measurement)
        averaged = []
        for location, repeats in groups.items():
            mean = sum(s.z_mm for s in repeats) / len(repeats)
            averaged.append(
                HeightSample(
                    *location,
                    mean,
                    repeats[0].source,
                    repeats[0].observed_at,
                    max(abs(s.z_mm - mean) + s.uncertainty_mm for s in repeats),
                )
            )
        # Bounded nearest support: no extrapolation and no unbounded combinatorics.
        candidates: list[tuple[float, HeightEstimate]] = []
        for tri in combinations(averaged[:24], 3):
            a, b, c = tuple((s.x_mm, s.y_mm) for s in tri)
            denominator = _cross(a, b, c)
            if abs(denominator) < 1e-10:
                continue
            weights = (_cross(p, b, c) / denominator, _cross(a, p, c) / denominator, _cross(a, b, p) / denominator)
            if min(weights) < -1e-9 or max(math.dist(a, b), math.dist(b, c), math.dist(c, a)) > self.max_gap_mm:
                continue
            # Triangles may not bridge a concavity or an excluded probe region.
            triangle = (a, b, c)
            if any(
                not self._allowed(((u[0] + v[0]) / 2, (u[1] + v[1]) / 2))
                for u, v in zip(triangle, triangle[1:] + triangle[:1])
            ):
                continue
            if any(
                _crosses(u, v, q, r)
                for u, v in zip(triangle, triangle[1:] + triangle[:1])
                for poly in (self.boundary,) + self.exclusions
                for q, r in zip(poly, poly[1:] + poly[:1])
            ):
                continue
            if any(contains(triangle, q) for e in self.exclusions for q in e):
                continue
            estimate = HeightEstimate(
                sum(w * s.z_mm for w, s in zip(weights, tri)),
                sum(w * s.uncertainty_mm for w, s in zip(weights, tri)),
                "interpolated",
                tuple(s for vertex in tri for s in groups[(vertex.x_mm, vertex.y_mm)]),
            )
            candidates.append((max(math.dist(p, a), math.dist(p, b), math.dist(p, c)), estimate))
        return min(candidates, key=lambda item: item[0])[1] if candidates else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "boundary": self.boundary,
            "samples": [asdict(s) for s in self.samples],
            "exclusions": self.exclusions,
            "max_gap_mm": self.max_gap_mm,
            "wcs": self.wcs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HeightMap:
        if data.get("version") != 1:
            raise ValueError("Unsupported height-map version")
        return cls(
            boundary=data["boundary"],
            samples=[HeightSample(**s) for s in data["samples"]],
            exclusions=tuple(data.get("exclusions", ())),
            max_gap_mm=data["max_gap_mm"],
            wcs=data["wcs"],
        )

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        handle, filename = tempfile.mkstemp(prefix=destination.name + ".", suffix=".tmp", dir=destination.parent)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(self.to_dict(), stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            Path(filename).replace(destination)
        finally:
            Path(filename).unlink(missing_ok=True)

    @classmethod
    def load(cls, path: str | Path) -> HeightMap:
        source = Path(path)
        if source.stat().st_size > 5_000_000:
            raise ValueError("Height map exceeds size limit")
        return cls.from_dict(json.loads(source.read_text(encoding="utf-8")))


@dataclass(frozen=True)
class FacingParameters:
    boundary: Polygon
    top_z_mm: float
    final_z_mm: float
    tool_diameter_mm: float
    stepover_mm: float
    pass_depth_mm: float
    feed_mm_min: float
    plunge_feed_mm_min: float
    spindle_rpm: float
    clearance_z_mm: float
    overtravel_mm: float = 0.0
    material: str = "unspecified"
    tool_id: str = "unspecified"
    wcs: str = "G54"
    flute_count: int = 3
    spinup_dwell_s: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "boundary", _polygon(self.boundary))
        for n in (
            self.top_z_mm,
            self.final_z_mm,
            self.tool_diameter_mm,
            self.stepover_mm,
            self.pass_depth_mm,
            self.feed_mm_min,
            self.plunge_feed_mm_min,
            self.spindle_rpm,
            self.clearance_z_mm,
            self.overtravel_mm,
            self.spinup_dwell_s,
        ):
            _number(n)
        if self.final_z_mm >= self.top_z_mm or self.clearance_z_mm <= self.top_z_mm or self.overtravel_mm < 0:
            raise ValueError("Final height must cut below top; clearance must be above top")
        if (
            not 0 < self.stepover_mm <= self.tool_diameter_mm / 2
            or min(self.pass_depth_mm, self.feed_mm_min, self.plunge_feed_mm_min, self.spindle_rpm) <= 0
        ):
            raise ValueError("Positive cutting parameters and stepover at most half diameter required")
        if self.wcs not in {f"G{i}" for i in range(54, 60)}:
            raise ValueError("Unsupported WCS")
        if (
            not isinstance(self.flute_count, int)
            or not 1 <= self.flute_count <= 100
            or not 0 <= self.spinup_dwell_s <= 120
        ):
            raise ValueError("Invalid flute count or spindle dwell")

    @property
    def chipload_mm_per_tooth(self) -> float:
        return self.feed_mm_min / (self.spindle_rpm * self.flute_count)

    @property
    def radial_engagement_fraction(self) -> float:
        return self.stepover_mm / self.tool_diameter_mm

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FacingParameters:
        values = dict(data)
        if values.pop("version", None) != 1:
            raise ValueError("Unsupported facing version")
        return cls(**values)


@dataclass(frozen=True)
class FacingSegment:
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    pass_index: int


@dataclass(frozen=True)
class FacingPlan:
    parameters: FacingParameters
    segments: tuple[FacingSegment, ...]
    warnings: tuple[str, ...] = (
        "Preview only: qualify datum, clearance, travel, tool and workholding before execution.",
    )

    @classmethod
    def from_params(cls, p: FacingParameters) -> FacingPlan:
        ymin, ymax = min(v[1] for v in p.boundary), max(v[1] for v in p.boundary)
        rows = math.ceil((ymax - ymin) / p.stepover_mm)
        passes = math.ceil((p.top_z_mm - p.final_z_mm) / p.pass_depth_mm)
        if rows * passes * len(p.boundary) > 200000:
            raise ValueError("Facing plan exceeds segment budget")
        result: list[FacingSegment] = []
        radius = p.tool_diameter_mm / 2 + p.overtravel_mm
        for level in range(1, passes + 1):
            z = max(p.final_z_mm, p.top_z_mm - level * p.pass_depth_mm)
            for row in range(rows + 1):
                y = ymin + (ymax - ymin) * row / rows
                # At extrema use an interior limit to keep even/odd intersections.
                scan_y = min(ymax - 1e-7, max(ymin + 1e-7, y))
                crossings = sorted(
                    a[0] + (scan_y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
                    for a, b in zip(p.boundary, p.boundary[1:] + p.boundary[:1])
                    if (a[1] > scan_y) != (b[1] > scan_y)
                )
                for left, right in zip(crossings[::2], crossings[1::2]):
                    start, end = (left - radius, y, z), (right + radius, y, z)
                    if row % 2:
                        start, end = end, start
                    result.append(FacingSegment(start, end, level))
        return cls(p, tuple(result))

    def gcode(self) -> str:
        p = self.parameters
        lines = [
            "(POLYGON FACING PREVIEW - verify setup before execution)",
            "G21 G90 G17 G94",
            p.wcs,
            f"G0 Z{p.clearance_z_mm:.5f}",
            f"M3 S{p.spindle_rpm:.0f}",
            f"G4 P{p.spinup_dwell_s:.3f}",
        ]
        for segment in self.segments:
            x, y, z = segment.start
            lines.extend(
                (
                    f"G0 Z{p.clearance_z_mm:.5f}",
                    f"G0 X{x:.5f} Y{y:.5f}",
                    f"G1 Z{z:.5f} F{p.plunge_feed_mm_min:.3f}",
                    f"G1 X{segment.end[0]:.5f} Y{segment.end[1]:.5f} F{p.feed_mm_min:.3f}",
                )
            )
        lines.extend((f"G0 Z{p.clearance_z_mm:.5f}", "M5", "M2"))
        return "\n".join(lines) + "\n"
