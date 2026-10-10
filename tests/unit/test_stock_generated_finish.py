"""Independent continuous height bounds, generated layers and complete replay."""

from dataclasses import replace
from fractions import Fraction as F
from types import MappingProxyType, SimpleNamespace

import pytest

from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.machine.stock_generated_finish import HeightBudget, generate_stock_finish, upper_surface
from carveracontroller.machine.surface_motion import SurfaceMesh
from tests.unit.test_stock_solid import box
from tests.unit.test_stock_tool_reach import analytic


def example(tmp_path, **kwargs):
    analysis = analytic(tmp_path, target_triangles=box((0.25, 0.25, 0.25), (1.75, 1.75, 1)), **kwargs)
    a, evolution, b = analysis.target.bindings
    inputs = SimpleNamespace(
        tools=evolution.inputs.tools, stocks={analysis.target.stock: ((10, -20, 30), analysis.target.initial)}
    )
    return replace(analysis, target=replace(analysis.target, bindings=(a, SimpleNamespace(inputs=inputs), b)))


def test_exact_clipping_finds_interior_maximum_instead_of_whole_triangle_vertex():
    triangle = ((0, 0, 0), (2, 0, 2), (0, 2, 0))
    mesh = SurfaceMesh.create([triangle])
    rectangle = (F(1, 4), F(1, 4), F(3, 4), F(3, 4))
    result = upper_surface(mesh, rectangle, HeightBudget())
    assert result.point[2] == F(3, 4) and result.point[0] == F(3, 4)
    assert sum(result.barycentric) == 1 and min(result.barycentric) >= 0
    assert result.point == tuple(sum(F(triangle[j][i]) * result.barycentric[j] for j in range(3)) for i in range(3))


def test_vertical_faces_boundary_contact_and_narrow_features_are_retained():
    triangles = [((0, 0, 0), (0, 1, 3), (0, 2, 0)), ((0.49, 0.49, 2), (0.51, 0.49, 2), (0.5, 0.51, 2))]
    mesh = SurfaceMesh.create(triangles)
    hit = upper_surface(mesh, (F(0), F(3, 4), F(0), F(5, 4)), HeightBudget())
    assert hit.point[2] == 3 and hit.triangle == 0
    hit = upper_surface(mesh, (F(1, 4), F(1, 4), F(3, 4), F(3, 4)), HeightBudget())
    assert hit.point[2] == 2 and hit.triangle == 1
    assert upper_surface(mesh, (F(3), F(3), F(4), F(4)), HeightBudget()) is None


def test_complete_layered_raster_conserves_material_and_preserves_inputs(tmp_path):
    analysis = example(tmp_path)
    before = analysis.target.initial, analysis.fits
    phases = []
    plan = generate_stock_finish(analysis, 2, progress=lambda *p: phases.append(p))
    assert len(plan.patches) == 8 and len(plan.moves) == 128
    assert len(plan.states) == 3 and not plan.target_contacts and not plan.declaration_gaps
    assert plan.clearance_z_mm > 3 and all(p.witness.point[2] == 1 for p in plan.patches)
    for label in ("Initial stock", "After selected move"):
        state = plan.states[label]
        assert state.removed_mm3 == 4 and state.after.material_mm3 == 4
        assert state.after.retained_target_mm3 == state.before.retained_target_mm3 == 4
        assert state.after.missing_mm3 == state.newly_missing_mm3 == 0
        assert all(c.contact.component == "cutter" and not plan.moves[c.move].cutting for c in state.contacts)
    assert plan.states["Candidate"].removed_mm3 == 0
    assert before == (analysis.target.initial, analysis.fits)
    assert phases[-1] == ("Complete generated finishing comparison", 384, 384)
    for at in range(0, len(plan.moves), 4):
        transfer, plunge, cut, retract = plan.moves[at : at + 4]
        assert not transfer.cutting and not retract.cutting and plunge.cutting and cut.cutting
        assert transfer.end == plunge.start and plunge.end == cut.start and cut.end == retract.start
        assert transfer.start[2] == transfer.end[2] == retract.end[2] == plan.clearance_z_mm
        patch = plan.patches[cut.patch]
        assert cut.start[2] == cut.end[2] >= patch.tip_z_mm > float(patch.witness.point[2]) + plan.allowance_mm
    with pytest.raises(TypeError):
        plan.states["forged"] = plan.states["Candidate"]


