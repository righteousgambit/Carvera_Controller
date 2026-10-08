from unittest.mock import Mock

from carveracontroller.desktop_program_picker import ProgramBrowser
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_inspection import wait_for_inspection


def test_revision_pin_compare_refresh_and_clear_never_load_or_transfer(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, upload, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    file = tmp_path / "revision.nc"
    file.write_text("G21 G90 G54\nT1 M6\nG0 X0 Y0 Z5\nG1 Z-2 F100\n")
    browser = ProgramBrowser(ws)
    browser.open()
    try:
        browser.navigate(str(file))
        wait_for_inspection(browser)
        browser.choose_detail("Compare")
        browser.comparison_pin.trigger_action(duration=0)
        pump_frames(3)
        digest = browser.comparison_baseline.digest
        file.write_text("G21 G90 G54\nT8 M6\nG0 X0 Y0 Z5\nG1 Z-4 F300\n")
        browser.navigate(str(file))
        wait_for_inspection(browser)
        assert browser.comparison_baseline.digest == digest != browser.inspection.digest
        assert browser.comparison_note.text.startswith("Captured bytes changed")
        assert browser.detail_tab_buttons["Compare"].right <= browser.detail_content.right - 10
        assert "Active tools changed" in browser.comparison_note.text
        assert "Z: -2.000…5.000 to -4.000…5.000" in browser.comparison_note.text
        assert browser.comparison_note.parent is browser.detail_content and browser.thumbnail.parent is None
        browser.popup.export_to_png(str(tmp_path / "program-revision-comparison.png"))
        browser.refresh()
        assert browser.comparison_baseline.digest == digest and browser.comparison_pin.disabled
        assert "Select a local program to compare" in browser.comparison_note.text
        assert "Active tools changed" not in browser.comparison_note.text
        browser.comparison_clear.trigger_action(duration=0)
        pump_frames(3)
        assert browser.comparison_baseline is None and browser.comparison_clear.disabled
        send.assert_not_called()
        upload.assert_not_called()
        preview.assert_not_called()
    finally:
        browser.dismiss()
