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


def test_section_planes_survive_library_and_portable_round_trip(tmp_path):
    record = layout()
    record["cutaway_state"] = {
        "setup_sha256": "a" * 64,
        "planes": {"stock": {"axis": 2, "coordinate_mm": 35.5, "keep_above": True}},
    }
    source = WorkspaceLayouts(tmp_path / "source.json")
    source.save(record)
    record["cutaway_state"]["planes"]["stock"]["coordinate_mm"] = 99
    loaded = WorkspaceLayouts(source.path)
    assert loaded.records[0]["cutaway_state"]["planes"]["stock"]["coordinate_mm"] == 35.5
    assert json.loads(source.path.read_text())["schema"] == 4
    portable = tmp_path / "section-layout.cvlayout"
    source.export_file(portable)
    target = WorkspaceLayouts(tmp_path / "target.json")
    assert target.import_file(portable) == 1
    assert target.records == source.records


@pytest.mark.parametrize("mutation", ["digest", "component", "axis", "coordinate", "side", "extra"])
def test_invalid_section_state_cannot_replace_saved_layout(tmp_path, mutation):
    store = WorkspaceLayouts(tmp_path / "layouts.json")
    store.save(layout())
    before = store.path.read_bytes()
    plane = {"axis": 2, "coordinate_mm": 35, "keep_above": False}
    state = {"setup_sha256": "a" * 64, "planes": {"stock": plane}}
    if mutation == "digest":
        state["setup_sha256"] = "not a digest"
    elif mutation == "component":
        state["planes"]["cutter"] = plane
    elif mutation == "axis":
        plane["axis"] = True
    elif mutation == "coordinate":
        plane["coordinate_mm"] = float("nan")
    elif mutation == "side":
        plane["keep_above"] = 1
    else:
        state["unexpected"] = 1
    record = layout()
    record["cutaway_state"] = state
    with pytest.raises(ValueError):
        store.save(record)
    assert store.path.read_bytes() == before


def test_legacy_layouts_and_duplicate_plane_fields_have_explicit_results(tmp_path):
    path = tmp_path / "layouts.json"
    path.write_text(json.dumps({"schema": 1, "layouts": [layout()]}))
    store = WorkspaceLayouts(path)
    assert store.load_error is None and store.records[0]["cutaway_state"] is None
    record = layout()
    record["cutaway_state"] = {"setup_sha256": "a" * 64, "planes": {}}
    encoded = json.dumps({"schema": 2, "layouts": [record]})
    encoded = encoded.replace('"planes": {}', '"planes": {}, "planes": {}')
    path.write_text(encoded)
    broken = WorkspaceLayouts(path)
    assert "Duplicate" in broken.load_error
    with pytest.raises(ValueError, match="Repair"):
        broken.save(layout())
    assert path.read_text() == encoded


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


def test_angled_plane_is_normalized_and_survives_portable_exchange(tmp_path):
    import json

    from carveracontroller.machine.workspace_layouts import validate_cutaway_state

    state = validate_cutaway_state(
        {
            "setup_sha256": "a" * 64,
            "planes": {"stock": {"axis": 2, "coordinate_mm": 4, "keep_above": False, "normal": [1, 1, 0]}},
        }
    )
    assert state["planes"]["stock"]["normal"] == pytest.approx([2**-0.5, 2**-0.5, 0])
    assert validate_cutaway_state(json.loads(json.dumps(state))) == state
    record = layout()
    record["cutaway_state"] = state
    library = WorkspaceLayouts(tmp_path / "angled.json")
    library.save(record)
    portable = tmp_path / "angled.cvlayout"
    library.export_file(portable)
    imported = WorkspaceLayouts(tmp_path / "imported.json")
    imported.import_file(portable)
    assert imported.records == library.records


def test_versioned_exploded_layouts_reject_ambiguous_schema_without_overwrite(tmp_path):
    record = validate_layout(layout())
    record["explosion_mm"] = 25
    path = tmp_path / "older.json"
    raw = json.dumps({"schema": 3, "layouts": [record]})
    path.write_text(raw)
    library = WorkspaceLayouts(path)
    assert "version 4" in library.load_error
    with pytest.raises(ValueError, match="Repair"):
        library.save(record)
    assert path.read_text() == raw
    raw_record = dict(record)
    raw_record.pop("explosion_mm")
    path.write_text(json.dumps({"schema": 4, "layouts": [raw_record]}))
    assert "explicit inspection separation" in WorkspaceLayouts(path).load_error
