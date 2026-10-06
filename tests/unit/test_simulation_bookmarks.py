import json
from types import SimpleNamespace

import pytest

from carveracontroller.machine.simulation_bookmarks import VIEW_FIELDS, BookmarkStore, revision_hash


def view():
    return {**dict.fromkeys(VIEW_FIELDS, 1.0), "orthographic": False}


def add(store, **changes):
    return store.add(
        **{
            **{
                "name": "First engagement",
                "profile_id": "machine-1",
                "program_hash": "a" * 64,
                "setup_hash": "b" * 64,
                "line": 14,
                "source": "G1 X10",
                "tool": 17,
                "view": view(),
            },
            **changes,
        }
    )


def test_persistence_identity_and_stale_revision_checks(tmp_path):
    path = tmp_path / "bookmarks.json"
    store = BookmarkStore(path)
    item = add(store)
    restored = BookmarkStore(path)
    assert restored.items == [item]
    current = {"profile_id": "machine-1", "program_hash": "a" * 64, "setup_hash": "b" * 64}
    assert restored.mismatch(item, **current) is None
    for key, value, reason in (
        ("profile_id", "machine-2", "Different machine"),
        ("program_hash", "c" * 64, "Program revision"),
        ("setup_hash", "d" * 64, "Setup or tool"),
    ):
        assert reason in restored.mismatch(item, **{**current, key: value})
    restored.delete(item["id"])
    assert BookmarkStore(path).items == []


@pytest.mark.parametrize(
    "change",
    [
        {"line": True},
        {"line": 0},
        {"tool": -1},
        {"name": " "},
        {"program_hash": "not a digest"},
        {"view": {**view(), "m_zoom": 0}},
        {"view": {**view(), "m_distance": float("nan")}},
        {"view": {**view(), "orthographic": 1}},
    ],
)
def test_invalid_points_preserve_existing_library(tmp_path, change):
    store = BookmarkStore(tmp_path / "bookmarks.json")
    add(store)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        add(store, **change)
    assert store.path.read_bytes() == before


def test_corrupt_library_is_preserved_instead_of_overwritten(tmp_path):
    path = tmp_path / "bookmarks.json"
    raw = '{"schema":1,"schema":1,"bookmarks":[]}'
    path.write_text(raw)
    store = BookmarkStore(path)
    assert "Duplicate" in store.load_error
    with pytest.raises(ValueError, match="Repair"):
        add(store)
    assert path.read_text() == raw


def test_atomic_replace_failure_leaves_original_library(tmp_path, monkeypatch):
    store = BookmarkStore(tmp_path / "bookmarks.json")
    add(store)
    before = store.path.read_bytes()
    monkeypatch.setattr(
        "carveracontroller.machine.simulation_bookmarks.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("disk failure")),
    )
    with pytest.raises(OSError):
        add(store)
    assert store.path.read_bytes() == before and len(store.items) == 1
    assert not list(tmp_path.glob(".bookmarks-*"))


def test_revision_digest_is_order_independent_and_rejects_nonfinite():
    assert revision_hash({"a": 1, "b": 2}) == revision_hash({"b": 2, "a": 1})
    with pytest.raises(ValueError):
        revision_hash({"a": float("inf")})


def test_other_writer_is_preserved_and_blank_source_is_allowed(tmp_path):
    first = BookmarkStore(tmp_path / "bookmarks.json")
    second = BookmarkStore(first.path)
    item = add(first, source="")
    with pytest.raises(ValueError, match="changed elsewhere"):
        add(second)
    assert BookmarkStore(first.path).items == [item]


def test_bookmark_native_widgets_restore_preview_and_refuse_changed_setup(tmp_path, monkeypatch):
    from carveracontroller.desktop_bookmarks import BookmarkPanel
    from carveracontroller.desktop_operations import OperationPanel
    from carveracontroller.machine.program_operations import ProgramOperations

    calls = []
    viewer = SimpleNamespace(
        **dict.fromkeys(VIEW_FIELDS, 1.0),
        _ortho_projection=False,
        set_operation_highlight=lambda *_: True,
        pose_mode="Preview",
        set_distance_by_lineidx=lambda *args: calls.append(args),
        update_proj=lambda: calls.append("projection"),
        update_view=lambda: calls.append("view"),
        canvas=SimpleNamespace(ask_update=lambda: calls.append("redraw")),
    )
    workspace = SimpleNamespace(
        machine=SimpleNamespace(gcode_viewer=viewer),
        selected_machine_profile={"id": "machine-1"},
        enter_preview=lambda: calls.append("preview"),
    )
    panel = OperationPanel(workspace)
    panel.generation = 1
    panel._loaded(1, ProgramOperations.from_text("G21 G90 G94 G54\nT17 M6\nG0 X0 Y0 Z0\nG1 X10 F600"), None)
    bookmarks = BookmarkPanel(panel, BookmarkStore(tmp_path / "bookmarks.json"))
    monkeypatch.setattr(
        "carveracontroller.desktop_bookmarks.capture_bookmark_context", lambda _: ("machine-1", "b" * 64)
    )
    panel.inspect_line(4)
    bookmarks.name.text = "First cut"
    bookmarks.save()
    item = bookmarks.store.items[0]
    assert item["line"] == 4 and item["tool"] == 17 and not calls
    viewer.m_xRot = 20
    bookmarks.go(item)
    assert viewer.m_xRot == 1 and calls == ["preview", (4, 0), "projection", "view", "redraw"]
    calls.clear()
    monkeypatch.setattr(
        "carveracontroller.desktop_bookmarks.capture_bookmark_context", lambda _: ("machine-1", "c" * 64)
    )
    bookmarks.go(item)
    assert not calls and "Setup or tool geometry changed" in bookmarks.note.text
    assert BookmarkStore(bookmarks.store.path).items == [item]
    bookmarks.delete(item["id"])
    assert not bookmarks.store.items


