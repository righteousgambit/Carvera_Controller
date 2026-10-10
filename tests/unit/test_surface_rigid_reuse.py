"""Exact sharing equals independent per-leg review, without masking relative motion."""

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


def test_unique_group_storage_budget_and_three_leg_limit(tmp_path):
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
    body = replace(
        route.scene.body_review, segments=route.scene.body_review.segments + (route.scene.body_review.segments[-1],)
    )
    with pytest.raises(ValueError, match="three"):
        refine_program_surfaces(body, route.scene.meshes, reuse_rigid_pairs=True)
