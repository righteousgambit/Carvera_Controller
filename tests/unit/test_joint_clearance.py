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


def test_long_common_rigid_attachment_keeps_every_membership_with_one_geometry_interval():
    machine = MachineKinematics(tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -100, 100),))
    bodies = (
        JointBody("a", "tool", 1, box((0, 0, 0), (2, 2, 2))),
        JointBody("b", "tool", 1, box((1, 1, 1), (3, 3, 3))),
    )
    waypoints = [{"X": (i % 2) * 80 - 40} for i in range(1001)]
    shared = review_joint_clearance(
        machine, waypoints, bodies, reuse_rigid_pairs=True, max_intervals=1, max_tested_pairs=1000
    )
    assert shared.tested_pairs == len(shared.contacts) == 1000 and shared.intervals == 1
    assert [r.segment for r in shared.contacts] == list(range(1000))
    assert all(r.lower_fraction == 0 and r.upper_fraction == 1 and r.witness_fraction == 0.5 for r in shared.contacts)
    with pytest.raises(ValueError, match="membership budget"):
        review_joint_clearance(machine, waypoints, bodies, reuse_rigid_pairs=True, max_tested_pairs=999)
    with pytest.raises(ValueError, match="ordered joint"):
        review_joint_clearance(machine, waypoints, bodies)


def test_rigid_sharing_keeps_relative_moving_full_turn_and_outward_near_contact():
    machine, moving = rotary_case()
    common = replace(moving[0], name="rigid cover")
    bodies = (moving[0], common, moving[1])
    waypoints = [{"C": i * 90} for i in range(9)]
    shared = review_joint_clearance(machine, waypoints, bodies, reuse_rigid_pairs=True)
    independent = tuple(review_joint_clearance(machine, waypoints[i : i + 2], bodies) for i in range(8))
    for i, report in enumerate(independent):
        assert [
            (r.first, r.second, r.lower_fraction, r.upper_fraction, r.witness_fraction)
            for r in shared.contacts
            if r.segment == i
        ] == [(r.first, r.second, r.lower_fraction, r.upper_fraction, r.witness_fraction) for r in report.contacts]
    assert shared.intervals < sum(r.intervals for r in independent)
    near = replace(common, bounds=box((10 + 0.5e-6, -0.1, -0.1), (11, 0.1, 0.1)))
    result = review_joint_clearance(machine, [{"C": 0}, {"C": 360}], (moving[0], near), reuse_rigid_pairs=True)
    assert len(result.contacts) == 1 and result.contacts[0].witness_fraction is None


def test_rigid_shared_cancellation_in_reused_memberships():
    machine, original = rotary_case()
    bodies = original[0], replace(original[0], name="cover")
    active = [False]

    def progress(done, _total):
        if done == 4:
            active[0] = True

    with pytest.raises(InterruptedError):
        review_joint_clearance(
            machine,
            [{"C": i} for i in range(12)],
            bodies,
            reuse_rigid_pairs=True,
            progress=progress,
            cancelled=lambda: active[0],
        )


def test_different_stationary_attachments_key_full_pose_without_reusing_moving_table():
    machine = MachineKinematics(
        tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -10, 10),),
        work_chain=(Joint("Y", "linear", Vec3(0, 1, 0), -10, 10),),
    )
    bodies = (
        JointBody("table", "work", 1, box((0, 0, 0), (1, 1, 1))),
        JointBody("frame", "world", 0, box((0.5, 0.5, 0.5), (1.5, 1.5, 1.5))),
    )
    points = [{"X": i % 2, "Y": 0 if i < 5 else 4} for i in range(10)]
    shared = review_joint_clearance(machine, points, bodies, reuse_rigid_pairs=True)
    independent = tuple(review_joint_clearance(machine, points[i : i + 2], bodies) for i in range(9))
    assert [(r.segment, r.lower_fraction, r.upper_fraction, r.witness_fraction) for r in shared.contacts] == [
        (i, r.lower_fraction, r.upper_fraction, r.witness_fraction)
        for i, report in enumerate(independent)
        for r in report.contacts
    ]
    assert not any(r.segment >= 5 for r in shared.contacts)
    assert shared.intervals < sum(r.intervals for r in independent)


