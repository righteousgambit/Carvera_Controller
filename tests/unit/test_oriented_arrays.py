"""Fixed stock rotations remain separate from declared G54–G59 toolpath translations."""

import json
import math
from dataclasses import replace

import pytest

from carveracontroller.addons.machine_simulation.stock_model import initial_stock
from carveracontroller.addons.manufacturing_simulation import StockVolume, Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_archive import load_repeat_result, save_repeat_result
from carveracontroller.machine.repeat_parts import (
    RepeatPartPlan,
    RepeatPartStore,
    StockInstance,
    StockSource,
    grid_draft,
    plan_revision,
    repeat_stock_geometry,
)
from carveracontroller.machine.repeat_playback import prepare_repeat_playback
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts
from tests.unit.test_imported_stock_arrays import array
from tests.unit.test_stock_orientation import oracle


def grid(angles=(23, -32, 41)):
    return RepeatPartPlan.grid(1, 2, (40, 0, 0), (10, 20, 30), (1, 2, -2), (8, 6, 4), stock_orientation_deg=angles)


def test_schema3_roundtrip_revision_grid_recovery(tmp_path):
    plan = grid()
    payload = json.loads(json.dumps(plan.to_dict()))
    assert payload["schema"] == 3
    restored = RepeatPartPlan.from_dict(payload)
    assert restored == plan
    assert grid_draft(restored).stock_orientation_deg == (23, -32, 41)
    assert plan_revision(plan) != plan_revision(grid((24, -32, 41)))
    store = RepeatPartStore(tmp_path / "plans.json")
    store.save("tilted", plan)
    assert store.load("tilted") == plan
    custom = replace(plan.parts[1], stock_orientation_deg=(90, 0, 0))
    assert grid_draft(RepeatPartPlan((plan.parts[0], custom))) is None
    payload["schema"] = 2
    with pytest.raises(ValueError):
        RepeatPartPlan.from_dict(payload)
    assert grid((0, 0, 0)).to_dict()["schema"] == 1


@pytest.mark.parametrize("angles", [(True, 0, 0), (0, float("nan"), 0), (0, 0), (10**1000, 0, 0)])
def test_invalid_orientation_never_enters_a_plan(angles):
    with pytest.raises(ValueError):
        grid(angles)


def test_oriented_machine_corner_is_not_rotated_aabb_minimum():
    plan = grid()
    part = plan.parts[0]
    machine = plan.setup(part, machine_space=True)
    assert machine.stock_origin_mm == (11, 22, 28)
    assert machine.stock_origin_mm != part.bounds[0]
    center = Vec3(*(a + b / 2 for a, b in zip(part.machine_origin_mm, part.stock_size_mm)))
    expected = oracle(part.stock_orientation_deg, center)
    corners = [
        expected.apply(
            Vec3(
                *(
                    part.machine_origin_mm[axis] + (part.stock_size_mm[axis] if index & (1 << axis) else 0)
                    for axis in range(3)
                )
            )
        ).tuple
        for index in range(8)
    ]
    assert part.bounds[0] == pytest.approx(tuple(min(p[axis] for p in corners) for axis in range(3)))
    assert part.bounds[1] == pytest.approx(tuple(max(p[axis] for p in corners) for axis in range(3)))
    local = plan.setup(part)
    for p in ((1, 2, -2), (9, 8, 2)):
        assert machine.stock_point(tuple(a + b for a, b in zip(p, part.work_offset_mm))) == pytest.approx(
            tuple(a + b for a, b in zip(local.stock_point(p), part.work_offset_mm))
        )
    mesh, _edges = repeat_stock_geometry(plan, 1)
    actual = [tuple(mesh.vertices[i : i + 3]) for i in range(0, len(mesh.vertices), 10)]
    for corner in corners:
        assert any(p == pytest.approx(corner) for p in actual)


def test_oriented_separating_axes_accept_disjoint_boxes_with_overlapping_aabbs():
    first = StockInstance("one", "G54", (0, 0, 0), (-5, -0.5, -0.5), (10, 1, 1), stock_orientation_deg=(0, 0, 45))
    second = replace(first, name="two", wcs="G55", work_offset_mm=(-math.sqrt(2), math.sqrt(2), 0))
    assert all(
        max(first.bounds[0][a], second.bounds[0][a]) < min(first.bounds[1][a], second.bounds[1][a]) for a in range(3)
    )
    assert RepeatPartPlan((first, second)).parts == (first, second)
    with pytest.raises(ValueError, match="overlap"):
        RepeatPartPlan((first, replace(second, work_offset_mm=(-0.3, 0.3, 0))))
    # Contact of the actual oriented faces preserves the existing touching rule.
    touch = 1 / math.sqrt(2)
    assert RepeatPartPlan((first, replace(second, work_offset_mm=(-touch, touch, 0))))


