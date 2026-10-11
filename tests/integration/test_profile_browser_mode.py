"""Compact browsing uses the full pane without saving or dropping editor drafts."""

import json
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.desktop_profiles import ProfileStore, validate_library
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_full_pane_profile_browser_selection_paging_and_drafts(kivy_app, monkeypatch, tmp_path, width):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    data = validate_library(
        {
            "schema": 1,
            "machines": [],
            "toolsets": [],
            "tools": [
                {"id": f"tool-{i}", "name": f"Cutter {i:03}", "diameter": 6.35, "shank_diameter": 6.35}
                for i in range(35)
            ],
        }
    )
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(data))
    store = ProfileStore(path)
    before = path.read_bytes()
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    library = ProfileLibrary(ws, store=store, embedded=True)
    library.select_record("tools", "tool-0")
    popup = Popup(content=library, size_hint=(None, None), size=(dp(width + 28), dp(700)))
    popup.open(animation=False)
    try:
        pump_frames(8)
        library.fields["name"].text = "Unsaved cutter draft"
        library.fields["name"].focus = True
        library.browser_toggle.dispatch("on_release")
        pump_frames(8)
        assert library.editor_card.parent is None
        assert not library.fields["name"].focus
        assert library.list_card.parent is library.body
        assert library.list_scroll.height > dp(300)
        assert library.browser_toggle.text.startswith("Back to editor")
        library.search.text = "Cutter 034"
        pump_frames(10, sleep=0.02)
        assert [r["id"] for r in library.matches] == ["tool-34"]
        row = next(w for w in library.list_items.children if getattr(w, "text", "").startswith("Cutter 034"))
        row.dispatch("on_release")
        pump_frames(8)
        assert library.selected_id == "tool-34"
        assert not library.browser_expanded and library.editor_card.parent is library.body
        assert library.fields["name"].text == "Cutter 034"
        library.select_record("tools", "tool-0")
        assert library.fields["name"].text == "Unsaved cutter draft"
        library.browser_toggle.dispatch("on_release")
        library.search.text = ""
        pump_frames(10, sleep=0.02)
        next(w for w in library.list_items.walk(restrict=True) if getattr(w, "text", "") == "Next").dispatch(
            "on_release"
        )
        pump_frames(5)
        assert library.page_index == 1
        assert {r["id"] for r in library.matches[30:]} == {"tool-30", "tool-31", "tool-32", "tool-33", "tool-34"}
        library.export_to_png(str(tmp_path / f"profile-browse-{width}.png"))
        library.new_button.dispatch("on_release")
        pump_frames(6)
        assert library.selected_id is None and library.editor_card.parent is library.body
        library.fields["name"].text = "Unsaved new tool"
        library.browser_toggle.dispatch("on_release")
        pump_frames(5)
        popup.size = (dp(1128), dp(700))
        pump_frames(8)
        assert library.editor_card.parent is library.body
        assert library.fields["name"].text == "Unsaved new tool"
        popup.size = (dp(width + 28), dp(700))
        pump_frames(8)
        assert library.editor_card.parent is None
        library.browser_toggle.dispatch("on_release")
        pump_frames(5)
        assert library.fields["name"].text == "Unsaved new tool"
        assert library.editor_scroll.height >= dp(160)
        assert path.read_bytes() == before
        send.assert_not_called()
        library.export_to_png(str(tmp_path / f"profile-editor-{width}.png"))
    finally:
        popup.dismiss(animation=False)
        pump_frames(3)