@pytest.mark.parametrize("reverse", [False, True])
def test_exact_linear_slab_bounds_match_independent_middle_chord_contact(reverse):
    machine = MachineKinematics(tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -20, 20),))
    bodies = (
        JointBody("tool", "tool", 1, box((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))),
        JointBody("fixture", "world", 0, box((4.9, -0.1, -0.1), (5.1, 0.1, 0.1))),
    )
    points = [{"X": 10 if reverse else 0}, {"X": 0 if reverse else 10}]
    result = review_joint_clearance(machine, points, bodies, linear_enclosures=True, max_intervals=1)
    (contact,) = result.contacts
    assert contact.lower_fraction < 0.48 and contact.lower_fraction == pytest.approx(0.48, abs=1e-6)
    assert contact.upper_fraction > 0.52 and contact.upper_fraction == pytest.approx(0.52, abs=1e-6)
    assert contact.witness_fraction == pytest.approx(0.5)
    assert result.intervals == 1 and "exact rational slab" in result.qualification
    # Endpoints are disjoint; the interval is from all three affine slab
    # inequalities, not from a sampled midpoint overlap or tolerance change.
    assert all(abs(points[i]["X"] - 5) > 0.2 for i in (0, 1))


def test_exact_linear_two_chains_and_constant_axis_separation():
    machine = MachineKinematics(
        tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -20, 20),),
        work_chain=(Joint("Y", "linear", Vec3(-1, 0, 0), -20, 20),),
    )
    bodies = (
        JointBody("tool", "tool", 1, box((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1))),
        JointBody("fixture", "work", 1, box((4.9, -0.1, -0.1), (5.1, 0.1, 0.1))),
    )
    points = [{"X": 0, "Y": 0}, {"X": 10, "Y": 10}]
    (contact,) = review_joint_clearance(machine, points, bodies, linear_enclosures=True).contacts
    assert contact.lower_fraction == pytest.approx(0.24, abs=1e-6) and contact.upper_fraction == pytest.approx(
        0.26, abs=1e-6
    )
    separated = replace(bodies[1], bounds=box((4.9, 0.11, -0.1), (5.1, 0.3, 0.1)))
    assert not review_joint_clearance(machine, points, (bodies[0], separated), linear_enclosures=True).contacts


def test_linear_mode_refuses_rotaries_and_rotated_bases_preserving_general_enclosure():
    machine, bodies = rotary_case()
    with pytest.raises(ValueError, match="pure translations"):
        review_joint_clearance(machine, [{"C": 0}, {"C": 360}], bodies, linear_enclosures=True)
    assert review_joint_clearance(machine, [{"C": 0}, {"C": 360}], bodies).contacts
    machine = MachineKinematics(
        tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -20, 20),),
        tool_base=Transform.rotation_about(Vec3(0, 0, 1), 30),
    )
    with pytest.raises(ValueError, match="unrotated"):
        review_joint_clearance(
            machine, [{"X": 0}, {"X": 1}], (replace(bodies[0], joint_count=1), bodies[1]), linear_enclosures=True
        )


def test_same_rigid_attachment_cancels_full_rotary_motion_without_omitting_pair():
    machine = MachineKinematics(
        tool_chain=(
            Joint("X", "linear", Vec3(1, 0, 0), -400, 400),
            Joint("C", "rotary", Vec3(0, 0, 1), -720, 720),
        )
    )
    first = JointBody("mounted A", "tool", 2, box((10, 0, 0), (11, 1, 1)))
    separated = JointBody("mounted B", "tool", 2, box((10, 1.001, 0), (11, 2, 1)))
    route = [{"X": -300, "C": -720}, {"X": 300, "C": 720}]
    result = review_joint_clearance(machine, route, (first, separated), max_intervals=1, tolerance_mm=1e-6)
    assert result.intervals == result.tested_pairs == 1 and not result.contacts
    overlapping = replace(separated, bounds=box((10, 0.5, 0), (11, 2, 1)))
    result = review_joint_clearance(machine, route, (first, overlapping), max_intervals=1, tolerance_mm=1e-6)
    assert result.intervals == result.tested_pairs == 1
    assert result.contacts[0].lower_fraction == 0 and result.contacts[0].upper_fraction == 1
    assert result.contacts[0].motion_bound_mm == 0 and result.contacts[0].witness_fraction == 0.5
