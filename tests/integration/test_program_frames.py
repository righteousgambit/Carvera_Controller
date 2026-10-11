from unittest.mock import Mock

from carveracontroller.desktop_program_picker import ProgramBrowser
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_inspection import wait_for_inspection


def test_candidate_frame_selector_never_combines_unregistered_origins(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, upload, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    file = tmp_path / "frames.nc"
    file.write_text("G21 G90 G54\nG0 X0 Y0 Z0\nG1 X10 F100\nG55\nG0 X100 Y50 Z5\nG1 X120\n")
    browser = ProgramBrowser(ws)
    browser.open()
    try:
        browser.navigate(str(file))
        wait_for_inspection(browser)
        assert browser.frame_selector.values == ["G54", "G55"]
        assert {segment.wcs for segment in browser.thumbnail.segments} == {"G54"}
        assert "X: 0.000 to 10.000" in browser.path_bounds.text
        browser.frame_selector.text = "G55"
        pump_frames(5)
        assert {segment.wcs for segment in browser.thumbnail.segments} == {"G55"}
        assert "X: 100.000 to 120.000" in browser.path_bounds.text
        assert "unresolved moves" in browser.dependencies.text.lower()
        browser.popup.export_to_png(str(tmp_path / "program-frame-bounds.png"))
        browser.refresh()
        assert browser.frame_selector.disabled and browser.frame_selector.values == []
        assert not browser.thumbnail.segments and browser.dependencies is None
        send.assert_not_called()
        upload.assert_not_called()
        preview.assert_not_called()
    finally:
        browser.dismiss()
