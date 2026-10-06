"""Embedded libraries keep primary actions and editor space without dropping capabilities."""

from unittest.mock import Mock

import pytest

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.desktop_profiles import ProfileStore
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 600])
def test_compact_library_menus_keep_drafts_and_primary_editor_space(kivy_app, tmp_path, monkeypatch, width):
    from kivy.core.window import Window
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    store = ProfileStore(tmp_path / "profiles.json")
    machine = store.save_machine({"name": "Bench", "model": "C1"})
    cutter = store.save_tool({"name": "Cutter", "diameter": 6.35, "shank_diameter": 6.35, "length": 75})
    before = store.path.read_bytes()
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    library = ProfileLibrary(ws, store=store, embedded=True)
    library.select_record("machines", machine["id"])
    popup = Popup(content=library, size_hint=(None, None), size=(dp(width + 28), dp(690)))
    popup.open(animation=False)
    try:
        pump_frames(8)
        assert library.toolbar.height == dp(34)
        assert library.actions.height == dp(36)
        assert library.editor_scroll.height >= dp(160)
        assert library.kind_choice.text == "Machines"
        assert set(library.library_menu.values) == {"Import JSON", "Export JSON", "Close library"}
        assert "Revert draft" not in library.editor_menu.values
        library.fields["name"].text = "Unsaved bench"
        assert "Revert draft" in library.editor_menu.values
        library.kind_choice.focus = True
        library.kind_choice.keyboard_on_key_down(Window, (13, "enter"), "", [])
        library.kind_choice.keyboard_on_key_up(Window, (13, "enter"))
        library.kind_choice.keyboard_on_key_down(Window, (274, "down"), "", [])
        library.kind_choice.keyboard_on_key_down(Window, (13, "enter"), "", [])
        library.kind_choice.keyboard_on_key_up(Window, (13, "enter"))
        pump_frames(5)
        assert library.selected_kind == "tools"
        library.select_record("tools", cutter["id"])
        assert library.fields["name"].text == "Cutter"
        library.select_kind("machines")
        pump_frames(5)
        assert library.kind_choice.text == "Machines"
        assert library.fields["name"].text == "Unsaved bench"
        library.editor_menu.text = "Revert draft"
        pump_frames(5)
        assert library.fields["name"].text == "Bench"
        assert library.editor_menu.text == "More…"
        assert "Revert draft" not in library.editor_menu.values
        assert "Delete profile" in library.editor_menu.values
        delete = Mock()
        monkeypatch.setattr(library, "delete", delete)
        library.editor_menu.text = "Delete profile"
        delete.assert_called_once_with()
        file_action = Mock()
        monkeypatch.setattr(library, "_file_action", file_action)
        library.library_menu.text = "Import JSON"
        file_action.assert_called_once_with(False)
        assert library.library_menu.text == "Library actions…"
        file_action.reset_mock()
        library.library_menu.text = "Export JSON"
        file_action.assert_called_once_with(True)
        assert library.library_menu.text == "Library actions…"
        library.editor_menu.text = "Revert draft"
        assert library.fields["name"].text == "Bench"
        assert store.path.read_bytes() == before
        send.assert_not_called()
        library.export_to_png(str(tmp_path / f"compact-profile-chrome-{width}.png"))
    finally:
        popup.dismiss(animation=False)
        pump_frames(3)
