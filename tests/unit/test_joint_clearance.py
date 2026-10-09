"""Between-pose articulated clearance, independently checked against dense poses."""

import math
from dataclasses import replace

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, Joint, MachineKinematics, Transform, Vec3
from carveracontroller.machine.joint_clearance import (
    JointBody,
    bodies_from_record,
    body_record,
    body_speed_bound,
    body_transform,
    corners,
    review_joint_clearance,
)
from carveracontroller.machine.kinematic_review import machine_from_record


def box(lo, hi):
    return AABB(Vec3(*lo), Vec3(*hi))


def rotary_case():
    machine = MachineKinematics(tool_chain=(Joint("C", "rotary", Vec3(0, 0, 1), -720, 720),))
    moving = JointBody("spindle arm", "tool", 1, box((9, -0.1, -0.1), (10, 0.1, 0.1)))
    obstacle = JointBody("fixture", "world", 0, box((-0.2, 9.4, -0.2), (0.2, 9.6, 0.2)))
    return machine, (moving, obstacle)


def test_full_turn_collision_between_identical_endpoint_poses():
    machine, bodies = rotary_case()
    assert body_transform(machine, bodies[0], {"C": 0}).apply(Vec3(10, 0, 0)).tuple == pytest.approx(
        body_transform(machine, bodies[0], {"C": 360}).apply(Vec3(10, 0, 0)).tuple
    )
    result = review_joint_clearance(machine, [{"C": 0}, {"C": 360}], bodies, tolerance_mm=0.001)
    (contact,) = result.contacts
    assert contact.first == "spindle arm" and contact.second == "fixture"
    assert 0.2 < contact.lower_fraction < contact.upper_fraction < 0.3
    assert contact.motion_bound_mm <= 0.001
    assert result.status == "potential_collision"
    # Analytic entry of the arm's rotated bounding box onto the fixture is near 90 degrees.
    assert contact.lower_fraction * 360 < 90
    assert "physical clearance unqualified" in result.qualification


def test_zero_motion_and_near_contact_never_become_false_clearance():
    machine, bodies = rotary_case()
    collision = review_joint_clearance(machine, [{"C": 90}, {"C": 90}], bodies)
    assert collision.contacts[0].witness_fraction == 0.5
    assert collision.intervals == 1
    touching = replace(bodies[1], bounds=box((10, -0.1, -0.1), (10.2, 0.1, 0.1)))
    assert review_joint_clearance(machine, [{"C": 0}, {"C": 0}], (bodies[0], touching)).contacts
    assert not review_joint_clearance(machine, [{"C": 0}, {"C": 0}], bodies).contacts


def test_intermediate_link_and_workpiece_chain_attachments_and_exclusions():
    machine = MachineKinematics(
        tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -20, 20), Joint("C", "rotary", Vec3(0, 0, 1), -720, 720)),
        work_chain=(Joint("A", "rotary", Vec3(0, 0, 1), -720, 720),),
        tool_base=Transform(translation=Vec3(3, 4, 5)),
        work_base=Transform(translation=Vec3(10, 0, 0)),
    )
    body = JointBody("carriage", "tool", 1, box((0, 0, 0), (1, 1, 1)))
    state = {"X": 2, "C": 90, "A": 0}
    assert body_transform(machine, body, state).apply(Vec3(0, 0, 0)).tuple == (5, 4, 5)
    table = replace(body, name="table", frame="work", joint_count=1)
    assert body_transform(machine, table, state).apply(Vec3(0, 0, 0)).tuple == (10, 0, 0)
    world = replace(body, name="base", frame="world", joint_count=0)
    assert body_transform(machine, world, state).apply(Vec3(0, 0, 0)).tuple == (0, 0, 0)
    bodies = (body, replace(body, name="mounted cover"), world)
    result = review_joint_clearance(machine, [state, state], bodies, (("carriage", "mounted cover"),))
    assert not result.contacts and result.tested_pairs == 2
    assert result.status == "clear_declared_envelopes"
    with pytest.raises(ValueError, match="All body pairs"):
        review_joint_clearance(machine, [state, state], bodies[:2], (("carriage", "mounted cover"),))


