"""Whole-sweep certificates preserve all per-move results; only separation is reusable."""

from dataclasses import replace
from fractions import Fraction as F
from types import MappingProxyType

import pytest

from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.machine.joint_clearance import JointContact, bodies_from_record
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramBodyContact
from carveracontroller.machine.program_surface_clearance import _translation, refine_program_surfaces
from carveracontroller.machine.surface_linear_sweep import complete_table_sweep
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceBudgetExceeded, SurfaceMesh, qpoint
from tests.unit.test_stock_solid import box, reverse
from tests.unit.test_surface_rigid_reuse import prepared


def scene(tmp_path, kind="separated"):
    route = prepared(tmp_path)
    original = route.scene.body_review
    record = original.records[2]
    for name, frame, count, lo, hi in (
        ("Sweep frame", "world", 0, (-3, -3, -3), (3, 3, 3)),
        ("Sweep ATC", "work", 1, (-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)),
    ):
        record["collision_bodies"].append(
            {"name": name, "frame": frame, "joint_count": count, "minimum_mm": lo, "maximum_mm": hi}
        )
    rows = {tool: dict(meshes) for tool, meshes in route.scene.meshes.items()}
    triangles = box((-3, -3, -3), (3, 3, 3)) + reverse(box((-2, -2, -2), (2, 2, 2)))
    rows[2]["Sweep frame"] = SurfaceMesh.create(triangles[:-1] if kind == "open" else triangles)
    rows[2]["Sweep ATC"] = SurfaceMesh.create(box((-0.1, -0.1, -0.1), (0.1, 0.1, 0.1)))
    step = 0.5 if kind == "crossing" else 0.01
    segments = tuple(
        replace(
            original.segments[0],
            line=i + 1,
            start=Vec3(-9, -0.4 - i * step, -8),
            end=Vec3(-9, -0.4 - (i + 1) * step, -8),
            source_start_ratio=0.2,
            source_end_ratio=0.8,
        )
        for i in range(8)
    )
    contacts = tuple(
        ProgramBodyContact(i, i + 1, 2, 0.2, 0.8, JointContact("Sweep frame", "Sweep ATC", i, 0, 1, 0.5, 0))
        for i in range(8)
    )
    return replace(original, segments=segments, contacts=contacts), MappingProxyType(rows)


@pytest.mark.parametrize("kind", ["separated", "crossing", "open"])
def test_complete_uncached_result_parity_and_no_positive_or_unknown_sweep_reuse(tmp_path, kind):
    body, meshes = scene(tmp_path, kind)
    independent = refine_program_surfaces(body, meshes, grouped=True)
    shared = refine_program_surfaces(body, meshes, grouped=True, reuse_rigid_pairs=True, reuse_complete_chords=True)
    for field in ("contacts", "groups", "occupancy", "rotating", "gaps", "refined_pairs"):
        assert getattr(shared, field) == getattr(independent, field), field
    assert {r.segment_index for r in (*shared.groups, *shared.occupancy, *shared.gaps)} == set(range(8))
    if kind == "separated":
        assert len(shared.occupancy) == 8 and all(r.interval.state == "separated" for r in shared.occupancy)
        assert shared.rigid_reused_pairs == 8 and shared.nodes < independent.nodes
    else:
        assert shared.rigid_reused_pairs == 0
        assert shared.groups if kind == "crossing" else shared.gaps


def test_exact_complete_pose_hull_rounds_both_endpoints_outward_and_refuses_partial_metadata(tmp_path):
    body, _meshes = scene(tmp_path)
    machine = machine_from_record(body.records[2])
    bodies, _ = bodies_from_record(body.records[2], machine)
    names = {b.name: b for b in bodies}
    first, second = names["Sweep frame"], names["Sweep ATC"]
    budget = SurfaceBudget()
    result = complete_table_sweep(machine, first, second, body.segments, _translation, budget)
    assert result is not None and budget.nodes == 8
    shift, delta = map(qpoint, result)
    for segment in body.segments:
        start, end = (dict(zip(("X", "Y", "Z"), p.tuple)) for p in (segment.start, segment.end))
        a, da = _translation(machine, first, start, end)
        b, db = _translation(machine, second, start, end)
        origin, speed = qpoint((a - b).tuple), qpoint((da - db).tuple)
        for p in (origin, tuple(origin[i] + speed[i] for i in range(3))):
            assert p[0] == shift[0] and p[2] == shift[2]
            assert shift[1] <= p[1] <= shift[1] + delta[1]
    with pytest.raises(SurfaceBudgetExceeded, match="nodes"):
        complete_table_sweep(machine, first, second, body.segments, _translation, SurfaceBudget(max_nodes=3))
    with pytest.raises(InterruptedError):
        complete_table_sweep(machine, first, second, body.segments, _translation, SurfaceBudget(cancelled=lambda: True))
    with pytest.raises(ValueError, match="20000"):
        complete_table_sweep(machine, first, second, body.segments * 2501, _translation, SurfaceBudget())
    assert complete_table_sweep(machine, first, first, body.segments, _translation, SurfaceBudget()) is None
    assert shift[1] <= F(0.4)


def test_master_contact_probe_cannot_hide_a_between_endpoint_collision(tmp_path):
    body, meshes = scene(tmp_path, "crossing")
    segment = replace(body.segments[0], start=Vec3(-9, -0.4, -8), end=Vec3(-9, -4.4, -8))
    body = replace(body, segments=(segment,), contacts=(body.contacts[0],))
    result = refine_program_surfaces(body, meshes, grouped=True, reuse_rigid_pairs=True, reuse_complete_chords=True)
    assert result.groups and result.rigid_reused_pairs == 0
    assert any(0 < r.group.lower < r.group.upper < 1 for r in result.groups)
