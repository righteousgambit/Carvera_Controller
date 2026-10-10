"""Analytic CAD entry/containment, exact poses, complete members and unknown coverage."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation import SimulationSegment, Vec3
from carveracontroller.machine.joint_clearance import JointContact, bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_cad_first_contact import contact_pose, locate_cad_first_contacts
from carveracontroller.machine.program_joint_clearance import ProgramBodyContact
from carveracontroller.machine.program_surface_clearance import SurfaceGap, contact_triangles, refine_program_surfaces
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_solid import box, reverse


def scene(tmp_path, *, grouped=True, kind="crossing"):
    parent, _ = example(tmp_path)
    record = parent.body_review.records[2]
    for name, frame, count, lo, hi in (
        ("Moving", "tool", 2, (-0.5, -0.5, -0.5), (0.5, 0.5, 0.5)),
        ("Wall", "world", 0, (0, -2, -2), (1, 2, 2)),
    ):
        record["collision_bodies"].append(
            {"name": name, "frame": frame, "joint_count": count, "minimum_mm": lo, "maximum_mm": hi}
        )
    machine = machine_from_record(record)
    bodies, _ = bodies_from_record(record, machine)
    origin = body_transform(
        machine, next(b for b in bodies if b.name == "Moving"), dict.fromkeys(("X", "Y", "Z"), 0.0)
    ).translation.tuple
    moving = box(tuple(v - 0.5 for v in origin), tuple(v + 0.5 for v in origin))
    wall = box((0, -2, -2), (1, 2, 2))
    start, end = Vec3(-4, 0, 0), Vec3(4, 0, 0)
    if kind in ("contained", "cavity"):
        wall = box((-10, -10, -10), (10, 10, 10))
        if kind == "cavity":
            wall += reverse(box((-9, -9, -9), (9, 9, 9)))
    elif kind == "open":
        wall = wall[:-1]
    elif kind == "separated":
        start, end = Vec3(-8, 0, 0), Vec3(-4, 0, 0)
    wall = tuple(tuple(tuple(p[j] + origin[j] for j in range(3)) for p in triangle) for triangle in wall)
    wall_body = next(b for b in record["collision_bodies"] if b["name"] == "Wall")
    for key in ("minimum_mm", "maximum_mm"):
        wall_body[key] = tuple(wall_body[key][j] + origin[j] for j in range(3))
    segment = SimulationSegment(start, end, "2", True, line=1, source_start_ratio=0.25, source_end_ratio=0.75)
    body = replace(
        parent.body_review,
        segments=(segment,),
        contacts=(ProgramBodyContact(0, 1, 2, 0.25, 0.75, JointContact("Moving", "Wall", 0, 0, 1, 0.5, 0)),),
    )
    return refine_program_surfaces(
        body, {2: {"Moving": SurfaceMesh.create(moving), "Wall": SurfaceMesh.create(wall)}}, grouped=grouped
    )


@pytest.mark.parametrize("grouped", [True, False])
def test_exact_entry_original_faces_and_every_nominal_body_pose(tmp_path, grouped):
    report = scene(tmp_path, grouped=grouped)
    study = locate_cad_first_contacts(report)
    row = study.pairs[0]
    entry = (F(4) - F(1, 2) - F(1e-6)) / 8
    assert row.state == "surface_entry" and row.earliest_proven and row.lower == row.upper == entry
    assert row.pose.sample == entry and row.pose.joints_mm == (F(-4) + 8 * entry, 0, 0)
    assert row.surface.source_lower_ratio == row.surface.source_upper_ratio == F(1, 4) + F(1, 2) * entry
    bodies, _ = bodies_from_record(report.body_review.records[2], machine_from_record(report.body_review.records[2]))
    assert {b.name for b in row.pose.bodies} == {b.name for b in bodies}
    moving = next(b for b in row.pose.bodies if b.name == "Moving")
    machine = machine_from_record(report.body_review.records[2])
    origin = body_transform(
        machine, next(b for b in bodies if b.name == "Moving"), dict.fromkeys(("X", "Y", "Z"), 0.0)
    ).translation.tuple
    assert moving.translation_mm == tuple(F(origin[j]) + row.pose.joints_mm[j] for j in range(3))
    triangles = contact_triangles(report, row.surface)
    # At the nominal entry the prepared surfaces are within the declared
    # outward micron guard. Their actual geometry is not claimed intersecting.
    assert max(p[0] for p in triangles[0]) <= origin[0] and min(p[0] for p in triangles[1]) == origin[0]
    assert study.timeline_rows == sum(len(getattr(report, n)) for n in ("contacts", "groups", "occupancy", "gaps"))
    if grouped:
        assert row.group is not None and row.group.group.triangle_pairs
        assert study.original_group_members == sum(len(g.group.triangle_pairs) for g in report.groups)


@pytest.mark.parametrize(
    "kind,state", [("contained", "contained"), ("cavity", "separated"), ("separated", "separated")]
)
def test_initial_containment_and_cavity_do_not_use_outer_boxes_as_material(tmp_path, kind, state):
    row = locate_cad_first_contacts(scene(tmp_path, kind=kind)).pairs[0]
    assert row.state == state and row.earliest_proven
    if state == "contained":
        assert row.pose.sample == row.lower == 0 and row.occupancy.interval.sample == 0
        assert row.occupancy.interval.witness_point is not None
    else:
        assert row.pose is None and row.lower is None


def test_open_solid_retains_surface_entry_but_never_claims_earliest_volume_contact(tmp_path):
    report = scene(tmp_path, kind="open")
    row = locate_cad_first_contacts(report).pairs[0]
    assert row.surface is not None and row.pose is not None and not row.earliest_proven
    assert "coverage unavailable" in row.reason


def test_gap_only_pair_and_earlier_unknown_move_remain_visible(tmp_path):
    report = scene(tmp_path)
    gaps = (
        SurfaceGap(0, 1, 2, "Moving", "Wall", "unknown prior material"),
        SurfaceGap(0, 1, 2, "Unmodeled", "Wall", "missing geometry"),
    )
    study = locate_cad_first_contacts(replace(report, gaps=gaps))
    known, missing = study.pairs
    assert not known.earliest_proven and known.surface is not None
    assert missing.state == "unavailable" and missing.pose is None


def test_rehashed_or_forged_selected_group_interval_is_refused(tmp_path):
    report = scene(tmp_path)
    first = min(report.groups, key=lambda g: g.group.lower)
    forged = replace(first, group=replace(first.group, lower=F(0)))
    report = replace(report, groups=(forged,) + tuple(g for g in report.groups if g is not first))
    with pytest.raises(ValueError, match="differs from its retained exact interval"):
        locate_cad_first_contacts(report)


def test_complete_group_members_source_cancel_and_exact_budget_thresholds(tmp_path):
    report = scene(tmp_path)
    study = locate_cad_first_contacts(report)
    nodes, pairs, contacts = study.surface_counts
    assert (
        locate_cad_first_contacts(
            report, budget=SurfaceBudget(max_nodes=nodes, max_pairs=pairs, max_contacts=contacts)
        ).pairs
        == study.pairs
    )
    for limits in ({"max_nodes": nodes - 1}, {"max_pairs": pairs - 1}, {"max_contacts": contacts - 1}):
        with pytest.raises(ValueError, match="budget"):
            locate_cad_first_contacts(report, budget=SurfaceBudget(**limits))
    budget = SurfaceBudget()
    prior = budget.cancelled
    cancel = [False]

    def progress(*_):
        cancel[0] = True

    with pytest.raises(InterruptedError):
        locate_cad_first_contacts(report, budget=budget, cancelled=lambda: cancel[0], progress=progress)
    assert budget.cancelled is prior
    first = report.groups[0]
    invalid = replace(first, group=replace(first.group, triangle_pairs=first.group.triangle_pairs + ((999, 0),)))
    with pytest.raises(ValueError, match="invalid original face"):
        locate_cad_first_contacts(replace(report, groups=(invalid,)))


def test_pose_rejects_wrong_tool_invalid_parameter_and_cancellation(tmp_path):
    report = scene(tmp_path)
    for tool, move, time in ((1, 0, F(0)), (2, 2, F(0)), (2, 0, 0.5), (2, 0, F(-1))):
        with pytest.raises(ValueError):
            contact_pose(report, tool, move, time)
    with pytest.raises(InterruptedError):
        contact_pose(report, 2, 0, F(0), cancelled=lambda: True)


@pytest.mark.parametrize("unknown", [False, True])
def test_complete_unsorted_move_timeline_selects_earliest_pose_and_retains_prior_unknown(tmp_path, unknown):
    report = scene(tmp_path)
    segment = report.body_review.segments[0]
    earlier = replace(segment, start=Vec3(-8, 0, 0), end=Vec3(-4, 0, 0))
    groups = tuple(replace(row, segment_index=i, line=i + 1) for i in (2, 1) for row in report.groups)
    solids = tuple(replace(row, segment_index=i, line=i + 1) for i in (2, 1) for row in report.occupancy)
    gaps = (SurfaceGap(0, 1, 2, "Moving", "Wall", "prior solid unknown"),) if unknown else ()
    report = replace(
        report,
        body_review=replace(report.body_review, segments=(earlier, replace(segment, line=2), replace(segment, line=3))),
        groups=groups,
        occupancy=solids,
        gaps=gaps,
    )
    row = locate_cad_first_contacts(report).pairs[0]
    assert row.segment_index == row.pose.segment_index == 1
    assert row.pose.line == 2 and row.earliest_proven is not unknown
    assert row.surface is not None and row.group is not None
