"""Whole-program exact grouping, occupancy and independently recomputed v3 exchange."""

import hashlib
import json
from dataclasses import replace

import pytest

from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_surface_archive import (
    GROUP_METHOD,
    load_surface_review,
    save_surface_review,
    surface_report_record,
)
from carveracontroller.machine.program_surface_clearance import group_member_contact, refine_program_surfaces
from carveracontroller.machine.surface_motion import ContactGroupBudget
from tests.unit.test_program_surface_archive import occupancy_example, resign


@pytest.mark.parametrize("state", ["contained", "cavity", "open"])
def test_grouped_program_retains_solid_partition_and_roundtrip_including_empty_groups(tmp_path, state):
    source, offsets, raw = occupancy_example(hollow=state == "cavity", open_shell=state == "open")
    grouped = refine_program_surfaces(raw.body_review, raw.meshes, grouped=True)
    assert grouped.contact_mode == "groups" and grouped.contacts == ()
    assert grouped.occupancy == raw.occupancy and grouped.gaps == raw.gaps
    expected = {
        (
            c.segment_index,
            c.first,
            c.second,
            c.contact.first_triangle,
            c.contact.second_triangle,
            c.contact.lower,
            c.contact.upper,
            c.source_lower_ratio,
            c.source_upper_ratio,
        )
        for c in raw.contacts
    }
    expanded = [group_member_contact(g, i) for g in grouped.groups for i in range(len(g.group.triangle_pairs))]
    assert {
        (
            c.segment_index,
            c.first,
            c.second,
            c.contact.first_triangle,
            c.contact.second_triangle,
            c.contact.lower,
            c.contact.upper,
            c.source_lower_ratio,
            c.source_upper_ratio,
        )
        for c in expanded
    } == expected
    path = tmp_path / "grouped.cvsurfacereview"
    save_surface_review(path, source, offsets, grouped)
    data = json.loads(path.read_bytes())
    assert data["method"] == GROUP_METHOD
    loaded = load_surface_review(path)
    assert encoded(surface_report_record(loaded.report)) == encoded(surface_report_record(grouped))
    original = path.read_bytes()
    save_surface_review(path, loaded.source, loaded.work_offsets, loaded.report)
    assert path.read_bytes() == original


def test_v3_rehashed_group_evidence_or_representation_counters_cannot_reuse_report(tmp_path):
    source, offsets, raw = occupancy_example()
    grouped = refine_program_surfaces(raw.body_review, raw.meshes, grouped=True)
    path = tmp_path / "grouped.cvsurfacereview"
    save_surface_review(path, source, offsets, grouped)
    original = path.read_bytes()
    for field in ("groups", "group_counts", "contact_mode"):
        data = json.loads(original)
        if field == "groups":
            data["report"][field].append({"forged": True})
        elif field == "group_counts":
            data["report"][field][1] += 1
        else:
            data["report"][field] = "triangles"
        path.write_bytes(resign(data))
        with pytest.raises(ValueError, match="differs"):
            load_surface_review(path)


def test_ambiguous_modes_and_group_member_indices_refuse_without_omitting_evidence(tmp_path):
    source, offsets, raw = occupancy_example()
    for report in (replace(raw, contact_mode="unknown"), replace(raw, group_counts=(1, 1))):
        path = tmp_path / "kept.cvsurfacereview"
        path.write_bytes(b"prior")
        with pytest.raises(ValueError):
            save_surface_review(path, source, offsets, report)
        assert path.read_bytes() == b"prior"
    with pytest.raises(ValueError):
        refine_program_surfaces(raw.body_review, raw.meshes, grouped=1)
    with pytest.raises(ValueError):
        refine_program_surfaces(raw.body_review, raw.meshes, group_budget=ContactGroupBudget())


