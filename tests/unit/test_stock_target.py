"""Actual closed-target raster, independent deficits and retained-source controls."""

from dataclasses import replace
from types import MappingProxyType

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.addons.manufacturing_simulation.stock_solid import StockSolid
from carveracontroller.machine.program_stock_evolution import StockEvolutionInput, review_stock_evolution
from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
from carveracontroller.machine.stock_target import analyze_stock_target, prepare_stock_target, target_sections
from tests.unit.test_stock_finishing import compare, finishing_example
from tests.unit.test_stock_solid import box, mesh, reverse, wedge


def prepare(report, path, *, index=0, name=None, **kwargs):
    name = name or next(iter(report.stock_evolution.inputs.stocks))
    state = reconstruct_stock_move(report.body_review, report.stock_evolution, report.rotating_envelopes, name, index)
    target = prepare_stock_target(state, name, str(path), units="mm", **kwargs)
    return target, state


def test_target_classifies_on_exact_stock_grid_without_resampling(tmp_path):
    grid = StockVolume(AABB(Vec3(-1, -1, -1), Vec3(5, 4, 6)), 0.7, rotation_deg=31, tilt_deg=(20, -10))
    solid = StockSolid.validate(mesh(tmp_path, wedge()))
    before = grid.snapshot()
    target = solid.voxelize_grid(grid)
    assert target.shape == grid.shape and target.cell_size == grid.cell_size
    assert (
        target.grid_bounds == grid.grid_bounds and target.orientation == grid.orientation and target.pivot == grid.pivot
    )
    for z in range(grid.shape[2]):
        for y in range(grid.shape[1]):
            for x in range(grid.shape[0]):
                p = grid.grid_center(x, y, z)
                expected = p.x >= 0 and p.y >= 0 and 3 * p.x + 4 * p.y <= 12 and 0 <= p.z <= 5
                assert target.occupied(x, y, z) == expected
    assert grid.snapshot() == before


def test_target_distinguishes_extra_material_and_potential_overcut(tmp_path):
    report = finishing_example()
    # Entire stock is the intended part; neither cutting variant should remove it.
    source = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    target, state = prepare(report, source.source_path)
    result = analyze_stock_target(target, state, compare(report, state=state))
    assert result.target_grid_mm3 == 8
    assert result.fits["Initial stock"].missing_mm3 == 0
    assert result.fits["After selected move"].missing_mm3 == 0
    assert result.fits["Planned continuation"].missing_mm3 == 7.75
    assert result.fits["T2 continuation"].missing_mm3 == 8
    assert all(f.excess_mm3 == 0 for f in result.fits.values())
    assert result.newly_missing_mm3["T2 continuation"] == 8
    assert "not a measured gouge" in result.qualification
    with pytest.raises(TypeError):
        target.target["minimum"] = (0, 0, 0)


def test_small_internal_target_counts_independent_excess_and_missing(tmp_path):
    report = finishing_example(small=True)
    source = mesh(tmp_path, box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5)))
    target, state = prepare(report, source.source_path)
    result = analyze_stock_target(target, state, compare(report, state=state))
    assert result.target_grid_mm3 == 1
    assert result.fits["Initial stock"].retained_target_mm3 == 1
    assert result.fits["Initial stock"].excess_mm3 == 7
    candidate = result.fits["T2 continuation"]
    assert candidate.material_mm3 == 5 and candidate.excess_mm3 == 5 and candidate.missing_mm3 == 1
    assert result.newly_missing_mm3["T2 continuation"] == 1


