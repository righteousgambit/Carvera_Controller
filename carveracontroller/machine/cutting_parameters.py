"""Declared milling kinematics and explicit ceilings, never engagement qualification."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .program_operations import ModalState


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


def review_cutting_parameters(
    diameter_mm: float,
    flutes: int,
    rpm: float,
    feed_mm_min: float,
    *,
    max_rpm: float | None = None,
    max_feed_mm_min: float | None = None,
    max_chip_mm_tooth: float | None = None,
) -> CuttingParameters:
    diameter = bounded(diameter_mm, "Diameter", 0.001, 10000)
    teeth = bounded(flutes, "Flutes", 1, 1000)
    if not teeth.is_integer():
        raise ValueError("Flutes require a whole number")
    speed = bounded(rpm, "RPM", 0.001, 1e9)
    feed = bounded(feed_mm_min, "Feed", 0, 1e9)
    chip, per_rev = feed / (speed * teeth), feed / speed
    violations, checked = [], []
    for name, value, ceiling in (
        ("RPM", speed, max_rpm),
        ("Feed mm/min", feed, max_feed_mm_min),
        ("Chip load mm/tooth", chip, max_chip_mm_tooth),
    ):
        if ceiling is not None:
            limit = bounded(ceiling, name + " ceiling", 1e-9 if name.startswith("Chip") else 0.001, 1e9)
            checked.append(f"{name} ceiling {limit:g}")
            if value > limit:
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
