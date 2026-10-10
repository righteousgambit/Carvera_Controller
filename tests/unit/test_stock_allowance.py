"""Retained closed-target distance, source identity and target-only approach."""

import math

import pytest

from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_stock_evolution import evolution_record
from carveracontroller.machine.stock_allowance import inspect_target_cell
from carveracontroller.machine.stock_target import analyze_stock_target
from carveracontroller.machine.surface_distance import DistanceBudget
from tests.unit.test_stock_finishing import compare, finishing_example
from tests.unit.test_stock_solid import box, mesh, reverse
from tests.unit.test_stock_target import prepare


def example(tmp_path, *, short=False, cavity=False):
    report = finishing_example(small=True, short=short)
    triangles = (
        box((-1, -1, 0), (1, 1, 2)) + reverse(box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5)))
        if cavity
        else box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5))
    )
    source = mesh(tmp_path, triangles)
    target, state = prepare(report, source.source_path)
    return report, analyze_stock_target(target, state, compare(report, state=state))


@pytest.mark.parametrize(
    "cell,category,distance",
    [
        ((0, 1, 1), "excess stock", 0.25),
        ((1, 1, 1), "retained target", -0.25),
        ((0, 0, 0), "excess stock", math.sqrt(3) / 4),
    ],
)
def test_exact_box_surface_and_cell_uncertainty(tmp_path, cell, category, distance):
    report, analysis = example(tmp_path)
    prior = encoded(evolution_record(report.stock_evolution))
    hit = inspect_target_cell(analysis, "Initial stock", cell)
    assert hit.category == category and hit.signed_distance_mm == pytest.approx(distance)
    assert hit.half_diagonal_mm == pytest.approx(math.sqrt(3) / 4)
    assert hit.cell_distance_interval_mm == pytest.approx((distance - math.sqrt(3) / 4, distance + math.sqrt(3) / 4))
    assert hit.approach is None and prior == encoded(evolution_record(report.stock_evolution))


def test_missing_target_and_source_byte_retention(tmp_path):
    _, analysis = example(tmp_path)
    prior = inspect_target_cell(analysis, "Initial stock", (1, 1, 1))
    mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)))
    assert inspect_target_cell(analysis, "Initial stock", (1, 1, 1)) == prior
    assert inspect_target_cell(analysis, "T2 continuation", (1, 1, 1)).category == "missing target"


def test_true_cavity_surface_instead_of_occupied_cell_box(tmp_path):
    _, analysis = example(tmp_path, cavity=True)
    hit = inspect_target_cell(analysis, "Initial stock", (1, 1, 1))
    assert hit.category == "excess stock" and hit.signed_distance_mm == 0.25
    assert all(abs(float(v)) <= 1.5 for v in hit.nearest.point)


def test_target_contacts_complete_and_noncutting_stock_estimates(tmp_path):
    report, analysis = example(tmp_path, short=True)
    hit = inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2)
    approach = hit.approach
    assert approach.start[2] == 3 and approach.end == (-0.25, -0.25, 0.25)
    assert approach.target_contacts and any(c.component == "shank" for c in approach.target_contacts)
    assert approach.stock_contacts and all(c.component != "cutter" for c in approach.stock_contacts)
    assert any("holder" in note for note in approach.coverage)
    assert "not a finishing toolpath" in approach.qualification
    assert all(0 <= c.witness.sample <= 1 and 0 <= c.triangle < 12 for c in approach.target_contacts)
    before = analysis.target.initial
    assert inspect_target_cell(analysis, "Initial stock", (1, 1, 0), tool=2).approach == approach
    assert analysis.target.initial == before


@pytest.mark.parametrize("change", ["index", "bool", "tool", "clearance", "nodes", "faces", "cancel", "distance"])
def test_refusals_never_return_partial_cell_result(tmp_path, change):
    _, analysis = example(tmp_path)
    args = {"tool": 2}
    cell = (0, 0, 0)
    if change == "index":
        cell = (4, 0, 0)
    elif change == "bool":
        cell = (True, 0, 0)
    elif change == "tool":
        args["tool"] = 9
    elif change == "clearance":
        args["approach_clearance_mm"] = float("nan")
    elif change == "nodes":
        args["max_nodes"] = 1
    elif change == "faces":
        args["max_faces"] = 1
    elif change == "cancel":
        args["cancelled"] = lambda: True
    elif change == "distance":
        args["distance_budget"] = DistanceBudget(max_triangles=1)
    with pytest.raises((ValueError, InterruptedError)):
        inspect_target_cell(analysis, "Initial stock", cell, **args)


def test_explicit_inch_translation_and_tilted_program_insertion(tmp_path):
    from carveracontroller.addons.manufacturing_simulation import StockVolume
    from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
    from carveracontroller.machine.stock_target import prepare_stock_target
    from tests.unit.test_program_stock_evolution import stock_example

    _, _, report, _ = stock_example(ball=True, rotation=31, tilt=(20, -10))
    name = next(iter(report.stock_evolution.inputs.stocks))
    state = reconstruct_stock_move(report.body_review, report.stock_evolution, report.rotating_envelopes, name, 0)
    source = mesh(tmp_path, box((0, 0, 0), (1 / 25.4, 1 / 25.4, 1 / 25.4)), units="inch")
    target = prepare_stock_target(state, name, source.source_path, units="inch", translation_mm=(-0.5, -0.5, 0.5))
    analysis = analyze_stock_target(target, state)
    hit = inspect_target_cell(analysis, "Initial stock", (1, 1, 1), tool=1)
    grid = StockVolume.from_snapshot(target.initial)
    assert hit.center_grid_mm == (-0.25, -0.25, 0.75)
    assert hit.center_program_mm == grid.program_point(grid.grid_center(1, 1, 1)).tuple
    assert hit.signed_distance_mm == pytest.approx(-0.25)
    assert hit.approach.end == hit.center_program_mm
    assert hit.approach.start[2] == grid.bounds.maximum.z + 1
    assert hit.approach.start[:2] == hit.approach.end[:2]
    assert hit.approach.target_contacts
