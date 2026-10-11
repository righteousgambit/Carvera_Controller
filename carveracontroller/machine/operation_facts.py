"""Resolved program motion facts, independent of stock contact and transport."""

from __future__ import annotations

from dataclasses import dataclass
from math import acos, degrees, dist, isclose, isfinite

from .inverse_time import analyze_inverse_time
from .move_inspection import MoveInspector
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
    nominal_feed_seconds: float
    timed_feed_lines: int
    untimed_feed_lines: tuple[int, ...]
    shortest_feed_block: tuple[int, float] | None
    largest_direction_change: tuple[int, int, float] | None
    analysis_dialect: str
    spline_conversions: tuple[tuple[int, int, float, float], ...]


def operation_facts(program: ProgramOperations, operation: Operation) -> OperationFacts:
    """Keep feed units/modes separate; never infer material engagement or initial state."""
    if operation not in program.operations:
        raise ValueError("Operation does not belong to this program")
    segments = [s for s in program.motion_segments if operation.start_line <= s.line_number <= operation.end_line]
    lines = {s.line_number for s in segments}
    feed_lines = {s.line_number for s in segments if not s.rapid}
    feeds = {}
    speeds = []
    lengths: dict[int, float] = {}
    durations: list[tuple[int, float]] = []
    untimed: list[int] = []
    corners: list[tuple[int, int, float]] = []
    inspector = None
    for segment in segments:
        if not segment.rapid:
            lengths[segment.line_number] = lengths.get(segment.line_number, 0) + dist(segment.start_mm, segment.end_mm)
    for line in sorted(lines):
        state = program.checkpoints[line - 1].state
        if state.spindle_speed is not None:
            speeds.append(state.spindle_speed)
        if line in feed_lines and state.feed is not None and state.feed_mode is not None and state.units is not None:
            key = (state.feed_mode, state.units)
            feeds.setdefault(key, []).append(state.feed)
    for line, length in lengths.items():
        state = program.checkpoints[line - 1].state
        feed = state.feed
        seconds = None
        if feed is not None and isfinite(feed) and feed > 0:
            if state.feed_mode == "G93":
                if inspector is None:
                    inspector = MoveInspector(program)
                seconds = analyze_inverse_time(inspector.explain(line)).seconds
            elif state.feed_mode == "G94" and state.units in ("G20", "G21"):
                seconds = 60 * length / (feed * (25.4 if state.units == "G20" else 1))
        if seconds is None or not isfinite(seconds):
            untimed.append(line)
        else:
            durations.append((line, seconds))
    for before, after in zip(segments, segments[1:]):
        # Arc tessellation is not a sequence of controller blocks. Only adjacent
        # source blocks in the same declared frame/tool can share a boundary.
        if (
            before.rapid
            or after.rapid
            or after.line_number != before.line_number + 1
            or before.wcs != after.wcs
            or before.wcs is None
            or before.tool_id != after.tool_id
            or not all(isclose(a, b, abs_tol=1e-9) for a, b in zip(before.end_mm, after.start_mm))
        ):
            continue
        incoming = tuple(b - a for a, b in zip(before.start_mm, before.end_mm))
        outgoing = tuple(b - a for a, b in zip(after.start_mm, after.end_mm))
        first, second = dist(before.start_mm, before.end_mm), dist(after.start_mm, after.end_mm)
        if min(first, second) <= 1e-12:
            continue
        cosine = sum(a * b for a, b in zip(incoming, outgoing)) / (first * second)
        corners.append((before.line_number, after.line_number, degrees(acos(max(-1, min(1, cosine))))))
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
        nominal_feed_seconds=sum(seconds for _, seconds in durations),
        timed_feed_lines=len(durations),
        untimed_feed_lines=tuple(untimed),
        shortest_feed_block=min(durations, key=lambda row: row[1]) if durations else None,
        largest_direction_change=max(corners, key=lambda row: row[2]) if corners else None,
        analysis_dialect=program.dialect,
        spline_conversions=tuple(
            (block.line_number, block.segments, block.maximum_error_bound_mm, block.tolerance_mm)
            for block in program.spline_blocks
            if operation.start_line <= block.line_number <= operation.end_line
        ),
    )


def format_operation_facts(facts: OperationFacts) -> str:
    rows = [
        f"Resolved path (arcs approximated) · feed {facts.feed_path_mm:.1f} mm · rapid {facts.rapid_mm:.1f} mm",
        f"{facts.resolved_moves} resolved motion lines · {len(facts.unresolved_lines)} unresolved",
        "Work frames · " + (", ".join(facts.frames) or "Unresolved"),
    ]
    if facts.analysis_dialect != "carvera":
        rows.append(f"Declared analysis dialect · {facts.analysis_dialect} · backend execution unqualified")
    for line, segments, bound, tolerance in facts.spline_conversions:
        rows.append(
            f"Cubic spline line {line} · {segments} segments · parameter-matched error bound {bound:.6g} mm"
            f" · requested tolerance {tolerance:.6g} mm · extent uses original control hull"
        )
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
    rows.append(
        f"Nominal programmed feed time · {facts.nominal_feed_seconds:.6g} s across {facts.timed_feed_lines} resolved blocks"
        f" · {len(facts.untimed_feed_lines)} resolved feed blocks untimed"
    )
    if facts.shortest_feed_block:
        line, seconds = facts.shortest_feed_block
        rows.append(f"Shortest nominal feed block · line {line} · {seconds * 1000:.6g} ms")
    if facts.largest_direction_change:
        before, after, angle = facts.largest_direction_change
        rows.append(f"Largest sampled adjacent-block direction change · lines {before}→{after} · {angle:.6g} degrees")
    else:
        rows.append("Adjacent-block direction change · no eligible continuous same-frame feed boundary")
    rows.append(
        "Timing excludes rapid, unresolved and unsupported feed modes; G93 is timed once per source block. "
        "Sampled arc directions approximate tangents. Acceleration, jerk, blending, overrides and backend timing are unqualified."
    )
    rows.append("Program geometry only · feed motion does not establish stock contact; unresolved moves are excluded.")
    return "\n".join(rows)
