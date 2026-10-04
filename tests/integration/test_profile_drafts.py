"""Editor transactions preserve drafts independently from saved and active state."""

from unittest.mock import Mock

import pytest

from carveracontroller.desktop_profiles import ProfileLibrary
from carveracontroller.machine.desktop_profiles import ProfileStore


def test_profile_switch_preserves_invalid_draft_and_revert_restores_saved(kivy_app, tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    first = store.save_machine({"name": "First", "model": "C1", "host": "192.0.2.1"})
    second = store.save_machine({"name": "Second", "model": "C1", "host": "192.0.2.2"})
    ws = kivy_app.root.desktop_workspace
    active = ws.selected_machine_profile
    library = ProfileLibrary(ws, store=store)
    library._edit(first)
    library.fields["name"].text = "Draft name"
    library.fields["port"].text = "invalid"
    assert "2 changed fields" in library.draft_status.text
    library._edit(second)
    library._edit(first)
    assert library.fields["name"].text == "Draft name"
    assert library.fields["port"].text == "invalid"
    before = store.path.read_bytes()
    assert library.save() is None
    assert store.path.read_bytes() == before
    assert ws.selected_machine_profile is active
    library.revert()
    assert library.fields["name"].text == "First"
    assert library.fields["port"].text == "2222"
    assert library.revert_button.disabled
    assert store.path.read_bytes() == before


def test_kind_switch_preserves_new_draft_and_save_clears_it(kivy_app, tmp_path, monkeypatch):
    store = ProfileStore(tmp_path / "profiles.json")
    ws = kivy_app.root.desktop_workspace
    load = Mock()
    monkeypatch.setattr(ws, "apply_tool_profile", load)
    library = ProfileLibrary(ws, store=store)
    library.select_kind("tools")
    library.new()
    library.fields["name"].text = "Imperial draft"
    library.fields["diameter"].text = "1/4 in"
    library.fields["shank_diameter"].text = "1/4 in"
    library.select_kind("machines")
    library.select_kind("tools")
    assert library.fields["name"].text == "Imperial draft"
    assert library.fields["diameter"].text == "1/4 in"
    saved = library.save()
    assert saved["diameter"] == 6.35
    assert not library.drafts
    assert library.revert_button.disabled
    load.assert_not_called()
    library.fields["name"].text = "Applied draft"
    library.apply()
    load.assert_called_once()
    assert load.call_args.args[0]["name"] == "Applied draft"
    assert not library.drafts


def test_tool_editor_drawing_tracks_focus_edits_invalidity_and_revert(kivy_app, tmp_path, monkeypatch):
    from kivy.uix.popup import Popup

    from tests.integration.conftest import pump_frames

    store = ProfileStore(tmp_path / "profiles.json")
    saved = store.save_tool(
        {
            "name": "Illustrated cutter",
            "diameter": 6.35,
            "shank_diameter": 6.35,
            "length": 75,
            "flute_length": 12,
            "stickout": 30,
        }
    )
    before = store.path.read_bytes()
    ws = kivy_app.root.desktop_workspace
    apply = Mock()
    monkeypatch.setattr(ws, "apply_tool_profile", apply)
    library = ProfileLibrary(ws, store=store)
    library.select_kind("tools")
    library._edit(saved)
    popup = Popup(title="Illustrated draft", content=library, size_hint=(0.9, 0.9))
    popup.open()
    try:
        pump_frames(8)
        assert library.tool_drawing.parent is library.tool_drawing_card
        library.fields["stickout"].focus = True
        library.fields["stickout"].text = "1.5 in"
        pump_frames(4)
        drawing = library.tool_drawing
        assert drawing.selected_dimension == "stickout"
        assert drawing.definition.stickout == pytest.approx(38.1)
        assert "38.1 mm" in library.tool_drawing_status.text
        assert drawing.dimensions[-1].value == pytest.approx(36.9)
        assert drawing.annotations[2].opacity == 1
        assert drawing.annotations[0].opacity == 0
        library.export_to_png(str(tmp_path / "illustrated-stickout.png"))
        library.fields["stickout"].text = "100"
        pump_frames(4)
        assert library.tool_drawing.parent is None
        assert "exceed" in library.tool_drawing_status.text
        assert store.path.read_bytes() == before
        library.revert()
        pump_frames(4)
        assert library.tool_drawing.parent is library.tool_drawing_card
        assert library.tool_drawing.definition.stickout == 30
        library.fields["diameter"].focus = True
        pump_frames(4)
        assert library.tool_drawing.selected_dimension == "diameter"
        library.export_to_png(str(tmp_path / "illustrated-diameter.png"))
        from kivy.core.window import Window

        original_size = Window.size
        try:
            Window.size = (1100, 850)
            pump_frames(8)
            assert library.tool_drawing_card.top <= library.editor_description.y
            assert library.editor_scroll.height > 100
            assert library.actions.top <= library.editor_scroll.y
            library.export_to_png(str(tmp_path / "illustrated-editor-narrow.png"))
        finally:
            Window.size = original_size
            pump_frames(3)
        library.select_kind("machines")
        pump_frames(3)
        assert library.tool_drawing_card is None
        assert store.path.read_bytes() == before
        apply.assert_not_called()
    finally:
        popup.dismiss()
