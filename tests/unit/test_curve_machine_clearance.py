"""Curve certificates must enclose actual motion rather than only chord samples."""

import json
import math
from dataclasses import replace

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, Joint, MachineKinematics, Vec3
from carveracontroller.machine.joint_clearance import JointBody, review_joint_clearance
from carveracontroller.machine.program_clearance_archive import (
    LEGACY_METHOD,
    METHOD,
    encoded,
    load_program_review,
    save_program_review,
)
from carveracontroller.machine.program_joint_clearance import (
    ProgramClearanceSource,
    review_program_body_records,
    review_program_clearance,
)
from carveracontroller.machine.program_operations import ProgramOperations
from tests.unit.test_program_joint_clearance import captures, program

OFFSETS = {"G54": (-180, -120, -110)}


@pytest.mark.parametrize(
    "plane,command,axes,axial",
    [
        ("G17", "G2 X10 Y0 Z3 I5 J0", (0, 1), 2),
        ("G18", "G2 Z10 X0 Y3 K5 I0", (2, 0), 1),
        ("G19", "G2 Y10 Z0 X3 J5 K0", (1, 2), 0),
        ("G17", "G3 X10 Y0 Z3 I5 J0", (0, 1), 2),
        ("G17", "G2 X0 Y0 Z3 I5 J0", (0, 1), 2),
    ],
)
def test_arc_bound_encloses_parameter_matched_analytic_helices(plane, command, axes, axial):
    p = ProgramOperations.from_text(
        f"G21 G90 G91.1 {plane} G94 G54\nT1 M6\nG0 X0 Y0 Z0\n{command}", arc_tolerance_mm=0.3
    )
    (curve,) = p.curve_enclosures
    sweep = 2 * math.pi if "X0 Y0" in command else math.pi
    direction = 1 if command.startswith("G3") else -1
    for index, (lo, hi) in enumerate(zip(curve.parameters, curve.parameters[1:])):
        for k in range(21):
            fraction = k / 20
            t = lo + (hi - lo) * fraction
            expected = [0.0, 0.0, 0.0]
            expected[axes[0]] = 5 + 5 * math.cos(math.pi + direction * sweep * t)
            expected[axes[1]] = 5 * math.sin(math.pi + direction * sweep * t)
            expected[axial] = 3 * t
            chord = tuple(a + fraction * (b - a) for a, b in zip(curve.points_mm[index], curve.points_mm[index + 1]))
            assert math.dist(expected, chord) <= curve.maximum_error_bound_mm
    assert curve.parameters[0] == 0 and curve.parameters[-1] == 1
    assert curve.maximum_error_bound_mm > 0


def test_arc_radius_mismatch_is_included_in_enclosure():
    p = ProgramOperations.from_text(
        "G21 G90 G91.1 G17 G54\nT1 M6\nG0 X0 Y0 Z0\nG2 X10.005 Y0 I5 J0", arc_tolerance_mm=0.01
    )
    curve = p.curve_enclosures[0]
    assert curve.maximum_error_bound_mm > 0.005
    assert curve.points_mm[-1] == (10.005, 0, 0)


def test_curve_enclosure_finds_contact_between_noncontacting_chords():
    machine = MachineKinematics(tool_chain=(Joint("X", "linear", Vec3(1, 0, 0), -5, 5),))
    small = AABB(Vec3(-0.01, -0.01, -0.01), Vec3(0.01, 0.01, 0.01))
    moving = JointBody("moving", "tool", 1, small)
    obstacle = JointBody("obstacle", "world", 0, AABB(Vec3(0.9, 0.08, -0.01), Vec3(1.1, 0.1, 0.01)))
    route = [{"X": 0}, {"X": 2}]
    assert not review_joint_clearance(machine, route, (moving, obstacle)).contacts
    enclosed = review_joint_clearance(machine, route, (moving, obstacle), body_position_error_mm=0.1)
    assert enclosed.contacts and all(c.witness_fraction is None for c in enclosed.contacts)
    assert enclosed.contacts[0].motion_bound_mm >= 0.2
    # A common uncertain translation changes neither relative position nor clearance.
    attached = replace(obstacle, frame="tool", joint_count=1)
    assert not review_joint_clearance(machine, route, (moving, attached), body_position_error_mm=0.1).contacts


@pytest.mark.parametrize("error", [-1, float("nan"), float("inf"), True, 1001])
def test_invalid_world_position_enclosures_refused(error):
    with pytest.raises(ValueError):
        review_joint_clearance(MachineKinematics(), [{}, {}], (), body_position_error_mm=error)


def test_program_curve_bound_and_parameter_intervals_reach_body_math():
    p = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG5 X10 Y1 I0 J9 P0 Q-1 F100",
        dialect="linuxcnc",
        spline_tolerance_mm=0.1,
    )
    source = ProgramClearanceSource.capture(p)
    result = review_program_clearance(source, captures(), OFFSETS, start_line=4)
    curve = p.curve_enclosures[0]
    assert len({round(b - a, 8) for a, b in zip(curve.parameters, curve.parameters[1:])}) > 1
    assert result.curve_coverage and result.curved_lines == ()
    assert result.curve_enclosures == ((4, "G5", curve.maximum_error_bound_mm),)
    assert tuple(s.source_start_ratio for s in result.segments) == curve.parameters[:-1]
    assert tuple(s.source_end_ratio for s in result.segments) == curve.parameters[1:]
    assert result.contacts
    widened = [c for c in result.contacts if c.contact.motion_bound_mm >= 2 * curve.maximum_error_bound_mm]
    assert widened and all(c.contact.witness_fraction is None for c in widened)
    for c in result.contacts:
        segment = result.segments[c.segment_index]
        assert segment.source_start_ratio <= c.source_lower_ratio <= c.source_upper_ratio <= segment.source_end_ratio
    assert "curve enclosure" in result.qualification


