"""Fixed-orientation work-point mapping; no indexing or controller transport."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
from carveracontroller.addons.manufacturing_simulation.kinematics import MachineKinematics
from carveracontroller.machine.kinematic_review import number, vector


@dataclass(frozen=True)
class IndexedPoint:
    target_mm: Vec3
    positions: dict[str, float]
    tip_error_mm: float
    limit_margin: dict[str, float]


@dataclass(frozen=True)
class IndexedSetupReview:
    fixed_rotary: dict[str, float]
    tool_axis: Vec3
    linear_basis: tuple[Vec3, ...]
    basis_determinant: float
    points: tuple[IndexedPoint, ...]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return Vec3(a.y * b.z - a.z * b.y, a.z * b.x - a.x * b.z, a.x * b.y - a.y * b.x)


def _dot(a: Vec3, b: Vec3) -> float:
    return float(a.x * b.x + a.y * b.y + a.z * b.z)


def review_indexed_setup(
    machine: MachineKinematics,
    fixed_rotary: dict[str, float],
    targets: list[Vec3],
    tool_length_mm: float,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> IndexedSetupReview | None:
    """Solve exactly three independent linear axes with all rotary axes fixed.

    At fixed rotation the rigid chains are affine in linear displacement. The
    declared work transform and tip length participate in the mapping. Every
    target must fit declared travel; a rejected point discards the whole route.
    Linear interpolation between these states follows their work-space chords.
    Getting to the indexed orientation, fixture clearance and backend conventions
    are separate requirements. The result cannot authorize a machine move.
    """
    joints = machine.tool_chain + machine.work_chain
    linear = [j for j in joints if j.kind == "linear"]
    rotary = [j for j in joints if j.kind == "rotary"]
    if len(linear) != 3 or not rotary:
        raise ValueError("Indexed review requires exactly three linear axes and at least one rotary axis")
    if not isinstance(fixed_rotary, dict) or set(fixed_rotary) != {j.name for j in rotary}:
        raise ValueError("Declare exactly one fixed angle for every rotary axis")
    fixed = {name: number(value) for name, value in fixed_rotary.items()}
    if any(not j.minimum <= fixed[j.name] <= j.maximum for j in rotary):
        raise ValueError("Fixed rotary angles exceed declared travel")
    if not isinstance(targets, list) or not 1 <= len(targets) <= 8:
        raise ValueError("Enter one to eight ordered work points")
    if any(not isinstance(target, Vec3) for target in targets):
        raise ValueError("Each work point requires an XYZ vector")
    points = [vector(target.tuple) for target in targets]
    length = number(tool_length_mm)
    if length < 0:
        raise ValueError("Tool length must be nonnegative")
    if cancelled():
        return None
    anchor = {**fixed, **{j.name: min(j.maximum, max(j.minimum, 0.0)) for j in linear}}
    origin = machine.forward(anchor, length)
    columns: list[Vec3] = []
    for joint in linear:
        if cancelled():
            return None
        # Keep the affine probe within declared travel, including very short axes.
        step = min(1.0, (joint.maximum - joint.minimum) / 2)
        if anchor[joint.name] + step > joint.maximum:
            step = -step
        shifted = dict(anchor)
        shifted[joint.name] += step
        moved = machine.forward(shifted, length)
        delta = moved.tooltip_work - origin.tooltip_work
        columns.append(Vec3(delta.x / step, delta.y / step, delta.z / step))
    a, b, c = columns
    determinant = _dot(a, _cross(b, c))
    scale = math.sqrt(_dot(a, a) * _dot(b, b) * _dot(c, c))
    if scale < 1e-12 or abs(determinant) / scale < 1e-8:
        raise ValueError("Declared linear axes are dependent or too ill-conditioned for indexed mapping")
    reviewed: list[IndexedPoint] = []
    for index, target in enumerate(points):
        if cancelled():
            return None
        delta = target - origin.tooltip_work
        displacement = (
            _dot(delta, _cross(b, c)) / determinant,
            _dot(a, _cross(delta, c)) / determinant,
            _dot(a, _cross(b, delta)) / determinant,
        )
        state = dict(anchor)
        for joint, value in zip(linear, displacement):
            state[joint.name] = number(anchor[joint.name] + value)
        pose = machine.forward(state, length)
        if pose.limit_violations:
            raise ValueError(f"Work point {index + 1} exceeds declared travel: {', '.join(pose.limit_violations)}")
        error = pose.tooltip_work - target
        residual = math.sqrt(_dot(error, error))
        if residual > 1e-6 or (pose.axis_in_work - origin.axis_in_work).length > 1e-8:
            raise ValueError("Declared geometry did not retain the fixed-orientation affine mapping")
        reviewed.append(
            IndexedPoint(
                target,
                state,
                residual,
                {j.name: min(state[j.name] - j.minimum, j.maximum - state[j.name]) for j in joints},
            )
        )
    if cancelled():
        return None
    return IndexedSetupReview(fixed, origin.axis_in_work, tuple(columns), determinant, tuple(reviewed))