def test_differently_tilted_boxes_require_edge_cross_axes():
    angles = ((23, -32, 41), (70, 25, -10))
    delta = (3.7937587760113525, 1.0882493754277052, 3.071896694777843)
    parts = tuple(
        StockInstance(str(i), f"G{54 + i}", offset, (-5, -0.5, -0.5), (10, 1, 1), stock_orientation_deg=a)
        for i, (a, offset) in enumerate(zip(angles, ((0, 0, 0), delta)))
    )
    # Independent corner projections demonstrate why testing only the six face
    # normals is insufficient for these skew rods. Their edge cross axes separate.
    transforms = [oracle(a) for a in angles]
    corners = [
        [
            tuple(a + b for a, b in zip(t.apply(Vec3(x, y, z)).tuple, offset))
            for x in (-5, 5)
            for y in (-0.5, 0.5)
            for z in (-0.5, 0.5)
        ]
        for t, offset in zip(transforms, ((0, 0, 0), delta))
    ]
    basis = [t.direction(Vec3(*p)).tuple for t in transforms for p in ((1, 0, 0), (0, 1, 0), (0, 0, 1))]

    def separated(axis):
        intervals = [sorted(sum(a * b for a, b in zip(p, axis)) for p in points) for points in corners]
        return intervals[0][-1] < intervals[1][0] or intervals[1][-1] < intervals[0][0]

    assert not any(separated(axis) for axis in basis)
    assert any(
        separated((u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]))
        for u in basis[:3]
        for v in basis[3:]
    )
    assert RepeatPartPlan(parts).parts == parts
    with pytest.raises(ValueError, match="overlap"):
        RepeatPartPlan((parts[0], replace(parts[1], work_offset_mm=(0, 0, 0))))


def test_oriented_source_references_parse_and_persist_without_opening_sources(tmp_path, monkeypatch):
    from carveracontroller.addons.machine_simulation.stock_model import StockModel

    plan, _model = array(tmp_path, translated=True)
    plan = RepeatPartPlan(tuple(replace(p, stock_orientation_deg=(23 + i, -32, 41)) for i, p in enumerate(plan.parts)))
    payload = json.loads(json.dumps(plan.to_dict()))
    monkeypatch.setattr(StockModel, "load", lambda *a, **kw: pytest.fail("declaration opened source"))
    assert RepeatPartPlan.from_dict(payload) == plan
    store = RepeatPartStore(tmp_path / "plans.json")
    store.save("sources", plan)
    assert store.load("sources") == plan


@pytest.mark.parametrize("imported", [False, True])
@pytest.mark.parametrize("angles", [(23, -32, 41), (0, 0, 41), (0, 0, 0)])
def test_simulation_archive_and_playback_preserve_per_part_orientation(tmp_path, imported, angles, monkeypatch):
    if imported:
        plan, _source = array(tmp_path)
        plan = RepeatPartPlan(tuple(replace(p, stock_orientation_deg=angles) for p in plan.parts))
    else:
        plan = grid(angles)
    # Toolpath stays in the declared WCS; fixed material orientation does not rotate it.
    program = ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X1.8 Y2.8 Z8\nG1 Z-1 F100\nG1 X2.1\n")
    tools = {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=10, stickout=12)}
    result = simulate_repeat_parts(program, plan, tools, {}, 0.25)
    assert result.reports[0].removed_volume_mm3 > 0
    assert result.reports[1].removed_volume_mm3 == 0
    schema = 4 if any(angles[:2]) else 3 if imported else 2 if angles[2] else 1
    assert all(s["schema"] == schema and s.get("tilt_deg", (0, 0)) == angles[:2] for s in result.snapshots)
    assert result.segments[-1].end.tuple == pytest.approx(
        tuple(a + b for a, b in zip((2.1, 2.8, -1), plan.parts[0].work_offset_mm))
    )
    context = {
        "program": program.file_hash,
        "repeat_plan": plan.to_dict(),
        "tools": {},
        "components": {},
        "machine_profile_id": "tilted",
        "resolution_mm": 0.25,
    }
    path = tmp_path / "tilted.cvstocks"
    save_repeat_result(path, result, context)
    restored = load_repeat_result(path, program, context)
    assert restored.plan == plan
    for p, snapshot in zip(restored.plan.parts, restored.snapshots):
        stock = StockVolume.from_snapshot(snapshot)
        initial = initial_stock(restored.plan.setup(p, machine_space=True), 0.25)
        assert stock.orientation == initial.orientation
        assert stock.pivot == initial.pivot
    playback = prepare_repeat_playback(program, plan)
    assert playback.plan.parts[0].stock_orientation_deg == angles
    assert playback.machine_rows[-1][:3] == pytest.approx(result.segments[-1].end.tuple)
    wrong = StockVolume.from_snapshot(result.snapshots[0])
    wrong.tilt_deg = (24, -32)
    from carveracontroller.addons.manufacturing_simulation.orientation import StockOrientation

    wrong.orientation = StockOrientation((24, -32, 41))
    forged = replace(result, snapshots=(wrong.snapshot(), result.snapshots[1]))
    save_repeat_result(path, forged, context)
    # A valid transport digest cannot authorize decoding a differently placed grid.
    monkeypatch.setattr(StockVolume, "from_snapshot", lambda *a, **kw: pytest.fail("decoded forged placement"))
    with pytest.raises(ValueError, match="placement differs"):
        load_repeat_result(path, program, context)
