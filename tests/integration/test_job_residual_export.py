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


@pytest.mark.parametrize("program", [b"G20\n", b"\xff"])
def test_residual_program_mismatch_or_invalid_utf8_preserves_destination(residual_case, program):
    item = residual_case
    job = jobs.capture_job(item.ws)
    save_package(JobPackage("Previous", b"G20\n"), item.target)
    previous = item.target.read_bytes()
    job.program = program
    with pytest.raises(JobPackageError, match="program"):
        save_package(job, item.target)
    assert item.target.read_bytes() == previous


@pytest.mark.parametrize("identity_kind", ["raw", "normalized"])
def test_residual_binding_accepts_equivalent_newline_encodings(residual_case, identity_kind):
    item = residual_case
    raw = b"G21\r\n"
    item.source.write_bytes(raw)
    if identity_kind == "raw":
        item.ws.operation_panel.program = ProgramOperations.from_text(raw.decode("utf-8"))
    context = capture_context(item.viewer, item.ws.operation_panel.program, verify_assets=False)
    item.ws.simulation_panel.rest_identity = context["program"], digest_context(context)
    job = jobs.capture_job(item.ws)
    save_package(job, item.target)
    assert load_package(item.target).package.program == raw


def _prepare_residual_case(item, tmp_path):
    from carveracontroller.machine.job_packages import resolve_setup_assets

    save_package(jobs.capture_job(item.ws), item.target)
    loaded = load_package(item.target, tmp_path / "installed")
    destination = tmp_path / "preview"
    destination.mkdir()
    return jobs.prepare_job_preview(loaded, resolve_setup_assets(loaded), destination), loaded


def _pending_workspace(item, retained, path):
    item.ws.machine.loading_file = False
    item.ws.machine._last_loaded_file_key = str(path)
    item.ws.pending_job_rest_stock = (str(path), retained)
    panel = item.ws.simulation_panel
    panel.rest_stock, panel.rest_identity = None, None
    panel.stock_source = SimpleNamespace(text="Initial stock")
    panel.note = SimpleNamespace(text="")
    geometries = []
    item.viewer.set_rest_stock_geometry = geometries.append
    return geometries


def test_archive_round_trip_matches_context_before_adopting_rest_stock(residual_case, tmp_path):
    item = residual_case
    prepared, loaded = _prepare_residual_case(item, tmp_path)
    placement, _definitions, _profile, _components, _bank, path, retained = prepared
    assert retained.context["interpretation"]["motion_sha256"]
    assert "residual_context_path" in loaded.package.stock
    geometries = _pending_workspace(item, retained, path)
    item.viewer.machine_setup = placement
    jobs.restore_pending_residual(item.ws)
    assert item.ws.simulation_panel.rest_stock is retained.stock
    context = capture_context(item.viewer, item.ws.operation_panel.program, verify_assets=False)
    assert item.ws.simulation_panel.rest_identity == (context["program"], digest_context(context))
    assert len(geometries) == 1 and item.ws.pending_job_rest_stock is None
    assert "context-matched" in item.ws.simulation_panel.note.text
    jobs.restore_pending_residual(item.ws)
    assert len(geometries) == 1


@pytest.mark.parametrize("change", ["interpretation", "workholding", "stock", "legacy", "tools"])
def test_context_mismatch_or_unknown_provenance_never_publishes_grid(residual_case, tmp_path, change):
    from carveracontroller.machine.residual_provenance import RetainedResidual

    item = residual_case
    prepared, _loaded = _prepare_residual_case(item, tmp_path)
    retained, path = prepared[-1], prepared[-2]
    if change == "legacy":
        retained = RetainedResidual(retained.stock, None)
    geometries = _pending_workspace(item, retained, path)
    if change == "interpretation":
        item.ws.operation_panel.program = ProgramOperations.from_text("G21\n", arc_tolerance_mm=0.01)
    elif change == "workholding":
        item.viewer.jaw_offset_mm = 1
    elif change == "stock":
        item.viewer.machine_setup = replace(item.viewer.machine_setup, stock_origin_mm=(1, 0, 0))
    elif change == "tools":
        retained.context["tools"]["1"] = {"diameter": 99}
    jobs.restore_pending_residual(item.ws)
    assert not geometries and item.ws.simulation_panel.rest_stock is None
    assert item.ws.simulation_panel.rest_identity is None and item.ws.pending_job_rest_stock is None
    assert "Residual stock not applied" in item.ws.package_note.text


def test_residual_waits_for_matching_completed_program_load(residual_case, tmp_path):
    item = residual_case
    prepared, _loaded = _prepare_residual_case(item, tmp_path)
    retained, path = prepared[-1], prepared[-2]
    geometries = _pending_workspace(item, retained, path)
    item.ws.machine.loading_file = True
    jobs.restore_pending_residual(item.ws)
    assert not geometries and item.ws.pending_job_rest_stock
    item.ws.machine.loading_file = False
    item.ws.machine._last_loaded_file_key = "another.cnc"
    jobs.restore_pending_residual(item.ws)
    assert not geometries and item.ws.pending_job_rest_stock
    item.ws.machine._last_loaded_file_key = str(path)
    jobs.restore_pending_residual(item.ws)
    assert len(geometries) == 1


