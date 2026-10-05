import json

import pytest

from carveracontroller.machine.repeat_parts import RepeatPartPlan, RepeatPartStore, StockInstance


def grid(**changes):
    values = {
        "rows": 2,
        "columns": 3,
        "pitch_mm": (50, 50, 0),
        "work_offset_mm": (-200, -150, -80),
        "stock_origin_mm": (0, 0, -10),
        "stock_size_mm": (40, 40, 10),
    }
    values.update(changes)
    return RepeatPartPlan.grid(**values)


def test_grid_assigns_distinct_frames_and_exact_machine_stock_positions():
    plan = grid()
    assert [p.wcs for p in plan.parts] == [f"G{i}" for i in range(54, 60)]
    assert plan.parts[-1].work_offset_mm == (-100, -100, -80)
    assert plan.parts[-1].bounds == ((-100, -100, -90), (-60, -60, -80))
    assert plan.parts[-1].machine_point((3, 2, 1)) == (-97, -98, -79)
    assert RepeatPartPlan.from_dict(json.loads(json.dumps(plan.to_dict()))) == plan


@pytest.mark.parametrize(
    "changes",
    [
        {"rows": True},
        {"columns": 0},
        {"rows": 7},
        {"first_wcs": "G55"},
        {"pitch_mm": (30, 50, 0)},
        {"pitch_mm": (50, 50, 1)},
        {"stock_size_mm": (0, 40, 10)},
        {"stock_size_mm": (float("nan"), 40, 10)},
        {"work_offset_mm": (True, 0, 0)},
        {"work_offset_mm": (990, 0, 0)},
    ],
)
def test_invalid_or_overlapping_arrays_are_rejected(changes):
    with pytest.raises(ValueError):
        grid(**changes)


def test_touching_stock_faces_and_negative_pitch_are_valid():
    assert len(grid(pitch_mm=(-40, -40, 0)).parts) == 6


def test_duplicate_frames_or_names_are_rejected():
    part = grid(rows=1, columns=1).parts[0]
    with pytest.raises(ValueError, match="distinct work"):
        RepeatPartPlan((part, part))
    with pytest.raises(ValueError, match="distinct name"):
        RepeatPartPlan((part, StockInstance(part.name, "G55", (-100, -100, -80), (0, 0, -10), (40, 40, 10))))


def test_store_is_machine_scoped_and_validates_before_replacing(tmp_path):
    store = RepeatPartStore(tmp_path / "parts.json")
    first, second = grid(), grid(rows=1, columns=1)
    store.save("machine-a", first)
    store.save("machine-b", second)
    assert store.load("machine-a") == first
    assert store.load("machine-b") == second
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.save("", first)
    assert store.path.read_bytes() == before
    assert store.load("machine-c") is None
    assert not list(tmp_path.glob("*.tmp"))


def test_store_rejects_duplicate_unknown_and_oversize_data(tmp_path):
    store = RepeatPartStore(tmp_path / "parts.json")
    for data in ('{"a":{},"a":{}}', '{"a":{"schema":true,"parts":[]}}', "x" * (1024 * 1024 + 1)):
        store.path.write_text(data)
        with pytest.raises(ValueError):
            store.load("a")
    value = grid().to_dict()
    value["parts"][0]["unexpected"] = 1
    with pytest.raises(ValueError):
        RepeatPartPlan.from_dict(value)


def test_array_mesh_has_every_nonactive_stock_in_machine_frame_with_valid_indices():
    from carveracontroller.machine.repeat_parts import repeat_stock_geometry
    from carveracontroller.machine.scene_inspection import geometry_bounds

    plan = grid()
    for active in range(6):
        solids, edges = repeat_stock_geometry(plan, active)
        assert len(solids.indices) == 5 * 36
        assert len(edges.indices) == 5 * 24
        remaining = [p for i, p in enumerate(plan.parts) if i != active]
        expected = (
            tuple(min(p.bounds[0][a] for p in remaining) for a in range(3)),
            tuple(max(p.bounds[1][a] for p in remaining) for a in range(3)),
        )
        assert geometry_bounds(solids) == expected
        assert geometry_bounds(edges) == expected
        for geometry in (solids, edges):
            assert max(geometry.indices) < len(geometry.vertices) // 10
            points = [tuple(geometry.vertices[i : i + 3]) for i in range(0, len(geometry.vertices), 10)]
            assert all(
                any(all(p.bounds[0][a] <= point[a] <= p.bounds[1][a] for a in range(3)) for p in remaining)
                for point in points
            )
            assert all(
                not all(
                    plan.parts[active].bounds[0][a] <= point[a] <= plan.parts[active].bounds[1][a] for a in range(3)
                )
                for point in points
            )
    solids, edges = repeat_stock_geometry(grid(rows=1, columns=1), 0)
    assert not solids.indices and not edges.indices
    assert not repeat_stock_geometry(None, None)[0].indices


@pytest.mark.parametrize("index", [None, True, -1, 6, 1.0])
def test_array_mesh_rejects_invalid_active_instance(index):
    from carveracontroller.machine.repeat_parts import repeat_stock_geometry

    with pytest.raises(ValueError):
        repeat_stock_geometry(grid(), index)
