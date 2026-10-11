"""Program-wide surface coverage, independent viewer frames and explicit gaps."""

from dataclasses import replace

import pytest

from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_surface_clearance import (
    contact_triangles,
    occupancy_witness,
    refine_program_surfaces,
    review_program_surfaces,
    scene_surfaces,
)
from carveracontroller.machine.scene_joint_clearance import build_scene_clearance
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh
from tests.unit.test_program_joint_clearance import captures, program, review
from tests.unit.test_scene_joint_clearance import capture, scene_viewer


@pytest.mark.parametrize("state", [(-180, -120, -110), (-25, -235, -10), (-350, -5, -135)])
def test_all_surface_vertices_agree_with_independent_viewer_geometry_and_pose(state):
    viewer = scene_viewer()
    snapshot = capture(viewer)
    record = build_scene_clearance(snapshot)
    meshes = scene_surfaces(snapshot, record)
    machine = machine_from_record(record)
    bodies, _ = bodies_from_record(record, machine)
    zero = dict.fromkeys(("X", "Y", "Z"), 0.0)
    joints = dict(zip(("X", "Y", "Z"), state))
    geometry = viewer.machine_profile.scene(
        viewer.machine_setup, viewer.workholding_offset_mm, viewer.workholding_rotation_deg, viewer.jaw_offset_mm
    )
    pose = viewer.machine_profile.pose(viewer.machine_setup, viewer.machine_setup.work_point(state), 30)
    assert len(meshes) == 8
    for body in bodies:
        if body.name not in meshes:
            assert body.name.startswith("T1")
            continue
        group = body.name.split()[0]
        source = geometry[group]
        shift = (
            pose["table"]
            if group in ("stock", "table", "fixture", "workholding", "atc")
            else pose.get(group, (0, 0, 0))
        )
        expected = [tuple(source.vertices[i * 10 + a] + shift[a] for a in range(3)) for i in source.indices]
        delta = body_transform(machine, body, joints).translation - body_transform(machine, body, zero).translation
        actual = [(Vec3(*p) + delta).tuple for tri in meshes[body.name].triangles for p in tri]
        assert len(actual) == len(expected)
        for a, e in zip(actual, expected):
            assert a == pytest.approx(e)


def test_component_override_repeat_stocks_and_full_flute_tool_need_no_shank_mesh():
    from carveracontroller.machine.repeat_parts import RepeatPartPlan, StockInstance

    viewer = scene_viewer()
    viewer.machine_component_profiles = {"fixture": scene_viewer(100).machine_profile}
    viewer.library_tool_table_mm[1].flute_length = 30
    viewer.repeat_stock_plan = RepeatPartPlan(
        (
            StockInstance("A", "G54", (-180, -120, -110), (0, 0, 0), (10, 8, 5), stock_orientation_deg=(20, 10, 35)),
            StockInstance("B", "G55", (-140, -120, -110), (0, 0, 0), (10, 8, 5)),
        )
    )
    snapshot = capture(viewer)
    meshes = scene_surfaces(snapshot, build_scene_clearance(snapshot))
    assert len(meshes) == 9
    assert len([name for name in meshes if name.startswith("stock")]) == 2
    assert (
        min(p[0] for name, m in meshes.items() if name.startswith("fixture") for tri in m.triangles for p in tri)
        == -210
    )


def test_full_chord_refinement_detects_contact_later_than_first_box_interval():
    base = review()
    segment = base.segments[0]
    fixed = next(b for b in base.records[1]["collision_bodies"] if b["name"].startswith("fixed"))["name"]
    moving = next(b for b in base.records[1]["collision_bodies"] if b["name"].startswith("carriage"))["name"]
    candidate = replace(
        base.contacts[0],
        contact=replace(base.contacts[0].contact, first=moving, second=fixed, lower_fraction=0.01, upper_fraction=0.02),
    )
    base = replace(base, contacts=(candidate,))
    # Moving q0 triangle at x=180 crosses world x=9 at X=-171 (t=.9).
    tri_a = ((180, 0, 0), (180, 2, 0), (180, 0, 2))
    tri_b = ((9, 0, 0), (9, 2, 0), (9, 0, 2))
    meshes = {1: {moving: SurfaceMesh.create((tri_a,)), fixed: SurfaceMesh.create((tri_b,))}}
    result = refine_program_surfaces(base, meshes)
    assert result.refined_pairs == 1 and len(result.contacts) == 1
    hit = result.contacts[0]
    assert float(hit.contact.lower) == pytest.approx(0.9, abs=1e-6)
    assert hit.contact.lower > candidate.contact.upper_fraction
    assert all(p[0] == pytest.approx(9) for tri in contact_triangles(result, hit) for p in tri)
    assert segment.end.x - segment.start.x == 10
    duplicated = {1: {moving: SurfaceMesh.create((tri_a,) * 2), fixed: SurfaceMesh.create((tri_b,))}}
    with pytest.raises(ValueError, match="shared pairs budget") as refusal:
        refine_program_surfaces(base, duplicated, budget=SurfaceBudget(max_pairs=1))
    message = str(refusal.value)
    assert f"Source line {segment.line} · T1" in message
    assert moving in message and fixed in message
    assert "Surface work:" in message and "Solid work:" in message
    assert "no partial report" in message


