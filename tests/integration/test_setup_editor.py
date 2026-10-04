"""Real setup editors keep drafts separate from active and persisted state."""

import copy
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_scene import SceneSetupStore, capture_scene_setup, restore_scene_geometry
from carveracontroller.desktop_setup_editor import open_setup_editor
from carveracontroller.desktop_view_state import capture_view
from tests.integration.conftest import pump_frames


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    baseline = capture_scene_setup(ws)
    geometry = copy.deepcopy(getattr(ws, "simulation_geometry", {}))
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "editor-machine"})
    monkeypatch.setattr(ws, "scene_setup_store", SceneSetupStore(tmp_path / "scene.json"))
    monkeypatch.setattr(ws, "setup_drafts", {}, raising=False)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    yield ws, send
    if getattr(ws, "setup_editor", None):
        ws.setup_editor.cancel()
    ws.scene_edit_in_progress = True
    try:
        for key, value in baseline["choices"].items():
            ws.component_choices[key].text = value
        restore_scene_geometry(ws, baseline)
        ws.simulation_geometry = geometry
    finally:
        ws.scene_edit_in_progress = False
    pump_frames(3)


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_cancel_and_close_have_distinct_draft_semantics(setup_workspace, kind):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, kind)
    key = next(iter(editor.fields))
    editor.fields[key].text = "invalid"
    assert editor.apply_button.disabled
    editor.keep()
    pump_frames(3)
    assert capture_scene_setup(ws) == before
    assert not ws.scene_setup_store.path.exists()
    editor = open_setup_editor(ws, kind)
    assert editor.fields[key].text == "invalid"
    editor.cancel()
    pump_frames(3)
    editor = open_setup_editor(ws, kind)
    assert editor.fields[key].text != "invalid"
    assert capture_scene_setup(ws) == before
    send.assert_not_called()


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_apply_updates_only_reviewed_local_setup(setup_workspace, kind):
    ws, send = setup_workspace
    original_profile = dict(ws.selected_machine_profile)
    editor = open_setup_editor(ws, kind)
    key = ("stock_size_mm", 0) if kind == "stock" else ("workholding_offset_mm", 0)
    editor.fields[key].text = "1/4 in"
    assert "6.35 mm" in editor.summary.text
    assert editor.apply()
    current = capture_scene_setup(ws)
    assert current[key[0]][0] == pytest.approx(6.35)
    assert ws.scene_setup_store.get("editor-machine") == current
    assert ws.selected_machine_profile == original_profile
    assert not ws.setup_drafts
    send.assert_not_called()


@pytest.mark.parametrize("kind", ["stock", "workholding"])
def test_failed_save_restores_geometry_view_and_keeps_editable_draft(setup_workspace, monkeypatch, kind):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    view = capture_view(ws.machine.gcode_viewer)
    geometry = copy.deepcopy(getattr(ws, "simulation_geometry", {}))
    editor = open_setup_editor(ws, kind)
    key = ("stock_size_mm", 0) if kind == "stock" else ("workholding_offset_mm", 0)
    editor.fields[key].text = "12"
    monkeypatch.setattr(ws.scene_setup_store, "save", Mock(side_effect=OSError("disk full")))
    assert editor.apply() is False
    assert "disk full" in editor.note.text
    assert editor.fields[key].text == "12"
    assert capture_scene_setup(ws) == before
    assert capture_view(ws.machine.gcode_viewer) == view
    assert ws.simulation_geometry == geometry
    assert not ws.scene_setup_store.path.exists()
    assert not ws.scene_edit_in_progress
    send.assert_not_called()


def test_changed_scene_or_profile_requires_reload_before_apply(setup_workspace):
    ws, send = setup_workspace
    editor = open_setup_editor(ws, "workholding")
    editor.fields["workholding_offset_mm", 0].text = "10"
    ws.machine.gcode_viewer.configure_workholding((20, 21, 22), 90, 4)
    assert editor.apply() is False
    assert "active setup changed" in editor.note.text
    assert ws.machine.gcode_viewer.workholding_offset_mm == (20, 21, 22)
    editor.reload()
    assert editor.fields["workholding_offset_mm", 0].text == "20"
    editor.fields["workholding_offset_mm", 0].text = "30"
    ws.selected_machine_profile = {"id": "different-machine"}
    assert editor.apply() is False
    editor.reload()
    assert "Machine profile changed" in editor.note.text
    assert ws.machine.gcode_viewer.workholding_offset_mm == (20, 21, 22)
    send.assert_not_called()


