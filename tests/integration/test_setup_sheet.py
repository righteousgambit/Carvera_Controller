"""Setup handoff uses selected declarations and never commands the machine."""

import time
from unittest.mock import Mock

from carveracontroller import desktop_setup_sheet
from carveracontroller.machine.job_packages import JobPackage
from tests.integration.conftest import pump_frames


def test_sheet_export_is_readback_verified_and_inert(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    program = tmp_path / "program.nc"
    program.write_bytes(b"G21\nG0 X1\n")
    monkeypatch.setattr(ws.app, "selected_local_filename", str(program))
    monkeypatch.setattr(
        desktop_setup_sheet,
        "capture_recording_job",
        lambda _, **kwargs: JobPackage(
            name="program", program=b"", program_name="program.nc", stock={"size_mm": [127, 69, 51]}
        ),
    )
    destination = tmp_path / "handoff.html"
    chooser = Mock()
    monkeypatch.setattr(ws, "choose_profile_file", chooser)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    desktop_setup_sheet.export_setup_sheet(ws)
    assert chooser.call_args.kwargs["extension"] == ".html"
    chooser.call_args.args[0](str(program))
    assert program.read_bytes() == b"G21\nG0 X1\n"
    assert "separate HTML" in ws.package_note.text
    chooser.call_args.args[0](str(destination))
    deadline = time.monotonic() + 5
    while ws._setup_sheet_pending and time.monotonic() < deadline:
        pump_frames(2)
    assert not ws._setup_sheet_pending
    assert destination.exists() and "HTML SHA256" in ws.package_note.text
    assert "program.nc" in destination.read_text()
    send.assert_not_called()


def test_sheet_picker_rejects_changed_setup_or_closed_workspace(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws.app, "selected_local_filename", "before.nc")
    monkeypatch.setattr(
        desktop_setup_sheet,
        "capture_recording_job",
        lambda _, **kwargs: JobPackage(name="program", program=b"", program_name="program.nc"),
    )
    chooser = Mock()
    monkeypatch.setattr(ws, "choose_profile_file", chooser)
    desktop_setup_sheet.export_setup_sheet(ws)
    monkeypatch.setattr(ws.app, "selected_local_filename", "after.nc")
    destination = tmp_path / "handoff.html"
    chooser.call_args.args[0](str(destination))
    assert not destination.exists() and "changed" in ws.package_note.text
    monkeypatch.setattr(ws, "_profile_load_closed", True)
    desktop_setup_sheet.export_setup_sheet(ws)
    assert chooser.call_count == 1


def test_setup_sheet_capture_does_not_require_camera_fit(kivy_app, tmp_path, monkeypatch):
    from carveracontroller import desktop_job_packages

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws.app, "selected_local_filename", str(tmp_path / "example.nc"))
    camera = Mock(side_effect=ValueError("Unfitted camera draft"))
    monkeypatch.setattr(desktop_job_packages, "_camera_snapshot", camera)
    # This handoff contains no camera calibration, and cannot claim one.
    job, _checks, _owner = desktop_setup_sheet._capture(ws)
    assert job.camera_calibration is None
    camera.assert_not_called()
