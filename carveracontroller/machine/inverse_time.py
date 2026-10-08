"""Nominal inverse-minute block analysis and explicitly supplied joint demand.

RS274 G93 semantics: https://linuxcnc.org/docs/stable/html/gcode/g-code.html#gcode:g93-g94-g95
No acceleration, controller scheduling or physical motion is inferred here.
Program XYZ is never silently treated as machine joints or TCP geometry.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from carveracontroller.addons.manufacturing_simulation.kinematics import MachineKinematics
from carveracontroller.machine.joint_feedback import JointFeedbackReview

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
    motion = move.after.motion in (1, 2, 3, 5) and (
        bool(words.intersection("XYZABCUVW"))
        or (move.after.motion in (2, 3) and bool(words.intersection("IJKR")))
        or (move.after.motion == 5 and bool(words.intersection("IJPQ")))
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
            travel = (
                math.fsum(abs(segment.end_mm[0] - segment.start_mm[0]) for segment in move.segments),
                math.fsum(abs(segment.end_mm[1] - segment.start_mm[1]) for segment in move.segments),
                math.fsum(abs(segment.end_mm[2] - segment.start_mm[2]) for segment in move.segments),
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

    def __post_init__(self) -> None:
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
    def exceeds_limit(self) -> bool:
        return self.maximum_sampled_per_second > self.limit_per_second


def joint_velocity_demands(
    seconds: float, samples: tuple[JointSample, ...], limits: tuple[JointVelocityLimit, ...]
) -> tuple[JointDemand, ...]:
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
    previous = -1.0
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


@dataclass(frozen=True)
class JointVelocityTransition:
    name: str
    kind: str
    fraction: float
    before_per_second: float
    after_per_second: float

    @property
    def reverses(self) -> bool:
        return self.before_per_second < 0 < self.after_per_second or self.after_per_second < 0 < self.before_per_second

    @property
    def velocity_change_per_second(self) -> float:
        return self.after_per_second - self.before_per_second


def joint_velocity_transitions(
    seconds: float,
    samples: tuple[JointSample, ...],
    limits: tuple[JointVelocityLimit, ...],
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[JointVelocityTransition, ...]:
    """Signed interior velocity jumps of the declared piecewise-linear path.

    Unequal intervals use their actual fraction durations. No rotary wrapping,
    endpoint rest, finite acceleration or controller corner blending is assumed.
    Numerically equal rates (relative 1e-9, absolute 1e-12) are omitted. Every
    remaining jump requires a dynamics/blending model before physical execution.
    """
    if len(samples) > 100000 or len(limits) > 9:
        raise ValueError("Corner review exceeds 100000 samples or nine joints")
    joint_velocity_demands(seconds, samples, limits)
    transitions = []
    previous_rates = None
    for index in range(1, len(samples)):
        if cancelled():
            raise InterruptedError("Joint corner review cancelled")
        start, end = dict(samples[index - 1].positions), dict(samples[index].positions)
        interval = (samples[index].fraction - samples[index - 1].fraction) * seconds
        rates = {limit.name: (end[limit.name] - start[limit.name]) / interval for limit in limits}
        if previous_rates is not None:
            for limit in limits:
                before, after = previous_rates[limit.name], rates[limit.name]
                if math.isclose(before, after, rel_tol=1e-9, abs_tol=1e-12):
                    continue
                if not math.isfinite(after - before):
                    raise ValueError("Joint velocity change exceeds finite numerical range")
                if len(transitions) >= 10000:
                    raise ValueError("Corner review exceeds 10000 velocity changes; no partial result returned")
                transitions.append(
                    JointVelocityTransition(limit.name, limit.kind, samples[index - 1].fraction, before, after)
                )
        previous_rates = rates
    return tuple(transitions)


@dataclass(frozen=True)
class DeclaredPathPoint:
    """A sampled declared pose, with the preceding interval's signed rates."""

    elapsed: float
    world_tip_mm: tuple[float, float, float]
    work_tip_mm: tuple[float, float, float]
    positions: tuple[tuple[str, float], ...]
    incoming_rates: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class MappedJointMotion:
    seconds: float
    world_tip_length_mm: float
    work_tip_length_mm: float
    maximum_sampled_work_tip_mm_s: float
    pose_samples: int
    position_limit_violations: tuple[str, ...]
    joint_demands: tuple[JointDemand, ...]
    model_source: str
    trajectory_source: str
    tool_length_mm: float
    rotary_step_degrees: float
    linear_step_mm: float
    joint_transitions: tuple[JointVelocityTransition, ...] = ()
    feedback: JointFeedbackReview | None = None
    path_points: tuple[DeclaredPathPoint, ...] = ()


