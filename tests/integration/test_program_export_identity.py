from types import SimpleNamespace

import pytest

from carveracontroller import desktop_job_packages as jobs
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.machine.job_packages import load_package
from carveracontroller.machine.program_bytes import preview_digest
from tests.integration.conftest import pump_frames


@pytest.fixture
def export_case(monkeypatch, tmp_path):
    source = tmp_path / "part.cnc"
    source.write_bytes(b"G21\r\n")
    target = tmp_path / "export.cvjob"
    workers = []
    monkeypatch.setattr(
        jobs,
        "threading",
        SimpleNamespace(Thread=lambda *, target, **_kwargs: SimpleNamespace(start=lambda: workers.append(target))),
    )
    viewer = SimpleNamespace(
        machine_setup=MachineSetup(stock_size_mm=(10, 20, 5)),
        machine_component_profiles={},
        workholding_offset_mm=(0, 0, 0),
        workholding_rotation_deg=0,
        jaw_offset_mm=0,
        loaded_program_hash=preview_digest(b"G21\n"),
    )
    ws = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(source), selected_remote_filename=""),
        machine=SimpleNamespace(gcode_viewer=viewer, _last_loaded_file_key=str(source)),
        profile_store=None,
        selected_machine_profile=None,
        loaded_toolset=None,
        package_note=SimpleNamespace(text=""),
        choose_profile_file=lambda selected, **_kwargs: selected(target),
    )
    return SimpleNamespace(source=source, target=target, workers=workers, ws=ws, viewer=viewer)


def test_export_prepares_program_on_worker_and_retains_captured_setup(export_case, monkeypatch):
    item = export_case
    original = jobs.read_program_bytes
    reads = []

    def read(*args, **kwargs):
        reads.append(args[0])
        return original(*args, **kwargs)

    monkeypatch.setattr(jobs, "read_program_bytes", read)
    jobs.export_job(item.ws)
    assert reads == [] and not item.target.exists()
    item.viewer.machine_setup = MachineSetup(stock_size_mm=(50, 50, 50))
    item.workers[0]()
    pump_frames(3)
    loaded = load_package(item.target)
    assert loaded.package.program == b"G21\r\n"
    assert loaded.package.stock["size_mm"] == [10, 20, 5]
    assert reads == [str(item.source)]
    assert "Saved self-contained job" in item.ws.package_note.text


def test_changed_reviewed_program_does_not_create_export(export_case):
    item = export_case
    jobs.export_job(item.ws)
    item.source.write_bytes(b"G20\r\n")
    item.workers[0]()
    pump_frames(3)
    assert not item.target.exists()
    assert "differ from the reviewed preview" in item.ws.package_note.text


def test_direct_capture_rejects_bytes_changed_since_current_preview(export_case):
    export_case.source.write_bytes(b"G20\r\n")
    with pytest.raises(ValueError, match="differ from the reviewed preview"):
        jobs.capture_job(export_case.ws)


@pytest.mark.parametrize("failure", [RuntimeError("worker unavailable"), MemoryError()])
def test_export_worker_start_failure_is_reported(export_case, monkeypatch, failure):
    def failed(**_kwargs):
        raise failure

    monkeypatch.setattr(jobs, "threading", SimpleNamespace(Thread=failed))
    jobs.export_job(export_case.ws)
    assert "Could not start export" in export_case.ws.package_note.text
    assert not export_case.target.exists()


def test_second_export_cannot_race_the_current_archive_publication(export_case):
    item = export_case
    jobs.export_job(item.ws)
    jobs.export_job(item.ws)
    assert len(item.workers) == 1
    assert "current export" in item.ws.package_note.text
    item.workers[0]()
    pump_frames(3)
    assert not item.ws._job_export_active
    assert load_package(item.target).package.program == b"G21\r\n"
