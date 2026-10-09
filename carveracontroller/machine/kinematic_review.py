"""Bounded declared-geometry branch review, with no machine transport."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Callable, cast

from carveracontroller.addons.manufacturing_simulation.geometry import Vec3
from carveracontroller.addons.manufacturing_simulation.kinematics import (
    InverseResult,
    Joint,
    MachineKinematics,
    Transform,
    inverse_kinematics,
    unwind_rotary,
)


def number(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Kinematic values require finite numbers, not booleans or strings")
    try:
        result = float(cast(float, value))
    except (OverflowError, ValueError):
        raise ValueError("Kinematic value is outside the numeric range") from None
    if not math.isfinite(result) or abs(result) > 1e6:
        raise ValueError("Kinematic values must be finite and within one million units")
    return result


def vector(value: object) -> Vec3:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError("Vectors require exactly three components")
    return Vec3(*(number(item) for item in value))


def machine_from_record(record: object) -> MachineKinematics:
    if not isinstance(record, dict) or type(record.get("schema")) is not int or record["schema"] != 1:
        raise ValueError("Expected kinematic profile schema 1")
    if set(record) - {
        "schema",
        "name",
        "controller_tcp_supported",
        "tool_chain",
        "work_chain",
        "tool_base",
        "work_base",
        "collision_bodies",
        "collision_exclusions",
        "scene_source",
    }:
        raise ValueError("Unknown kinematic profile fields")
    if not isinstance(record.get("name", "Declared profile"), str) or len(record.get("name", "")) > 120:
        raise ValueError("Profile name must be text of at most 120 characters")
    if record.get("controller_tcp_supported", False) is not False:
        raise ValueError("This review cannot establish controller TCP support")
    chains = []
    for name in ("tool_chain", "work_chain"):
        rows = record.get(name, [])
        if not isinstance(rows, list) or len(rows) > 9:
            raise ValueError("Each kinematic chain needs at most nine joints")
        joints = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str) or not row["name"].strip():
                raise ValueError("Every joint needs a name")
            if set(row) - {"name", "kind", "axis", "minimum", "maximum", "pivot"}:
                raise ValueError("Unknown joint fields")
            if len(row["name"]) > 32 or row.get("kind") not in ("linear", "rotary"):
                raise ValueError("Invalid joint name or kind")
            joints.append(
                Joint(
                    row["name"],
                    row["kind"],
                    vector(row.get("axis")),
                    number(row.get("minimum")),
                    number(row.get("maximum")),
                    vector(row.get("pivot", [0, 0, 0])),
                )
            )
        chains.append(tuple(joints))
    if not 1 <= sum(map(len, chains)) <= 9:
        raise ValueError("Declare between one and nine joints")
    bases = []
    for name in ("tool_base", "work_base"):
        row = record.get(name, {})
        if not isinstance(row, dict):
            raise ValueError("Base transforms require rotation and translation records")
        if set(row) - {"rotation", "translation"}:
            raise ValueError("Unknown base transform fields")
        rotation = row.get("rotation", [1, 0, 0, 0, 1, 0, 0, 0, 1])
        if not isinstance(rotation, (list, tuple)) or len(rotation) != 9:
            raise ValueError("Base rotation requires nine components")
        bases.append(Transform(tuple(number(item) for item in rotation), vector(row.get("translation", [0, 0, 0]))))
    machine = MachineKinematics(chains[0], chains[1], bases[0], bases[1], False)
    from carveracontroller.machine.joint_clearance import bodies_from_record

    bodies_from_record(record, machine)
    if "scene_source" in record:
        from carveracontroller.machine.scene_joint_clearance import validate_scene_source

        validate_scene_source(record["scene_source"])
    return machine


def profile_digest(record: object) -> str:
    machine_from_record(record)
    return hashlib.sha256(json.dumps(record, sort_keys=True, allow_nan=False).encode()).hexdigest()


def example_profile(topology: str) -> dict[str, Any]:
    linear = [
        {"name": name, "kind": "linear", "axis": axis, "minimum": -200, "maximum": 200}
        for name, axis in (("X", [1, 0, 0]), ("Y", [0, 1, 0]), ("Z", [0, 0, 1]))
    ]
    b = {"name": "B", "kind": "rotary", "axis": [0, 1, 0], "minimum": -120, "maximum": 120}
    c = {"name": "C", "kind": "rotary", "axis": [0, 0, 1], "minimum": -720, "maximum": 720}
    if topology == "Head / head":
        tool, work = linear + [c, b], []
    elif topology == "Head / table":
        tool, work = linear + [b], [c]
    elif topology == "Table / table":
        tool, work = linear, [b, c]
    else:
        raise ValueError("Unknown example topology")
    return {"schema": 1, "name": "Illustrative " + topology, "tool_chain": tool, "work_chain": work}


def local_rank(machine: MachineKinematics, positions: dict[str, float], length: float) -> tuple[int, int]:
    """Finite-difference tip/axis Jacobian rank, normalized per column.

    The 1e-3 residual threshold is a local diagnostic, not a clearance or
    reachability certificate. At limits, derivatives stay inside declared travel.
    """
    pose = machine.forward(positions, length)
    current = (*pose.tooltip_work.tuple, *pose.axis_in_work.tuple)
    basis: list[list[float]] = []
    joints = machine.tool_chain + machine.work_chain
    for joint in joints:
        step = min(0.001 if joint.kind == "linear" else 0.01, (joint.maximum - joint.minimum) / 2)
        if positions[joint.name] + step > joint.maximum:
            step = -step
        moved = dict(positions)
        moved[joint.name] += step
        following = machine.forward(moved, length)
        values = (*following.tooltip_work.tuple, *following.axis_in_work.tuple)
        column = [(a - b) / step for a, b in zip(values, current)]
        # Unit-axis derivatives live in its tangent plane; remove finite-step
        # radial curvature so it cannot invent a sixth degree of freedom.
        radial = sum(a * b for a, b in zip(column[3:], pose.axis_in_work.tuple))
        column[3:] = [a - radial * b for a, b in zip(column[3:], pose.axis_in_work.tuple)]
        norm = math.sqrt(sum(value * value for value in column))
        if norm < 1e-10:
            continue
        column = [value / norm for value in column]
        for direction in basis:
            projection = sum(a * b for a, b in zip(column, direction))
            column = [a - projection * b for a, b in zip(column, direction)]
        remainder = math.sqrt(sum(value * value for value in column))
        if remainder > 1e-3:
            basis.append([value / remainder for value in column])
    return len(basis), min(5, len(joints))


@dataclass(frozen=True)
class BranchReview:
    seed: dict[str, float]
    result: InverseResult
    equivalent_positions: dict[str, float] | None
    rank: tuple[int, int]
    limit_margin: dict[str, float]


def review_branches(
    machine: MachineKinematics,
    target: Vec3,
    axis: Vec3,
    seeds: list[dict[str, float]],
    length: float,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> tuple[BranchReview, ...]:
    if not 1 <= len(seeds) <= 8 or abs(axis.length - 1) > 1e-8:
        raise ValueError("Use one to eight seeds and a unit target axis")
    target = vector(target.tuple)
    length = number(length)
    if length < 0:
        raise ValueError("Tool tip offset must be nonnegative")
    joints = machine.tool_chain + machine.work_chain
    # Validate every seed before any branch is calculated.
    states = [{name: number(value) for name, value in seed.items()} for seed in seeds]
    for state in states:
        if machine.forward(state, length).limit_violations:
            raise ValueError("Seed positions must respect declared joint limits")
    reviews = []
    for seed in states:
        if cancelled():
            return ()
        result = inverse_kinematics(machine, target, seed, length, axis, max_iterations=100, cancelled=cancelled)
        if cancelled() or result.reason == "cancelled":
            return ()
        equivalent = unwind_rotary(machine, result.positions, seed) if result.converged else None
        reviews.append(
            BranchReview(
                seed,
                result,
                equivalent,
                local_rank(machine, result.positions, length),
                {
                    joint.name: min(
                        result.positions[joint.name] - joint.minimum, joint.maximum - result.positions[joint.name]
                    )
                    for joint in joints
                },
            )
        )
    return tuple(reviews)
