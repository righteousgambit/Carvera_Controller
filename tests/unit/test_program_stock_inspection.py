"""Independent section cells, prefix binding, datums and complete-work refusal."""

from dataclasses import replace
from math import cos, radians, sin
from threading import Event

import pytest

from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_stock_evolution import evolution_record, review_stock_evolution
from carveracontroller.machine.program_stock_inspection import inspect_stock_section
from carveracontroller.machine.program_surface_archive import load_surface_review, save_surface_review
from tests.unit.test_program_stock_evolution import stock_example


def inspect(report, index=1, plane="XY", layer=0, name=None, **kwargs):
    return inspect_stock_section(
        report.body_review,
        report.stock_evolution,
        report.rotating_envelopes,
        name or next(iter(report.stock_evolution.inputs.stocks)),
        index,
        plane,
        layer,
        **kwargs,
    )


def cells(rectangles, plane, layer):
    axes = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (1, 2, 0)}[plane]
    result = set()
    for x in range(4):
        for y in range(4):
            u = -1 + (x + 0.5) * 0.5 if axes[0] < 2 else (x + 0.5) * 0.5
            v = -1 + (y + 0.5) * 0.5 if axes[1] < 2 else (y + 0.5) * 0.5
            if any(left < u < right and bottom < v < top for left, bottom, right, top in rectangles):
                result.add((x, y))
    return result


@pytest.mark.parametrize("plane", ["XY", "XZ", "YZ"])
@pytest.mark.parametrize("layer", [0, 2, 3])
@pytest.mark.parametrize("rotation", [0, 31])
def test_before_after_sections_match_independent_sphere_center_oracle(plane, layer, rotation):
    _, _, report, _ = stock_example(ball=True, rotation=rotation)
    section = inspect(report, plane=plane, layer=layer)
    u, v, normal = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (1, 2, 0)}[plane]
    expected = set()
    a = radians(rotation)
    for column in range(4):
        for row in range(4):
            indices = [0, 0, 0]
            indices[u], indices[v], indices[normal] = column, row, layer
            x, y, z = (-1 + (indices[0] + 0.5) * 0.5, -1 + (indices[1] + 0.5) * 0.5, (indices[2] + 0.5) * 0.5)
            px, py = x * cos(a) - y * sin(a), x * sin(a) + y * cos(a)
            dx = px - min(1, max(0, px))
            if dx * dx + py * py + (z - 2) ** 2 > 4:
                expected.add((column, row))
    assert cells(section.remaining, plane, layer) == expected
    assert cells(section.removed, plane, layer) == {(x, y) for x in range(4) for y in range(4)} - expected
    assert section.before_mm3 == 8 and section.after_mm3 == report.stock_evolution.steps[1].remaining_mm3
    assert section.layer == layer and section.layers == 4


def test_rapid_before_and_after_cut_never_mislabels_empty_as_removed():
    _, _, report, _ = stock_example(ball=True)
    first, cut, last = (inspect(report, index=i) for i in range(3))
    assert len(cells(first.remaining, "XY", 0)) == 16 and first.removed == ()
    assert len(cells(cut.remaining, "XY", 0)) == 2 and len(cells(cut.removed, "XY", 0)) == 14
    assert last.remaining == cut.remaining and last.removed == ()
    assert first.before_mm3 == first.after_mm3 == 8
    assert last.before_mm3 == last.after_mm3 == 0.25


def test_repeated_stock_uses_selected_instance_and_all_prior_tool_moves():
    _, _, report, _ = stock_example(repeat=True)
    names = tuple(report.stock_evolution.inputs.stocks)
    first, second = (inspect(report, name=name) for name in names)
    assert first.after_mm3 == 0 and first.remaining == () and first.removed
    assert second.after_mm3 == 8 and second.remaining and second.removed == ()
    final = inspect(report, index=len(report.body_review.segments) - 1, name=names[1])
    assert final.before_mm3 == final.after_mm3 == 0 and final.removed == ()


def test_portable_detached_history_reconstructs_same_section_without_current_scene(tmp_path):
    source, offsets, report, _ = stock_example(ball=True, rotation=31, tilt=(20, -10))
    path = tmp_path / "sections.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    detached = load_surface_review(path).report
    assert inspect(detached, plane="XZ", layer=2) == inspect(report, plane="XZ", layer=2)


@pytest.mark.parametrize(
    "index,layer,plane",
    [(True, 0, "XY"), (-1, 0, "XY"), (3, 0, "XY"), (1, True, "XY"), (1, -1, "XY"), (1, 4, "XY"), (1, 0, "AB")],
)
def test_invalid_selection_never_publishes_a_section(index, layer, plane):
    _, _, report, _ = stock_example()
    with pytest.raises(ValueError):
        inspect(report, index=index, layer=layer, plane=plane)


