"""Editor transactions preserve drafts independently from saved and active state."""

from unittest.mock import Mock

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
