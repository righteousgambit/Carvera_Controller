from dataclasses import replace

import pytest

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_display import RepeatStockDisplay
from carveracontroller.machine.repeat_parts import repeat_stock_geometry
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts
from tests.unit.test_repeat_simulation import TEXT, definitions, plan


def test_worker_prepares_complete_view_and_rendering_never_converts_again(monkeypatch):
    declared = plan()
    result = simulate_repeat_parts(ProgramOperations.from_text(TEXT), declared, definitions(), {}, 1)
    source = dict(result.geometries)
    display = RepeatStockDisplay.prepare(declared, 0, source, 2.5)
    expected, edges = repeat_stock_geometry(declared, 0, source)
    assert display.solids.vertices == tuple(expected.vertices)
    assert display.solids.indices == tuple(expected.indices)
    assert display.edges.vertices == tuple(edges.vertices)
    assert display.matches(declared, 0) and not display.matches(declared, 1)
    source.clear()
    assert set(display) == {"G54", "G55"}
    with pytest.raises(TypeError):
        display.stocks["G54"] = display["G55"]

    def forbid(*args, **kwargs):
        pytest.fail("The UI attempted to convert already prepared geometry")

    monkeypatch.setattr(GeometrySnapshot, "_prepare_render_batches", forbid)
    solid, edge = repeat_stock_geometry(declared, 0, display)
    assert solid is display.solids and edge is display.edges
    offset = declared.parts[0].work_offset_mm
    assert display["G54"].render_batches(offset, 2.5)
    assert solid.render_batches(offset, 2.5)
    assert edge.render_line_batches(offset, 2.5)
    assert RepeatStockDisplay.prepare(declared, 0, display, 2.5) is display


def test_selection_and_revision_cannot_reuse_other_parts_combined_surface():
    declared = plan()
    result = simulate_repeat_parts(ProgramOperations.from_text(TEXT), declared, definitions(), {}, 1)
    first = RepeatStockDisplay.prepare(declared, 0, result.geometries, 1)
    second = RepeatStockDisplay.prepare(declared, 1, first, 1)
    assert second is not first
    assert second.solids.bounds == first["G54"].bounds
    assert first.solids.bounds == first["G55"].bounds
    assert second["G54"] is first["G54"]
    moved = replace(declared, parts=(replace(declared.parts[0], name="Renamed"), declared.parts[1]))
    assert not first.matches(moved, 0)


def test_display_cancellation_or_incomplete_results_never_replace_source():
    declared = plan()
    result = simulate_repeat_parts(ProgramOperations.from_text(TEXT), declared, definitions(), {}, 1)
    before = dict(result.geometries)
    with pytest.raises(InterruptedError):
        RepeatStockDisplay.prepare(declared, 0, result.geometries, 1, cancelled=lambda: True)
    with pytest.raises(ValueError, match="complete immutable"):
        RepeatStockDisplay.prepare(declared, 0, {"G54": result.geometries["G54"]}, 1)
    assert dict(result.geometries) == before


def test_imported_result_prepares_actual_source_edges_for_each_selection(tmp_path):
    from tests.unit.test_imported_stock_arrays import simulate_array

    _, result, _, _ = simulate_array(tmp_path)
    first = RepeatStockDisplay.prepare(result.plan, 0, result.geometries, 1)
    second = RepeatStockDisplay.prepare(result.plan, 1, first, 1)
    assert first.solids.bounds == result.geometries["G55"].bounds
    assert second.solids.bounds == result.geometries["G54"].bounds
    assert len(first.edges.indices) > 24  # Concave solid edges, not a block outline.
    assert len(second.edges.indices) == len(first.edges.indices)
