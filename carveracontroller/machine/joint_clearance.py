"""Continuous conservative clearance of declared bodies on articulated chains."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from carveracontroller.addons.manufacturing_simulation import AABB, MachineKinematics, Transform, Vec3


@dataclass(frozen=True)
class JointBody:
    name: str
    frame: str
    joint_count: int
    bounds: AABB


@dataclass(frozen=True)
class JointContact:
    first: str
    second: str
    segment: int
    lower_fraction: float
    upper_fraction: float
    witness_fraction: float | None
    motion_bound_mm: float


@dataclass(frozen=True)
class JointClearance:
    contacts: tuple[JointContact, ...]
    tested_pairs: int
    intervals: int
    tolerance_mm: float
    status: str
    qualification: str = "declared bounding bodies and joint interpolation only; completeness, registration, backend and physical clearance unqualified"


def bodies_from_record(
    record: Mapping[str, object], machine: MachineKinematics
) -> tuple[tuple[JointBody, ...], tuple[tuple[str, str], ...]]:
    from carveracontroller.machine.kinematic_review import vector

    rows = record.get("collision_bodies", [])
    if not isinstance(rows, list) or len(rows) > 32:
        raise ValueError("Declare at most 32 collision bodies")
    bodies = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "frame", "joint_count", "minimum_mm", "maximum_mm"}:
            raise ValueError("Every collision body needs name, frame, joint_count and minimum/maximum_mm")
        name, frame, count = row["name"], row["frame"], row["joint_count"]
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or any(ord(c) < 32 for c in name):
            raise ValueError("Body names need 1–80 characters without control characters")
        if frame not in ("world", "tool", "work") or type(count) is not int:
            raise ValueError("Body frames are world/tool/work with an integer joint count")
        maximum = len(machine.tool_chain) if frame == "tool" else len(machine.work_chain) if frame == "work" else 0
        if not 0 <= count <= maximum:
            raise ValueError("Body attachment exceeds its declared joint chain")
        bodies.append(JointBody(name, frame, count, AABB(vector(row["minimum_mm"]), vector(row["maximum_mm"]))))
    names = {b.name for b in bodies}
    if len(names) != len(bodies):
        raise ValueError("Collision body names must be unique")
    exclusions = record.get("collision_exclusions", [])
    if not isinstance(exclusions, list) or len(exclusions) > 496:
        raise ValueError("Declare at most 496 excluded body pairs")
    pairs = []
    for pair in exclusions:
        if (
            not isinstance(pair, (list, tuple))
            or len(pair) != 2
            or any(not isinstance(n, str) or n not in names for n in pair)
            or pair[0] == pair[1]
        ):
            raise ValueError("Excluded pairs need two distinct declared body names")
        ordered = sorted(pair)
        canonical = (ordered[0], ordered[1])
        if canonical in pairs:
            raise ValueError("Duplicate excluded collision pair")
        pairs.append(canonical)
    return tuple(bodies), tuple(pairs)


def body_record(body: JointBody) -> dict[str, object]:
    return {
        "name": body.name,
        "frame": body.frame,
        "joint_count": body.joint_count,
        "minimum_mm": body.bounds.minimum.tuple,
        "maximum_mm": body.bounds.maximum.tuple,
    }


def body_transform(machine: MachineKinematics, body: JointBody, state: Mapping[str, float]) -> Transform:
    if body.frame == "world":
        return Transform()
    chain = machine.tool_chain if body.frame == "tool" else machine.work_chain
    transform = machine.tool_base if body.frame == "tool" else machine.work_base
    for joint in chain[: body.joint_count]:
        transform = transform.compose(joint.transform(state[joint.name]))
    return transform


def corners(bounds: AABB) -> tuple[Vec3, ...]:
    return tuple(
        Vec3(x, y, z)
        for x in (bounds.minimum.x, bounds.maximum.x)
        for y in (bounds.minimum.y, bounds.maximum.y)
        for z in (bounds.minimum.z, bounds.maximum.z)
    )


def body_speed_bound(
    machine: MachineKinematics, body: JointBody, start: Mapping[str, float], end: Mapping[str, float]
) -> float:
    """Maximum point speed per normalized segment, not sampled speed.

    Compose from the innermost joint outwards. A rotary derivative adds
    |delta radians| * distance-to-pivot; rotation preserves existing speed.
    Linear translations add |delta mm|. Suffix norm bounds include all nested
    pivots and extrema of linearly interpolated translations. Fixed bases do
    not change speed. Full turns are intentionally never reduced modulo 360.
    """
    if body.frame == "world":
        return 0.0
    chain = machine.tool_chain if body.frame == "tool" else machine.work_chain
    radius = max(p.length for p in corners(body.bounds))
    speed = 0.0
    for joint in reversed(chain[: body.joint_count]):
        delta = abs(end[joint.name] - start[joint.name])
        if joint.kind == "rotary":
            speed += math.radians(delta) * (radius + joint.pivot.length)
            radius += 2 * joint.pivot.length
        else:
            speed += delta
            radius += max(abs(start[joint.name]), abs(end[joint.name]))
    return speed


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _separated(first: tuple[Vec3, ...], second: tuple[Vec3, ...], a: Transform, b: Transform, padding: float) -> bool:
    axes = [tuple(t.rotation[3 * r + c] for r in range(3)) for t in (a, b) for c in range(3)]
    cross = [
        (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        for u in axes[:3]
        for v in axes[3:]
    ]
    for axis in axes + cross:
        norm = math.hypot(*axis)
        if norm < 1e-12:
            continue
        pa, pb = [_dot(p.tuple, axis) for p in first], [_dot(p.tuple, axis) for p in second]
        # Roundoff only makes admission more conservative, never discards contact.
        coordinate_scale = 1 + max(abs(v) for p in first + second for v in p.tuple)
        allowance = norm * (padding + 1e-10 * coordinate_scale)
        if min(pb) - max(pa) > allowance or min(pa) - max(pb) > allowance:
            return True
    return False


def review_joint_clearance(
    machine: MachineKinematics,
    waypoints: list[dict[str, float]],
    bodies: tuple[JointBody, ...],
    exclusions: tuple[tuple[str, str], ...] = (),
    *,
    tolerance_mm: float = 0.05,
    max_intervals: int = 50000,
    cancelled: Callable[[], bool] = lambda: False,
) -> JointClearance:
    """Bound the full entered piecewise-linear joint route, including rotations.

    Every body attaches to world, a chain base, or an intermediate/full chain.
    At a midpoint, exact oriented-box separating axes plus a derivative-based
    displacement enclosure can exclude the entire interval. Remaining intervals
    subdivide chronologically. The first possible interval per pair/segment is
    retained at the requested motion bound; it is not an exact contact time.
    A midpoint overlap is separately identified as a declared-envelope witness.
    Budgets/cancellation withhold the whole report, never return false clearance.
    """
    from carveracontroller.machine.kinematic_review import number

    if not isinstance(waypoints, list) or not 2 <= len(waypoints) <= 8:
        raise ValueError("Enter two to eight ordered joint waypoints")
    tolerance = number(tolerance_mm)
    if not 1e-6 <= tolerance <= 10 or type(max_intervals) is not int or not 1 <= max_intervals <= 50000:
        raise ValueError("Clearance needs tolerance 0.000001–10 mm and at most 50000 intervals")
    # Revalidate direct API inputs through the same profile contract.
    body_data, excluded = bodies_from_record(
        {"collision_bodies": [body_record(b) for b in bodies], "collision_exclusions": list(exclusions)}, machine
    )
    if not 2 <= len(body_data) <= 32:
        raise ValueError("Declare at least two collision bodies before review")
    states = []
    for row in waypoints:
        if not isinstance(row, dict):
            raise ValueError("Each waypoint needs named joint values")
        state = {name: number(value) for name, value in row.items()}
        if machine.forward(state).limit_violations:
            raise ValueError("Route positions must respect every joint limit")
        states.append(state)
    pairs = [
        (a, b)
        for i, a in enumerate(body_data)
        for b in body_data[i + 1 :]
        if tuple(sorted((a.name, b.name))) not in excluded
    ]
    if not pairs:
        raise ValueError("All body pairs are excluded; no clearance review can be established")
    contacts = []
    intervals = 0
    for segment, (start, end) in enumerate(zip(states, states[1:])):
        speeds = {body.name: body_speed_bound(machine, body, start, end) for body in body_data}
        for first, second in pairs:
            pending = [(0.0, 1.0, 0)]
            speed = speeds[first.name] + speeds[second.name]
            while pending:
                if cancelled():
                    raise InterruptedError("Joint clearance review cancelled; previous report retained")
                if intervals >= max_intervals:
                    raise ValueError(
                        "Joint clearance exceeds 50000/shared interval budget; shorten route or loosen tolerance"
                    )
                low, high, depth = pending.pop()
                mid = (low + high) / 2
                state = {key: start[key] + mid * (end[key] - start[key]) for key in start}
                a, b = body_transform(machine, first, state), body_transform(machine, second, state)
                ca, cb = (
                    tuple(a.apply(p) for p in corners(first.bounds)),
                    tuple(b.apply(p) for p in corners(second.bounds)),
                )
                padding = speed * (high - low) / 2
                intervals += 1
                if _separated(ca, cb, a, b, padding):
                    continue
                if padding <= tolerance:
                    witness = None if _separated(ca, cb, a, b, 0) else mid
                    contacts.append(JointContact(first.name, second.name, segment, low, high, witness, padding))
                    break
                if depth >= 40 or mid in (low, high):
                    raise ValueError("Joint clearance cannot resolve the requested motion bound")
                pending.extend(((mid, high, depth + 1), (low, mid, depth + 1)))
    if cancelled():
        raise InterruptedError("Joint clearance review cancelled; previous report retained")
    return JointClearance(
        tuple(contacts),
        len(pairs) * (len(states) - 1),
        intervals,
        tolerance,
        "potential_collision" if contacts else "clear_declared_envelopes",
    )