def contact_example():
    from carveracontroller.machine.surface_motion import SurfaceMesh
    from tests.unit.test_stock_solid import box

    source, offsets, initial = occupancy_example()
    meshes = {tool: dict(rows) for tool, rows in initial.meshes.items()}
    fixed = next(n for n in meshes[1] if n.startswith("fixed"))
    meshes[1][fixed] = SurfaceMesh.create(box((-1, -1, -1), (1, 1, 1)))
    return source, offsets, refine_program_surfaces(initial.body_review, meshes)


def test_complete_original_members_and_source_intervals_replay_and_rehashed_members_refuse(tmp_path):
    source, offsets, raw = contact_example()
    report = refine_program_surfaces(raw.body_review, raw.meshes, grouped=True)
    assert 1 <= len(report.groups) < len(raw.contacts) and len(raw.contacts) > 50
    assert report.group_counts == (len(report.groups), len(raw.contacts))
    assert {
        group_member_contact(group, i) for group in report.groups for i in range(len(group.group.triangle_pairs))
    } == set(raw.contacts)
    for index in (True, -1, len(report.groups[0].group.triangle_pairs)):
        with pytest.raises(ValueError):
            group_member_contact(report.groups[0], index)
    path = tmp_path / "contact.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    restored = load_surface_review(path)
    assert restored.report.groups == report.groups
    data = json.loads(path.read_bytes())
    data["report"]["groups"][0]["group"]["triangle_pairs"][0][0] += 1
    path.write_bytes(resign(data))
    with pytest.raises(ValueError, match="differs"):
        load_surface_review(path)


def dense_example():
    from carveracontroller.machine.surface_motion import SurfaceMesh

    source, offsets, initial = occupancy_example()
    meshes = {tool: dict(rows) for tool, rows in initial.meshes.items()}
    moving = next(n for n in meshes[1] if n.startswith("carriage"))
    fixed = next(n for n in meshes[1] if n.startswith("fixed"))
    meshes[1][moving] = SurfaceMesh.create((((180.0, 0.0, 0.0),) * 3,) * 8)
    meshes[1][fixed] = SurfaceMesh.create((((0.0, 0.0, 0.0),) * 3,) * 9)
    return source, offsets, refine_program_surfaces(initial.body_review, meshes, grouped=True)


@pytest.mark.parametrize("kind", ["arc", "multiple WCS", "NURBS"])
def test_grouped_review_preserves_curve_bounds_named_datums_and_tool_transitions(tmp_path, kind):
    from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
    from carveracontroller.machine.program_operations import ProgramOperations
    from carveracontroller.machine.program_surface_clearance import review_program_surfaces
    from tests.unit.test_program_joint_clearance import captures, program

    offsets = {"G54": (-180, -120, -110), "G55": (-200, -100, -100)}
    if kind == "arc":
        parsed = program(arc=True)
    elif kind == "multiple WCS":
        parsed = ProgramOperations.from_text(
            "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X1 F100\nG55\nT2 M6\nG1 X2", work_offsets=offsets
        )
    else:
        from tests.unit.test_linuxcnc_nurbs_program import BLOCK, HEADER

        parsed = ProgramOperations.from_text(
            HEADER.replace("G0", "T1 M6\nG0", 1) + BLOCK, dialect="linuxcnc", spline_tolerance_mm=0.025
        )
    source = ProgramClearanceSource.capture(parsed)
    raw = review_program_surfaces(source, captures(1, 2), offsets)
    report = review_program_surfaces(source, captures(1, 2), offsets, grouped=True)
    assert report.occupancy == raw.occupancy and report.gaps == raw.gaps
    expanded = {group_member_contact(g, i) for g in report.groups for i in range(len(g.group.triangle_pairs))}
    assert expanded == set(raw.contacts)
    path = tmp_path / "curved.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    loaded = load_surface_review(path)
    assert encoded(surface_report_record(loaded.report)) == encoded(surface_report_record(report))
    assert loaded.report.body_review.curve_enclosures == raw.body_review.curve_enclosures
    assert loaded.report.body_review.tool_change_lines == raw.body_review.tool_change_lines
    assert loaded.source.parse_settings == source.parse_settings
