"""Residual job assets are prepared on archive workers, never UI capture."""

import hashlib
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from kivy.clock import Clock

from carveracontroller import desktop_job_packages as jobs
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.machine.geometry_changes import capture_context, digest_context
from carveracontroller.machine.job_packages import JobPackage, JobPackageError, load_package, save_package
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames


@pytest.fixture
def residual_case(tmp_path):
    source = tmp_path / "part.cnc"
    source.write_bytes(b"G21\n")
    viewer = SimpleNamespace(
        machine_setup=MachineSetup(stock_size_mm=(2, 3, 1)),
        library_tool_table_mm={},
        machine_profile=None,
        machine_component_profiles={},
        assembly_preview_binding=None,
        workholding_offset_mm=(0, 0, 0),
        workholding_rotation_deg=0,
        jaw_offset_mm=0,
        loaded_program_hash=hashlib.sha256(b"G21\n").hexdigest(),
    )
    ws = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(source), selected_remote_filename=""),
        machine=SimpleNamespace(gcode_viewer=viewer, _last_loaded_file_key=str(source)),
        operation_panel=SimpleNamespace(program=ProgramOperations.from_text("G21\n")),
        profile_store=None,
        selected_machine_profile=None,
        loaded_toolset=None,
        package_note=SimpleNamespace(text=""),
    )
    volume = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 3, 1)))
    context = capture_context(viewer, ws.operation_panel.program, verify_assets=False)
    ws.simulation_panel = SimpleNamespace(
        rest_stock=volume, rest_identity=(context["program"], digest_context(context))
    )
    target = tmp_path / "export.cvjob"
    ws.choose_profile_file = lambda selected, **_kwargs: selected(target)
    return SimpleNamespace(ws=ws, viewer=viewer, volume=volume, source=source, target=target)


