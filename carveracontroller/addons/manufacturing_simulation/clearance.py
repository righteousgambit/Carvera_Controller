"""Bounded continuous clearance to conservative assembly/obstacle envelopes.

Distance between a translating convex cylinder and a convex box is convex in
translation time. Golden-section minimization retains a minimizer interval;
translation speed supplies a Lipschitz error bound. Positive clearance is a
distance to the declared envelopes, not qualified clearance to real hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import hypot, isfinite, sqrt

from .geometry import AxialEnvelope, SweptTool


@dataclass(frozen=True)
class ClearancePoint:
    line: int
    tool_id: str
    component: str
    obstacle: str
    start_distance_mm: float
    end_distance_mm: float
    lower_mm: float
    upper_mm: float | None
    fraction: float | None
    section: AxialEnvelope
    method: str
    evaluations: int
    source_ratio: float = 0.0


@dataclass(frozen=True)
class ClearanceReport:
    points: tuple[ClearancePoint, ...]
    processed_segments: int
    total_segments: int
    tolerance_mm: float
    evaluations: int
    cancelled: bool
    budget_exhausted: bool
    qualification: str = "Declared rotating assembly envelopes and obstacle boxes; physical clearance unqualified"
    unknown_components: tuple[str, ...] = ()
    scope_lines: tuple[int, int] | None = None


def _box_distance(a, b):
    return sqrt(
        sum(
            max(c - d, e - f, 0) ** 2
            for c, d, e, f in zip(a.minimum.tuple, b.maximum.tuple, b.minimum.tuple, a.maximum.tuple)
        )
    )


def section_distance(sweep, section, obstacle, t):
    point = sweep.start + (sweep.end - sweep.start).scaled(t)
    dx = max(obstacle.minimum.x - point.x, point.x - obstacle.maximum.x, 0)
    dy = max(obstacle.minimum.y - point.y, point.y - obstacle.maximum.y, 0)
    radial = max(0, hypot(dx, dy) - section.radius_mm)
    axial = max(obstacle.minimum.z - point.z - section.high_mm, point.z + section.low_mm - obstacle.maximum.z, 0)
    return hypot(radial, axial)


def section_clearance(sweep, section, obstacle, tolerance_mm=0.05):
    if not isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("Clearance tolerance must be finite and positive")
    if sweep.axis.tuple != (0, 0, 1):
        return (
            _box_distance(sweep.section_bounds(section), obstacle),
            None,
            None,
            "Tilted swept-box lower bound only",
            0,
        )
    if sweep.intersects_section(section, obstacle):
        return (0.0, 0.0, None, "Continuous vertical envelope contact; contact time not localized", 0)
    speed = (sweep.end - sweep.start).length
    if speed == 0:
        value = section_distance(sweep, section, obstacle, 0)
        return (value, value, 0.0, "Stationary vertical cylinder distance", 1)
    a, b = 0.0, 1.0
    ratio = (sqrt(5) - 1) / 2
    x, y = b - ratio * (b - a), a + ratio * (b - a)
    fx, fy = section_distance(sweep, section, obstacle, x), section_distance(sweep, section, obstacle, y)
    evaluations = 2
    while speed * (b - a) > tolerance_mm:
        if evaluations >= 128:
            raise ValueError("Clearance precision exceeds bounded minimization budget")
        if fx <= fy:
            b, y, fy = y, x, fx
            x = b - ratio * (b - a)
            fx = section_distance(sweep, section, obstacle, x)
        else:
            a, x, fx = x, y, fy
            y = a + ratio * (b - a)
            fy = section_distance(sweep, section, obstacle, y)
        evaluations += 1
    fraction, upper = (x, fx) if fx <= fy else (y, fy)
    lower = max(0, upper - speed * (b - a))
    return (lower, upper, fraction, "Continuous vertical cylinder distance with translation error bound", evaluations)


def analyze_clearance(
    segments,
    tools,
    scene,
    *,
    tolerance_mm=0.05,
    cancelled=None,
    progress=None,
    max_evaluations=2_000_000,
    max_points=100_000,
):
    """One minimum interval per motion/component, across every relevant obstacle.

    Stock is excluded only for cutting cutter sections. Non-cutting bodies and
    rapid cutter sections are checked against the initial blank. Never decimate
    calculation coverage: cancellation/budget exhaustion leave it explicit.
    """
    if not isfinite(tolerance_mm) or tolerance_mm <= 0:
        raise ValueError("Clearance tolerance must be finite and positive")
    if (
        any(isinstance(value, bool) or not isinstance(value, int) for value in (max_evaluations, max_points))
        or not 128 <= max_evaluations <= 2_000_000
        or not 1 <= max_points <= 100_000
    ):
        raise ValueError("Clearance calculation needs bounded budgets")
    points, evaluations, processed, distance = [], 0, 0, 0.0
    exhausted = stopped = False
    for segment in segments:
        if cancelled and cancelled():
            stopped = True
            break
        if segment.tool_id not in tools:
            raise ValueError(f"Missing geometry for tool {segment.tool_id}")
        sweep = SweptTool(segment.start, segment.end, tools[segment.tool_id], segment.axis)
        end_distance = distance + (segment.end - segment.start).length
        components = {}
        for section in sweep.sections():
            obstacles = [(item.name, item.bounds) for item in scene.obstacles]
            if scene.stock and (section.component != "cutter" or not segment.cutting):
                obstacles.append(("initial stock", scene.stock))
            for name, obstacle in obstacles:
                if cancelled and cancelled():
                    stopped = True
                    break
                if evaluations + 128 > max_evaluations:
                    exhausted = True
                    break
                lower, upper, fraction, method, cost = section_clearance(sweep, section, obstacle, tolerance_mm)
                evaluations += cost
                source_ratio = segment.source_start_ratio + (segment.source_end_ratio - segment.source_start_ratio) * (
                    fraction if fraction is not None else 0
                )
                entry = ClearancePoint(
                    segment.line,
                    segment.tool_id,
                    section.component,
                    name,
                    distance,
                    end_distance,
                    lower,
                    upper,
                    fraction,
                    section,
                    method,
                    cost,
                    source_ratio,
                )
                components.setdefault(section.component, []).append(entry)
            if exhausted or stopped:
                break
        if exhausted or stopped:
            break  # Do not label a partly examined segment as complete.
        selected = []
        for entries in components.values():
            witness = min(entries, key=lambda p: p.upper_mm if p.upper_mm is not None else p.lower_mm)
            lower = min(p.lower_mm for p in entries)
            upper = min((p.upper_mm for p in entries if p.upper_mm is not None), default=None)
            # All sections have one fixed orientation; mixed known/unknown is not possible.
            selected.append(
                ClearancePoint(
                    witness.line,
                    witness.tool_id,
                    witness.component,
                    witness.obstacle,
                    distance,
                    end_distance,
                    lower,
                    upper,
                    witness.fraction,
                    witness.section,
                    witness.method,
                    sum(p.evaluations for p in entries),
                    witness.source_ratio,
                )
            )
        if len(points) + len(selected) > max_points:
            exhausted = True
            break
        points.extend(selected)
        processed += 1
        distance = end_distance
        if progress:
            progress(processed, len(segments), evaluations)
    unknown = []
    for identifier in sorted({segment.tool_id for segment in segments}):
        if identifier in tools:
            tool = tools[identifier]
            if not any(s.component == "holder" for s in tool.noncutting_sections) and not (
                tool.holder_diameter_mm and tool.holder_length_mm
            ):
                unknown.append(f"T{identifier} holder geometry missing")
    if not scene.geometry_complete:
        unknown.append("Complete machine/obstacle geometry unavailable")
    if not scene.registration_confirmed:
        unknown.append("Physical registration unconfirmed")
    return ClearanceReport(
        tuple(points),
        processed,
        len(segments),
        tolerance_mm,
        evaluations,
        stopped,
        exhausted,
        unknown_components=tuple(unknown),
        scope_lines=(min(s.line for s in segments), max(s.line for s in segments)) if segments else None,
    )
