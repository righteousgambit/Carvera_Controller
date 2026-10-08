"""Declared rigid-body forward kinematics; never invents controller TCP support."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from math import cos, isfinite, radians, sin
from typing import Callable

from .geometry import Vec3


@dataclass(frozen=True)
class Transform:
    """Row-major 3x3 rotation plus millimetre translation."""

    rotation: tuple[float, ...] = (1, 0, 0, 0, 1, 0, 0, 0, 1)
    translation: Vec3 = field(default_factory=lambda: Vec3(0, 0, 0))

    def __post_init__(self) -> None:
        r = self.rotation
        if len(r) != 9 or not all(isfinite(v) for v in r):
            raise ValueError("Transform needs finite 3x3 rotation")
        for i in range(3):
            for j in range(3):
                dot = sum(r[3 * i + k] * r[3 * j + k] for k in range(3))
                if abs(dot - (1 if i == j else 0)) > 1e-8:
                    raise ValueError("Rotation must be orthonormal")
        determinant = r[0] * (r[4] * r[8] - r[5] * r[7]) - r[1] * (r[3] * r[8] - r[5] * r[6])
        determinant += r[2] * (r[3] * r[7] - r[4] * r[6])
        if abs(determinant - 1) > 1e-8:
            raise ValueError("Rigid rotation must be right handed")

    def direction(self, point: Vec3) -> Vec3:
        return Vec3(*(sum(self.rotation[3 * i + j] * point.tuple[j] for j in range(3)) for i in range(3)))

    def apply(self, point: Vec3) -> Vec3:
        return self.direction(point) + self.translation

    def compose(self, child: Transform) -> Transform:
        r = tuple(
            sum(self.rotation[3 * i + k] * child.rotation[3 * k + j] for k in range(3))
            for i in range(3)
            for j in range(3)
        )
        return Transform(r, self.apply(child.translation))

    def inverse(self) -> Transform:
        r = tuple(self.rotation[3 * j + i] for i in range(3) for j in range(3))
        rotation = Transform(r)
        return Transform(r, rotation.direction(self.translation).scaled(-1))

    @classmethod
    def rotation_about(cls, axis: Vec3, angle_degrees: float, pivot: Vec3 | None = None) -> Transform:
        if abs(axis.length - 1) > 1e-8 or not isfinite(angle_degrees):
            raise ValueError("Rotation requires unit axis and finite angle")
        pivot = pivot or Vec3(0, 0, 0)
        x, y, z = axis.tuple
        c, s = cos(radians(angle_degrees)), sin(radians(angle_degrees))
        d = 1 - c
        r = (
            c + x * x * d,
            x * y * d - z * s,
            x * z * d + y * s,
            y * x * d + z * s,
            c + y * y * d,
            y * z * d - x * s,
            z * x * d - y * s,
            z * y * d + x * s,
            c + z * z * d,
        )
        result = cls(r)
        return cls(r, pivot - result.direction(pivot))


@dataclass(frozen=True)
class Joint:
    name: str
    kind: str
    axis: Vec3
    minimum: float
    maximum: float
    pivot: Vec3 = field(default_factory=lambda: Vec3(0, 0, 0))

    def __post_init__(self) -> None:
        if self.kind not in ("linear", "rotary") or abs(self.axis.length - 1) > 1e-8:
            raise ValueError("Joint needs linear/rotary kind and unit axis")
        if not self.name or not all(isfinite(v) for v in (self.minimum, self.maximum)):
            raise ValueError("Joint name and finite limits required")
        if self.minimum >= self.maximum:
            raise ValueError("Joint limits need positive range")

    def transform(self, value: float) -> Transform:
        if not isfinite(value):
            raise ValueError("Joint positions must be finite")
        if self.kind == "linear":
            return Transform(translation=self.axis.scaled(value))
        return Transform.rotation_about(self.axis, value, self.pivot)


@dataclass(frozen=True)
class MachinePose:
    tool_world: Transform
    work_world: Transform
    tool_in_work: Transform
    tooltip_world: Vec3
    tooltip_work: Vec3
    axis_in_work: Vec3
    limit_violations: tuple[str, ...]
    controller_tcp_supported: bool

    def transform_tool_mesh(self, vertices: Iterable[Vec3]) -> tuple[Vec3, ...]:
        """Tool/holder vertices declared in spindle-local millimetres."""
        return tuple(self.tool_world.apply(v) for v in vertices)


@dataclass(frozen=True)
class MachineKinematics:
    """Separate ordered spindle and workpiece chains cover head/table variants.

    Joint axes/pivots are in their parent's coordinate frame. Linear units are
    mm; rotary units degrees. TCP support is declared controller capability,
    not supplied by these forward-geometry calculations.
    """

    tool_chain: tuple[Joint, ...] = ()
    work_chain: tuple[Joint, ...] = ()
    tool_base: Transform = field(default_factory=Transform)
    work_base: Transform = field(default_factory=Transform)
    controller_tcp_supported: bool = False

    def __post_init__(self) -> None:
        names = [j.name for j in self.tool_chain + self.work_chain]
        if len(names) != len(set(names)):
            raise ValueError("Joint names must be unique across machine chains")

    def forward(self, positions: Mapping[str, float], tool_length_mm: float = 0) -> MachinePose:
        joints = self.tool_chain + self.work_chain
        missing = {j.name for j in joints} - set(positions)
        unknown = set(positions) - {j.name for j in joints}
        if missing or unknown:
            raise ValueError(f"Joint state mismatch: missing={sorted(missing)}, unknown={sorted(unknown)}")
        if not isfinite(tool_length_mm) or tool_length_mm < 0:
            raise ValueError("Tool length must be finite nonnegative millimetres")
        violations = tuple(j.name for j in joints if not j.minimum <= positions[j.name] <= j.maximum)
        tool, work = self.tool_base, self.work_base
        for joint in self.tool_chain:
            tool = tool.compose(joint.transform(positions[joint.name]))
        for joint in self.work_chain:
            work = work.compose(joint.transform(positions[joint.name]))
        relative = work.inverse().compose(tool)
        tip = Vec3(0, 0, -tool_length_mm)
        return MachinePose(
            tool,
            work,
            relative,
            tool.apply(tip),
            relative.apply(tip),
            relative.direction(Vec3(0, 0, 1)),
            violations,
            self.controller_tcp_supported,
        )


@dataclass(frozen=True)
class InverseResult:
    positions: dict[str, float]
    converged: bool
    tip_error_mm: float
    axis_error: float
    iterations: int
    reason: str


def _solve(matrix: Sequence[Sequence[float]], right: Sequence[float]) -> list[float]:
    """Small dense pivoted solve for damped normal equations."""
    size = len(right)
    rows = [list(row) + [value] for row, value in zip(matrix, right)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda i: abs(rows[i][column]))
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        if abs(divisor) < 1e-15:
            raise ValueError("Singular kinematic solve")
        rows[column] = [v / divisor for v in rows[column]]
        for index in range(size):
            if index != column:
                factor = rows[index][column]
                rows[index] = [a - factor * b for a, b in zip(rows[index], rows[column])]
    return [row[-1] for row in rows]


def inverse_kinematics(
    machine: MachineKinematics,
    target_tip: Vec3,
    seed: Mapping[str, float],
    tool_length_mm: float = 0,
    target_axis: Vec3 | None = None,
    tolerance_mm: float = 0.01,
    axis_tolerance: float = 0.001,
    max_iterations: int = 80,
    cancelled: Callable[[], bool] = lambda: False,
) -> InverseResult:
    """Bounded numerical tool-tip/axis solver for declared forward geometry.

    This supplies preview/postprocessor geometry, never controller compensation.
    Local convergence is explicit: no global reachability or collision claim.
    Seed determines the rotary branch. Limits are enforced at every iteration.
    """
    if (
        type(max_iterations) is not int
        or not 1 <= max_iterations <= 500
        or not isfinite(tolerance_mm)
        or not isfinite(axis_tolerance)
        or tolerance_mm <= 0
        or axis_tolerance <= 0
    ):
        raise ValueError("Solver tolerances and bounded iterations must be positive")
    if target_axis and abs(target_axis.length - 1) > 1e-8:
        raise ValueError("Target axis must be unit length")
    joints = machine.tool_chain + machine.work_chain
    state = dict(seed)
    machine.forward(state, tool_length_mm)  # Validate exact state before iteration.
    if any(not j.minimum <= state[j.name] <= j.maximum for j in joints):
        raise ValueError("Inverse seed must respect joint limits")
    orientation_weight = 50.0

    def values(pose: MachinePose) -> list[float]:
        result = list(pose.tooltip_work.tuple)
        if target_axis:
            result.extend(v * orientation_weight for v in pose.axis_in_work.tuple)
        return result

    desired = list(target_tip.tuple)
    if target_axis:
        desired.extend(v * orientation_weight for v in target_axis.tuple)
    for iteration in range(max_iterations + 1):
        pose = machine.forward(state, tool_length_mm)
        current = values(pose)
        error = [a - b for a, b in zip(desired, current)]
        tip_error = (target_tip - pose.tooltip_work).length
        axis_error = (target_axis - pose.axis_in_work).length if target_axis else 0.0
        if cancelled():
            return InverseResult(state, False, tip_error, axis_error, iteration, "cancelled")
        if tip_error <= tolerance_mm and axis_error <= axis_tolerance:
            return InverseResult(state, True, tip_error, axis_error, iteration, "converged")
        if iteration == max_iterations or not joints:
            return InverseResult(
                state, False, tip_error, axis_error, iteration, "iteration limit or unreachable local branch"
            )
        columns = []
        for joint in joints:
            perturbation = min(0.001 if joint.kind == "linear" else 0.01, (joint.maximum - joint.minimum) / 2)
            if state[joint.name] + perturbation > joint.maximum:
                perturbation = -perturbation
            moved = dict(state)
            moved[joint.name] += perturbation
            next_values = values(machine.forward(moved, tool_length_mm))
            columns.append([(a - b) / perturbation for a, b in zip(next_values, current)])
        count = len(joints)
        normal = [
            [sum(a * b for a, b in zip(columns[i], columns[j])) + (0.01 if i == j else 0) for j in range(count)]
            for i in range(count)
        ]
        right = [sum(a * b for a, b in zip(column, error)) for column in columns]
        increments = _solve(normal, right)
        for joint, change in zip(joints, increments):
            step_limit = 10.0 if joint.kind == "linear" else 15.0
            change = min(step_limit, max(-step_limit, change))
            state[joint.name] = min(joint.maximum, max(joint.minimum, state[joint.name] + change))
    raise AssertionError("Bounded loop should always return")


def unwind_rotary(
    machine: MachineKinematics, desired: Mapping[str, float], previous: Mapping[str, float]
) -> dict[str, float]:
    """Choose nearest physically equivalent declared rotary angle inside limits.

    Returns a preview state. Does not insert a clearance move or approve a cable
    unwind; collision/clearance checks must evaluate the entire resulting path.
    """
    from math import ceil, floor

    machine.forward(desired)
    machine.forward(previous)
    result = dict(desired)
    for joint in machine.tool_chain + machine.work_chain:
        value = desired[joint.name]
        if joint.kind == "rotary":
            lo, hi = ceil((joint.minimum - value) / 360), floor((joint.maximum - value) / 360)
            if lo > hi:
                raise ValueError(f"No equivalent angle within limits for {joint.name}")
            k = round((previous[joint.name] - value) / 360)
            k = min(hi, max(lo, k))
            result[joint.name] = value + 360 * k
        elif not joint.minimum <= value <= joint.maximum:
            raise ValueError(f"Linear position outside limits for {joint.name}")
    return result