def test_different_tool_geometry_changes_footprint_and_final_material(tmp_path):
    analysis = example(tmp_path)
    small = generate_stock_finish(analysis, 1, stepover_mm=0.2)
    large = generate_stock_finish(analysis, 2)
    assert len(small.patches) > len(large.patches)
    assert small.patches[0].rectangle != large.patches[0].rectangle
    assert small.states["Initial stock"].removed_mm3 == 4


def test_short_flute_contact_recorded_before_cut_and_missing_holder_stays_unknown(tmp_path):
    analysis = example(tmp_path, short=True, holder=False)
    plan = generate_stock_finish(analysis, 1, stepover_mm=0.2)
    assert plan.declaration_gaps == ("No holder geometry declared",)
    contacts = plan.states["Initial stock"].contacts
    assert contacts and all(c.contact.component != "cutter" or not plan.moves[c.move].cutting for c in contacts)
    assert any(c.contact.component == "shank" for c in contacts)
    assert plan.states["Initial stock"].removed_mm3 == 4
    assert "do not silently suppress" in plan.qualification


def test_allowance_can_above_stock_and_clearance_still_contains_all_paths(tmp_path):
    plan = generate_stock_finish(example(tmp_path), 2, allowance_mm=10)
    assert plan.clearance_z_mm > 12
    assert all(m.start[2] <= plan.clearance_z_mm and m.end[2] <= plan.clearance_z_mm for m in plan.moves)
    assert all(s.removed_mm3 == 0 for s in plan.states.values())


def test_every_shared_limit_admits_at_threshold_and_refuses_below(tmp_path):
    analysis = example(tmp_path)
    plan = generate_stock_finish(analysis, 2)
    exact = {
        "max_patches": len(plan.patches),
        "max_moves": len(plan.moves),
        "max_cell_work": plan.cell_work,
        "max_nodes": plan.target_nodes,
        "max_faces": plan.target_faces,
    }
    assert generate_stock_finish(analysis, 2, **exact).moves == plan.moves
    for name, value in exact.items():
        with pytest.raises(ValueError, match="budget"):
            generate_stock_finish(analysis, 2, **{name: value - 1})


@pytest.mark.parametrize(
    "options",
    [
        {"tool": True},
        {"tool": 9},
        {"stepover_mm": 1.01},
        {"patch_length_mm": float("nan")},
        {"allowance_mm": -1},
        {"stepdown_mm": 3.01},
        {"clearance_mm": 0},
        {"max_moves": True},
        {"max_contacts": 100001},
        {"max_nodes": 0},
        {"max_faces": 250001},
    ],
)
def test_invalid_inputs_refuse_without_partial_output(tmp_path, options):
    args = {"tool": 2}
    args.update(options)
    with pytest.raises(ValueError):
        generate_stock_finish(example(tmp_path), **args)


def test_nonflat_tools_and_corrupt_material_declarations_refuse(tmp_path):
    with pytest.raises(ValueError, match="flat mill"):
        generate_stock_finish(example(tmp_path, shape="ball"), 2)
    analysis = example(tmp_path)
    fit = analysis.fits["Initial stock"]
    for corrupt in (replace(fit, material_mm3=7), replace(fit, excess=fit.missing)):
        wrong = replace(analysis, fits=MappingProxyType({"Initial stock": corrupt}))
        with pytest.raises(ValueError, match="volumes"):
            generate_stock_finish(wrong, 2)


def test_cancel_during_geometry_and_replay_never_mutates_retained_state(tmp_path):
    analysis = example(tmp_path)
    original = analysis.target.initial
    for selected_phase in ("Generate continuous target-envelope patches", "Replay Initial stock"):
        stop = [False]

        def progress(name, done, total, stop=stop, selected_phase=selected_phase):
            stop[0] = name == selected_phase

        with pytest.raises(InterruptedError):
            generate_stock_finish(analysis, 2, cancelled=lambda stop=stop: stop[0], progress=progress)
    assert analysis.target.initial == original


def holder_example(tmp_path):
    analysis = analytic(
        tmp_path, target_triangles=box((0.25, 0.25, 0.25), (1.75, 1.75, 1)) + box((1.9, 0.5, 1.2), (2, 0.75, 1.8))
    )
    a, old, b = analysis.target.bindings
    tool = replace(
        old.inputs.tools[1], flute_length_mm=0.4, overall_length_mm=0.5, holder_diameter_mm=2, holder_length_mm=1
    )
    inputs = SimpleNamespace(tools={1: tool}, stocks={analysis.target.stock: ((0, 0, 0), analysis.target.initial)})
    return replace(analysis, target=replace(analysis.target, bindings=(a, SimpleNamespace(inputs=inputs), b)))