def test_cavity_and_disconnected_target_preserve_voids_in_sections(tmp_path):
    report = finishing_example()
    triangles = box((-1, -1, 0), (1, 1, 2)) + reverse(box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5)))
    source = mesh(tmp_path, triangles)
    target, state = prepare(report, source.source_path)
    result = analyze_stock_target(target, state)
    assert result.target_grid_mm3 == 7
    assert result.fits["Initial stock"].excess_mm3 == 1
    sections = target_sections(result, "After selected move", "XY", 1)
    assert sum((r - l) * (t - b) for l, b, r, t in sections[0].remaining) == 3
    assert sum((r - l) * (t - b) for l, b, r, t in sections[1].remaining) == 1
    assert sections[2].remaining == ()
    assert all(s.bounds == (-1, -1, 1, 1) for s in sections)
    islands = box((-1, -1, 0), (-0.5, -0.5, 2)) + box((0.5, 0.5, 0), (1, 1, 2))
    source = mesh(tmp_path, islands)
    second, state = prepare(report, source.source_path)
    assert analyze_stock_target(second, state).target_grid_mm3 == 1


def test_existing_missing_stock_is_not_attributed_to_new_cut(tmp_path):
    report = finishing_example()
    source = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    target, state = prepare(report, source.source_path)
    initial = StockVolume.from_snapshot(target.initial)
    initial._occupied[0] = 0
    initial._remaining_count -= 1
    # The original declared imported stock lacks this cell before any move.
    stocks = dict(report.stock_evolution.inputs.stocks)
    stocks[target.stock] = (stocks[target.stock][0], MappingProxyType(initial.snapshot()))
    evolution = review_stock_evolution(
        report.body_review,
        StockEvolutionInput(MappingProxyType(stocks), report.stock_evolution.inputs.tools),
        report.rotating_envelopes,
    )
    report = replace(report, stock_evolution=evolution)
    target, state = prepare(report, source.source_path)
    result = analyze_stock_target(target, state, compare(report, state=state))
    assert result.fits["Initial stock"].missing_mm3 == 0.125
    assert result.newly_missing_mm3["T2 continuation"] == 7.875


@pytest.mark.parametrize("change", ["review", "move", "stock", "grid"])
def test_target_context_and_continuation_mismatch_refuse(tmp_path, change):
    report = finishing_example()
    source = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    target, state = prepare(report, source.source_path)
    comparison = compare(report, state=state)
    if change == "review":
        state = replace(state, bindings=(object(), *state.bindings[1:]))
    elif change == "move":
        comparison = replace(comparison, after_segment=1)
    elif change == "stock":
        comparison = replace(comparison, stock="other stock")
    else:
        snapshot = dict(comparison.candidate.final, rotation_deg=10, pivot_mm=(0, 0, 1), schema=2)
        comparison = replace(comparison, candidate=replace(comparison.candidate, final=snapshot))
    with pytest.raises(ValueError, match="different|differ"):
        analyze_stock_target(target, state, comparison)


@pytest.mark.parametrize("units", ["mm", "inch"])
def test_explicit_units_and_translation_without_auto_centering(tmp_path, units):
    grid = StockVolume(AABB(Vec3(10, 20, 30), Vec3(12, 22, 32)), 0.5)
    scale = 1 if units == "mm" else 25.4
    source = mesh(tmp_path, box((0, 0, 0), (2 / scale, 2 / scale, 2 / scale)), units=units)
    solid = StockSolid.validate(source)
    target = solid.voxelize_grid(grid, translation_mm=(10, 20, 30))
    assert target.remaining_volume_mm3 == 8
    with pytest.raises(ValueError, match="not clipped"):
        solid.voxelize_grid(grid)


@pytest.mark.parametrize("translation", [(float("nan"), 0, 0), (True, 0, 0), (0, 0), (1, 0, 0)])
def test_invalid_or_outside_target_placement_refuses(tmp_path, translation):
    solid = StockSolid.validate(mesh(tmp_path, box()))
    grid = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 2, 2)), 1)
    before = grid.snapshot()
    with pytest.raises(ValueError):
        solid.voxelize_grid(grid, translation_mm=translation)
    assert grid.snapshot() == before


