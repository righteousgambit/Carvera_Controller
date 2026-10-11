"""Exact source shapes must survive repeat plans, rendering, cutting and exchange."""

import json
from dataclasses import replace

import pytest

from carveracontroller.addons.machine_simulation.stock_model import StockModel, initial_stock
from carveracontroller.addons.manufacturing_simulation import StockVolume
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_archive import load_repeat_result, save_repeat_result
from carveracontroller.machine.repeat_parts import RepeatPartPlan, RepeatPartStore, StockSource, repeat_stock_geometry
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts
from tests.unit.test_stock_solid import l_stock, mesh


def array(tmp_path, units="mm", translated=False):
    triangles = l_stock()
    if translated:
        triangles = [tuple(tuple(p[i] + (10, -20, 30)[i] for i in range(3)) for p in tri) for tri in triangles]
    source = mesh(tmp_path, triangles, units)
    model = StockModel.load(source.source_path, units)
    plan = RepeatPartPlan.grid(
        1, 2, (100, 0, 0), (10, 20, 30), (1, 2, -2), model.size_mm, stock_source=StockSource.from_model(model)
    )
    return plan, model


def test_plan_references_are_immutable_and_parse_without_source_io(tmp_path, monkeypatch):
    plan, model = array(tmp_path)
    serialized = json.loads(json.dumps(plan.to_dict()))
    assert serialized["schema"] == 2
    source = plan.parts[0].stock_source
    ref = source.reference
    ref["minimum_mm"][0] = -500
    assert source.reference == model.reference
    monkeypatch.setattr(StockModel, "load", lambda *a, **k: pytest.fail("Plan parsing opened source"))
    assert RepeatPartPlan.from_dict(serialized) == plan
    store = RepeatPartStore(tmp_path / "parts.json")
    store.save("first", plan)
    assert store.load("first") == plan
    assert store.revision("first")
    with pytest.raises(ValueError, match="dimensions"):
        replace(plan.parts[0], stock_size_mm=(4, 4, 4))
    serialized["schema"] = 1
    with pytest.raises(ValueError):
        RepeatPartPlan.from_dict(serialized)


@pytest.mark.parametrize("units,translated", [("mm", False), ("mm", True), ("inch", True)])
def test_prepared_preview_preserves_concavity_units_and_each_machine_placement(tmp_path, units, translated):
    plan, model = array(tmp_path, units, translated)
    with pytest.raises(ValueError, match="Prepare"):
        repeat_stock_geometry(plan, 0)
    prepared = plan.prepared(selected_index=0)
    solids, edges = repeat_stock_geometry(prepared, 0)
    other = plan.parts[1]
    assert len(solids.indices) == len(l_stock()) * 3
    expected = [
        tuple(p[i] - model.minimum_mm[i] + other.bounds[0][i] for i in range(3))
        for tri in model.solid.mesh.triangles_mm
        for p in tri
    ]
    for i, point in enumerate(expected):
        assert solids.vertices[solids.indices[i] * 10 : solids.indices[i] * 10 + 3] == pytest.approx(point)
    assert edges.indices
    assert prepared.stock_models["G54"].solid is prepared.stock_models["G55"].solid
    assert prepared.stock_models["G54"]._cache is not prepared.stock_models["G55"]._cache
    with pytest.raises(ValueError, match="Prepare"):
        repeat_stock_geometry(prepared, 1)


def simulate_array(tmp_path, notch=False, translated=False):
    plan, model = array(tmp_path, translated=translated)
    x, y = (3.5, 4.5) if notch else (1.5, 2.5)
    program = ProgramOperations.from_text(f"G21 G90 G17 G94 G54\nT1 M6\nG0 X{x} Y{y} Z1\nG1 Z-1 F100\nG1 X{x + 0.1}\n")
    tools = {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=0.5, shank_diameter=0.5, flute_length=2, stickout=3)}
    result = simulate_repeat_parts(program, plan, tools, {}, 0.25)
    context = {
        "program": program.file_hash,
        "repeat_plan": plan.to_dict(),
        "tools": {},
        "components": {},
        "machine_profile_id": "test",
        "resolution_mm": 0.25,
    }
    return program, result, context, model


@pytest.mark.parametrize("notch", [False, True])
def test_simulation_cuts_actual_material_and_does_not_duplicate_wcs_paths(tmp_path, notch):
    _, result, _, _ = simulate_array(tmp_path, notch)
    first, second = result.reports
    assert first.remaining_volume_mm3 + first.removed_volume_mm3 == pytest.approx(10)
    assert second.remaining_volume_mm3 == pytest.approx(10)
    assert second.removed_volume_mm3 == 0
    if notch:
        assert first.removed_volume_mm3 == 0
    else:
        assert first.removed_volume_mm3 > 0
    assert all(snapshot["initial_occupied_voxels"] == 640 for snapshot in result.snapshots)


