"""Exact sharing equals independent per-leg review, including repeated moving chords."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from carveracontroller.machine.program_surface_archive import surface_report_record
from carveracontroller.machine.program_surface_clearance import refine_program_surfaces
from carveracontroller.machine.stock_allowance import inspect_target_cell
from carveracontroller.machine.stock_approach_clearance import review_stock_approach
from carveracontroller.machine.stock_approach_path import ApproachStart
from carveracontroller.machine.surface_motion import ContactGroupBudget, SurfaceMesh
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_solid import box


def prepared(tmp_path):
    report, analysis = example(tmp_path)
    rows = {n: dict(m) for n, m in report.meshes.items()}
    for name, lo, hi in (
        ("Rigid A", (10, 10, 10), (12, 12, 12)),
        ("Rigid B", (11, 11, 11), (13, 13, 13)),
        ("Nested", (10.2, 10.2, 10.2), (10.4, 10.4, 10.4)),
    ):
        report.body_review.records[2]["collision_bodies"].append(
            {"name": name, "frame": "world", "joint_count": 0, "minimum_mm": lo, "maximum_mm": hi}
        )
        rows[2][name] = SurfaceMesh.create(box(lo, hi))
    report = replace(report, meshes=MappingProxyType(rows))
    cell = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    return review_stock_approach(cell, report, route_start=ApproachStart((-9.0, -5.0, -8.0)))


@pytest.mark.parametrize("grouped", [True, False])
def test_identical_semantics_and_rebased_source_parameters(tmp_path, grouped):
    route = prepared(tmp_path)
    segments = tuple(
        replace(s, source_start_ratio=0.1 * i, source_end_ratio=0.1 * i + 0.4)
        for i, s in enumerate(route.scene.body_review.segments)
    )
    body = replace(route.scene.body_review, segments=segments)
    kwargs = {"grouped": grouped, "rotating_envelopes": route.scene.rotating_envelopes}
    independent = refine_program_surfaces(body, route.scene.meshes, **kwargs)
    shared = refine_program_surfaces(body, route.scene.meshes, reuse_rigid_pairs=True, **kwargs)
    for field in ("contacts", "groups", "occupancy", "rotating", "gaps", "refined_pairs"):
        assert getattr(shared, field) == getattr(independent, field), field
    assert shared.rigid_reused_pairs > 0 and shared.nodes < independent.nodes
    if grouped:
        grouped_rows = [r for r in shared.groups if (r.first, r.second) == ("Rigid A", "Rigid B")]
        assert len(grouped_rows) == 3 and len({id(r.group) for r in grouped_rows}) == 1
        assert [r.segment_index for r in grouped_rows] == [0, 1, 2]
        assert [r.source_lower_ratio for r in grouped_rows] == [segments[i].source_start_ratio for i in range(3)]
    with pytest.raises(ValueError, match="legacy"):
        surface_report_record(shared)
    assert surface_report_record(independent)


def test_unique_group_storage_budget_and_complete_move_limit(tmp_path):
    route = prepared(tmp_path)
    cap = route.scene.group_counts[1]
    shared = refine_program_surfaces(
        route.scene.body_review,
        route.scene.meshes,
        grouped=True,
        reuse_rigid_pairs=True,
        group_budget=ContactGroupBudget(max_members=cap),
        rotating_envelopes=route.scene.rotating_envelopes,
    )
    assert shared.groups == route.scene.groups
    with pytest.raises(ValueError, match="budget"):
        refine_program_surfaces(
            route.scene.body_review,
            route.scene.meshes,
            grouped=True,
            group_budget=ContactGroupBudget(max_members=cap),
            rotating_envelopes=route.scene.rotating_envelopes,
        )
    body = replace(route.scene.body_review, segments=(route.scene.body_review.segments[-1],) * 20_001)
    with pytest.raises(ValueError, match="20000"):
        refine_program_surfaces(body, route.scene.meshes, reuse_rigid_pairs=True)


@pytest.mark.parametrize("grouped", [True, False])
def test_longer_review_matches_every_independent_source_wrapper_and_refuses_one_below_storage(tmp_path, grouped):
    from carveracontroller.machine.program_joint_clearance import ProgramBodyContact

    route = prepared(tmp_path)
    original = route.scene.body_review
    segment = original.segments[0]
    assert segment.start != segment.end  # Complete moving chords, not only rigid pairs.
    segments = tuple(replace(segment, line=i + 1, source_start_ratio=0.1, source_end_ratio=0.9) for i in range(8))
    contacts = tuple(
        ProgramBodyContact(i, i + 1, r.tool, r.source_lower_ratio, r.source_upper_ratio, replace(r.contact, segment=i))
        for i in range(8)
        for r in original.contacts
        if r.segment_index == 0
    )
    body = replace(original, segments=segments, contacts=contacts)
    kwargs = {"grouped": grouped, "rotating_envelopes": route.scene.rotating_envelopes}
    independent = refine_program_surfaces(body, route.scene.meshes, **kwargs)
    shared = refine_program_surfaces(
        body, route.scene.meshes, reuse_rigid_pairs=True, reuse_complete_chords=True, **kwargs
    )
    for field in ("contacts", "groups", "occupancy", "rotating", "gaps", "refined_pairs"):
        assert getattr(shared, field) == getattr(independent, field), field
    count = sum(len(getattr(shared, f)) for f in ("contacts", "groups", "occupancy", "rotating", "gaps"))
    exact = refine_program_surfaces(
        body, route.scene.meshes, reuse_rigid_pairs=True, reuse_complete_chords=True, max_shared_rows=count, **kwargs
    )
    assert exact.groups == shared.groups and exact.occupancy == shared.occupancy
    with pytest.raises(ValueError, match="shared result budget"):
        refine_program_surfaces(
            body,
            route.scene.meshes,
            reuse_rigid_pairs=True,
            reuse_complete_chords=True,
            max_shared_rows=count - 1,
            **kwargs,
        )


def test_changed_relative_start_delta_direction_and_allowance_match_independent_review(tmp_path):
    from carveracontroller.addons.manufacturing_simulation import Vec3
    from carveracontroller.machine.program_joint_clearance import ProgramBodyContact

    route = prepared(tmp_path)
    original = route.scene.body_review
    base = original.segments[0]
    offset = Vec3(0.125, 0, 0)
    motions = (
        base,
        base,
        replace(base, start=base.start + offset, end=base.end + offset),
        replace(base, end=base.end + offset),
        replace(base, start=base.end, end=base.start),
        base,
    )
    segments = tuple(
        replace(s, line=i + 1, source_start_ratio=0.2, source_end_ratio=0.7) for i, s in enumerate(motions)
    )
    contacts = tuple(
        ProgramBodyContact(i, i + 1, r.tool, r.source_lower_ratio, r.source_upper_ratio, replace(r.contact, segment=i))
        for i in range(len(segments))
        for r in original.contacts
        if r.segment_index == 0
    )
    body = replace(original, segments=segments, contacts=contacts, curve_enclosures=((6, "G1", 0.01),))
    kwargs = {"grouped": True, "rotating_envelopes": route.scene.rotating_envelopes}
    independent = refine_program_surfaces(body, route.scene.meshes, **kwargs)
    shared = refine_program_surfaces(
        body, route.scene.meshes, reuse_rigid_pairs=True, reuse_complete_chords=True, **kwargs
    )
    for field in ("contacts", "groups", "occupancy", "rotating", "gaps", "refined_pairs"):
        assert getattr(shared, field) == getattr(independent, field), field
    assert shared.rigid_reused_pairs > 0 and shared.triangle_pairs < independent.triangle_pairs


def test_complete_motion_optimization_is_explicit_and_invalid_modes_are_refused(tmp_path):
    from hashlib import sha256

    from carveracontroller.machine.program_clearance_archive import encoded
    from carveracontroller.machine.stock_generated_clearance import _record

    route = prepared(tmp_path)
    kwargs = {"grouped": True, "rotating_envelopes": route.scene.rotating_envelopes, "reuse_rigid_pairs": True}
    legacy = refine_program_surfaces(route.scene.body_review, route.scene.meshes, **kwargs)
    explicit = refine_program_surfaces(
        route.scene.body_review, route.scene.meshes, reuse_complete_chords=False, **kwargs
    )
    for field in (
        "contacts",
        "groups",
        "occupancy",
        "rotating",
        "gaps",
        "nodes",
        "triangle_pairs",
        "solid_counts",
        "group_counts",
        "qualification",
    ):
        assert getattr(legacy, field) == getattr(explicit, field), field
    assert "No relative-moving pair is reused" in legacy.qualification
    # Golden independently computed by published b6bda22's refinement method
    # for this complete three-leg case. Saved v1 evidence includes counters and
    # qualification, so semantic equality alone cannot preserve public reopen.
    fields = (
        "contacts",
        "groups",
        "occupancy",
        "rotating",
        "gaps",
        "refined_pairs",
        "nodes",
        "triangle_pairs",
        "solid_counts",
        "group_counts",
        "rigid_reused_pairs",
        "qualification",
    )
    assert sha256(encoded({name: _record(getattr(legacy, name)) for name in fields})).hexdigest() == (
        "fb5b1c90e44c8172dfc899b98ed7fba1abb1469c8caddf4279da0286b44780fc"
    )
    for value in (1, None, "true"):
        with pytest.raises(ValueError, match="explicit"):
            refine_program_surfaces(route.scene.body_review, route.scene.meshes, reuse_complete_chords=value, **kwargs)
    with pytest.raises(ValueError, match="explicit"):
        refine_program_surfaces(route.scene.body_review, route.scene.meshes, reuse_complete_chords=True)
