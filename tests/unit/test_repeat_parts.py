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


@pytest.mark.parametrize("component", [True, "1", None, 10**1000, float("inf")])
def test_bad_runtime_coordinates_fail_as_validation_errors(component):
    with pytest.raises(ValueError):
        grid(work_offset_mm=(component, 0, 0))


def test_review_lists_actual_bounds_and_nearest_declared_separation():
    from carveracontroller.machine.repeat_parts import frame_review

    plan = grid()
    review = frame_review(plan, 0)
    assert review["datum_mm"] == (-200, -150, -80)
    assert review["bounds_mm"] == ((-200, -150, -90), (-160, -110, -80))
    assert review["nearest_stock_gap_mm"] == 10
    assert frame_review(grid(rows=1, columns=1), 0)["nearest_stock_gap_mm"] is None
    assert frame_review(grid(pitch_mm=(-40, -40, 0)), 0)["nearest_stock_gap_mm"] == 0
    for bad in (True, -1, 6, "0"):
        with pytest.raises(ValueError):
            frame_review(plan, bad)


def test_saved_plan_requires_matching_review_and_preserves_other_machines(tmp_path):
    from carveracontroller.machine.repeat_parts import plan_revision

    store = RepeatPartStore(tmp_path / "parts.json")
    first = grid()
    revision = store.save("a", first)
    assert revision == plan_revision(first)
    store.save("b", grid(rows=1, columns=1))
    changed = grid(rows=1, columns=2)
    new_revision = store.save("a", changed, revision)
    assert new_revision != revision
    original = store.path.read_bytes()
    with pytest.raises(ValueError, match="changed elsewhere"):
        store.save("a", first, revision)
    with pytest.raises(ValueError, match="changed elsewhere"):
        store.save("a", first)
    assert store.path.read_bytes() == original
    assert store.load("b") == grid(rows=1, columns=1)
    assert not store.path.with_suffix(".lock").exists()


def test_plan_lock_and_atomic_failure_preserve_existing_file(tmp_path):
    from unittest.mock import patch

    store = RepeatPartStore(tmp_path / "parts.json")
    revision = store.save("a", grid())
    original = store.path.read_bytes()
    lock = store.path.with_suffix(".lock")
    lock.write_text("owned elsewhere")
    with pytest.raises(FileExistsError):
        store.save("a", grid(rows=1, columns=1), revision)
    assert lock.read_text() == "owned elsewhere" and store.path.read_bytes() == original
    lock.unlink()
    with (
        patch("carveracontroller.machine.repeat_parts.os.replace", side_effect=OSError("full")),
        pytest.raises(OSError, match="full"),
    ):
        store.save("a", grid(rows=1, columns=1), revision)
    assert store.path.read_bytes() == original
    assert not lock.exists() and not list(tmp_path.glob(".repeat-parts-*"))


