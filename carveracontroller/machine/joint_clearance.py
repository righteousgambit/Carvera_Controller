"""Continuous conservative clearance of declared bodies on articulated chains."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction

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


def _linear_contact(
    machine: MachineKinematics,
    first: JointBody,
    second: JointBody,
    start: Mapping[str, float],
    end: Mapping[str, float],
    segment: int,
    error: float,
) -> JointContact | None:
    """Exact slab intersection over a complete untranslated-orientation chord.

    Fraction coefficients retain the declared binary float inputs exactly;
    the outward positional guard encloses nominal transform roundoff. This
    bounds the full possible box-contact interval, without pose sampling.
    """
    first_start, first_end = (body_transform(machine, first, s).translation.tuple for s in (start, end))
    second_start, second_end = (body_transform(machine, second, s).translation.tuple for s in (start, end))
    lower, upper = Fraction(0), Fraction(1)
    guard = Fraction(error)
    for axis in range(3):
        shift = Fraction(first_start[axis]) - Fraction(second_start[axis])
        delta = (
            Fraction(first_end[axis])
            - Fraction(first_start[axis])
            - Fraction(second_end[axis])
            + Fraction(second_start[axis])
        )
        lo = Fraction(second.bounds.minimum.tuple[axis]) - Fraction(first.bounds.maximum.tuple[axis]) - guard
        hi = Fraction(second.bounds.maximum.tuple[axis]) - Fraction(first.bounds.minimum.tuple[axis]) + guard
        if not delta:
            if not lo <= shift <= hi:
                return None
        else:
            a, b = (lo - shift) / delta, (hi - shift) / delta
            lower, upper = max(lower, min(a, b)), min(upper, max(a, b))
            if lower > upper:
                return None
    # Display/legacy body parameters stay floats, rounded outward. The CAD
    # refiner still reviews the entire original chord, not this interval alone.
    lo_float = max(0.0, math.nextafter(float(lower), -math.inf))
    hi_float = min(1.0, math.nextafter(float(upper), math.inf))
    mid = float((lower + upper) / 2)
    state = {key: start[key] + mid * (end[key] - start[key]) for key in start}
    a_transform, b_transform = body_transform(machine, first, state), body_transform(machine, second, state)
    a_points = tuple(a_transform.apply(p) for p in corners(first.bounds))
    b_points = tuple(b_transform.apply(p) for p in corners(second.bounds))
    witness = None if _separated(a_points, b_points, a_transform, b_transform, 0) else mid
    return JointContact(first.name, second.name, segment, lo_float, hi_float, witness, error)


def review_joint_clearance(
    machine: MachineKinematics,
    waypoints: list[dict[str, float]],
    bodies: tuple[JointBody, ...],
    exclusions: tuple[tuple[str, str], ...] = (),
    *,
    tolerance_mm: float = 0.05,
    max_intervals: int = 50000,
    body_position_error_mm: float = 0.0,
    cancelled: Callable[[], bool] = lambda: False,
    reuse_rigid_pairs: bool = False,
    max_tested_pairs: int = 250_000,
    progress: Callable[[int, int], None] = lambda _done, _total: None,
    linear_enclosures: bool = False,
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

    waypoint_limit = 20_001 if reuse_rigid_pairs is True else 8
    if not isinstance(waypoints, list) or not 2 <= len(waypoints) <= waypoint_limit:
        raise ValueError(f"Enter two to {waypoint_limit} ordered joint waypoints")
    tolerance = number(tolerance_mm)
    position_error = number(body_position_error_mm)
    if not 0 <= position_error <= 1000:
        raise ValueError("Body position enclosure must be from zero to1000 mm")
    if not 1e-6 <= tolerance <= 10 or type(max_intervals) is not int or not 1 <= max_intervals <= 50000:
        raise ValueError("Clearance needs tolerance 0.000001–10 mm and at most 50000 intervals")
    if type(reuse_rigid_pairs) is not bool or type(max_tested_pairs) is not int or not 1 <= max_tested_pairs <= 250_000:
        raise ValueError("Rigid review needs boolean sharing and at most 250000 complete pair memberships")
    if type(linear_enclosures) is not bool:
        raise ValueError("Linear enclosure mode must be boolean")
    if linear_enclosures and (
        any(j.kind != "linear" for j in machine.tool_chain + machine.work_chain)
        or any(t.rotation != (1, 0, 0, 0, 1, 0, 0, 0, 1) for t in (machine.tool_base, machine.work_base))
    ):
        raise ValueError("Exact linear enclosures require pure translations and unrotated chain bases")
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
    if reuse_rigid_pairs and len(pairs) * (len(states) - 1) > max_tested_pairs:
        raise ValueError("Joint clearance exceeds complete shared pair-membership budget; no partial report")
    contacts = []
    intervals = 0
    rigid: dict[tuple[str, str], JointContact | None] = {}
    stationary: dict[tuple[str, str, Transform, Transform], JointContact | None] = {}
    for segment, (start, end) in enumerate(zip(states, states[1:])):
        progress(segment, len(states) - 1)
        speeds = {body.name: body_speed_bound(machine, body, start, end) for body in body_data}
        for first, second in pairs:
            if cancelled():
                raise InterruptedError("Joint clearance review cancelled; previous report retained")
            same_attachment = (first.frame, first.joint_count) == (second.frame, second.joint_count)
            if reuse_rigid_pairs and same_attachment:
                key = (first.name, second.name)
                if key not in rigid:
                    if intervals >= max_intervals:
                        raise ValueError("Joint clearance exceeds shared interval budget; no partial report")
                    intervals += 1
                    # Cancelling the identical full rigid transform leaves these
                    # declared AABBs in one attachment frame. A uniform outward
                    # guard admits roundoff-near contact at every common pose.
                    rigid_first, rigid_second = corners(first.bounds), corners(second.bounds)
                    identity = Transform()
                    rigid[key] = None
                    if not _separated(rigid_first, rigid_second, identity, identity, 1e-6):
                        witness = None if _separated(rigid_first, rigid_second, identity, identity, 0) else 0.5
                        rigid[key] = JointContact(first.name, second.name, segment, 0, 1, witness, 1e-6)
                rigid_row = rigid[key]
                if rigid_row is not None:
                    contacts.append(replace(rigid_row, segment=segment))
                continue
            stationary_key = None
            if reuse_rigid_pairs and speeds[first.name] == speeds[second.name] == 0:
                # Different attachments may both stay stationary during a
                # move (e.g. a table at fixed Y while X/Z traverse). Full exact
                # nominal transforms bind this query; changing Y or a base
                # cannot borrow a contact/clear result at another pose.
                stationary_key = (
                    first.name,
                    second.name,
                    body_transform(machine, first, start),
                    body_transform(machine, second, start),
                )
                if stationary_key in stationary:
                    stationary_row = stationary[stationary_key]
                    if stationary_row is not None:
                        contacts.append(replace(stationary_row, segment=segment))
                    continue
                stationary[stationary_key] = None
            if linear_enclosures:
                if intervals >= max_intervals:
                    raise ValueError(
                        "Joint clearance exceeds complete shared linear interval budget; no partial report"
                    )
                intervals += 1
                linear_row = _linear_contact(machine, first, second, start, end, segment, 1e-6 + 2 * position_error)
                if linear_row is not None:
                    contacts.append(linear_row)
                if stationary_key is not None:
                    stationary[stationary_key] = linear_row
                continue
            pending = [(0.0, 1.0, 0)]
            # Two boxes on the same rigid attachment have constant relative
            # pose, even across full rotary turns. Common motion cancels
            # exactly; it is not a sampled approximation or a pair exclusion.
            speed = 0.0 if same_attachment else speeds[first.name] + speeds[second.name]
            # The caller supplies a uniform world-position error for each
            # rigid body about its interpolated pose. Same attachment motion
            # cancels; independent attachments need the sum of both errors.
            curve_padding = (
                0.0 if (first.frame, first.joint_count) == (second.frame, second.joint_count) else 2 * position_error
            )
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
                if _separated(ca, cb, a, b, padding + curve_padding):
                    continue
                if padding <= tolerance:
                    witness = None if curve_padding or _separated(ca, cb, a, b, 0) else mid
                    contact = JointContact(
                        first.name, second.name, segment, low, high, witness, padding + curve_padding
                    )
                    contacts.append(contact)
                    if stationary_key is not None:
                        stationary[stationary_key] = contact
                    break
                if depth >= 40 or mid in (low, high):
                    raise ValueError("Joint clearance cannot resolve the requested motion bound")
                pending.extend(((mid, high, depth + 1), (low, mid, depth + 1)))
    if cancelled():
        raise InterruptedError("Joint clearance review cancelled; previous report retained")
    progress(len(states) - 1, len(states) - 1)
    result = JointClearance(
        tuple(contacts),
        len(pairs) * (len(states) - 1),
        intervals,
        tolerance,
        "potential_collision" if contacts else "clear_declared_envelopes",
    )
    if linear_enclosures:
        result = replace(
            result,
            qualification=result.qualification
            + " Complete pure-translation box intersections use exact rational slab intervals with outward positional allowance and outward float parameter conversion; nominal midpoint witnesses are separate from certified CAD contact. Shared intervals count unique geometry queries while every pair/move membership remains included.",
        )
    return result