def test_loaded_geometry_and_tool_edits_change_context(monkeypatch):
    from carveracontroller.desktop_bookmarks import capture_bookmark_context

    monkeypatch.setattr("carveracontroller.desktop_bookmarks.capture_scene_setup", lambda _: {"stock": [10, 20, 30]})
    component = SimpleNamespace(components=[{"vertices": [1, 2, 3]}], atc={}, workholding={})
    viewer = SimpleNamespace(
        machine_component_profiles={"fixture": component},
        machine_profile=None,
        preview_tool_override=None,
        tool_table={},
    )
    workspace = SimpleNamespace(
        machine=SimpleNamespace(gcode_viewer=viewer),
        selected_machine_profile={"id": "machine-1"},
        profile_store=SimpleNamespace(data={"tools": [{"diameter": 6.35}]}),
        loaded_toolset=None,
    )
    original = capture_bookmark_context(workspace)
    # Cached loaded geometry must retain the exact old bookmark identity.
    component.geometry_json = json.dumps(
        {"components": component.components, "atc": component.atc, "workholding": component.workholding},
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    assert capture_bookmark_context(workspace) == original
    del component.geometry_json
    component.components[0]["vertices"][0] = 4
    changed = capture_bookmark_context(workspace)
    assert original != changed
    workspace.profile_store.data["tools"][0]["diameter"] = 3.175
    assert capture_bookmark_context(workspace) != changed


def test_duplicate_identity_rejected(tmp_path):
    store = BookmarkStore(tmp_path / "bookmarks.json")
    item = add(store)
    store.path.write_text(json.dumps({"schema": 1, "bookmarks": [item, item]}))
    assert "Duplicate bookmark identity" in BookmarkStore(store.path).load_error


def test_view_rejects_unrepresentable_integer_without_mutating_input(tmp_path):
    from copy import deepcopy
    from types import MappingProxyType

    from carveracontroller.machine.simulation_bookmarks import validate_view

    values = {**view(), "m_xRot": 10**1000}
    before = deepcopy(values)
    with pytest.raises(ValueError, match="bounded"):
        validate_view(values)
    assert values == before
    readonly = MappingProxyType(view())
    assert validate_view(readonly) == view()
    assert add(BookmarkStore(tmp_path / "readonly.json"), view=readonly)["view"] == view()
    store = BookmarkStore(tmp_path / "bookmarks.json")
    add(store)
    raw = store.path.read_bytes()
    with pytest.raises(ValueError):
        add(store, view=values)
    assert store.path.read_bytes() == raw


def test_bookmark_read_is_bounded_and_rejects_oversized_changed_library(tmp_path, monkeypatch):
    store = BookmarkStore(tmp_path / "bookmarks.json")
    add(store)
    items = list(store.items)
    monkeypatch.setattr(BookmarkStore, "MAX_BYTES", 64)
    store.path.write_bytes(b" " * 10000)
    with pytest.raises(ValueError, match="exceeds"):
        store.delete(items[0]["id"])
    assert store.items == items and store.path.read_bytes() == b" " * 10000
    assert "exceeds" in BookmarkStore(store.path).load_error


def test_bookmark_save_readback_failure_does_not_publish_success(tmp_path, monkeypatch):
    store = BookmarkStore(tmp_path / "bookmarks.json")
    reads = [None, b"changed after replacement"]
    monkeypatch.setattr(store, "_read_bytes", lambda: reads.pop(0))
    with pytest.raises(OSError, match="readback"):
        add(store)
    assert store.items == [] and store._disk_hash is None
    assert len(BookmarkStore(store.path).items) == 1  # Replacement happened; caller must reopen.


@pytest.mark.parametrize("width", [320, 1200])
@pytest.mark.parametrize(
    "program_hash,state", [("a" * 64, "Program matches"), ("c" * 64, "Program changed"), (None, "Load saved program")]
)
def test_bookmark_rows_keep_metadata_visible_without_writing(tmp_path, width, program_hash, state):
    from kivy.clock import Clock

    from carveracontroller.desktop_bookmarks import BookmarkPanel

    store = BookmarkStore(tmp_path / "bookmarks.json")
    item = add(store, name="Long saved simulation point " * 3)
    before = store.path.read_bytes()
    operations = SimpleNamespace(
        workspace=SimpleNamespace(selected_machine_profile={"id": "machine-1"}),
        program=SimpleNamespace(file_hash=program_hash) if program_hash else None,
        _reveal=lambda *_: None,
    )
    panel = BookmarkPanel(operations, store, width=width, size_hint_x=None)
    panel.toggle_expanded()
    for _ in range(12):
        Clock.tick()
    row = panel.rows.children[0]
    info = row.children[1]
    detail, button = info.children
    assert button.text == item["name"]
    assert detail.text == f"Line 14 · T17 · {state}"
    assert detail.height >= detail.texture_size[1] > 0
    assert row.height >= button.height + detail.height
    assert detail.width <= width and panel.scroll.height <= 180
    assert store.path.read_bytes() == before
