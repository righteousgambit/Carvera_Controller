"""Real window keyboard routing, recycled list reach and stale activation refusal."""

import time
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_program_picker import ProgramBrowser, ProgramEntry
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_inspection import wait_for_inspection, wait_for_listing


@pytest.mark.parametrize("width", [360, 1000])
def test_all_program_rows_reachable_without_inspection_or_transfer(kivy_app, tmp_path, monkeypatch, width):
    from kivy.core.window import Window
    from kivy.metrics import dp
    from kivy.uix.modalview import ModalView

    ws = kivy_app.root.desktop_workspace
    send, upload, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    browser = ProgramBrowser(ws)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        wait_for_listing(browser)
        browser._resize(None, (dp(width), Window.height))
        browser.entries = [
            ProgramEntry(f"program-{i:05d}.nc", str(tmp_path / f"program-{i:05d}.nc"), False) for i in range(10000)
        ]
        started = time.monotonic()
        browser._render_rows()
        publication = time.monotonic() - started
        pump_frames(8)
        assert len(browser.files.data) == 10000
        assert 0 < len(browser.rows.children) < 40
        allocated = len(browser.rows.children)
        old_row = browser.rows.children[0]
        old_entry, old_token = old_row.entry, old_row.listing_token
        started = time.monotonic()
        assert Window.dispatch("on_key_down", 279, 0, "", [])
        navigation = time.monotonic() - started
        pump_frames(8)
        assert browser.cursor_path.endswith("program-09999.nc")
        assert browser.files.scroll_y < 0.01
        assert any(row.selected and row.entry.name == "program-09999.nc" for row in browser.rows.children)
        assert browser.selected is None and browser.inspection is None
        assert browser.preview_button.disabled
        assert Window.dispatch("on_key_down", 278, 0, "", [])
        assert Window.dispatch("on_key_down", 281, 0, "", [])
        pump_frames(5)
        assert browser.cursor_path != browser.entries[0].path
        overlay = ModalView()
        overlay.open()
        try:
            assert not browser.keydown(Window, 279)
            assert not browser.keydown(Window, 27)
        finally:
            overlay.dismiss(animation=False)
        browser.path_field.focus = True
        assert not browser.keydown(Window, 279)
        assert not browser.keydown(Window, 13)
        assert browser.keydown(Window, 102, modifiers=["meta"])
        assert browser.search.focus and not browser.path_field.focus
        browser.search.text = "program-00003"
        pump_frames(5)
        assert browser.cursor_path is None and len(browser.files.data) == 1
        activate = Mock()
        monkeypatch.setattr(browser, "select", activate)
        browser.activate_row(old_entry, old_token)
        activate.assert_not_called()
        browser.search.focus = False
        # Clicking a row can retain keyboard focus while the recycle view
        # rebinds it. Its keyboard route must follow the current list cursor.
        focused_row = browser.rows.children[0]
        focused_row.focus = True
        assert browser.keydown(Window, 274)
        assert Window.dispatch("on_key_down", 13, 0, "", [])
        activate.assert_called_once_with(browser.entries[3])
        activate.reset_mock()
        focused_row.entry = old_entry
        assert focused_row.keyboard_on_key_down(Window, (13, "enter"), "", [])
        activate.assert_called_once_with(browser.entries[3])
        focused_row.focus = False
        token, entry = browser._listing_token(), browser.entries[3]
        browser._local_generation += 1
        browser.activate_row(entry, token)
        assert activate.call_count == 1
        browser.popup.export_to_png(str(tmp_path / f"program-navigation-{width}.png"))
        print(
            f"PROGRAM LIST {width}dp: 10000 entries, publication={publication:.6f}s, End dispatch={navigation:.6f}s, rendered={allocated}"
        )
        send.assert_not_called()
        upload.assert_not_called()
        preview.assert_not_called()
    finally:
        browser.dismiss()
        pump_frames(3)
    assert not browser.keydown(Window, 13)


def test_program_keyboard_opens_folder_then_inspects_without_loading(kivy_app, tmp_path, monkeypatch):
    from kivy.core.window import Window

    folder = tmp_path / "nested"
    folder.mkdir()
    program = folder / "fixture.nc"
    program.write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X5 F100\n")
    ws = kivy_app.root.desktop_workspace
    send, upload, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    browser = ProgramBrowser(ws)
    browser.local_path = str(tmp_path)
    browser._build()
    before = len(Window.get_property_observers("on_key_down"))
    try:
        browser.open()
        wait_for_listing(browser)
        assert Window.dispatch("on_key_down", 274, 0, "", [])
        assert browser.selected is None
        assert Window.dispatch("on_key_down", 13, 0, "", [])
        wait_for_listing(browser)
        assert browser.local_path == str(folder)
        assert browser.cursor_path is None
        assert Window.dispatch("on_key_down", 274, 0, "", [])
        assert Window.dispatch("on_key_down", 13, 0, "", [])
        wait_for_inspection(browser)
        assert browser.selected.path == str(program)
        assert browser.inspection.digest
        assert browser.thumbnail.segments
        assert browser.keydown(Window, 108, modifiers=["ctrl"])
        assert browser.path_field.focus
        assert not browser.keydown(Window, 13)
        assert Window.dispatch("on_key_down", 27, 0, "", [])
        pump_frames(5)
        assert not browser._reference_visible
        send.assert_not_called()
        upload.assert_not_called()
        preview.assert_not_called()
        assert program.read_text() == "G21 G90 G54\nG0 X0 Y0 Z5\nG1 X5 F100\n"
    finally:
        browser.dismiss()
        pump_frames(3)
    assert len(Window.get_property_observers("on_key_down")) == before
