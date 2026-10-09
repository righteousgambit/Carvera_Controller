"""Scene drafts survive restarts independently without mutating machine state."""

import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_scene import SceneSetupStore, capture_scene_setup, restore_scene_geometry


def setup_record():
    return {
        "work_offset_mm": [-180, -120, -110],
        "stock_size_mm": [127, 69.4182, 50.8762],
        "stock_origin_mm": [-118.6, -94.7091, -0.36788],
        "stock_rotation_deg": 0,
        "workholding_offset_mm": [-77.9376, -45, 0],
        "workholding_rotation_deg": 90,
        "jaw_offset_mm": -74.5953,
        "choices": {
            "cutter": "Follow program",
            "fixture": "Saunders ¼-inch plate",
            "workholding": "Gen3 Hobby Mod Vise",
            "stock": "Current stock",
        },
        "visibility": {kind: kind != "outer" for kind in SceneSetupStore.COMPONENTS},
        "scope": "workarea",
    }


def test_restart_restores_independent_profile_stock_and_geometry(tmp_path):
    path = tmp_path / "scene-setups.json"
    first = setup_record()
    other = copy.deepcopy(first)
    other.update(stock_size_mm=[20, 30, 40], stock_origin_mm=[0, 0, 0], workholding_rotation_deg=0)
    store = SceneSetupStore(path)
    store.save("workshop", first)
    store.save("second-machine", other)
    restarted = SceneSetupStore(path)
    assert restarted.get("workshop") == first
    assert restarted.get("second-machine") == other
    assert restarted.get("unconfigured-machine") is None
    copy_of_setup = restarted.get("workshop")
    copy_of_setup["stock_size_mm"][0] = 1
    assert restarted.get("workshop")["stock_size_mm"][0] == 127


def test_save_merges_other_profile_updates_from_another_store(tmp_path):
    path = tmp_path / "scene-setups.json"
    a, b = SceneSetupStore(path), SceneSetupStore(path)
    a.save("first", setup_record())
    b.save("second", setup_record())
    assert set(SceneSetupStore(path).data) == {"first", "second"}


@pytest.mark.parametrize(
    "change",
    [
        {"stock_size_mm": [0, 20, 30]},
        {"stock_size_mm": [True, 20, 30]},
        {"stock_origin_mm": [float("nan"), 0, 0]},
        {"work_offset_mm": [-1001, 0, 0]},
        {"workholding_rotation_deg": float("inf")},
        {"unexpected": 1},
        {"choices": {"stock": "New stock…"}},
        {"visibility": {"outer": True}},
        {"scope": "machine"},
    ],
)
def test_invalid_draft_preserves_prior_file(tmp_path, change):
    path = tmp_path / "scene-setups.json"
    store = SceneSetupStore(path)
    store.save("workshop", setup_record())
    before = path.read_bytes()
    record = setup_record()
    record.update(change)
    with pytest.raises(ValueError):
        store.save("workshop", record)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"schema_version":4,"profiles":{}}',
        '{"schema_version":true,"profiles":{}}',
        '{"schema_version":1,"profiles":{},"surprise":1}',
        '{"schema_version":1,"schema_version":1,"profiles":{}}',
        json.dumps({"schema_version": 1, "profiles": {"workshop": {}}}),
        "[" * 2000 + "0" + "]" * 2000,
    ],
)
def test_corrupt_document_never_silently_overwritten(tmp_path, raw):
    path = tmp_path / "scene-setups.json"
    path.write_text(raw)
    store = SceneSetupStore(path)
    assert store.load_error
    assert store.get("workshop") is None
    with pytest.raises(ValueError, match="Repair"):
        store.save("workshop", setup_record())
    assert path.read_text() == raw


def test_corruption_after_loading_is_detected_before_save(tmp_path):
    path = tmp_path / "scene-setups.json"
    store = SceneSetupStore(path)
    store.save("workshop", setup_record())
    path.write_text("damaged externally")
    with pytest.raises(ValueError):
        store.save("workshop", setup_record())
    assert path.read_text() == "damaged externally"