def test_speed_enclosure_covers_nested_rotaries_pivots_and_translations():
    machine = MachineKinematics(
        tool_chain=(
            Joint("B", "rotary", Vec3(0, 1, 0), -720, 720, Vec3(3, -2, 1)),
            Joint("X", "linear", Vec3(1, 0, 0), -20, 20),
            Joint("C", "rotary", Vec3(0, 0, 1), -720, 720, Vec3(-1, 4, 2)),
        ),
        tool_base=Transform.rotation_about(Vec3(1, 0, 0), 30, Vec3(2, 4, 8)),
    )
    body = JointBody("holder", "tool", 3, box((-2, -1, -6), (3, 2, 4)))
    start, end = {"B": -70, "X": -10, "C": -350}, {"B": 110, "X": 15, "C": 370}
    speed = body_speed_bound(machine, body, start, end)
    previous = None
    for i in range(301):
        fraction = i / 300
        state = {name: start[name] + fraction * (end[name] - start[name]) for name in start}
        points = tuple(body_transform(machine, body, state).apply(p) for p in corners(body.bounds))
        if previous:
            assert max((a - b).length for a, b in zip(points, previous)) <= speed / 300 + 1e-10
        previous = points
    assert speed > 0
    assert body_speed_bound(machine, replace(body, frame="world", joint_count=0), start, end) == 0


def test_two_moving_chains_detect_a_mid_route_collision():
    machine, bodies = rotary_case()
    machine = replace(machine, work_chain=(Joint("X", "linear", Vec3(1, 0, 0), -20, 20),))
    obstacle = replace(bodies[1], frame="work", joint_count=1)
    result = review_joint_clearance(machine, [{"C": 0, "X": -1}, {"C": 180, "X": 1}], (bodies[0], obstacle))
    assert result.contacts and 0.4 < result.contacts[0].lower_fraction < 0.6


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r["collision_bodies"][0].update(joint_count=True),
        lambda r: r["collision_bodies"][0].update(joint_count=2),
        lambda r: r["collision_bodies"][0].update(frame="unknown"),
        lambda r: r["collision_bodies"][0].update(minimum_mm=[False, 0, 0]),
        lambda r: r.update(collision_exclusions=[["spindle arm", "missing"]]),
        lambda r: r.update(collision_exclusions=[["spindle arm", "fixture"], ["fixture", "spindle arm"]]),
    ],
)
def test_profile_rejects_malformed_collision_declarations(mutate):
    _machine, bodies = rotary_case()
    record = {
        "schema": 1,
        "tool_chain": [{"name": "C", "kind": "rotary", "axis": [0, 0, 1], "minimum": -720, "maximum": 720}],
        "collision_bodies": [body_record(b) for b in bodies],
    }
    mutate(record)
    with pytest.raises(ValueError):
        machine_from_record(record)


def test_cancellation_and_budget_withhold_partial_results():
    machine, bodies = rotary_case()
    with pytest.raises(InterruptedError):
        review_joint_clearance(machine, [{"C": 0}, {"C": 360}], bodies, cancelled=lambda: True)
    with pytest.raises(ValueError, match="budget"):
        review_joint_clearance(machine, [{"C": 0}, {"C": 360}], bodies, max_intervals=1)
    with pytest.raises(ValueError, match="joint limit"):
        review_joint_clearance(machine, [{"C": 0}, {"C": 721}], bodies)
    with pytest.raises(ValueError):
        review_joint_clearance(machine, [{"C": False}, {"C": 1}], bodies)


def test_profile_roundtrip_canonical_bodies_and_world_attachment():
    machine, bodies = rotary_case()
    records = [body_record(b) for b in bodies]
    assert bodies_from_record({"collision_bodies": records}, machine) == (bodies, ())
    for count in (-1, 1):
        records[1]["joint_count"] = count
        with pytest.raises(ValueError):
            bodies_from_record({"collision_bodies": records}, machine)
