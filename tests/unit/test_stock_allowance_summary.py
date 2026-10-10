"""Independent closed-box/cavity extrema, full masks and shared work admission."""

import math
from dataclasses import replace
from fractions import Fraction as F
from types import MappingProxyType

import pytest

from carveracontroller.addons.manufacturing_simulation import StockVolume
from carveracontroller.machine.stock_allowance_summary import summarize_target_allowance
from carveracontroller.machine.stock_target import analyze_stock_target
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_finishing import finishing_example
from tests.unit.test_stock_solid import box, mesh
from tests.unit.test_stock_target import prepare


def test_all_state_extrema_match_independent_box_distances(tmp_path):
    _, analysis = example(tmp_path)
    result = summarize_target_allowance(analysis)
    assert result.cell_work == 256 and result.center_queries == 64
    grid = StockVolume.from_snapshot(analysis.target.target)
    for label, fit in analysis.fits.items():
        state = result.states[label]
        for mask, count, peak, sign in (
            (fit.excess, state.excess_centers, state.excess_peak, 1),
            (fit.missing, state.missing_centers, state.missing_peak, -1),
        ):
            volume = StockVolume.from_snapshot(mask)
            oracle = []
            for z in range(4):
                for y in range(4):
                    for x in range(4):
                        if not volume.occupied(x, y, z):
                            continue
                        p = grid.grid_center(x, y, z).tuple
                        outside = [
                            max(low - v, 0, v - high) for v, low, high in zip(p, (-0.5, -0.5, 0.5), (0.5, 0.5, 1.5))
                        ]
                        squared = (
                            sum(F(v) ** 2 for v in outside)
                            if sign > 0
                            else min(F(v - low) ** 2 for v, low in zip(p, (-0.5, -0.5, 0.5)))
                        )
                        if sign < 0:
                            squared = min(squared, *(F(high - v) ** 2 for v, high in zip(p, (0.5, 0.5, 1.5))))
                        oracle.append((squared, (x, y, z)))
            assert count == len(oracle)
            if not oracle:
                assert peak is None
            else:
                maximum = max(row[0] for row in oracle)
                expected = next(cell for squared, cell in oracle if squared == maximum)
                assert peak.cell == expected and peak.nearest.distance_squared == maximum
                assert peak.signed_center_distance_mm == pytest.approx(sign * math.sqrt(float(maximum)))
    assert result.states["Initial stock"].excess_peak.cell == (0, 0, 0)
    assert result.states["Initial stock"].excess_peak.nearest.distance_squared == F(3, 16)
    assert result.states["T2 continuation"].missing_peak.signed_center_distance_mm == -0.25
    with pytest.raises(TypeError):
        result.states["forged"] = result.states["Initial stock"]


def test_cavity_true_distances_and_empty_categories(tmp_path):
    _, analysis = example(tmp_path, cavity=True)
    result = summarize_target_allowance(analysis)
    assert result.states["Initial stock"].excess_centers == 8
    assert result.states["Initial stock"].excess_peak.nearest.distance_squared == F(1, 16)
    assert result.states["Initial stock"].missing_peak is None
    report = finishing_example()
    source = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    target, state = prepare(report, source.source_path)
    result = summarize_target_allowance(analyze_stock_target(target, state))
    assert result.center_queries == result.distance_faces == result.distance_nodes == 0
    assert all(s.excess_peak is None and s.missing_peak is None for s in result.states.values())


def test_shared_queries_and_exact_budget_thresholds(tmp_path):
    _, analysis = example(tmp_path)
    observations = []
    result = summarize_target_allowance(analysis, progress=lambda *row: observations.append(row))
    assert observations[0] == (0, 256, 0) and observations[-1] == (256, 256, 64)
    assert (
        summarize_target_allowance(
            analysis, max_nodes=result.distance_nodes, max_faces=result.distance_faces, max_cell_work=result.cell_work
        ).states
        == result.states
    )
    for kwargs in (
        {"max_nodes": result.distance_nodes - 1},
        {"max_faces": result.distance_faces - 1},
        {"max_cell_work": 255},
    ):
        with pytest.raises(ValueError, match="budget"):
            summarize_target_allowance(analysis, **kwargs)
    for kwargs in ({"max_nodes": True}, {"max_faces": 50000001}, {"max_cell_work": 8000001}):
        with pytest.raises(ValueError):
            summarize_target_allowance(analysis, **kwargs)


def test_mid_query_cancel_and_retained_sources_unchanged(tmp_path):
    _, analysis = example(tmp_path)
    before = analysis.target.target
    calls = [0]

    def cancelled():
        calls[0] += 1
        return calls[0] > 100

    with pytest.raises(InterruptedError):
        summarize_target_allowance(analysis, cancelled=cancelled)
    assert analysis.target.target == before
    result = summarize_target_allowance(analysis)
    mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    assert summarize_target_allowance(analysis).states == result.states


def test_corrupted_grid_and_membership_masks_refuse(tmp_path):
    _, analysis = example(tmp_path)
    fit = analysis.fits["Initial stock"]
    wrong = dict(fit.excess, minimum=(-2, -1, 0))
    changed = replace(analysis, fits=MappingProxyType({"Initial stock": replace(fit, excess=wrong)}))
    with pytest.raises(ValueError):
        summarize_target_allowance(changed)
    missing = StockVolume.from_snapshot(fit.missing)
    missing._occupied[0] = 1
    missing._remaining_count = missing._initial_count = 1
    changed = replace(analysis, fits=MappingProxyType({"Initial stock": replace(fit, missing=missing.snapshot())}))
    with pytest.raises(ValueError, match="overlap"):
        summarize_target_allowance(changed)


def test_full_two_million_cell_masks_without_false_peaks(tmp_path):
    from carveracontroller.addons.manufacturing_simulation import AABB, Vec3
    from carveracontroller.addons.manufacturing_simulation.stock_solid import StockSolid
    from carveracontroller.machine.stock_target import StockTarget, TargetAnalysis, TargetFit

    # A detached complete-grid control tests capacity/iteration, not machine registration.
    solid = StockSolid.validate(mesh(tmp_path, box((0, 0, 0), (100, 100, 200))))
    grid = StockVolume(AABB(Vec3(0, 0, 0), Vec3(100, 100, 200)), 1, max_voxels=2000000)
    empty = grid.clone()
    empty._occupied = bytearray(2000000)
    empty._remaining_count = empty._initial_count = 0
    snapshot = MappingProxyType(grid.snapshot())
    target = StockTarget(
        (object(), object(), object()),
        "synthetic full grid",
        solid.mesh.source_path,
        solid.mesh.source_sha256,
        "mm",
        (0, 0, 0),
        2000000,
        solid,
        snapshot,
        snapshot,
    )
    fit = TargetFit(2000000, 2000000, 0, 0, MappingProxyType(empty.snapshot()), MappingProxyType(empty.snapshot()))
    analysis = TargetAnalysis(
        target,
        0,
        1,
        2000000,
        MappingProxyType({"Initial stock": fit, "After selected move": fit}),
        MappingProxyType({}),
        4000000,
    )
    result = summarize_target_allowance(analysis)
    assert result.cell_work == 4000000 and result.center_queries == 0
    assert all(
        state.excess_centers == state.missing_centers == 0 and state.excess_peak is None and state.missing_peak is None
        for state in result.states.values()
    )
    with pytest.raises(ValueError, match="cell-work"):
        summarize_target_allowance(analysis, max_cell_work=3999999)
