"""Sample declared joint interpolation, never a controller motion plan."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
from carveracontroller.addons.manufacturing_simulation.kinematics import MachineKinematics
from carveracontroller.machine.kinematic_review import local_rank, number

MAX_PATH_SAMPLES = 2001


@dataclass(frozen=True)
class JointPathSample:
    segment: int
    fraction: float
    positions: dict[str, float]
    tip_mm: Vec3
    axis: Vec3
    rank: tuple[int, int]
    limit_margin: dict[str, float]
    tip_chord_error_mm: float


@dataclass(frozen=True)
class JointPathReview:
    samples: tuple[JointPathSample, ...]
    joint_travel: dict[str, float]
    singular_indices: tuple[int, ...]
    largest_tip_step_mm: float
    largest_axis_step_deg: float
    largest_tip_chord_error_mm: float


def review_joint_path(
    machine: MachineKinematics,
    waypoints: list[dict[str, float]],
    tool_length_mm: float,
    *,
    linear_step_mm: float = 2,
    rotary_step_deg: float = 2,
    cancelled: Callable[[], bool] = lambda: False,
) -> JointPathReview | None:
    """Review the *entered* joint route, including full turns, without unwinding.

    All endpoints and the total sampling budget validate before calculation.
    Rank uses the existing finite-difference local diagnostic. Between-sample
    behavior, collision, velocity, acceleration and controller interpolation are
    unqualified. Cancellation returns no partial path.
    """
    if not isinstance(waypoints, list) or not 2 <= len(waypoints) <= 8:
        raise ValueError("Enter two to eight ordered joint waypoints")
    length = number(tool_length_mm)
    linear_step, rotary_step = number(linear_step_mm), number(rotary_step_deg)
    if length < 0 or min(linear_step, rotary_step) <= 0:
        raise ValueError("Tool length must be nonnegative and sample steps positive")
    joints = machine.tool_chain + machine.work_chain
    if not joints:
        raise ValueError("Declare at least one joint before path review")
    states = []
    poses = []
    for waypoint in waypoints:
        if not isinstance(waypoint, dict):
            raise ValueError("Each waypoint requires named joint positions")
        state = {name: number(value) for name, value in waypoint.items()}
        pose = machine.forward(state, length)
        if pose.limit_violations:
            raise ValueError("Waypoint positions must respect declared joint limits")
        states.append(state)
        poses.append(pose)
    counts = []
    for start, end in zip(states, states[1:]):
        intervals = max(
            abs(end[j.name] - start[j.name]) / (linear_step if j.kind == "linear" else rotary_step) for j in joints
        )
        if not math.isfinite(intervals) or intervals > MAX_PATH_SAMPLES - 1:
            raise ValueError("Path exceeds 2001 samples; increase sample steps or shorten the declared route")
        counts.append(max(1, math.ceil(intervals)))
    if 1 + sum(counts) > MAX_PATH_SAMPLES:
        raise ValueError("Path exceeds 2001 samples; increase sample steps or shorten the declared route")
    samples = []
    max_tip_step = max_axis_step = max_chord_error = 0.0
    for segment, count in enumerate(counts):
        start, end = states[segment : segment + 2]
        start_tip, end_tip = poses[segment].tooltip_work, poses[segment + 1].tooltip_work
        for step in range(0 if segment == 0 else 1, count + 1):
            if cancelled():
                return None
            fraction = step / count
            state = {j.name: start[j.name] + fraction * (end[j.name] - start[j.name]) for j in joints}
            pose = machine.forward(state, length)
            chord_tip = start_tip + (end_tip - start_tip).scaled(fraction)
            chord_error = (pose.tooltip_work - chord_tip).length
            rank = local_rank(machine, state, length)
            if cancelled():
                return None
            if samples:
                previous = samples[-1]
                max_tip_step = max(max_tip_step, (pose.tooltip_work - previous.tip_mm).length)
                dot = sum(a * b for a, b in zip(pose.axis_in_work.tuple, previous.axis.tuple))
                max_axis_step = max(max_axis_step, math.degrees(math.acos(min(1, max(-1, dot)))))
            max_chord_error = max(max_chord_error, chord_error)
            samples.append(
                JointPathSample(
                    segment,
                    fraction,
                    state,
                    pose.tooltip_work,
                    pose.axis_in_work,
                    rank,
                    {j.name: min(state[j.name] - j.minimum, j.maximum - state[j.name]) for j in joints},
                    chord_error,
                )
            )
    return JointPathReview(
        tuple(samples),
        {j.name: sum(abs(end[j.name] - start[j.name]) for start, end in zip(states, states[1:])) for j in joints},
        tuple(i for i, sample in enumerate(samples) if sample.rank[0] < sample.rank[1]),
        max_tip_step,
        max_axis_step,
        max_chord_error,
    )