@pytest.mark.parametrize(
    "mutation",
    [
        lambda c: replace(c, parameters=(0.0,) * len(c.parameters)),
        lambda c: replace(c, maximum_error_bound_mm=float("nan")),
        lambda c: replace(c, points_mm=c.points_mm[:-1]),
        lambda c: replace(c, command="unknown"),
    ],
)
def test_malformed_curve_metadata_never_closes_gaps(mutation):
    source = ProgramClearanceSource.capture(program(arc=True))
    source = replace(source, curve_enclosures=(mutation(source.curve_enclosures[0]),))
    with pytest.raises(ValueError, match="enclosure"):
        review_program_clearance(source, captures(), OFFSETS, start_line=4)


def test_missing_certificate_retains_curve_gap_and_duplicate_refused():
    source = ProgramClearanceSource.capture(program(arc=True))
    result = review_program_clearance(replace(source, curve_enclosures=()), captures(), OFFSETS, start_line=4)
    assert result.curved_lines == (4,) and not result.curve_enclosures
    with pytest.raises(ValueError, match="Duplicate"):
        review_program_clearance(replace(source, curve_enclosures=source.curve_enclosures * 2), captures(), OFFSETS)


def test_curve_enclosure_cannot_cross_machine_travel_limits():
    source = ProgramClearanceSource.capture(program(arc=True))
    records = review_program_clearance(source, captures(), OFFSETS, start_line=4).records
    # Chord endpoints are in travel, but declared position error crosses X minimum.
    curve = source.curve_enclosures[0]
    source = replace(source, curve_enclosures=(replace(curve, maximum_error_bound_mm=10.0),))
    with pytest.raises(ValueError, match="curve enclosure exceeds"):
        review_program_body_records(source, records, {"G54": (-359, -120, -110)}, start_line=4)


def test_both_legacy_chord_and_curve_archive_methods_recompute(tmp_path):
    source = ProgramClearanceSource.capture(program(arc=True))
    for mode, method in ((False, LEGACY_METHOD), (True, METHOD)):
        report = review_program_clearance(source, captures(), OFFSETS, start_line=4, cover_curves=mode)
        path = tmp_path / f"{mode}.cvprogramclearance"
        save_program_review(path, source, OFFSETS, report)
        raw = json.loads(path.read_bytes())
        assert raw["method"] == method
        loaded = load_program_review(path)
        assert loaded.report.curve_coverage is mode
        assert bool(loaded.report.curved_lines) is not mode
        if mode:
            raw["report"]["curve_enclosures"][0][2] *= 2
            import hashlib

            raw.pop("sha256")
            raw["sha256"] = hashlib.sha256(encoded(raw)).hexdigest()
            path.write_bytes(encoded(raw))
            with pytest.raises(ValueError, match="recomputed"):
                load_program_review(path)


def test_actual_arc_contact_between_chords_is_not_reported_clear():
    from copy import deepcopy

    from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
    from carveracontroller.machine.kinematic_review import machine_from_record
    from carveracontroller.machine.scene_joint_clearance import build_scene_clearance

    p = ProgramOperations.from_text(
        "G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG2 X10 Y0 I5 J0 F100", arc_tolerance_mm=0.5
    )
    source = ProgramClearanceSource.capture(p)
    curve = p.curve_enclosures[0]
    t = (curve.parameters[0] + curve.parameters[1]) / 2
    x, y = 5 + 5 * math.cos(math.pi - math.pi * t), 5 * math.sin(math.pi - math.pi * t)
    record = deepcopy(build_scene_clearance(captures()[1]))
    record["tool_base"] = {"translation": [0, 0, 0]}
    record["work_base"] = {"translation": [0, 0, 0]}
    center = (-180 + x, -120 + y, -110)
    epsilon = 0.00001

    def body(name, frame, count, position):
        return {
            "name": name,
            "frame": frame,
            "joint_count": count,
            "minimum_mm": [v - epsilon for v in position],
            "maximum_mm": [v + epsilon for v in position],
        }

    record["collision_bodies"] = [body("tip", "tool", 2, (0, 0, 0)), body("small fixture", "work", 1, center)]
    record["collision_exclusions"] = []
    machine = machine_from_record(record)
    bodies, _ = bodies_from_record(record, machine)
    actual = dict(zip(("X", "Y", "Z"), center))
    # Independent analytic curve point: both small boxes have exactly the same world centre.
    positions = [
        body_transform(machine, b, actual).apply(Vec3(*center) if b.frame == "work" else Vec3(0, 0, 0)) for b in bodies
    ]
    assert positions[0].tuple == pytest.approx(positions[1].tuple)
    legacy = review_program_body_records(source, {1: record}, OFFSETS, start_line=4, cover_curves=False)
    current = review_program_body_records(source, {1: record}, OFFSETS, start_line=4)
    assert not legacy.contacts
    assert current.contacts and current.curved_lines == ()
    assert all(c.contact.witness_fraction is None for c in current.contacts)
    # The solver reports the first conservative interval in a chord, not the complete contact duration.
    assert any(c.segment_index == 0 for c in current.contacts)
