"""Resolved program motion facts, independent of stock contact and transport."""

from __future__ import annotations

from dataclasses import dataclass
from math import dist

from .program_operations import Operation, ProgramOperations


@dataclass(frozen=True)
class OperationFacts:
    rapid_mm: float
    feed_path_mm: float
    resolved_moves: int
    unresolved_lines: tuple[int, ...]
    frames: tuple[str, ...]
    feeds: tuple[tuple[str, str, float, float], ...]
    spindle_range: tuple[float, float] | None


def operation_facts(program: ProgramOperations, operation: Operation) -> OperationFacts:
    """Keep feed units/modes separate; never infer material engagement or initial state."""
    if operation not in program.operations:
        raise ValueError("Operation does not belong to this program")
    segments = [s for s in program.motion_segments if operation.start_line <= s.line_number <= operation.end_line]
    lines = {s.line_number for s in segments}
    feed_lines = {s.line_number for s in segments if not s.rapid}
    feeds = {}
    speeds = []
    for line in sorted(lines):
        state = program.checkpoints[line - 1].state
        if state.spindle_speed is not None:
            speeds.append(state.spindle_speed)
        if line in feed_lines and state.feed is not None and state.feed_mode is not None and state.units is not None:
            key = (state.feed_mode, state.units)
            feeds.setdefault(key, []).append(state.feed)
    return OperationFacts(
        rapid_mm=sum(dist(s.start_mm, s.end_mm) for s in segments if s.rapid),
        feed_path_mm=sum(dist(s.start_mm, s.end_mm) for s in segments if not s.rapid),
        resolved_moves=len(lines),
        unresolved_lines=tuple(
            n for n in program.unresolved_motion_lines if operation.start_line <= n <= operation.end_line
        ),
        frames=tuple(sorted({s.wcs or "Unknown frame" for s in segments})),
        feeds=tuple((mode, units, min(values), max(values)) for (mode, units), values in sorted(feeds.items())),
        spindle_range=(min(speeds), max(speeds)) if speeds else None,
    )


def format_operation_facts(facts: OperationFacts) -> str:
    rows = [
        f"Resolved path (arcs approximated) · feed {facts.feed_path_mm:.1f} mm · rapid {facts.rapid_mm:.1f} mm",
        f"{facts.resolved_moves} resolved motion lines · {len(facts.unresolved_lines)} unresolved",
        "Work frames · " + (", ".join(facts.frames) or "Unresolved"),
    ]
    for mode, units, low, high in facts.feeds:
        unit = "1/min" if mode == "G93" else ("in" if units == "G20" else "mm") + ("/rev" if mode == "G95" else "/min")
        rows.append(f"Programmed feed · {low:g}–{high:g} {unit} ({mode})")
    if not facts.feeds:
        rows.append("Programmed feed · unknown")
    if facts.spindle_range:
        low, high = facts.spindle_range
        rows.append(f"Programmed spindle · {low:g}–{high:g} RPM")
    else:
        rows.append("Programmed spindle · unknown")
    rows.append("Program geometry only · feed motion does not establish stock contact; unresolved moves are excluded.")
    return "\n".join(rows)
