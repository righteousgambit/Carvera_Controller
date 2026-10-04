"""Program shortcuts select for inspection, never transfer or execute."""

from unittest.mock import Mock

from carveracontroller.desktop_program_picker import ProgramBrowser
from carveracontroller.machine.program_places import ProgramPlaces
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_inspection import wait_for_inspection


def test_recent_and_favorite_programs_survive_reopen_and_distinguish_paths(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, upload, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    files = []
    for directory in ("a", "b"):
        path = tmp_path / directory / "part.nc"
        path.parent.mkdir()
        path.write_text("G21 G90\nT2 M6\nG0 X0 Y0 Z2\nG1 X8 F100\n")
        files.append(path)
    store = ProgramPlaces(tmp_path / "places.json")
    browser = ProgramBrowser(ws, places=store)
    browser.open()
    try:
        for path in files:
            browser.navigate(str(path))
            wait_for_inspection(browser)
            browser.favorite_button.trigger_action(duration=0)
            pump_frames(3)
        browser.choose_collection("favorites")
        assert [entry.path for entry in browser.entries] == [str(path) for path in files]
        row_text = "\n".join(row.text for row in browser.rows.children)
        assert str(files[0].parent) in row_text and str(files[1].parent) in row_text
        assert browser.path_field.disabled and browser.go_button.disabled
        assert browser.path_field.text == "Favorites"
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        assert browser.selected.path == str(files[0])
        pump_frames(5)
        browser.popup.export_to_png(str(tmp_path / "favorite-programs.png"))
    finally:
        browser.dismiss()
    reopened = ProgramBrowser(ws, places=ProgramPlaces(store.path))
    reopened.open()
    try:
        reopened.choose_collection("recent")
        assert [entry.path for entry in reopened.entries] == [str(files[0]), str(files[1])]
        reopened.choose_collection("favorites")
        assert len(reopened.entries) == 2
    finally:
        reopened.dismiss()
    send.assert_not_called()
    upload.assert_not_called()
    preview.assert_not_called()


def test_missing_favorite_can_be_removed_without_loading_an_old_selection(kivy_app, tmp_path):
    path = tmp_path / "missing.nc"
    store = ProgramPlaces(tmp_path / "places.json")
    store.toggle_favorite(path)
    browser = ProgramBrowser(kivy_app.root.desktop_workspace, places=store)
    browser.open()
    try:
        browser.choose_collection("favorites")
        assert not browser.entries[0].available
        browser.select(browser.entries[0])
        pump_frames(5)
        assert browser.inspection is None
        assert browser.preview_button.disabled and browser.upload_button.disabled
        assert "Unavailable" in browser.metadata.text
        assert browser.favorite_button.text == "Remove favorite"
        browser.favorite_button.trigger_action(duration=0)
        pump_frames(5)
        assert browser.entries == [] and browser.selected is None
        assert ProgramPlaces(store.path).favorites == []
    finally:
        browser.dismiss()