def test_external_save_is_preserved_and_preview_rolls_back(setup_workspace):
    ws, send = setup_workspace
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "workholding")
    editor.fields["workholding_offset_mm", 0].text = "10"
    newer = copy.deepcopy(before)
    newer["workholding_offset_mm"][0] = 33
    SceneSetupStore(ws.scene_setup_store.path).save("editor-machine", newer)
    newer_bytes = ws.scene_setup_store.path.read_bytes()
    assert editor.apply() is False
    assert "Saved scene changed" in editor.note.text
    assert ws.scene_setup_store.path.read_bytes() == newer_bytes
    assert capture_scene_setup(ws) == before
    editor.reload()
    assert "reload the machine profile" in editor.note.text.lower()
    assert editor.fields["workholding_offset_mm", 0].text == "10"
    send.assert_not_called()


def test_corrupt_scene_can_be_reported_without_losing_editor(setup_workspace):
    ws, send = setup_workspace
    ws.scene_setup_store.path.write_text("not json")
    editor = open_setup_editor(ws, "stock")
    editor.fields["stock_size_mm", 0].text = "15"
    assert editor.apply() is False
    assert "Scene file unavailable" in editor.note.text
    assert ws.scene_setup_store.path.read_text() == "not json"
    editor.keep()
    editor = open_setup_editor(ws, "stock")
    assert editor.fields["stock_size_mm", 0].text == "15"
    # The failed write still refuses the corrupt source, even with a saved draft.
    assert editor.apply() is False
    assert ws.scene_setup_store.path.read_text() == "not json"
    send.assert_not_called()


def test_render_failure_restores_data_even_if_redraw_is_unavailable(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    viewer = ws.machine.gcode_viewer
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    editor.fields["stock_size_mm", 0].text = "15"
    with monkeypatch.context() as patch:
        patch.setattr(viewer, "machine_visible", True)
        patch.setattr(viewer, "_build_machine_scene", Mock(side_effect=OSError("mesh unavailable")))
        assert editor.apply() is False
        assert "prior geometry restored, redraw unavailable" in editor.note.text
        assert capture_scene_setup(ws) == before
        assert not ws.scene_setup_store.path.exists()
        assert not ws.scene_edit_in_progress
        send.assert_not_called()


def test_editor_open_suspends_keyboard_jog_and_reuses_existing_dialog(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    monkeypatch.setattr(ws.machine, "keyboard_jog_control", True)
    disable = Mock()
    monkeypatch.setattr(ws.machine, "toggle_keyboard_jog_control", disable)
    editor = open_setup_editor(ws, "stock")
    disable.assert_called_once_with(disable=True)
    editor.fields["stock_size_mm", 0].text = "15"
    assert open_setup_editor(ws, "stock") is editor
    assert editor.fields["stock_size_mm", 0].text == "15"
    send.assert_not_called()


def test_untouched_fields_preserve_full_precision_and_named_stock(setup_workspace):
    ws, send = setup_workspace
    ws.scene_edit_in_progress = True
    try:
        ws.component_choices["stock"].text = "Precision stock"
        ws.machine.gcode_viewer.configure_machine(
            stock_size_mm=(127.123456789123, 69.418212345678, 50.876212345678),
            stock_origin_mm=(-118.6123456789, -94.7091234567, -0.36788123456),
        )
    finally:
        ws.scene_edit_in_progress = False
    before = capture_scene_setup(ws)
    editor = open_setup_editor(ws, "stock")
    assert editor.candidate() == before
    assert editor.apply_button.disabled
    editor.fields["work_offset_mm", 0].text = "-200"
    candidate = editor.candidate()
    assert candidate["stock_size_mm"] == before["stock_size_mm"]
    assert candidate["stock_origin_mm"] == before["stock_origin_mm"]
    assert candidate["choices"]["stock"] == before["choices"]["stock"]
    assert editor.apply()
    assert ws.scene_setup_store.read_current("editor-machine")["stock_size_mm"] == before["stock_size_mm"]
    send.assert_not_called()
