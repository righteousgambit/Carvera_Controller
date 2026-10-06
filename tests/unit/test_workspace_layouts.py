"""Presentation library limits, validation and retained malformed evidence."""

import copy
import json

import pytest

from carveracontroller.machine.simulation_bookmarks import VIEW_FIELDS
from carveracontroller.machine.workspace_layouts import WorkspaceLayouts, validate_layout


def layout():
    return {
        "name": "Inspect",
        "media_share": 0.5,
        "camera_visible": True,
        "section": "Setup",
        "task": "Holes",
        "scroll": 0.75,
        "view": {**dict.fromkeys(VIEW_FIELDS, 1.0), "orthographic": False},
    }


@pytest.mark.parametrize(
    "key,value",
    [
        ("media_share", True),
        ("media_share", float("nan")),
        ("media_share", 0.9),
        ("camera_visible", 1),
        ("name", " "),
        ("task", ""),
        ("scroll", True),
        ("scroll", float("inf")),
        ("scroll", -0.1),
    ],
)
def test_invalid_layouts_rejected_before_save(tmp_path, key, value):
    store = WorkspaceLayouts(tmp_path / "layouts.json")
    record = layout()
    record[key] = value
    with pytest.raises(ValueError):
        store.save(record)
    assert not store.path.exists() and not store.records


def test_round_trip_replacement_delete_and_independent_copies(tmp_path):
    path = tmp_path / "layouts.json"
    store = WorkspaceLayouts(path)
    record = layout()
    store.save(record)
    record["view"]["m_zoom"] = 5
    assert store.records[0]["view"]["m_zoom"] == 1
    replacement = layout()
    replacement["media_share"] = 0.6
    store.save(replacement)
    assert len(store.records) == 1
    assert WorkspaceLayouts(path).records == store.records
    store.delete("Inspect")
    assert WorkspaceLayouts(path).records == []


def test_malformed_library_is_retained_and_cannot_be_overwritten(tmp_path):
    path = tmp_path / "layouts.json"
    raw = b'{"schema": true, "layouts": []}'
    path.write_bytes(raw)
    store = WorkspaceLayouts(path)
    assert store.load_error and store.records == []
    with pytest.raises(ValueError, match="Repair"):
        store.save(layout())
    assert path.read_bytes() == raw


def test_duplicate_and_oversized_libraries_are_retained(tmp_path):
    path = tmp_path / "layouts.json"
    path.write_text(json.dumps({"schema": 1, "layouts": [layout(), layout()]}))
    assert WorkspaceLayouts(path).load_error
    path.write_bytes(b" " * (256 * 1024 + 1))
    assert WorkspaceLayouts(path).load_error == "Workspace layouts exceed 256 KiB"


def test_reading_position_requires_a_task():
    record = copy.deepcopy(layout())
    record["task"] = None
    with pytest.raises(ValueError, match="requires a task"):
        validate_layout(record)
    record["scroll"] = None
    assert validate_layout(record)["task"] is None


def test_portable_exchange_merges_without_overwriting_or_applying(tmp_path):
    import hashlib

    source = WorkspaceLayouts(tmp_path / "source.json")
    source.save(layout())
    exported = tmp_path / "layouts.cvlayout"
    digest = source.export_file(exported)
    assert digest == hashlib.sha256(exported.read_bytes()).hexdigest()
    with pytest.raises(FileExistsError):
        source.export_file(exported)
    target = WorkspaceLayouts(tmp_path / "target.json")
    assert target.import_file(exported) == 1
    assert target.import_file(exported) == 0
    assert target.records == source.records
    changed = layout()
    changed["media_share"] = 0.6
    target.save(changed)
    before = target.path.read_bytes()
    with pytest.raises(ValueError, match="conflict"):
        target.import_file(exported)
    assert target.path.read_bytes() == before and target.records[0]["media_share"] == 0.6


def test_invalid_portable_import_preserves_destination_and_source(tmp_path):
    target = WorkspaceLayouts(tmp_path / "target.json")
    target.save(layout())
    before = target.path.read_bytes()
    incoming = tmp_path / "bad.cvlayout"
    incoming.write_text('{"schema": 1, "layouts": [{"name":"invalid"}]}')
    raw = incoming.read_bytes()
    with pytest.raises(ValueError):
        target.import_file(incoming)
    assert target.path.read_bytes() == before and incoming.read_bytes() == raw


def test_legacy_camera_defaults_and_framing_round_trip(tmp_path):
    store = WorkspaceLayouts(tmp_path / "layouts.json")
    record = layout()
    store.save(record)
    assert store.records[0]["camera_view"] == {"zoom": 1, "center_x": 0.5, "center_y": 0.5}
    record["camera_view"] = {"zoom": 3, "center_x": 0.3, "center_y": 0.6}
    store.save(record)
    assert WorkspaceLayouts(store.path).records[0]["camera_view"] == record["camera_view"]
    original = store.path.read_bytes()
    for framing in (
        {"zoom": True, "center_x": 0.5, "center_y": 0.5},
        {"zoom": 9, "center_x": 0.5, "center_y": 0.5},
        {"zoom": 2, "center_x": float("nan"), "center_y": 0.5},
    ):
        record["camera_view"] = framing
        with pytest.raises(ValueError):
            store.save(record)
        assert store.path.read_bytes() == original