def test_restore_only_calls_local_viewer_and_preserves_numeric_draft():
    record = setup_record()
    viewer = SimpleNamespace(configure_machine=Mock(), configure_workholding=Mock())
    workspace = SimpleNamespace(machine=SimpleNamespace(gcode_viewer=viewer, executeCommand=Mock()))
    restore_scene_geometry(workspace, record)
    viewer.configure_machine.assert_called_once_with(
        work_offset_mm=record["work_offset_mm"],
        stock_size_mm=record["stock_size_mm"],
        stock_origin_mm=record["stock_origin_mm"],
        stock_rotation_deg=record["stock_rotation_deg"],
        stock_model=None,
    )
    viewer.configure_workholding.assert_called_once_with(
        record["workholding_offset_mm"], record["workholding_rotation_deg"], record["jaw_offset_mm"]
    )
    workspace.machine.executeCommand.assert_not_called()
    assert workspace.simulation_geometry["size"] == record["stock_size_mm"]
    record["stock_size_mm"] = None
    restore_scene_geometry(workspace, record)
    assert "size" not in workspace.simulation_geometry


def test_capture_retains_selected_components_and_visibility():
    record = setup_record()
    viewer = SimpleNamespace(
        machine_setup=SimpleNamespace(
            **{key: record[key] for key in ("work_offset_mm", "stock_size_mm", "stock_origin_mm")}
        ),
        workholding_offset_mm=record["workholding_offset_mm"],
        workholding_rotation_deg=90,
        jaw_offset_mm=record["jaw_offset_mm"],
        machine_view_scope="workarea",
        cutter_visible=record["visibility"]["cutter"],
        machine_group_visibility={
            "fixed" if key == "outer" else key: value for key, value in record["visibility"].items() if key != "cutter"
        },
    )
    workspace = SimpleNamespace(
        machine=SimpleNamespace(gcode_viewer=viewer),
        component_choices={key: SimpleNamespace(text=value) for key, value in record["choices"].items()},
        component_checks={key: SimpleNamespace(active=not value) for key, value in record["visibility"].items()},
    )
    assert capture_scene_setup(workspace) == record


def test_atomic_replace_failure_preserves_existing_file_and_removes_temporary(tmp_path, monkeypatch):
    import carveracontroller.desktop_scene as scene

    path = tmp_path / "scene-setups.json"
    store = SceneSetupStore(path)
    store.save("workshop", setup_record())
    before = path.read_bytes()
    monkeypatch.setattr(scene.os, "replace", Mock(side_effect=OSError("write failed")))
    with pytest.raises(OSError, match="write failed"):
        store.save("other", setup_record())
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]
    assert set(store.data) == {"workshop"}


def test_legacy_scene_migrates_without_modifying_until_save(tmp_path):
    path = tmp_path / "scene-setups.json"
    legacy = setup_record()
    del legacy["stock_rotation_deg"]
    raw = json.dumps({"schema_version": 1, "profiles": {"workshop": legacy}})
    path.write_text(raw)
    store = SceneSetupStore(path)
    assert not store.load_error
    assert store.get("workshop")["stock_rotation_deg"] == 0
    assert path.read_text() == raw
    rotated = store.get("workshop")
    rotated["stock_rotation_deg"] = 37
    store.save("workshop", rotated)
    assert json.loads(path.read_text())["schema_version"] == 2
    assert SceneSetupStore(path).get("workshop")["stock_rotation_deg"] == 37


def test_version_two_cannot_silently_drop_rotation(tmp_path):
    path = tmp_path / "scene-setups.json"
    record = setup_record()
    del record["stock_rotation_deg"]
    path.write_text(json.dumps({"schema_version": 2, "profiles": {"workshop": record}}))
    store = SceneSetupStore(path)
    assert "requires stock orientation" in store.load_error
    with pytest.raises(ValueError, match="Repair"):
        store.save("workshop", setup_record())
