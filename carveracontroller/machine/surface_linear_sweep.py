"""Complete C1 world/table translation hulls for separation-only certificates."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from fractions import Fraction as F
from math import inf, nextafter

from carveracontroller.addons.manufacturing_simulation import MachineKinematics, SimulationSegment, Vec3
from carveracontroller.machine.joint_clearance import JointBody
from carveracontroller.machine.surface_motion import Point, SurfaceBudget, qpoint

Translation = Callable[[MachineKinematics, JointBody, Mapping[str, float], Mapping[str, float]], tuple[Vec3, Vec3]]


def complete_table_sweep(
    machine: MachineKinematics,
    first: JointBody,
    second: JointBody,
    segments: Sequence[SimulationSegment],
    translate: Translation,
    budget: SurfaceBudget,
) -> tuple[Point, Point] | None:
    """Enclose every exact relative chord; no endpoint is sampled or omitted.

    Only the validated C1 world/table attachment pair is eligible. All relative
    X/Z coordinates must be identical and every relative delta purely Y. Float
    conversion rounds the complete exact Y hull outward, including its end.
    Each source move charges shared nodes and checks cancellation. This hull is
    useful only after complete surface/closed-solid separation is established.
    """
    if {(first.frame, first.joint_count), (second.frame, second.joint_count)} != {("world", 0), ("work", 1)}:
        return None
    if len(machine.work_chain) != 1 or machine.work_chain[0].kind != "linear":
        return None
    if not 1 <= len(segments) <= 20_000:
        raise ValueError("Complete table sweep supports one to20000 retained moves")
    anchor: Point | None = None
    low, high = F(0), F(0)
    for segment in segments:
        budget.consume("nodes")
        start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
        a, da = translate(machine, first, start, end)
        b, db = translate(machine, second, start, end)
        shift, delta = (a - b).tuple, (da - db).tuple
        if delta[0] or delta[2] or (anchor is not None and (shift[0], shift[2]) != (anchor[0], anchor[2])):
            return None
        qs, qd = qpoint(shift), qpoint(delta)
        values = qs[1], qs[1] + qd[1]
        if anchor is None:
            anchor, low, high = shift, min(values), max(values)
        else:
            low, high = min(low, *values), max(high, *values)
    assert anchor is not None
    lower = float(low)
    if F(lower) > low:
        lower = nextafter(lower, -inf)
    distance = float(high - F(lower))
    if F(lower) + F(distance) < high:
        distance = nextafter(distance, inf)
    shift, delta = (anchor[0], lower, anchor[2]), (0.0, distance, 0.0)
    qpoint(shift), qpoint(delta)
    assert F(lower) <= low and F(lower) + F(distance) >= high
    return shift, delta
