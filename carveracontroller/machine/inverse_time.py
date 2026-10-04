"""Nominal inverse-minute block analysis and explicitly supplied joint demand.

RS274 G93 semantics: https://linuxcnc.org/docs/stable/html/gcode/g-code.html#gcode:g93-g94-g95
No acceleration, controller scheduling or physical motion is inferred here.
Program XYZ is never silently treated as machine joints or TCP geometry.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .move_inspection import MoveExplanation

_WORD = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


@dataclass(frozen=True)
class InverseTimeBlock:
    line: int
    applicable: bool
    seconds: float | None
    sampled_length_mm: float | None
    average_path_mm_min: float | None
    axis_travel_mm: tuple[float, float, float] | None
    issues: tuple[str, ...]


def analyze_inverse_time(move: MoveExplanation) -> InverseTimeBlock:
    """One F belongs to the source block, not each tessellated arc segment."""
    code = re.sub(r"\([^()]*\)|;.*", "", move.source).strip()
    tokens = [(match[1].upper(), float(match[2])) for match in _WORD.finditer(code)]
    words = {name for name, _ in tokens}
    gs = {value for name, value in tokens if name == "G"}
    motion = move.after.motion in (1, 2, 3) and (
        bool(words.intersection("XYZABCUVW")) or (move.after.motion in (2, 3) and bool(words.intersection("IJKR")))
    )
    applicable = move.after.feed_mode == "G93" and motion and not gs.intersection((4, 80))
    if not applicable:
        return InverseTimeBlock(move.line_number, False, None, None, None, None, ())
    issues = []
    seconds = None
    feeds = [value for name, value in tokens if name == "F"]
    if _WORD.sub("", code).strip() or any(not math.isfinite(value) for _, value in tokens):
        issues.append("Block syntax requires interpretation; inverse-time duration unknown")
    elif len(feeds) != 1:
        issues.append("Exactly one explicit F word is required on each inverse-time feed block")
    elif feeds[0] <= 0 or not math.isfinite(60 / feeds[0]):
        issues.append("Inverse feed must be positive with a finite representable duration")
    else:
        seconds = 60 / feeds[0]
    length, travel, speed = None, None, None
    if move.unresolved or not move.segments:
        issues.append("Program geometry unresolved; path and joint demand unknown")
    else:
        try:
            length = math.fsum(math.dist(segment.start_mm, segment.end_mm) for segment in move.segments)
            travel = tuple(
                math.fsum(abs(segment.end_mm[axis] - segment.start_mm[axis]) for segment in move.segments)
                for axis in range(3)
            )
            if not all(math.isfinite(value) for value in (length, *travel)):
                raise OverflowError
        except OverflowError:
            length, travel = None, None
            issues.append("Program path exceeds finite numerical range")
        if seconds is not None and length is not None:
            speed = length * feeds[0]
            if not math.isfinite(speed):
                speed = None
                issues.append("Average path rate exceeds finite numerical range")
    return InverseTimeBlock(move.line_number, True, seconds, length, speed, travel, tuple(issues))


@dataclass(frozen=True)
class JointVelocityLimit:
    name: str
    kind: str
    per_second: float
    source: str

    def __post_init__(self):
        if not self.name or self.kind not in ("linear", "rotary") or not self.source.strip():
            raise ValueError("Named linear/rotary joint and limit source required")
        if not math.isfinite(self.per_second) or self.per_second <= 0:
            raise ValueError("Velocity limit must be finite and positive")


@dataclass(frozen=True)
class JointSample:
    fraction: float
    positions: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class JointDemand:
    name: str
    kind: str
    maximum_sampled_per_second: float
    limit_per_second: float
    limit_source: str

    @property
    def exceeds_limit(self):
        return self.maximum_sampled_per_second > self.limit_per_second


def joint_velocity_demands(seconds: float, samples: tuple[JointSample, ...], limits: tuple[JointVelocityLimit, ...]):
    """Piecewise-linear rates for an explicit joint path, mm/s or degrees/s.

    Fractions must span the entire block. Rotary positions are unwrapped joint
    coordinates: a 350→10 transition remains -340°, never an invented +20°.
    This checks sampled velocity only, not acceleration, servo or machine safety.
    """
    if not math.isfinite(seconds) or seconds <= 0 or len(samples) < 2 or not limits:
        raise ValueError("Positive finite duration, complete joint samples and limits required")
    names = {limit.name for limit in limits}
    if len(names) != len(limits) or samples[0].fraction != 0 or samples[-1].fraction != 1:
        raise ValueError("Unique joint limits and sample fractions spanning 0..1 required")
    coordinates = []
    previous = -1
    for sample in samples:
        position = dict(sample.positions)
        if len(position) != len(sample.positions) or set(position) != names:
            raise ValueError("Every sample must contain exactly the configured joints")
        if not math.isfinite(sample.fraction) or not previous < sample.fraction <= 1:
            raise ValueError("Sample fractions must be finite and strictly increasing")
        if any(not math.isfinite(value) for value in position.values()):
            raise ValueError("Joint positions must be finite")
        previous = sample.fraction
        coordinates.append(position)
    maximum = dict.fromkeys(names, 0.0)
    for index in range(1, len(samples)):
        interval = (samples[index].fraction - samples[index - 1].fraction) * seconds
        if not math.isfinite(interval) or interval <= 0:
            raise ValueError("Joint sample interval cannot be represented")
        for name in names:
            rate = abs(coordinates[index][name] - coordinates[index - 1][name]) / interval
            if not math.isfinite(rate):
                raise ValueError("Joint velocity exceeds finite numerical range")
            maximum[name] = max(maximum[name], rate)
    return tuple(
        JointDemand(limit.name, limit.kind, maximum[limit.name], limit.per_second, limit.source) for limit in limits
    )