def test_surface_separation_and_rotating_envelopes_are_gaps_not_solid_clearance():
    base = review()
    rows = {t: scene_surfaces(captures(t)[t], r) for t, r in base.records.items()}
    result = refine_program_surfaces(base, rows)
    assert result.gaps
    assert any("envelope_only" in g.reason for g in result.gaps)
    assert "Closed-solid containment/separation" in result.qualification
    assert result.body_review is base
    assert len(result.contacts) + len(result.gaps) + len(result.occupancy) >= len(base.contacts)


def test_full_review_curve_interiors_source_ranges_and_shared_budget_restore():
    source = ProgramClearanceSource.capture(program(arc=True))
    budget = SurfaceBudget()
    original = budget.cancelled
    result = review_program_surfaces(source, captures(), {"G54": (-180, -120, -110)}, start_line=4, budget=budget)
    assert result.body_review.curve_enclosures and not result.body_review.curved_lines
    assert all(c.line == 4 and 0 <= c.source_lower_ratio <= c.source_upper_ratio <= 1 for c in result.contacts)
    assert budget.cancelled is original
    for kwargs in ({"max_triangles": 1}, {"cancelled": lambda: True}):
        with pytest.raises((ValueError, InterruptedError), match="budget|cancelled"):
            review_program_surfaces(source, captures(), {"G54": (-180, -120, -110)}, **kwargs)


def test_surface_factory_triangle_budget_is_complete_and_bounded():
    snapshot = capture(scene_viewer())
    record = build_scene_clearance(snapshot)
    for limit in (0, True, 1):
        with pytest.raises(ValueError, match="budget"):
            scene_surfaces(snapshot, record, max_triangles=limit)


def solid_report(p=None, *, hollow=False, open_mesh=False):
    from tests.unit.test_stock_solid import box, reverse

    base = review(p)
    names = [b["name"] for b in base.records[1]["collision_bodies"]]
    first, second = next(n for n in names if n.startswith("carriage")), next(n for n in names if n.startswith("fixed"))
    candidate = replace(base.contacts[0], contact=replace(base.contacts[0].contact, first=first, second=second))
    segment = replace(
        base.segments[0], start=Vec3(5, 0, 0), end=Vec3(5, 0, 0), source_start_ratio=0.25, source_end_ratio=0.75
    )
    base = replace(base, segments=(segment,), contacts=(candidate,))
    outer = box((-2, -2, -2), (2, 2, 2))
    if hollow:
        outer += reverse(box((-1.5, -1.5, -1.5), (1.5, 1.5, 1.5)))
    if open_mesh:
        outer = outer[:-1]
    return refine_program_surfaces(
        base,
        {
            1: {
                first: SurfaceMesh.create(box((-6, -1, -1), (-4, 1, 1))),
                second: SurfaceMesh.create(outer),
            }
        },
    )


def test_nested_closed_surfaces_prove_declared_solid_containment():
    result = solid_report()
    assert not result.contacts and not result.gaps
    assert len(result.occupancy) == 1 and result.occupancy[0].interval.state == "contained"
    assert result.occupancy[0].source_lower_ratio == 0.25 and result.occupancy[0].source_upper_ratio == 0.75
    assert occupancy_witness(result, result.occupancy[0]) == (-1, -1, -1)
    # Admission can be proved entirely by certificates; steps and queries still count.
    assert result.solid_counts[0] > 0 and result.solid_counts[3] > 0