def test_archive_roundtrip_rejects_material_forged_into_the_source_notch(tmp_path):
    program, result, context, _ = simulate_array(tmp_path)
    path = tmp_path / "stocks.cvstocks"
    save_repeat_result(path, result, context)
    restored = load_repeat_result(path, program, context)
    assert restored.snapshots == tuple(json.loads(json.dumps(result.snapshots)))
    stock = StockVolume.from_snapshot(result.snapshots[0])
    initial = initial_stock(result.plan.setup(result.plan.parts[0], machine_space=True), 0.25)
    full, empty = stock._occupied.index(1), initial._occupied.index(0)
    stock._occupied[full], stock._occupied[empty] = 0, 1  # Preserve count/volume and recompute the transport digest.
    forged = replace(result, snapshots=(stock.snapshot(), result.snapshots[1]))
    save_repeat_result(path, forged, context)
    with pytest.raises(ValueError, match="outside the imported initial shape"):
        load_repeat_result(path, program, context)
    assert result.snapshots[0] != forged.snapshots[0]


def test_changed_or_missing_source_refuses_preview_simulation_and_exchange(tmp_path):
    program, result, context, model = simulate_array(tmp_path)
    path = tmp_path / "preserve.cvstocks"
    path.write_bytes(b"previous destination")
    from pathlib import Path

    Path(model.source_path).write_text("changed source")
    with pytest.raises(ValueError, match="changed"):
        save_repeat_result(path, result, context)
    assert path.read_bytes() == b"previous destination"
    with pytest.raises(ValueError):
        result.plan.prepared(selected_index=0)
    with pytest.raises(InterruptedError):
        result.plan.prepared(selected_index=0, cancelled=lambda: True)


def test_mixed_source_and_block_parts_keep_their_own_material_and_roundtrip(tmp_path):
    plan, _ = array(tmp_path)
    plan = replace(plan, parts=(plan.parts[0], replace(plan.parts[1], stock_source=None)))
    assert RepeatPartPlan.from_dict(json.loads(json.dumps(plan.to_dict()))) == plan
    prepared = plan.prepared(selected_index=0)
    solids, _ = repeat_stock_geometry(prepared, 0)
    assert len(solids.indices) == 36  # The second instance is explicitly a block.
    source_stock = initial_stock(prepared.setup(plan.parts[0], machine_space=True), 0.5)
    block_stock = initial_stock(prepared.setup(plan.parts[1], machine_space=True), 0.5)
    assert source_stock.remaining_volume_mm3 == 10
    assert block_stock.remaining_volume_mm3 == 18


def test_source_change_during_preparation_is_detected_before_geometry_publication(tmp_path, monkeypatch):
    from pathlib import Path

    plan, model = array(tmp_path)
    original = StockModel.fork_preview_cache

    def changed(self):
        result = original(self)
        Path(model.source_path).write_text("source changed after loading")
        return result

    monkeypatch.setattr(StockModel, "fork_preview_cache", changed)
    with pytest.raises(ValueError, match="changed during preparation"):
        plan.prepared(selected_index=0)
    assert plan.nominal_geometry is None and not plan.stock_models


def test_replaced_part_cannot_reuse_geometry_from_an_older_plan_revision(tmp_path):
    plan, _ = array(tmp_path)
    prepared = plan.prepared(selected_index=0)
    moved = replace(prepared.parts[1], work_offset_mm=(210, 20, 30))
    updated = replace(prepared, parts=(prepared.parts[0], moved))
    assert updated.nominal_geometry is prepared.nominal_geometry
    with pytest.raises(ValueError, match="Prepare"):
        repeat_stock_geometry(updated, 0)
    refreshed = updated.prepared(selected_index=0)
    solid, _ = repeat_stock_geometry(refreshed, 0)
    assert min(solid.vertices[i] for i in range(0, len(solid.vertices), 10)) == 211


def test_forged_grid_extent_is_refused_before_occupancy_allocation(tmp_path, monkeypatch):
    from carveracontroller.machine.geometry_changes import digest_context

    program, result, context, _ = simulate_array(tmp_path)
    path = tmp_path / "oversized.cvstocks"
    save_repeat_result(path, result, context)
    payload = json.loads(path.read_text())
    payload.pop("sha256")
    payload["stocks"][0]["maximum"][0] += 100
    payload["sha256"] = digest_context(payload)
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(StockVolume, "from_snapshot", lambda *a, **k: pytest.fail("Decoded a mismatched source grid"))
    with pytest.raises(ValueError, match="placement differs"):
        load_repeat_result(path, program, context)


def test_source_with_nonzero_minimum_roundtrips_machine_space_residuals(tmp_path):
    program, result, context, _ = simulate_array(tmp_path, translated=True)
    path = tmp_path / "translated-source.cvstocks"
    save_repeat_result(path, result, context)
    restored = load_repeat_result(path, program, context)
    assert restored.snapshots == tuple(json.loads(json.dumps(result.snapshots)))
    assert restored.reports[0].remaining_volume_mm3 == result.reports[0].remaining_volume_mm3
    assert restored.plan.parts[0].stock_source.reference["minimum_mm"] == [10, -20, 30]