def test_ui_capture_does_not_snapshot_hash_cad_or_write_export_assets(residual_case, monkeypatch, tmp_path):
    item = residual_case
    cad = tmp_path / "fixture.json"
    cad.write_bytes(b"fixture bytes")
    digest = hashlib.sha256(cad.read_bytes()).hexdigest()
    item.viewer.machine_component_profiles["fixture"] = SimpleNamespace(
        asset_path=str(cad), asset_sha256=digest, source_revision="source", source_sha256=digest
    )
    context = capture_context(item.viewer, item.ws.operation_panel.program, verify_assets=False)
    item.ws.simulation_panel.rest_identity = context["program"], digest_context(context)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("UI touched asset bytes or encoded residual stock")

    monkeypatch.setattr(StockVolume, "snapshot", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(Path, "mkdir", forbidden)
    monkeypatch.setattr(Path, "write_text", forbidden)
    job = jobs.capture_job(residual_case.ws, include_program=False)
    assert job.residual_stock.stock is residual_case.volume
    assert job.assets == {str(cad): cad} and "residual_stock_path" not in job.stock


def test_archive_materializes_captured_grid_even_if_ui_replaces_result(residual_case):
    item = residual_case
    job = jobs.capture_job(item.ws)
    item.ws.simulation_panel.rest_stock = StockVolume(AABB(Vec3(0, 0, 0), Vec3(1, 1, 1)))
    item.viewer.machine_setup = MachineSetup(stock_size_mm=(1, 1, 1))
    save_package(job, item.target)
    loaded = load_package(item.target)
    reference = loaded.package.stock["residual_stock_path"]
    restored = StockVolume.from_snapshot(json.loads(loaded.asset_bytes[reference]))
    assert restored.remaining_volume_mm3 == 6
    assert loaded.package.stock["size_mm"] == [2, 3, 1]
    assert job.assets == {} and "residual_stock_path" not in job.stock


def test_changed_cad_is_rejected_on_worker_without_replacing_destination(residual_case, tmp_path):
    item = residual_case
    cad = tmp_path / "fixture.json"
    cad.write_bytes(b"original CAD")
    digest = hashlib.sha256(cad.read_bytes()).hexdigest()
    item.viewer.machine_component_profiles["fixture"] = SimpleNamespace(
        asset_path=str(cad), asset_sha256=digest, source_revision="source", source_sha256=digest
    )
    context = capture_context(item.viewer, item.ws.operation_panel.program, verify_assets=False)
    item.ws.simulation_panel.rest_identity = context["program"], digest_context(context)
    job = jobs.capture_job(item.ws)
    save_package(JobPackage("Previous", b"G20\n"), item.target)
    previous = item.target.read_bytes()
    cad.write_bytes(b"changed CAD")
    with pytest.raises(JobPackageError, match="CAD or context changed"):
        save_package(job, item.target)
    assert item.target.read_bytes() == previous


@pytest.mark.parametrize("change", ["grid", "declaration", "context", "reference"])
def test_inconsistent_residual_inputs_do_not_publish_an_archive(residual_case, change):
    item = residual_case
    job = jobs.capture_job(item.ws)
    if change == "grid":
        job.residual_stock = replace(job.residual_stock, stock=StockVolume(AABB(Vec3(0, 0, 0), Vec3(1, 1, 1))))
    elif change == "declaration":
        job.stock["size_mm"] = [1, 1, 1]
    elif change == "context":
        job.residual_stock.context["workholding"]["jaw_offset_mm"] = 99
    else:
        job.assets["residual-stock.cvstock"] = b"other asset"
    with pytest.raises(ValueError):
        save_package(job, item.target)
    assert not item.target.exists()


def test_large_snapshot_preparation_leaves_ui_event_loop_responsive(residual_case, monkeypatch):
    item = residual_case
    item.viewer.machine_setup = MachineSetup(stock_size_mm=(200, 200, 200))
    item.ws.simulation_panel.rest_stock = StockVolume(AABB(Vec3(0, 0, 0), Vec3(200, 200, 200)))
    assert item.ws.simulation_panel.rest_stock.memory_bytes == 8_000_000
    context = capture_context(item.viewer, item.ws.operation_panel.program, verify_assets=False)
    item.ws.simulation_panel.rest_identity = context["program"], digest_context(context)
    entered, release = threading.Event(), threading.Event()
    original = StockVolume.snapshot
    ui_thread = threading.get_ident()

    def slow_snapshot(stock, **kwargs):
        assert threading.get_ident() != ui_thread
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Test did not release snapshot preparation")
        return original(stock, **kwargs)

    monkeypatch.setattr(StockVolume, "snapshot", slow_snapshot)
    pulses = []
    pulse = Clock.schedule_interval(lambda _dt: pulses.append(True), 0)
    try:
        jobs.export_job(item.ws)
        assert entered.wait(1)
        pump_frames(8, sleep=0.01)
        assert len(pulses) >= 3 and item.ws._job_export_active
        assert not item.target.exists()
    finally:
        release.set()
        pulse.cancel()
    deadline = time.monotonic() + 3
    while item.ws._job_export_active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not item.ws._job_export_active
    assert "Saved self-contained job" in item.ws.package_note.text
    assert "residual_stock_path" in load_package(item.target).package.stock


def test_stale_residual_identity_is_rejected_before_worker_start(residual_case):
    residual_case.ws.simulation_panel.rest_identity = ("old", "context")
    with pytest.raises(ValueError, match="older setup"):
        jobs.capture_job(residual_case.ws, include_program=False)
    assert not residual_case.target.exists()


def test_snapshot_worker_failure_preserves_destination_and_releases_action(residual_case, monkeypatch):
    item = residual_case
    save_package(JobPackage("Previous", b"G20\n"), item.target)
    previous = item.target.read_bytes()
    workers = []
    monkeypatch.setattr(
        jobs,
        "threading",
        SimpleNamespace(Thread=lambda *, target, **_kwargs: SimpleNamespace(start=lambda: workers.append(target))),
    )

    def failed(*_args, **_kwargs):
        raise RuntimeError("snapshot preparation failed")

    monkeypatch.setattr(StockVolume, "snapshot", failed)
    jobs.export_job(item.ws)
    assert item.ws._job_export_active
    workers[0]()
    pump_frames(3)
    assert not item.ws._job_export_active
    assert "snapshot preparation failed" in item.ws.package_note.text
    assert item.target.read_bytes() == previous


@pytest.mark.parametrize("rewrite_context", [False, True])
def test_cad_changed_after_verification_cannot_enter_retained_archive(
    residual_case, tmp_path, monkeypatch, rewrite_context
):
    item = residual_case
    cad = tmp_path / "fixture.json"
    original_bytes = b"original CAD"
    cad.write_bytes(original_bytes)
    digest = hashlib.sha256(original_bytes).hexdigest()
    item.viewer.machine_component_profiles["fixture"] = SimpleNamespace(
        asset_path=str(cad), asset_sha256=digest, source_revision="source", source_sha256=digest
    )
    context = capture_context(item.viewer, item.ws.operation_panel.program, verify_assets=False)
    item.ws.simulation_panel.rest_identity = context["program"], digest_context(context)
    job = jobs.capture_job(item.ws)
    snapshot = StockVolume.snapshot

    def change_after_verification(stock, **kwargs):
        data = snapshot(stock, **kwargs)
        cad.write_bytes(b"late CAD change")
        if rewrite_context:
            state = job.residual_stock.context["components"]["fixture"]["asset"]
            state["loaded_sha256"] = state["current_sha256"] = hashlib.sha256(cad.read_bytes()).hexdigest()
        return data

    monkeypatch.setattr(StockVolume, "snapshot", change_after_verification)
    with pytest.raises(JobPackageError, match="changed while preparing"):
        save_package(job, item.target)
    assert not item.target.exists()


def test_camera_and_deferred_residual_assets_roundtrip_without_mutating_capture(residual_case):
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from carveracontroller.machine.job_packages import retained_camera_calibration
    from tests.unit.test_camera_calibration_file import data

    item = residual_case
    job = jobs.capture_job(item.ws)
    calibration = decode_calibration(data())
    job.camera_calibration = calibration
    save_package(job, item.target)
    loaded = load_package(item.target)
    assert "residual_stock_path" in loaded.package.stock
    assert "camera_calibration_path" in loaded.package.inspection_plan
    assert retained_camera_calibration(loaded)[2].frame.jpeg == calibration[2].frame.jpeg
    assert job.camera_calibration is calibration
    assert job.assets == {} and "residual_stock_path" not in job.stock
