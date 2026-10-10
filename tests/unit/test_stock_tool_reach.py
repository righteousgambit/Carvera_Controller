"""Complete candidate access, analytic obstacles and source/limit controls."""

from dataclasses import replace
from types import MappingProxyType, SimpleNamespace

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import ToolGeometry
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, StockSolid
from carveracontroller.machine.stock_target import StockTarget, TargetAnalysis, TargetFit
from carveracontroller.machine.stock_tool_reach import review_tool_reach
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_solid import box, mesh


def analytic(tmp_path, *, target_triangles=None, short=False, holder=True, shape="flat"):
    grid = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 2, 2)), 1)
    solid = StockSolid.validate(mesh(tmp_path, target_triangles or box((0.05, 0.05, 0.05), (0.1, 0.1, 0.1))))
    target = solid.voxelize_grid(grid)
    target_snapshot = MappingProxyType(target.snapshot())
    empty = grid.clone()
    empty._occupied = bytearray(8)
    empty._initial_count = empty._remaining_count = 0
    missing = MappingProxyType(empty.snapshot())
    small = ToolGeometry(0.2, 0.4 if short else 3, 0.2, 4, 0.5 if holder else 0, 1 if holder else 0, shape)
    large = ToolGeometry(1, 3, 1, 4, 1.5, 1, shape)
    evolution = SimpleNamespace(inputs=SimpleNamespace(tools={1: small, 2: large}))
    declared = StockTarget(
        (object(), evolution, object()),
        "analytic stock",
        solid.mesh.source_path,
        solid.mesh.source_sha256,
        "mm",
        (0, 0, 0),
        8,
        solid,
        target_snapshot,
        MappingProxyType(grid.snapshot()),
    )
    fits = {}
    for name, removed in (("Initial stock", False), ("After selected move", False), ("Candidate", True)):
        extra = target.clone()
        extra._occupied = bytearray(8) if removed else bytearray(not v for v in target._occupied)
        extra._remaining_count = extra._initial_count = sum(extra._occupied)
        fits[name] = TargetFit(
            grid.remaining_volume_mm3 if not removed else target.remaining_volume_mm3,
            target.remaining_volume_mm3,
            extra.remaining_volume_mm3,
            0,
            MappingProxyType(extra.snapshot()),
            missing,
        )
    return TargetAnalysis(declared, 0, 1, target.remaining_volume_mm3, MappingProxyType(fits), MappingProxyType({}), 24)


