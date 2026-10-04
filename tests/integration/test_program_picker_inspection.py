import threading
from unittest.mock import Mock

from carveracontroller.desktop_program_picker import ProgramBrowser, ProgramEntry
from tests.integration.conftest import pump_frames


def wait_for_inspection(browser):
    for _ in range(40):
        pump_frames(2)
        if browser.inspection is not None:
            return
    raise AssertionError("Inspection did not finish")


def test_picker_shows_captured_geometry_and_missing_preview_tools_without_transfer(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, upload = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    file = tmp_path / "fixture.nc"
    file.write_text("G21 G90 G17 G94 G54\nT99 M6\nG0 X0 Y0 Z2\n(Operation: Face)\nG1 Z0 F100\nG1 X8\n")
    browser = ProgramBrowser(ws)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        assert "G21" in browser.metadata.text
        assert "Missing preview definitions: T99" in browser.excerpt.text
        assert "Face" in browser.excerpt.text
        pump_frames(3)
        assert browser.excerpt.cursor == (0, 0)
        assert browser.excerpt.scroll_y == 0
        assert browser.thumbnail.segments
        assert "geometry incomplete" in browser.inspection_note.text
        assert browser.rows.children[0].valign == "middle"
        browser.popup.export_to_png(str(tmp_path / "program-inspection.png"))
        send.assert_not_called()
        upload.assert_not_called()
    finally:
        browser.dismiss()


def test_slow_old_file_cannot_replace_new_selection_or_closed_picker(kivy_app, tmp_path, monkeypatch):
    from carveracontroller.machine import program_preview

    first, second = tmp_path / "first.nc", tmp_path / "second.nc"
    first.write_text("G21\nT1\n")
    second.write_text("G20\nT2\n")
    release, entered = threading.Event(), threading.Event()
    original = program_preview.inspect_program

    def controlled(path):
        if path == str(first):
            entered.set()
            release.wait(5)
        return original(path)

    monkeypatch.setattr(program_preview, "inspect_program", controlled)
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(ProgramEntry(first.name, str(first), False))
        for _ in range(20):
            pump_frames(2)
            if entered.is_set():
                break
        assert entered.is_set()
        browser.select(ProgramEntry(second.name, str(second), False))
        wait_for_inspection(browser)
        assert browser.inspection.tool_ids == (2,)
        release.set()
        pump_frames(20)
        assert browser.inspection.tool_ids == (2,)
        browser.select(ProgramEntry(first.name, str(first), False))
        browser.dismiss()
        previous = browser.excerpt.text
        pump_frames(20)
        assert browser.excerpt.text == previous
    finally:
        release.set()
        browser.dismiss()


def test_multi_frame_thumbnail_does_not_overlay_unregistered_frames(kivy_app, tmp_path):
    file = tmp_path / "frames.nc"
    file.write_text("G21 G90 G17 G94 G54\nG0 X0 Y0 Z1\nG1 X1 F100\nG55\nG1 X2\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        assert not browser.thumbnail.segments
        assert "Multiple work frames" in browser.inspection_note.text
    finally:
        browser.dismiss()


def test_program_picker_stacks_inspection_at_narrow_width(kivy_app, tmp_path):
    from kivy.core.window import Window
    from kivy.metrics import dp

    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser._resize(None, (dp(600), Window.height))
        pump_frames(10)
        assert browser.body.orientation == "vertical"
        assert browser.details.width <= browser.body.width + dp(1)
        viewport = browser.detail_content.parent
        assert browser.detail_content.height > viewport.height
        top = browser.detail_title.to_window(browser.detail_title.x, browser.detail_title.top)[1]
        assert top <= browser.details.to_window(browser.details.x, browser.details.top)[1]
        assert top >= browser.details.to_window(browser.details.x, browser.details.y)[1]
        assert browser.local_button.parent.cols == 2
        browser.popup.export_to_png(str(tmp_path / "program-picker-narrow.png"))
        browser._resize(None, (dp(1100), Window.height))
        pump_frames(10)
        assert browser.body.orientation == "horizontal"
    finally:
        browser._resize(None, Window.size)
        browser.dismiss()
