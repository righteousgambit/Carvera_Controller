from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller import desktop_job_packages as jobs
from carveracontroller.machine.job_packages import JobPackage, save_package
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("change", ["connection", "program", "machine", "new_import"])
def test_late_import_cannot_replace_new_selection(tmp_path, monkeypatch, change):
    archive = save_package(JobPackage("Imported", b"G21\n"), tmp_path / "job.cvjob")
    workers = []
    monkeypatch.setattr(
        jobs.threading, "Thread", lambda target, **_kw: SimpleNamespace(start=lambda: workers.append(target))
    )
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)
    viewer = SimpleNamespace(configure_machine=Mock(), configure_workholding=Mock(), load_tool_profiles=Mock())
    controller = SimpleNamespace(_connection_generation=1, executeCommand=Mock())
    workspace = SimpleNamespace(
        app=SimpleNamespace(state="Idle", playing=False, selected_local_filename="previous.cnc"),
        profile_store=None,
        selected_machine_profile={"id": "previous"},
        machine=SimpleNamespace(controller=controller, gcode_viewer=viewer),
        package_note=SimpleNamespace(text=""),
        choose_asset_file=lambda selected, **_kw: selected(archive),
    )
    jobs.import_job(workspace)
    if change == "connection":
        controller._connection_generation += 1
    elif change == "program":
        workspace.app.selected_local_filename = "new.cnc"
    elif change == "machine":
        workspace.selected_machine_profile = {"id": "new"}
    else:
        workspace._job_import_generation += 1
        workspace.package_note.text = "New request owns this status"
    workers[0]()
    pump_frames(3)
    viewer.configure_machine.assert_not_called()
    controller.executeCommand.assert_not_called()
    if change == "new_import":
        assert workspace.package_note.text == "New request owns this status"
    else:
        assert "selection or connection changed" in workspace.package_note.text


def test_invalid_fixture_fails_before_program_or_preview_publication(tmp_path, monkeypatch):
    from carveracontroller.addons.machine_simulation.profile import MachineProfile

    monkeypatch.setattr(MachineProfile, "load", lambda _path: SimpleNamespace(groups={}))
    setup = {
        "stock": {},
        "tools": [],
        "machine": {},
        "toolsets": [],
        "fixtures": [{"group": "spindle", "cad_path": "bad"}],
    }
    loaded = SimpleNamespace(package=JobPackage("Preview", b"G21\n"))
    with pytest.raises(ValueError, match="registered fixture/vise"):
        jobs.prepare_job_preview(loaded, setup, tmp_path)
    assert not (tmp_path / loaded.package.program_name).exists()


def test_prepared_import_replaces_calibration_and_clears_previous_rest_stock(tmp_path, monkeypatch):
    archive = save_package(JobPackage("Imported", b"G21\n"), tmp_path / "job.cvjob")
    workers = []
    monkeypatch.setattr(
        jobs.threading, "Thread", lambda target, **_kw: SimpleNamespace(start=lambda: workers.append(target))
    )
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)
    viewer = SimpleNamespace(configure_machine=Mock(), configure_workholding=Mock(), load_tool_profiles=Mock())
    controller = SimpleNamespace(_connection_generation=1, executeCommand=Mock())
    calibration = SimpleNamespace(apply_calibration=Mock())
    local = SimpleNamespace(curr_selected_file="old.cnc")
    workspace = SimpleNamespace(
        app=SimpleNamespace(state="Idle", playing=False, selected_local_filename="previous.cnc"),
        profile_store=None,
        selected_machine_profile=None,
        machine=SimpleNamespace(
            controller=controller,
            gcode_viewer=viewer,
            file_popup=SimpleNamespace(local_rv=local),
            view_local_file=Mock(),
        ),
        camera_registration_panel=calibration,
        pending_job_rest_stock=("old.cnc", object()),
        package_note=SimpleNamespace(text=""),
        choose_asset_file=lambda selected, **_kw: selected(archive),
    )
    jobs.import_job(workspace)
    workers[0]()
    # Preparation is complete before the scheduled UI publication.
    monkeypatch.setattr(jobs, "prepare_job_preview", Mock(side_effect=AssertionError("UI must not prepare assets")))
    pump_frames(3)
    assert "Restored local preview" in workspace.package_note.text
    assert workspace.pending_job_rest_stock is None
    calibration.apply_calibration.assert_called_once_with(None)
    assert jobs.Path(local.curr_selected_file).read_bytes() == b"G21\n"
    viewer.configure_machine.assert_called_once()
    workspace.machine.view_local_file.assert_called_once()
    jobs.prepare_job_preview.assert_not_called()
    controller.executeCommand.assert_not_called()
