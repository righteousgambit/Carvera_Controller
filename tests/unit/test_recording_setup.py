import copy
import hashlib
import json
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
    receipt = export_recorded_job(replay, path, bundle, setup_archive=snapshot)
    assert receipt["setup_included"] and not receipt["camera_included"]
    assert receipt["retained_events"] == len(replay.payload["events"])
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


def test_individual_cutter_profile_retained_without_toolset_and_stale_metadata_excluded(tmp_path):
    from carveracontroller.addons.machine_simulation.model import MachineSetup
    from carveracontroller.desktop_job_packages import capture_recording_job
    from carveracontroller.machine.desktop_profiles import to_tool_definition, validate_record

    path, setup, _job, asset = declared_job(tmp_path)
    drawing = tmp_path / "tool.dxf"
    drawing.write_bytes(b"retained drawing")
    profile = validate_record(
        "tools",
        {
            "id": "individual",
            "name": "Individual cutter",
            "number": 1,
            "shape": "flat_end_mill",
            "diameter": 6.35,
            "shank_diameter": 6.35,
            "geometry_path": str(asset),
            "drawing_path": str(drawing),
            "vendor": "Manufacturer",
            "product_id": "03182",
            "notes": "Stickout remains unverified",
        },
    )
    definition = to_tool_definition(profile, number=4)
    definition.geometry_sha256 = hashlib.sha256(asset.read_bytes()).hexdigest()
    viewer = SimpleNamespace(
        machine_setup=MachineSetup((1, 2, 3), (10, 20, 8), (0, 0, 0)),
        library_tool_table_mm={4: definition},
        assembly_preview_binding=None,
        machine_component_profiles={},
        workholding_offset_mm=(0, 0, 0),
        workholding_rotation_deg=0,
        jaw_offset_mm=0,
    )
    workspace = SimpleNamespace(
        app=SimpleNamespace(selected_local_filename=str(path)),
        machine=SimpleNamespace(gcode_viewer=viewer),
        profile_store=None,
        selected_machine_profile=None,
        loaded_toolset=None,
        loaded_tool_profiles={4: profile},
        camera_registration_panel=None,
    )
    job = capture_recording_job(workspace)
    assert len(job.tools) == 1 and job.tools[0]["number"] == 4
    assert job.tools[0]["notes"] == profile["notes"] and job.toolsets == []
    record, snapshot = bind_recording_setup(path, setup, job, tmp_path / "individual-snapshot")
    bundle = tmp_path / "individual.cvsession"
    export_recorded_job(RecordingReplay(record.export_bytes()), path, bundle, setup_archive=snapshot)
    imported = import_recorded_job(bundle, tmp_path / "imported-individual")
    loaded = load_package(imported.setup_archive)
    assert loaded.package.tools[0]["product_id"] == "03182"
    assert set(loaded.asset_bytes.values()) == {asset.read_bytes(), drawing.read_bytes()}
    profile["notes"] = "changed after capture"
    assert job.tools[0]["notes"] != profile["notes"]
    definition.diameter = 3.175
    assert capture_recording_job(workspace).tools == []
    viewer.library_tool_table_mm.clear()
    assert capture_recording_job(workspace).tools == []


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


def shaped_job(tmp_path):
    from carveracontroller.addons.machine_simulation.model import MachineSetup
    from carveracontroller.addons.machine_simulation.stock_model import StockModel
    from tests.unit.test_stock_solid import box, mesh

    path, _setup, job, _asset = declared_job(tmp_path)
    source = mesh(tmp_path, box((0, 0, 0), (10, 20, 8)))
    model = StockModel.load(source.source_path, "mm")
    setup = MachineSetup((1, 2, 3), model.size_mm, stock_model=model).record()
    job.stock["stock_source"] = model.reference
    job.assets[model.source_path] = tmp_path / "stock.stl"
    return path, setup, job, model


def test_recording_binds_stock_bytes_and_omits_original_local_path(tmp_path):
    path, setup, job, model = shaped_job(tmp_path)
    record, snapshot = bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    context = record.snapshot()["context"]
    assert context["setup"]["stock_source"]["source_sha256"] == model.source_sha256
    assert "source_path" not in context["setup"]["stock_source"]
    assert model.source_path not in record.export_bytes().decode()
    assert RecordingReplay(record.export_bytes()).payload["context"] == json.loads(json.dumps(context))
    loaded = load_package(snapshot)
    assert loaded.package.stock["stock_source"]["source_path"].startswith("asset://")


@pytest.mark.parametrize("change", ["units", "digest", "bounds", "missing"])
def test_recording_rejects_different_initial_shape_identity(tmp_path, change):
    path, setup, job, _model = shaped_job(tmp_path)
    if change == "missing":
        job.stock.pop("stock_source")
    else:
        key, value = {
            "units": ("source_units", "inch"),
            "digest": ("source_sha256", "0" * 64),
            "bounds": ("maximum_mm", [11, 20, 8]),
        }[change]
        job.stock["stock_source"][key] = value
    with pytest.raises(ValueError, match="stock source differs"):
        bind_recording_setup(path, setup, job, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_recording_rejects_stock_bytes_changed_before_archive_capture(tmp_path):
    path, setup, job, model = shaped_job(tmp_path)
    from pathlib import Path

    Path(model.source_path).write_bytes(b"changed shape")
    with pytest.raises(ValueError, match="stock geometry changed"):
        bind_recording_setup(path, setup, job, tmp_path / "rejected")
    assert not list((tmp_path / "rejected").glob("*.cvjob"))


def test_recorded_stock_scene_restores_from_custody_without_original_mesh(tmp_path):
    from carveracontroller.addons.machine_simulation.stock_model import initial_stock
    from carveracontroller.machine.historical_scene import prepare_historical_scene

    path, setup, job, model = shaped_job(tmp_path)
    job.inspection_plan["tool_definitions_mm"] = []
    record, archive = bind_recording_setup(path, setup, job, tmp_path / "snapshots")
    from pathlib import Path

    Path(model.source_path).unlink()
    replay = RecordingReplay(record.export_bytes())
    scene = prepare_historical_scene(
        replay, archive, tmp_path / "scene", {}, 1, 0.1, path, hashlib.sha256(path.read_text().encode()).hexdigest()
    )
    assert scene.setup.stock_model.source_sha256 == model.source_sha256
    assert scene.setup.stock_model.source_path != model.source_path
    assert initial_stock(scene.setup, 1).remaining_volume_mm3 == 1600
    assert len(scene.geometry["stock"].indices) == 36
