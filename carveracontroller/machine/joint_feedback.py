"""Sourced, block-relative feedback review; no clock alignment or servo inference."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, cast


@dataclass(frozen=True)
class FeedbackDemand:
    name: str
    kind: str
    maximum_velocity: float
    maximum_acceleration: float | None
    maximum_jerk: float | None
    maximum_following_error: float | None
    reversals: int


@dataclass(frozen=True)
class JointFeedbackReview:
    source: str
    timing_source: str
    samples: int
    maximum_gap_seconds: float
    demands: tuple[FeedbackDemand, ...]


def _number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Feedback needs finite numeric coordinates and times")
    try:
        result = float(cast(float, value))
    except (OverflowError, ValueError):
        raise ValueError("Feedback number exceeds finite range") from None
    if not math.isfinite(result):
        raise ValueError("Feedback needs finite numeric coordinates and times")
    return result


def review_joint_feedback(
    record: object,
    seconds: float,
    joint_kinds: tuple[tuple[str, str], ...],
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> JointFeedbackReview:
    """Secants at interval midpoints, recursively differenced on nonuniform time.

    Acceleration needs three positions; jerk needs four. Error requires command
    and reported positions supplied together at every timestamp. Peaks between
    samples, filtering, clock alignment and backend following-error semantics
    are unqualified. Rotary coordinates are unwrapped, never shortest-path.
    """
    if not isinstance(record, dict) or set(record) != {"source", "timing_source", "samples"}:
        raise ValueError("Feedback requires source, timing_source and samples")
    sources = []
    for key in ("source", "timing_source"):
        value = record[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 240:
            raise ValueError("Feedback source and timing source need 1–240 characters")
        sources.append(value.strip())
    duration = _number(seconds)
    kinds = dict(joint_kinds)
    if duration <= 0 or not 1 <= len(kinds) <= 9 or len(kinds) != len(joint_kinds):
        raise ValueError("Feedback requires positive duration and unique configured joints")
    if any(kind not in ("linear", "rotary") for kind in kinds.values()):
        raise ValueError("Feedback requires linear/rotary joint kinds")
    rows = record["samples"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= 2001:
        raise ValueError("Feedback requires two to 2001 timestamped samples")
    times: list[float] = []
    positions: dict[str, list[float]] = {name: [] for name in kinds}
    errors: dict[str, list[float]] = {name: [] for name in kinds}
    commands_present = isinstance(rows[0], dict) and "commanded" in rows[0]
    fields = {"seconds", "reported"} | ({"commanded"} if commands_present else set())
    for row in rows:
        if cancelled():
            raise InterruptedError("Feedback review cancelled")
        if not isinstance(row, dict) or set(row) != fields:
            raise ValueError("Feedback samples need consistent seconds/reported and optional commanded fields")
        time = _number(row["seconds"])
        if time < 0 or time > duration or (times and time <= times[-1]):
            raise ValueError("Feedback times must increase within the selected block")
        times.append(time)
        for field in ("reported", "commanded") if commands_present else ("reported",):
            coordinates = row[field]
            if not isinstance(coordinates, dict) or set(coordinates) != set(kinds):
                raise ValueError("Feedback coordinates must match every configured joint exactly")
            for name in kinds:
                value = _number(coordinates[name])
                if field == "reported":
                    positions[name].append(value)
                else:
                    error = abs(positions[name][-1] - value)
                    if not math.isfinite(error):
                        raise ValueError("Feedback error exceeds finite range")
                    errors[name].append(error)
    if times[0] != 0 or not math.isclose(times[-1], duration, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("Feedback must cover the selected block from zero to its duration")
    demands = []
    for name, kind in joint_kinds:
        values, derivative_times = positions[name], times
        peaks: list[float | None] = []
        reversals = 0
        for order in range(3):
            if cancelled():
                raise InterruptedError("Feedback review cancelled")
            rates = []
            midpoints = []
            for index in range(1, len(values)):
                dt = derivative_times[index] - derivative_times[index - 1]
                if dt <= 0:
                    raise ValueError("Feedback derivative interval cannot be represented")
                rate = (values[index] - values[index - 1]) / dt
                if not math.isfinite(rate):
                    raise ValueError("Feedback derivative exceeds finite range")
                rates.append(rate)
                midpoints.append(derivative_times[index - 1] + dt / 2)
            peaks.append(max(map(abs, rates)) if rates else None)
            if order == 0:
                signs = [1 if value > 0 else -1 for value in rates if value != 0]
                reversals = sum(before != after for before, after in zip(signs, signs[1:]))
            values, derivative_times = rates, midpoints
        demands.append(
            FeedbackDemand(
                name,
                kind,
                cast(float, peaks[0]),
                peaks[1],
                peaks[2],
                max(errors[name]) if commands_present else None,
                reversals,
            )
        )
    return JointFeedbackReview(
        sources[0], sources[1], len(times), max(b - a for a, b in zip(times, times[1:])), tuple(demands)
    )