def test_shared_work_and_rectangle_limits_refuse_complete_section_not_truncated():
    _, _, report, _ = stock_example(ball=True)
    before = encoded(evolution_record(report.stock_evolution))
    complete = inspect(report)
    with pytest.raises(ValueError, match="work budget"):
        inspect(report, max_cell_work=complete.cell_work - 1)
    assert inspect(report, max_cell_work=complete.cell_work) == complete
    with pytest.raises(ValueError, match="rectangle budget"):
        inspect(report, max_rectangles=1)
    assert encoded(evolution_record(report.stock_evolution)) == before


def test_prefix_move_and_final_occupancy_changes_are_rejected():
    _, _, report, _ = stock_example(ball=True)
    evolution = report.stock_evolution
    for at, selected in ((0, 1), (1, 1)):
        rows = list(evolution.steps)
        rows[at] = replace(rows[at], remaining_mm3=999)
        with pytest.raises(ValueError, match="differs from retained history"):
            inspect(replace(report, stock_evolution=replace(evolution, steps=tuple(rows))), index=selected)
    final = {name: dict(snapshot, occupancy_sha256="0" * 64) for name, snapshot in evolution.final_snapshots.items()}
    with pytest.raises(ValueError, match="final cells"):
        inspect(replace(report, stock_evolution=replace(evolution, final_snapshots=final)), index=2)
    with pytest.raises(ValueError, match="complete ordered"):
        inspect(replace(report, stock_evolution=replace(evolution, steps=evolution.steps[:-1])))


def test_cancellation_during_section_scan_retains_history(monkeypatch):
    from carveracontroller.addons.manufacturing_simulation import StockVolume

    _, _, report, _ = stock_example(ball=True)
    before = encoded(evolution_record(report.stock_evolution))
    event = Event()
    occupied = StockVolume.occupied

    def cancel_scan(stock, *indices):
        event.set()
        return occupied(stock, *indices)

    monkeypatch.setattr(StockVolume, "occupied", cancel_scan)
    with pytest.raises(InterruptedError, match="section cancelled"):
        inspect(report, cancelled=event.is_set)
    assert encoded(evolution_record(report.stock_evolution)) == before


def test_uncertified_curve_section_retains_material_without_invented_removal():
    _, _, report, _ = stock_example()
    body = replace(report.body_review, curved_lines=(5,))
    history = review_stock_evolution(body, report.stock_evolution.inputs, report.rotating_envelopes)
    result = inspect(replace(report, body_review=body, stock_evolution=history))
    assert result.before_mm3 == result.after_mm3 == 8 and result.removed == ()


def test_imported_cavity_is_dark_before_cut_and_never_marked_as_removed(tmp_path):
    from carveracontroller.addons.machine_simulation.model import MachineSetup
    from carveracontroller.addons.machine_simulation.stock_model import StockModel
    from carveracontroller.machine.program_surface_clearance import review_program_surfaces
    from tests.unit.test_scene_joint_clearance import capture, scene_viewer
    from tests.unit.test_stock_solid import box, mesh, reverse

    source, offsets, _, captures = stock_example()
    shape = mesh(tmp_path, box((-1, -1, 0), (1, 1, 2)) + reverse(box((-0.5, -0.5, 0.5), (0.5, 0.5, 1.5))))
    viewer = scene_viewer()
    viewer.machine_setup = replace(captures[1].setup, stock_model=StockModel.load(shape.source_path, "mm"))
    assert isinstance(viewer.machine_setup, MachineSetup)
    viewer.library_tool_table_mm[1] = captures[1].definition
    report = review_program_surfaces(source, {1: capture(viewer)}, offsets, grouped=True, stock_resolution_mm=0.5)
    result = inspect(report, layer=1)
    void = {(1, 1), (1, 2), (2, 1), (2, 2)}
    assert result.before_mm3 == 7 and result.after_mm3 == 0
    assert result.remaining == ()
    assert cells(result.removed, "XY", 1) == {(x, y) for x in range(4) for y in range(4)} - void


def test_million_cell_section_merges_exact_runs_without_omitting_cells():
    from carveracontroller.machine.program_surface_clearance import review_program_surfaces
    from tests.unit.test_scene_joint_clearance import capture, scene_viewer

    source, offsets, _, captures = stock_example()
    viewer = scene_viewer()
    viewer.machine_setup = replace(captures[1].setup, stock_origin_mm=(0, 0, 0), stock_size_mm=(50, 50, 0.05))
    viewer.library_tool_table_mm[1] = captures[1].definition
    report = review_program_surfaces(source, {1: capture(viewer)}, offsets, grouped=True, stock_resolution_mm=0.05)
    result = inspect(report, index=0, layer=0)
    assert result.remaining == ((0, 0, 50, 50),) and result.removed == ()
    assert result.before_mm3 == result.after_mm3 == pytest.approx(125)
    assert result.cell_work == 3_000_000