@pytest.mark.parametrize("change", ["grid", "program", "schema", "nan", "duplicate", "oversize"])
def test_invalid_residual_context_refuses_import_before_publication(residual_case, tmp_path, change):
    from carveracontroller.machine.residual_provenance import MAX_CONTEXT_BYTES, decode_provenance

    item = residual_case
    _prepared, loaded = _prepare_residual_case(item, tmp_path)
    raw = loaded.asset_bytes[loaded.package.stock["residual_stock_path"]]
    payload = loaded.asset_bytes[loaded.package.stock["residual_context_path"]]
    program = loaded.package.program
    if change == "grid":
        raw += b" "
    elif change == "program":
        program += b"G20\n"
    elif change == "schema":
        record = json.loads(payload)
        record["schema"] = 99
        payload = json.dumps(record).encode()
    elif change == "nan":
        record = json.loads(payload)
        record["context"]["work_offset_mm"][0] = float("nan")
        payload = json.dumps(record).encode()
    elif change == "duplicate":
        payload = payload[:-1] + b',"schema":1}'
    else:
        payload = b" " * (MAX_CONTEXT_BYTES + 1)
    with pytest.raises(ValueError):
        decode_provenance(payload, program, raw)


def test_portable_context_accepts_relocated_identical_cad_but_not_changed_bytes(residual_case, tmp_path):
    from carveracontroller.machine.residual_provenance import match_provenance, portable_context

    item = residual_case
    first = tmp_path / "first.json"
    second = tmp_path / "elsewhere.json"
    first.write_bytes(b"CAD fixture")
    second.write_bytes(first.read_bytes())
    digest = hashlib.sha256(first.read_bytes()).hexdigest()

    def select(path, identity=digest):
        item.viewer.machine_component_profiles["fixture"] = SimpleNamespace(
            asset_path=str(path), asset_sha256=identity, source_revision="R1", source_sha256=digest
        )
        return capture_context(item.viewer, item.ws.operation_panel.program)

    before = select(first)
    # Tool geometry's duplicated location fields must normalize with its asset record.
    before["tools"]["1"] = {"geometry_path": str(first), "cutter_asset": before["components"]["fixture"]["asset"]}
    retained = portable_context(before)
    current = select(second)
    current["tools"]["1"] = {"geometry_path": str(second), "cutter_asset": current["components"]["fixture"]["asset"]}
    match_provenance(retained, current)
    second.write_bytes(b"different CAD")
    with pytest.raises(ValueError, match="unverified CAD"):
        match_provenance(retained, select(second))


def test_actual_profile_archive_relocation_preserves_residual_context(residual_case, tmp_path):
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    item = residual_case
    data = profile_data()
    data["components"].append(dict(data["components"][0], group="fixture"))
    cad = tmp_path / "plate.json"
    import gzip

    cad.write_bytes(gzip.compress(json.dumps(data).encode()))
    item.viewer.machine_component_profiles["fixture"] = MachineProfile.load(cad)
    context = capture_context(item.viewer, item.ws.operation_panel.program)
    item.ws.simulation_panel.rest_identity = context["program"], digest_context(context)
    prepared, _loaded = _prepare_residual_case(item, tmp_path)
    placement, _tools, _profile, components, _bank, path, retained = prepared
    assert components[0][1].asset_path != str(cad)
    cad.unlink()  # Restoration must be independent of original location.
    geometries = _pending_workspace(item, retained, path)
    item.viewer.machine_setup = placement
    item.viewer.machine_component_profiles = dict(components)
    jobs.restore_pending_residual(item.ws)
    assert len(geometries) == 1 and item.ws.simulation_panel.rest_stock is retained.stock


def test_residual_mesh_is_worker_prepared_and_not_rebuilt_during_publication(residual_case, tmp_path, monkeypatch):
    from carveracontroller.machine import simulation_preview

    item = residual_case
    entered, release = threading.Event(), threading.Event()
    ui = threading.get_ident()
    original = simulation_preview.stock_geometry
    results, errors = [], []

    def blocked_mesh(stock, *args, **kwargs):
        assert threading.get_ident() != ui
        entered.set()
        if not release.wait(3):
            raise TimeoutError("Mesh test not released")
        return original(stock, *args, **kwargs)

    monkeypatch.setattr(simulation_preview, "stock_geometry", blocked_mesh)

    def prepare():
        try:
            results.append(_prepare_residual_case(item, tmp_path))
        except Exception as exc:
            errors.append(exc)

    pulses = []
    pulse = Clock.schedule_interval(lambda _dt: pulses.append(True), 0)
    thread = threading.Thread(target=prepare)
    thread.start()
    try:
        assert entered.wait(2)
        pump_frames(8, sleep=0.01)
        assert len(pulses) >= 3 and not results
    finally:
        release.set()
        pulse.cancel()
        thread.join(3)
    assert not errors and not thread.is_alive()
    prepared, _loaded = results[0]
    retained, path = prepared[-1], prepared[-2]
    assert retained.geometry is not None
    geometries = _pending_workspace(item, retained, path)
    monkeypatch.setattr(simulation_preview, "stock_geometry", lambda *_a, **_k: pytest.fail("UI rebuilt residual mesh"))
    jobs.restore_pending_residual(item.ws)
    assert geometries == [retained.geometry]
    assert item.ws.simulation_panel.rest_stock is retained.stock


def test_display_mesh_failure_rejects_import_preparation(residual_case, tmp_path, monkeypatch):
    from carveracontroller.machine import simulation_preview

    def oversized(*_args, **_kwargs):
        raise ValueError("Rest-stock display exceeds face budget")

    monkeypatch.setattr(simulation_preview, "stock_geometry", oversized)
    with pytest.raises(ValueError, match="face budget"):
        _prepare_residual_case(residual_case, tmp_path)
    assert not hasattr(residual_case.ws, "pending_job_rest_stock")