def test_plan_io_keeps_navigation_live_and_rejects_stale_restore(tmp_path):
    import threading
    import time
    from types import SimpleNamespace
    from unittest.mock import Mock

    from kivy.clock import Clock

    from carveracontroller.desktop_repeat_parts import RepeatPartsPanel

    controller = Mock()
    workspace = SimpleNamespace(
        selected_machine_profile={"id": "async-machine"},
        active_section="Setup",
        machine=SimpleNamespace(gcode_viewer=Mock(), controller=controller),
    )
    panel = RepeatPartsPanel(workspace)
    panel.store = RepeatPartStore(tmp_path / "plans.json")
    panel.generate()
    original = panel.plan
    started, release = threading.Event(), threading.Event()
    save = panel.store.save
    calls = []

    def delayed_save(*args):
        calls.append(args)
        started.set()
        assert release.wait(5)
        return save(*args)

    panel.store.save = delayed_save
    panel.save()
    assert started.wait(2)
    assert panel.io_busy and panel.save_plan_action.disabled
    panel.save()
    assert len(calls) == 1
    panel.show_page("Results")
    assert panel.page == "Results"
    panel.columns.text = "3"
    assert panel.plan is None
    release.set()
    deadline = time.monotonic() + 5
    while panel.io_busy and time.monotonic() < deadline:
        Clock.tick()
        time.sleep(0.01)
    assert not panel.io_busy
    assert panel.store.load("async-machine") == original
    assert panel.plan is None and panel.plan_io_receipt["state"] == "saved"
    assert "snapshot saved" in panel.note.text
    started.clear()
    release.clear()
    load = panel.store.load

    def delayed_load(*args):
        started.set()
        assert release.wait(5)
        return load(*args)

    panel.store.load = delayed_load
    panel.restore()
    assert started.wait(2)
    workspace.selected_machine_profile = {"id": "other-machine"}
    panel.refresh_frame_review()
    release.set()
    deadline = time.monotonic() + 5
    while panel.io_busy and time.monotonic() < deadline:
        Clock.tick()
        time.sleep(0.01)
    assert not panel.io_busy and panel.plan is None
    assert panel.plan_io_receipt["state"] == "not applied"
    assert "not applied" in panel.note.text
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width", [360, 760])
def test_declared_frame_review_reflows_and_clears_when_machine_changes(width, tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from kivy.clock import Clock
    from kivy.metrics import dp

    from carveracontroller.desktop_repeat_parts import RepeatPartsPanel

    workspace = SimpleNamespace(
        selected_machine_profile={"id": "review-machine"},
        active_section="Setup",
        machine=SimpleNamespace(gcode_viewer=Mock()),
    )
    panel = RepeatPartsPanel(workspace)
    panel.store = RepeatPartStore(tmp_path / "plans.json")
    panel.size_hint_x = None
    panel.width = dp(width)
    panel.toggle()
    panel.generate()
    panel.choice.text = panel.choice.values[1]
    panel.part_editor.toggle()
    for _ in range(12):
        Clock.tick()
    assert "Part 2 · G55" in panel.frame_detail.text
    assert "Datum: -120, -120, -110" in panel.frame_detail.text
    assert "Nearest declared stock gap: 20 mm" in panel.frame_detail.text
    from carveracontroller.desktop_components import ACCENT, AdaptiveGrid

    assert panel.tab_actions["Review"].base_color == ACCENT
    for grid_widget in panel.review_body.children:
        if isinstance(grid_widget, AdaptiveGrid):
            for child in grid_widget.children:
                assert child.y >= grid_widget.y and child.top <= grid_widget.top
                for nested in child.children:
                    assert nested.y >= child.y and nested.top <= child.top
    for grid_widget in panel.part_editor.content.children:
        if isinstance(grid_widget, AdaptiveGrid):
            for child in grid_widget.children:
                assert child.y >= grid_widget.y and child.top <= grid_widget.top
                for nested in child.children:
                    assert nested.y >= child.y and nested.top <= child.top
    assert panel.frame_detail.height >= panel.frame_detail.texture_size[1]
    for child in panel.review_body.children:
        assert child.x >= panel.review_body.x and child.right <= panel.review_body.right
        assert child.y >= panel.review_body.y and child.top <= panel.review_body.top
    workspace.selected_machine_profile = {"id": "different-machine"}
    panel.refresh_frame_review()
    assert "Build or restore" in panel.frame_detail.text
    assert "Part 2" not in panel.frame_detail.text


def test_plan_worker_launch_failure_releases_controls(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock, patch

    from carveracontroller.desktop_repeat_parts import RepeatPartsPanel

    workspace = SimpleNamespace(
        selected_machine_profile={"id": "launch-test"},
        active_section="Setup",
        machine=SimpleNamespace(gcode_viewer=Mock()),
    )
    panel = RepeatPartsPanel(workspace)
    panel.store = RepeatPartStore(tmp_path / "plans.json")
    panel.generate()
    with patch("carveracontroller.desktop_repeat_parts.threading.Thread.start", side_effect=RuntimeError("no worker")):
        panel.save()
    assert not panel.io_busy and not panel.save_plan_action.disabled and not panel.restore_plan_action.disabled
    assert panel.plan_io_receipt["state"] == "failed" and "no worker" in panel.note.text
    assert not panel.store.path.exists()


@pytest.mark.parametrize(
    "rows,columns,pitch,first",
    [(2, 2, (-50, 60, 0), "G55"), (1, 3, (50, 60, 0), "G54"), (3, 1, (50, -60, 0), "G56"), (1, 1, (50, 60, 0), "G59")],
)
def test_saved_grid_geometry_recovers_editable_fields(rows, columns, pitch, first):
    from carveracontroller.machine.repeat_parts import grid_draft

    plan = grid(rows=rows, columns=columns, pitch_mm=pitch, first_wcs=first, work_offset_mm=(-200.1, -150.2, -80.3))
    before = plan.to_dict()
    draft = grid_draft(plan)
    assert (draft.rows, draft.columns, draft.first_wcs) == (rows, columns, first)
    rebuilt = RepeatPartPlan.grid(
        draft.rows,
        draft.columns,
        draft.pitch_mm,
        draft.work_offset_mm,
        draft.stock_origin_mm,
        draft.stock_size_mm,
        draft.first_wcs,
    )
    for actual, expected in zip(rebuilt.parts, plan.parts):
        assert actual.work_offset_mm == pytest.approx(expected.work_offset_mm)
    assert plan.to_dict() == before


def test_custom_part_edits_preserve_neighbors_and_validate_whole_plan():
    from dataclasses import replace

    from carveracontroller.machine.repeat_parts import grid_draft, replace_part

    plan = grid(rows=1, columns=2)
    edited = replace(plan.parts[1], name="Bracket", stock_size_mm=(20, 30, 10))
    custom = replace_part(plan, 1, edited)
    assert custom.parts[0] is plan.parts[0]
    assert custom.parts[1] is edited
    assert grid_draft(custom) is None
    for invalid in (
        replace(edited, wcs="G54"),
        replace(edited, name="Part 1"),
        replace(edited, work_offset_mm=plan.parts[0].work_offset_mm),
    ):
        with pytest.raises(ValueError):
            replace_part(custom, 1, invalid)
    for index in (True, -1, 2):
        with pytest.raises(ValueError):
            replace_part(custom, index, edited)
    assert custom.parts[1] is edited