def test_complete_shared_budget_and_cancel_leave_inputs_unchanged(tmp_path):
    report = finishing_example()
    source = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    target, state = prepare(report, source.source_path)
    comparison = compare(report, state=state)
    result = analyze_stock_target(target, state, comparison)
    assert result.cell_work == 256
    assert analyze_stock_target(target, state, comparison, max_cell_work=256).fits == result.fits
    with pytest.raises(ValueError, match="shared cell-work"):
        analyze_stock_target(target, state, comparison, max_cell_work=255)
    with pytest.raises(InterruptedError):
        analyze_stock_target(target, state, comparison, cancelled=lambda: True)
    assert analyze_stock_target(target, state, comparison).fits == result.fits
    solid = StockSolid.validate(source)
    grid = StockVolume.from_snapshot(target.initial)
    with pytest.raises(ValueError, match="work budget"):
        solid.voxelize_grid(grid, max_ray_tests=1)
    with pytest.raises(InterruptedError):
        solid.voxelize_grid(grid, cancelled=lambda: True)


def test_dense_full_two_million_cell_grid_is_complete(tmp_path):
    grid = StockVolume(AABB(Vec3(0, 0, 0), Vec3(100, 100, 200)), 1, max_voxels=2_000_000)
    solid = StockSolid.validate(mesh(tmp_path, box((10, 10, 10), (90, 90, 190))))
    target = solid.voxelize_grid(grid)
    assert target.memory_bytes == 2_000_000 and target.remaining_volume_mm3 == 80 * 80 * 180
    assert target.occupied(10, 10, 10) and target.occupied(89, 89, 189)
    assert not target.occupied(9, 10, 10) and not target.occupied(90, 10, 10)


def test_complete_two_million_cell_four_state_target_analysis(tmp_path):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolType
    from carveracontroller.machine.geometry_changes import capture_context
    from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
    from carveracontroller.machine.program_operations import ProgramOperations
    from carveracontroller.machine.program_surface_clearance import review_program_surfaces
    from carveracontroller.machine.scene_joint_clearance import capture_scene_clearance
    from tests.unit.test_program_stock_evolution import stock_example
    from tests.unit.test_scene_joint_clearance import scene_viewer

    source, offsets, _, original = stock_example(ball=True)
    first = original[1]
    setup = replace(first.setup, stock_size_mm=(5, 5, 10))
    second = replace(first.definition, number=2, tool_type=ToolType.FLAT_END_MILL)
    viewer = scene_viewer()
    viewer.machine_setup = setup
    viewer.library_tool_table_mm = {1: first.definition, 2: second}
    captures = {
        number: capture_scene_clearance(
            first.profile,
            first.components,
            setup,
            first.placement,
            tool,
            number,
            None,
            capture_context(viewer, None, verify_assets=False),
        )
        for number, tool in viewer.library_tool_table_mm.items()
    }
    program = ProgramClearanceSource.capture(ProgramOperations.from_text(source.text + "\nT2 M6\nG0 X0\nG1 X1 F100"))
    report = review_program_surfaces(program, captures, offsets, grouped=True, stock_resolution_mm=0.05)
    source = mesh(tmp_path, box((0, 0, 4), (3, 3, 9)))
    target, state = prepare(report, source.source_path)
    comparison = compare(report, state=state, end=report.body_review.end_line)
    result = analyze_stock_target(target, state, comparison)
    assert result.cell_work == 8_000_000 and result.target_grid_mm3 == pytest.approx(45)
    assert all(f.missing_mm3 == 0 and f.retained_target_mm3 == result.target_grid_mm3 for f in result.fits.values())
    assert result.fits["Initial stock"].excess_mm3 == pytest.approx(205)
    assert result.fits["Planned continuation"].excess_mm3 == pytest.approx(
        comparison.planned.remaining_mm3 - result.target_grid_mm3
    )
    assert result.fits["T2 continuation"].excess_mm3 == pytest.approx(
        comparison.candidate.remaining_mm3 - result.target_grid_mm3
    )
    with pytest.raises(ValueError, match="complete shared"):
        analyze_stock_target(target, state, comparison, max_cell_work=7_999_999)