def test_all_states_all_cells_and_shared_exact_queries(tmp_path):
    analysis = analytic(tmp_path)
    phases = []
    result = review_tool_reach(analysis, progress=lambda *row: phases.append(row))
    assert result.tools == (1, 2) and result.logical_outcomes == 32 and result.unique_queries == 16
    assert len(result.states["Initial stock"][1]) == len(result.states["After selected move"][2]) == 8
    assert result.states["Candidate"][1] == result.states["Candidate"][2] == ()
    for tool in (1, 2):
        for index, outcome in enumerate(result.states["Initial stock"][tool]):
            assert outcome.status == "No detected target/stock obstacle"
            assert outcome.query.cell == (index % 2, index // 2 % 2, index // 4)
            assert outcome.query.start_program_mm[2] == 3
            assert outcome.query is result.states["After selected move"][tool][index].query
    assert phases[-1] == ("Complete candidate-tool access", 32, 32)
    with pytest.raises(TypeError):
        result.states["forged"] = result.states["Initial stock"]
    with pytest.raises(TypeError):
        result.states["Initial stock"][1] = ()


def test_unobstructed_missing_holder_is_not_complete_access(tmp_path):
    result = review_tool_reach(analytic(tmp_path, holder=False), [1])
    assert all(o.status == "Incomplete declaration" for o in result.states["Initial stock"][1])
    assert all(o.query.declaration_gaps == ("No holder geometry declared",) for o in result.states["Initial stock"][1])


def test_short_flutes_show_remaining_stock_shank_limit(tmp_path):
    result = review_tool_reach(analytic(tmp_path, short=True), [1])
    assert all(
        o.status == "Stock body estimate" and "shank" in o.limiting_components
        for o in result.states["Initial stock"][1]
    )
    assert all(o.stock_contacts[0].first_fraction is not None for o in result.states["Initial stock"][1])


def test_target_between_endpoints_blocks_large_but_not_small_tool(tmp_path):
    # A thin elevated ledge crosses only the large tool's swept radius.
    analysis = analytic(tmp_path, target_triangles=box((0.85, 0.4, 1.8), (0.95, 0.6, 1.9)))
    result = review_tool_reach(analysis)
    small, large = (result.states["Initial stock"][n][0] for n in (1, 2))
    assert small.query.start_program_mm[2] == 3
    assert not small.query.target_contacts
    assert large.status == "Target obstacle" and large.query.target_contacts
    assert all(c.component == "cutter" and 0 <= c.witness.sample <= 1 for c in large.query.target_contacts)
    assert large.query.target_contacts[0].witness.sample.denominator > 0


def test_shaped_profile_chords_match_independent_selected_cell_inspection(tmp_path):
    from carveracontroller.machine.stock_allowance import inspect_target_cell

    _, analysis = example(tmp_path, cavity=True)
    study = review_tool_reach(analysis, [1, 2])
    for tool, rows in study.states["Initial stock"].items():
        for row in rows:
            original = inspect_target_cell(analysis, "Initial stock", row.query.cell, tool=tool).approach
            assert set(row.query.target_contacts) == set(original.target_contacts)
            assert row.stock_contacts == original.stock_contacts
    assert study.logical_outcomes == sum(len(rows) for state in study.states.values() for rows in state.values())


def test_source_retention_cancellation_and_exact_shared_limits(tmp_path):
    analysis = analytic(tmp_path)
    initial = analysis.target.initial
    result = review_tool_reach(analysis)
    assert (
        review_tool_reach(
            analysis,
            max_cell_work=result.cell_work,
            max_outcomes=result.logical_outcomes,
            max_nodes=result.target_nodes,
        ).states
        == result.states
    )
    for kwargs in (
        {"max_cell_work": result.cell_work - 1},
        {"max_outcomes": result.logical_outcomes - 1},
        {"max_nodes": result.target_nodes - 1},
    ):
        with pytest.raises(ValueError, match="budget"):
            review_tool_reach(analysis, **kwargs)
    calls = [0]

    def cancelled():
        calls[0] += 1
        return calls[0] > 75

    with pytest.raises(InterruptedError):
        review_tool_reach(analysis, cancelled=cancelled)
    assert initial == analysis.target.initial
    budget = SolidBudget(cancelled=lambda: False)
    prior = budget.cancelled
    review_tool_reach(analysis, solid_budget=budget)
    assert budget.cancelled is prior


@pytest.mark.parametrize(
    "options",
    [
        {"tools": [1, 1]},
        {"tools": [True]},
        {"tools": [7]},
        {"tools": []},
        {"clearance_mm": float("nan")},
        {"clearance_mm": True},
        {"max_cell_work": 50000001},
        {"max_faces": 0},
        {"max_contacts": True},
    ],
)
def test_invalid_choices_never_return_partial_study(tmp_path, options):
    with pytest.raises(ValueError):
        review_tool_reach(analytic(tmp_path), **options)


def test_inconsistent_grid_or_membership_refuses_complete_study(tmp_path):
    analysis = analytic(tmp_path)
    fit = analysis.fits["Initial stock"]
    for change in (dict(fit.excess, minimum=(-1, 0, 0)), fit.missing):
        wrong = replace(analysis, fits=MappingProxyType({"Initial stock": replace(fit, excess=change)}))
        with pytest.raises(ValueError):
            review_tool_reach(wrong)


def test_dense_full_grid_with_no_excess_has_no_fake_query(tmp_path):
    source = mesh(tmp_path, box((0, 0, 0), (100, 100, 200)))
    solid = StockSolid.validate(source)
    grid = StockVolume(AABB(Vec3(0, 0, 0), Vec3(100, 100, 200)), 1, max_voxels=2000000)
    empty = grid.clone()
    empty._occupied = bytearray(2000000)
    empty._initial_count = empty._remaining_count = 0
    snapshot, zero = MappingProxyType(grid.snapshot()), MappingProxyType(empty.snapshot())
    evolution = SimpleNamespace(inputs=SimpleNamespace(tools={1: ToolGeometry(1, 3, 1, 5, 2, 1)}))
    target = StockTarget(
        (object(), evolution, object()),
        "dense grid",
        source.source_path,
        source.source_sha256,
        "mm",
        (0, 0, 0),
        2000000,
        solid,
        snapshot,
        snapshot,
    )
    fit = TargetFit(2000000, 2000000, 0, 0, zero, zero)
    analysis = TargetAnalysis(
        target, 0, 1, 2000000, MappingProxyType({"Initial": fit, "Current": fit}), MappingProxyType({}), 4000000
    )
    result = review_tool_reach(analysis)
    assert result.cell_work == 4000000 and result.logical_outcomes == result.unique_queries == result.target_faces == 0
    assert all(rows[1] == () for rows in result.states.values())


def test_tilt_rotation_inch_target_and_all_cell_centers(tmp_path):
    from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
    from carveracontroller.machine.stock_target import analyze_stock_target, prepare_stock_target
    from tests.unit.test_program_stock_evolution import stock_example

    _, _, report, _ = stock_example(ball=True, rotation=31, tilt=(20, -10))
    history = report.stock_evolution
    name = next(iter(history.inputs.stocks))
    state = reconstruct_stock_move(report.body_review, history, report.rotating_envelopes, name, 0)
    source = mesh(tmp_path, box((0, 0, 0), (1 / 25.4, 1 / 25.4, 1 / 25.4)), units="inch")
    target = prepare_stock_target(state, name, source.source_path, units="inch", translation_mm=(-0.5, -0.5, 0.5))
    analysis = analyze_stock_target(target, state)
    result = review_tool_reach(analysis)
    grid = StockVolume.from_snapshot(target.target)
    for state in result.states.values():
        for row in state[1]:
            assert row.query.end_program_mm == grid.center(*row.query.cell).tuple
            assert row.query.start_program_mm[:2] == row.query.end_program_mm[:2]
            assert row.query.start_program_mm[2] > grid.bounds.maximum.z
    assert result.logical_outcomes == 112 and result.unique_queries == 56


def test_exact_face_contact_and_solid_budget_limits_refuse(tmp_path):
    analysis = analytic(tmp_path, target_triangles=box((0.85, 0.4, 1.8), (0.95, 0.6, 1.9)))
    result = review_tool_reach(analysis, [2])
    assert result.target_faces > 1 and result.contact_records > 1
    assert (
        review_tool_reach(analysis, [2], max_faces=result.target_faces, max_contacts=result.contact_records).states
        == result.states
    )
    for options in (
        {"max_faces": result.target_faces - 1},
        {"max_contacts": result.contact_records - 1},
        {"solid_budget": SolidBudget(max_nodes=1)},
    ):
        with pytest.raises(ValueError, match="budget"):
            review_tool_reach(analysis, [2], **options)


@pytest.mark.parametrize("field", ["material_mm3", "excess_mm3", "missing_mm3", "retained_target_mm3"])
def test_forged_volume_never_appears_as_completed_study(tmp_path, field):
    analysis = analytic(tmp_path)
    fit = analysis.fits["Initial stock"]
    forged = replace(
        analysis, fits=MappingProxyType({"Initial stock": replace(fit, **{field: getattr(fit, field) + 1})})
    )
    with pytest.raises(ValueError, match="volumes"):
        review_tool_reach(forged)