def analyze_mapped_joint_motion(
    seconds: float,
    samples: tuple[JointSample, ...],
    limits: tuple[JointVelocityLimit, ...],
    machine: MachineKinematics,
    tool_length_mm: float,
    *,
    model_source: str,
    trajectory_source: str,
    rotary_step_degrees: float = 1,
    linear_step_mm: float = 1,
    max_pose_samples: int = 10000,
    cancelled: Callable[[], bool] = lambda: False,
) -> MappedJointMotion:
    """Subdivide explicitly unwrapped, piecewise-linear joint motion.

    Tool-tip lengths are sampled chords in world and moving workpiece frames.
    Step sizes limit joint increments, not Cartesian error. No compensation,
    acceleration or physical qualification is supplied by this calculation.
    """
    if (
        isinstance(max_pose_samples, bool)
        or not isinstance(max_pose_samples, int)
        or not 2 <= max_pose_samples <= 100000
    ):
        raise ValueError("Pose sample budget must be an integer in 2..100000")
    if len(samples) > max_pose_samples:
        raise ValueError("Input trajectory exceeds the pose sample budget")
    if cancelled():
        raise InterruptedError("Mapped joint analysis cancelled")
    demands = joint_velocity_demands(seconds, samples, limits)
    joints = {joint.name: joint for joint in machine.tool_chain + machine.work_chain}
    if set(joints) != {limit.name for limit in limits} or any(
        joints[limit.name].kind != limit.kind for limit in limits
    ):
        raise ValueError("Joint limits must match the declared machine chains and kinds")
    if not model_source.strip() or not trajectory_source.strip():
        raise ValueError("Machine model and trajectory sources are required")
    if any(not math.isfinite(value) or value <= 0 for value in (rotary_step_degrees, linear_step_mm)):
        raise ValueError("Joint subdivision steps must be finite and positive")
    if cancelled():
        raise InterruptedError("Mapped joint analysis cancelled")
    transitions = joint_velocity_transitions(seconds, samples, limits, cancelled=cancelled)
    previous_pose = machine.forward(dict(samples[0].positions), tool_length_mm)
    path_points = [
        DeclaredPathPoint(
            0.0,
            previous_pose.tooltip_world.tuple,
            previous_pose.tooltip_work.tuple,
            samples[0].positions,
            (),
        )
    ]
    violations = set(previous_pose.limit_violations)
    count, world_length, work_length, speed = 1, 0.0, 0.0, 0.0
    for index in range(1, len(samples)):
        start, end = dict(samples[index - 1].positions), dict(samples[index].positions)
        ratios = [
            abs(end[name] - start[name]) / (rotary_step_degrees if joint.kind == "rotary" else linear_step_mm)
            for name, joint in joints.items()
        ]
        if any(not math.isfinite(ratio) or ratio > max_pose_samples for ratio in ratios):
            raise ValueError(
                "Mapped trajectory exceeds the pose sample budget; declare coarser steps or shorter intervals"
            )
        steps = max(1, math.ceil(max(ratios, default=0)))
        if count + steps > max_pose_samples:
            raise ValueError("Mapped trajectory exceeds the pose sample budget; no partial result returned")
        interval = (samples[index].fraction - samples[index - 1].fraction) * seconds / steps
        if interval <= 0 or not math.isfinite(interval):
            raise ValueError("Pose interval cannot be represented")
        rates = tuple((name, (end[name] - start[name]) / (interval * steps)) for name in joints)
        for step in range(1, steps + 1):
            if cancelled():
                raise InterruptedError("Mapped joint analysis cancelled")
            ratio = step / steps
            pose = machine.forward(
                {name: start[name] + (end[name] - start[name]) * ratio for name in joints}, tool_length_mm
            )
            world_delta = (pose.tooltip_world - previous_pose.tooltip_world).length
            work_delta = (pose.tooltip_work - previous_pose.tooltip_work).length
            world_length += world_delta
            work_length += work_delta
            speed = max(speed, work_delta / interval)
            if not all(math.isfinite(value) for value in (world_length, work_length, speed)):
                raise ValueError("Mapped tool-tip path exceeds finite numerical range")
            violations.update(pose.limit_violations)
            path_points.append(
                DeclaredPathPoint(
                    (samples[index - 1].fraction + (samples[index].fraction - samples[index - 1].fraction) * ratio)
                    * seconds,
                    pose.tooltip_world.tuple,
                    pose.tooltip_work.tuple,
                    tuple((name, start[name] + (end[name] - start[name]) * ratio) for name in joints),
                    rates,
                )
            )
            previous_pose = pose
            count += 1
    return MappedJointMotion(
        seconds,
        world_length,
        work_length,
        speed,
        count,
        tuple(sorted(violations)),
        demands,
        model_source,
        trajectory_source,
        tool_length_mm,
        rotary_step_degrees,
        linear_step_mm,
        transitions,
        path_points=tuple(path_points),
    )
