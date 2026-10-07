"""Declared milling kinematics and explicit ceilings, never engagement qualification."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .program_operations import ModalState, Operation, ProgramOperations


def bounded(value: object, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} requires a finite number")
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum:g} and {maximum:g}")
    return float(value)


@dataclass(frozen=True)
class CuttingParameters:
    diameter_mm: float
    flutes: int
    rpm: float
    feed_mm_min: float
    chip_mm_tooth: float
    feed_mm_rev: float
    surface_m_min: float
    violations: tuple[str, ...]
    checked_limits: tuple[str, ...]
    removal_mm3_min: float | None = None
    cutting_power_w: float | None = None
    cutting_torque_nm: float | None = None
    radial_engagement_degrees: float | None = None
    ideal_max_chip_mm: float | None = None


def review_cutting_parameters(
    diameter_mm: float,
    flutes: int,
    rpm: float,
    feed_mm_min: float,
    *,
    max_rpm: float | None = None,
    max_feed_mm_min: float | None = None,
    max_chip_mm_tooth: float | None = None,
    radial_width_mm: float | None = None,
    axial_depth_mm: float | None = None,
    specific_energy_j_mm3: float | None = None,
    max_cutting_power_w: float | None = None,
    max_cutting_torque_nm: float | None = None,
    ideal_radial_model: bool = False,
) -> CuttingParameters:
    diameter = bounded(diameter_mm, "Diameter", 0.001, 10000)
    teeth = bounded(flutes, "Flutes", 1, 1000)
    if not teeth.is_integer():
        raise ValueError("Flutes require a whole number")
    speed = bounded(rpm, "RPM", 0.001, 1e9)
    feed = bounded(feed_mm_min, "Feed", 0, 1e9)
    chip, per_rev = feed / (speed * teeth), feed / speed
    removal = power = torque = angle = maximum_chip = None
    if not isinstance(ideal_radial_model, bool):
        raise ValueError("Ideal radial model requires an explicit boolean assumption")
    if ideal_radial_model and radial_width_mm is None:
        raise ValueError("Ideal radial model requires declared radial width and axial depth")
    if (radial_width_mm is None) != (axial_depth_mm is None):
        raise ValueError("Supply both radial width and axial depth, or omit both")
    if radial_width_mm is not None:
        width = bounded(radial_width_mm, "Radial width", 0, diameter)
        depth = bounded(axial_depth_mm, "Axial depth", 0, 10000)
        removal = bounded(width * depth * feed, "Removal rate", 0, 1e15)
        if ideal_radial_model:
            fraction = width / diameter
            angle = math.degrees(math.acos(max(-1.0, min(1.0, 1 - 2 * fraction))))
            # Straight wall, circular peripheral edge, 90-degree entering angle.
            # The engagement reaches peak sin(phi) at half-diameter and beyond.
            factor = 2 * math.sqrt(fraction * (1 - fraction)) if fraction < 0.5 else 1.0
            maximum_chip = chip * factor if depth > 0 else 0.0
    if specific_energy_j_mm3 is not None:
        energy = bounded(specific_energy_j_mm3, "Specific cutting energy", 1e-9, 1e6)
        if removal is None:
            raise ValueError("Specific cutting energy requires declared radial width and axial depth")
        power = bounded(removal * energy / 60, "Cutting power", 0, 1e15)
        torque = bounded(power * 60 / (2 * math.pi * speed), "Cutting torque", 0, 1e15)
    violations, checked = [], []
    for name, value, ceiling in (
        ("RPM", speed, max_rpm),
        ("Feed mm/min", feed, max_feed_mm_min),
        ("Chip load mm/tooth", chip, max_chip_mm_tooth),
        ("Cutting power W", power, max_cutting_power_w),
        ("Cutting torque Nm", torque, max_cutting_torque_nm),
    ):
        if ceiling is not None:
            limit = bounded(ceiling, name + " ceiling", 1e-9 if name.startswith("Chip") else 0.001, 1e9)
            checked.append(f"{name} ceiling {limit:g}" + (" · demand unknown" if value is None else ""))
            if value is not None and value > limit:
                violations.append(f"{name} {value:.6g} exceeds declared ceiling {limit:g}")
    return CuttingParameters(
        diameter,
        int(teeth),
        speed,
        feed,
        chip,
        per_rev,
        math.pi * diameter * speed / 1000,
        tuple(violations),
        tuple(checked),
        removal,
        power,
        torque,
        angle,
        maximum_chip,
    )


def program_feed_rpm(state: ModalState, selected_tool: int | None = None) -> tuple[float, float]:
    """Convert one explicit milling feed state; do not interpret inverse time/CSS."""
    if state.recovery_errors:
        raise ValueError("Selected line has unresolved modal errors")
    if state.motion not in (1, 2, 3):
        raise ValueError("Select a feed-motion line, not rapid or an unknown motion")
    if state.spindle not in ("M3", "M4"):
        raise ValueError("Selected line has stopped or unknown spindle state")
    if state.tool is None or (selected_tool is not None and selected_tool != state.tool):
        raise ValueError("Selected line tool is unknown or differs from the reviewed tool")
    if state.units not in ("G20", "G21") or state.feed_mode not in ("G94", "G95"):
        raise ValueError("Explicit G20/G21 and G94/G95 required; inverse time is not chip load")
    speed = bounded(state.spindle_speed, "Programmed RPM", 0.001, 1e9)
    feed = bounded(state.feed, "Programmed feed", 0, 1e9) * (25.4 if state.units == "G20" else 1)
    return bounded(feed * speed if state.feed_mode == "G95" else feed, "Converted feed", 0, 1e9), speed


@dataclass(frozen=True)
class OperationCuttingSetting:
    tool: int
    units: str
    feed_mode: str
    feed_mm_min: float
    rpm: float
    lines: tuple[int, ...]


@dataclass(frozen=True)
class OperationCuttingReview:
    settings: tuple[OperationCuttingSetting, ...]
    excluded: tuple[tuple[int, str], ...]
    rapid_lines: int


def operation_cutting_review(program: ProgramOperations, operation: Operation) -> OperationCuttingReview:
    """Group actual resolved feed lines by declared state, without inventing engagement."""
    if operation not in program.operations:
        raise ValueError("Operation does not belong to this program")
    resolved = {
        s.line_number: s.rapid
        for s in program.motion_segments
        if operation.start_line <= s.line_number <= operation.end_line
    }
    unresolved = {n for n in program.unresolved_motion_lines if operation.start_line <= n <= operation.end_line}
    grouped: dict[tuple[int, str, str, float, float], list[int]] = {}
    excluded = []
    rapid = 0
    for number in sorted(set(resolved) | unresolved):
        state = program.checkpoints[number - 1].state
        if number in unresolved:
            excluded.append((number, "Unresolved motion geometry"))
            continue
        if resolved[number]:
            rapid += 1
            continue
        try:
            feed, rpm = program_feed_rpm(state)
        except ValueError as exc:
            excluded.append((number, str(exc)))
            continue
        assert state.tool is not None and state.units is not None and state.feed_mode is not None
        key = (state.tool, state.units, state.feed_mode, feed, rpm)
        grouped.setdefault(key, []).append(number)
    return OperationCuttingReview(
        tuple(OperationCuttingSetting(*key, tuple(lines)) for key, lines in grouped.items()),
        tuple(excluded),
        rapid,
    )