def test_complete_target_holder_contact_is_retained_on_generated_moves(tmp_path):
    analysis = holder_example(tmp_path)
    plan = generate_stock_finish(analysis, 1, stepover_mm=0.2)
    assert plan.target_contacts and any(r.contact.component == "holder" for r in plan.target_contacts)
    assert all(0 <= r.move < len(plan.moves) for r in plan.target_contacts)
    assert all(0 <= r.contact.witness.sample <= 1 for r in plan.target_contacts if hasattr(r.contact, "witness"))
    contacts = len(plan.target_contacts) + sum(len(s.contacts) for s in plan.states.values())
    assert (
        generate_stock_finish(analysis, 1, stepover_mm=0.2, max_contacts=contacts).target_contacts
        == plan.target_contacts
    )
    with pytest.raises(ValueError, match="contact budget"):
        generate_stock_finish(analysis, 1, stepover_mm=0.2, max_contacts=contacts - 1)


def test_retained_target_center_loss_refuses_whole_plan_even_if_other_checks_pass(tmp_path, monkeypatch):
    from carveracontroller.addons.manufacturing_simulation import StockVolume, Vec3

    analysis = example(tmp_path)
    original = analysis.target.initial

    def broken_removal(self, sweep, **kwargs):
        self._occupied = bytearray(len(self._occupied))
        self._remaining_count = 0

    monkeypatch.setattr(StockVolume, "subtract", broken_removal)
    with pytest.raises(ValueError, match="removed retained target centers"):
        generate_stock_finish(analysis, 2)
    assert analysis.target.initial == original


def test_explicit_inch_target_rotated_grid_and_retained_offset_are_not_recentred(tmp_path):
    from carveracontroller.addons.manufacturing_simulation import StockVolume
    from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
    from carveracontroller.machine.stock_target import analyze_stock_target, prepare_stock_target
    from tests.unit.test_program_stock_evolution import stock_example
    from tests.unit.test_stock_solid import mesh

    _, _, report, _ = stock_example(rotation=31, tilt=(20, -10))
    name = next(iter(report.stock_evolution.inputs.stocks))
    state = reconstruct_stock_move(report.body_review, report.stock_evolution, report.rotating_envelopes, name, 0)
    source = mesh(tmp_path, box((0, 0, 0), (1 / 25.4, 1 / 25.4, 1 / 25.4)), units="inch")
    target = prepare_stock_target(state, name, source.source_path, units="inch", translation_mm=(-0.5, -0.5, 0.5))
    plan = generate_stock_finish(analyze_stock_target(target, state), 1)
    assert plan.stock_offset_mm == report.stock_evolution.inputs.stocks[name][0]
    grid = StockVolume.from_snapshot(target.target)
    placed = [
        grid.program_point(Vec3(*p) + Vec3(*target.translation_mm)).tuple
        for row in target.solid.mesh.triangles_mm
        for p in row
    ]
    assert plan.patches[0].start_xy == (min(p[0] for p in placed), min(p[1] for p in placed))
    assert plan.patches[-1].end_xy[1] == max(p[1] for p in placed)


def test_disconnected_target_gaps_are_skipped_without_invented_surface(tmp_path):
    analysis = analytic(
        tmp_path, target_triangles=box((0.1, 0.1, 0.2), (0.3, 0.3, 0.6)) + box((1.7, 0.1, 0.2), (1.9, 0.3, 0.8))
    )
    a, old, b = analysis.target.bindings
    inputs = SimpleNamespace(
        tools=old.inputs.tools, stocks={analysis.target.stock: ((0, 0, 0), analysis.target.initial)}
    )
    analysis = replace(analysis, target=replace(analysis.target, bindings=(a, SimpleNamespace(inputs=inputs), b)))
    plan = generate_stock_finish(analysis, 1, stepover_mm=0.2, patch_length_mm=0.2)
    assert any(p.witness is None and p.tip_z_mm is None for p in plan.patches)
    assert all(plan.patches[m.patch].witness is not None for m in plan.moves)
