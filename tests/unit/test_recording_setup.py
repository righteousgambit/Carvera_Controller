import copy
import hashlib
from types import SimpleNamespace

import pytest

from carveracontroller.machine.job_packages import JobPackage, load_package
from carveracontroller.machine.recorded_jobs import export_recorded_job, import_recorded_job
from carveracontroller.machine.recording_setup import bind_recording_setup
from carveracontroller.machine.run_recording import RecordingReplay


def declared_job(tmp_path):
    path = tmp_path / "program.nc"
    path.write_bytes(b"G21\nG90\nG1 X1 F100\n")
    asset = tmp_path / "tool.json"
    asset.write_text('{"geometry": "declared"}')
    setup = {
        "work_offset_mm": [1, 2, 3],
        "stock_origin_mm": [0, 0, 0],
        "stock_size_mm": [10, 20, 8],
        "alignment_confirmed": False,
    }
    stock = {"size_mm": [10, 20, 8], "origin_mm": [0, 0, 0], "work_offset_mm": [1, 2, 3], "alignment_confirmed": False}
    job = JobPackage(
        "Recorded",
        b"",
        stock=stock,
        tools=[{"id": "cutter", "geometry_path": str(asset)}],
        assets={str(asset): asset},
        inspection_plan={
            "tool_definitions_mm": [
                {"geometry_path": str(asset), "geometry_sha256": hashlib.sha256(asset.read_bytes()).hexdigest()}
            ]
        },
    )
    return path, setup, job, asset


def test_retained_setup_survives_source_changes_and_combined_run_roundtrip(tmp_path):
    path, setup, job, asset = declared_job(tmp_path)
    record, snapshot = bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    payload = record.snapshot()
    assert payload["schema"] == 3
    configuration = payload["context"]["configuration"]
    assert configuration["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()
    assert configuration["scope"] == "declared_setup_assets_at_recording_start"
    assert RecordingReplay(record.export_bytes()).payload == payload
    asset.write_text("changed after capture")
    loaded = load_package(snapshot)
    assert next(iter(loaded.asset_bytes.values())) != asset.read_bytes()
    bundle = tmp_path / "full.cvsession"
    replay = RecordingReplay(record.export_bytes())
    export_recorded_job(replay, path, bundle, setup_archive=snapshot)
    installed = import_recorded_job(bundle, tmp_path / "installed")
    assert installed.setup_archive.read_bytes() == snapshot.read_bytes()
    assert installed.replay.payload["context"]["configuration"] == configuration
    assert load_package(installed.setup_archive).package.stock == job.stock
    with pytest.raises(ValueError, match="missing or unbound"):
        export_recorded_job(replay, path, tmp_path / "incomplete.cvsession")
    snapshot.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="bytes differ"):
        export_recorded_job(replay, path, tmp_path / "corrupt.cvsession", setup_archive=snapshot)


def test_selected_geometry_and_nominal_setup_changes_withhold_new_record(tmp_path):
    path, setup, job, asset = declared_job(tmp_path)
    wrong = copy.deepcopy(setup)
    wrong["stock_origin_mm"] = [9, 9, 9]
    with pytest.raises(ValueError, match="stock/offset"):
        bind_recording_setup(path, wrong, job, tmp_path / "wrong")
    assert not (tmp_path / "wrong").exists()
    asset.write_text("changed before snapshot")
    with pytest.raises(ValueError, match="geometry changed"):
        bind_recording_setup(path, setup, job, tmp_path / "rejected")
    assert list((tmp_path / "rejected").glob("*.cvjob"))  # Preserve failed-attempt custody.


def test_native_tuple_dimensions_bind_to_json_setup_snapshot(tmp_path):
    path, setup, job, _asset = declared_job(tmp_path)
    # Native MachineSetup/asdict retains tuples; portable job JSON uses lists.
    for key in ("work_offset_mm", "stock_origin_mm", "stock_size_mm"):
        setup[key] = tuple(setup[key])
    record, snapshot = bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    loaded = load_package(snapshot)
    assert loaded.package.stock["size_mm"] == list(setup["stock_size_mm"])
    replay = RecordingReplay(record.export_bytes())
    assert replay.payload["context"]["setup"]["stock_size_mm"] == list(setup["stock_size_mm"])
    assert replay.payload["context"]["configuration"]["sha256"] == hashlib.sha256(snapshot.read_bytes()).hexdigest()


def test_capture_recording_declarations_performs_no_file_io(tmp_path, monkeypatch):
    from pathlib import Path

    from carveracontroller.desktop_job_packages import capture_recording_job

    viewer = SimpleNamespace(
        machine_setup=SimpleNamespace(
            stock_size_mm=(10, 20, 8), stock_origin_mm=(0, 0, 0), work_offset_mm=(1, 2, 3), alignment_confirmed=False
        ),
        library_tool_table_mm={},
        assembly_preview_binding=None,
        machine_component_profiles={"vise": SimpleNamespace(asset_path="vise.json")},
        workholding_offset_mm=(0, 1, 2),
        workholding_rotation_deg=90,
        jaw_offset_mm=4,
    )
    machine = {"id": "selected", "name": "Workshop", "cad_path": "machine.json"}
    workspace = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename="selected.nc"),
        machine=SimpleNamespace(gcode_viewer=viewer),
        profile_store=None,
        loaded_toolset=None,
        selected_machine_profile=machine,
        camera_registration_panel=SimpleNamespace(registration=None),
    )

    def forbid(*_args, **_kwargs):
        raise AssertionError("UI declaration capture performed file I/O")

    monkeypatch.setattr(Path, "open", forbid)
    job = capture_recording_job(workspace)
    assert job.program == b"" and set(job.assets) == {"machine.json", "vise.json"}
    assert job.vise["rotation_deg"] == 90
    machine["name"] = "changed"
    assert job.machine["name"] == "Workshop"


def test_recorded_setup_binds_stock_rotation_and_rejects_unrotated_archive(tmp_path):
    path, setup, job, _asset = declared_job(tmp_path)
    setup["stock_rotation_deg"] = 37
    with pytest.raises(ValueError, match="rotation differs"):
        bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    job.stock["rotation_deg"] = 37
    recording, archive = bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    assert load_package(archive).package.stock["rotation_deg"] == 37
    assert recording.snapshot()["context"]["setup"]["stock_rotation_deg"] == 37


def test_recorded_setup_retains_exact_calibration_reference_in_combined_run(tmp_path):
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from carveracontroller.machine.job_packages import retained_camera_calibration
    from tests.unit.test_camera_calibration_file import data

    path, setup, job, _asset = declared_job(tmp_path)
    job.camera_calibration = decode_calibration(data())
    record, snapshot = bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    replay = RecordingReplay(record.export_bytes())
    bundle = tmp_path / "camera.cvsession"
    export_recorded_job(replay, path, bundle, setup_archive=snapshot)
    loaded = import_recorded_job(bundle, tmp_path / "installed")
    calibration = retained_camera_calibration(load_package(loaded.setup_archive))
    assert calibration[2].to_dict() == job.camera_calibration[2].to_dict()
    assert calibration[1] == job.camera_calibration[1]