def test_true_cavity_separation_and_open_shell_gap_preserve_program_scope():
    separated = solid_report(hollow=True)
    assert not separated.contacts and not separated.gaps
    assert separated.occupancy[0].interval.state == "separated"
    assert occupancy_witness(separated, separated.occupancy[0]) is None
    gap = solid_report(open_mesh=True)
    assert not gap.contacts and not gap.occupancy
    assert "solid_unavailable" in gap.gaps[0].reason
    assert gap.gaps[0].line == separated.occupancy[0].line == 4


def test_imported_repeat_stock_keeps_concavity_and_rechecks_mutated_bytes(tmp_path, monkeypatch):
    from pathlib import Path

    import carveracontroller.machine.program_surface_clearance as module
    from carveracontroller.machine.repeat_parts import RepeatPartPlan, StockInstance, StockSource
    from tests.unit.test_stock_model import model

    stock = model(tmp_path)
    viewer = scene_viewer()
    part = StockInstance(
        "Imported",
        "G54",
        (-180, -120, -110),
        (0, 0, 0),
        stock.size_mm,
        stock_source=StockSource.from_model(stock),
        stock_orientation_deg=(20, 10, 35),
    )
    viewer.repeat_stock_plan = RepeatPartPlan((part,))
    snapshot = capture(viewer)
    record = build_scene_clearance(snapshot)
    surfaces = scene_surfaces(snapshot, record)
    mesh = surfaces["stock G54 · Imported"]
    from carveracontroller.addons.machine_simulation.model import MachineSetup

    expected = stock.geometry(
        MachineSetup(
            part.work_offset_mm,
            part.stock_size_mm,
            part.stock_origin_mm,
            stock_model=stock,
            stock_rotation_deg=part.stock_orientation_deg[2],
            stock_tilt_deg=part.stock_orientation_deg[:2],
        ),
        (0.7, 0.5, 0.25, 1),
    )
    actual = [p for tri in mesh.triangles for p in tri]
    table_shift = viewer.machine_profile.pose(viewer.machine_setup, viewer.machine_setup.work_point((0, 0, 0)), 30)[
        "table"
    ]
    points = [tuple(expected.vertices[i * 10 + a] + table_shift[a] for a in range(3)) for i in expected.indices]
    assert len(actual) == len(points) == len(stock.solid.mesh.triangles_mm) * 3
    for a, e in zip(actual, points):
        assert a == pytest.approx(e)
    original = module.refine_program_surfaces

    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        Path(stock.source_path).write_text("changed while reviewing")
        return result

    monkeypatch.setattr(module, "refine_program_surfaces", changed)
    with pytest.raises(ValueError, match="repeat stock bytes changed"):
        review_program_surfaces(ProgramClearanceSource.capture(program()), {1: snapshot}, {"G54": part.work_offset_mm})


def test_multi_tool_review_shares_only_validated_common_meshes_and_preserves_spindle_stickout():
    source = ProgramClearanceSource.capture(program("T2 M6\nG1 X11"))
    result = review_program_surfaces(source, captures(1, 2), {"G54": (-180, -120, -110)})
    first, second = result.meshes[1], result.meshes[2]
    for name in first:
        if name.startswith("spindle "):
            assert first[name] is not second[name]
            assert second[name].triangles[0][0][2] - first[name].triangles[0][0][2] == 1
        else:
            assert first[name] is second[name]
    assert result.triangles == sum(len(m.triangles) for m in first.values()) + sum(
        len(m.triangles) for n, m in second.items() if n.startswith("spindle ")
    )
    bad = captures(1, 2)
    bad[2] = replace(bad[2], placement=((0, 0, 0), 0, 0))
    with pytest.raises(ValueError, match="share one captured"):
        review_program_surfaces(source, bad, {"G54": (-180, -120, -110)})


def test_solid_work_refusal_keeps_budget_context_and_never_returns_partial_occupancy(monkeypatch):
    import carveracontroller.machine.program_surface_clearance as module
    from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, SolidBudgetExceeded

    monkeypatch.setattr(module, "SolidBudget", lambda **kwargs: SolidBudget(max_nodes=1, **kwargs))
    with pytest.raises(ValueError, match="Solid review exhausted shared nodes budget") as refusal:
        solid_report()
    assert isinstance(refusal.value.__cause__, SolidBudgetExceeded)
    message = str(refusal.value)
    assert "Source line 4 · T1" in message
    assert "carriage" in message and "fixed" in message
    assert "Surface work:" in message and "Solid work: 1 steps" in message
    assert "no partial report" in message
