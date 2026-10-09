"""Portable archives preserve exact bytes and reject unsafe or incomplete input."""

import hashlib
import json
import stat
import zipfile

import pytest

from carveracontroller.machine.job_packages import JobPackage, JobPackageError, load_package, save_package


def job(tmp_path):
    cad = tmp_path / "vise.step"
    cad.write_bytes(b"STEP\x00\xffgeometry")
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"photo bytes")
    return JobPackage(
        "Aluminum fixture",
        b"G21\r\nG1 X10\r\n",
        machine={"id": "c1", "cad_path": str(cad)},
        tools=[{"id": "t1", "drawing_path": str(cad), "diameter": 6.35}],
        toolsets=[{"id": "bank", "slots": {"1": "t1"}}],
        stock={"size": [127, 69, 51]},
        fixtures=[{"id": "plate"}],
        vise={"rotation": 90},
        material_recipes=[{"feed": 500}],
        inspection_plan={"features": ["bore"]},
        photographs=[str(photo)],
        assets={str(cad): cad, str(photo): photo},
    )


def mutate(source, target, change):
    with zipfile.ZipFile(source) as archive:
        files = {info.filename: archive.read(info) for info in archive.infolist()}
    manifest = json.loads(files["manifest.json"])
    change(manifest, files)
    files["manifest.json"] = json.dumps(manifest).encode()
    with zipfile.ZipFile(target, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)


def test_roundtrip_self_contained_and_restorable(tmp_path):
    original = job(tmp_path)
    archive = save_package(original, tmp_path / "fixture.cvjob")
    for asset in original.assets.values():
        asset.unlink()
    loaded = load_package(archive, tmp_path / "restored", inventory={"t1": {"id": "t1"}})
    assert loaded.package.program == original.program
    assert loaded.package.stock == original.stock
    assert loaded.package.inspection_plan == original.inspection_plan
    assert loaded.report.conflicting_inventory == ("t1",)
    assert loaded.package.machine["cad_path"].startswith("asset://")
    assert len(loaded.asset_paths) == 2  # duplicate drawing/CAD deduplicated
    assert all(path.read_bytes() == loaded.asset_bytes[ref] for ref, path in loaded.asset_paths.items())
    second = save_package(loaded.package, tmp_path / "second.cvjob")
    assert load_package(second).package.program == original.program
    with pytest.raises(JobPackageError, match="already exists"):
        load_package(archive, tmp_path / "restored")


def test_missing_asset_is_explicit(tmp_path):
    original = job(tmp_path)
    original.assets.clear()
    with pytest.raises(JobPackageError, match="Missing asset"):
        save_package(original, tmp_path / "bad.cvjob")
    assert not (tmp_path / "bad.cvjob").exists()


@pytest.mark.parametrize("name", ["../escape", "/absolute", "assets/../escape", "assets\\escape", "./manifest.json"])
def test_reject_member_paths(tmp_path, name):
    archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(name, b"evil")
    with pytest.raises(JobPackageError, match="Unsafe archive path"):
        load_package(archive, tmp_path / "install")
    assert not (tmp_path / "install").exists()


def test_reject_symlink(tmp_path):
    archive = tmp_path / "linked.zip"
    info = zipfile.ZipInfo("link")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr(info, "../../private")
    with pytest.raises(JobPackageError, match="Linked"):
        load_package(archive)


@pytest.mark.parametrize(
    "change",
    [
        lambda manifest, files: manifest.update(schema=True),
        lambda manifest, files: manifest["setup"]["stock"].update(size=[float("nan")]),
        lambda manifest, files: files.update({"program.bin": b"tampered"}),
        lambda manifest, files: files.update({"unexpected": b"extra"}),
        lambda manifest, files: manifest["setup"]["machine"].update(cad_path="/unbundled.step"),
        lambda manifest, files: manifest["assets"].update({"../bad": {"size": 3}}),
        lambda manifest, files: manifest["setup"].update(tools=[1]),
    ],
)
def test_reject_corruption_and_schema(tmp_path, change):
    good = save_package(job(tmp_path), tmp_path / "good.zip")
    mutate(good, tmp_path / "bad.zip", change)
    with pytest.raises(JobPackageError):
        load_package(tmp_path / "bad.zip", tmp_path / "install")
    assert not (tmp_path / "install").exists()


def test_reject_bomb_and_duplicates(tmp_path):
    archive = tmp_path / "bomb.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as stream:
        stream.writestr("program.bin", b"a" * (2 * 1024 * 1024))
    with pytest.raises(JobPackageError, match="limits"):
        load_package(archive)
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("program.bin", b"a")
        with pytest.warns(UserWarning):
            stream.writestr("program.bin", b"b")
    with pytest.raises(JobPackageError, match="duplicate"):
        load_package(archive)


def test_inventory_missing_and_exact_match(tmp_path):
    archive = save_package(job(tmp_path), tmp_path / "job.zip")
    loaded = load_package(archive, inventory={})
    assert loaded.report.missing_inventory == ("t1",)
    loaded = load_package(archive, inventory={"t1": loaded.package.tools[0]})
    assert not loaded.report.missing_inventory
    assert not loaded.report.conflicting_inventory


def test_reject_asset_tampering(tmp_path):
    good = save_package(job(tmp_path), tmp_path / "good.zip")

    def change(manifest, files):
        digest = next(iter(manifest["assets"]))
        files[f"assets/{digest}"] = b"wrong"

    mutate(good, tmp_path / "bad.zip", change)
    with pytest.raises(JobPackageError, match="digest mismatch"):
        load_package(tmp_path / "bad.zip")


def test_resolved_setup_is_separate_and_preserves_file_suffix(tmp_path):
    from carveracontroller.machine.job_packages import resolve_setup_assets

    archive = save_package(job(tmp_path), tmp_path / "job.zip")
    loaded = load_package(archive, tmp_path / "restore")
    resolved = resolve_setup_assets(loaded)
    assert resolved["machine"]["cad_path"].endswith(".step")
    assert resolved["photographs"][0].endswith(".jpg")
    assert loaded.package.machine["cad_path"].startswith("asset://")
    assert (tmp_path / "restore" / "program.bin").read_bytes() == loaded.package.program
    with pytest.raises(JobPackageError, match="Missing asset"):
        resolve_setup_assets(load_package(archive))


def test_package_binary_stream_load_preserves_exact_assets_without_install(tmp_path):
    import io

    original = job(tmp_path)
    archive = save_package(original, tmp_path / "stream.cvjob")
    with io.BytesIO(archive.read_bytes()) as source:
        loaded = load_package(source)
        assert not source.closed
        assert loaded.package.program == original.program
        assert set(loaded.asset_bytes.values()) == {b"STEP\x00\xffgeometry", b"photo bytes"}
        assert loaded.asset_paths == {}
    assert not (tmp_path / "installed").exists()


def test_stock_export_binds_bytes_actually_bundled_before_publication(tmp_path):
    original = job(tmp_path)
    source = tmp_path / "stock.stl"
    source.write_bytes(b"selected stock bytes")
    original.assets[str(source)] = source
    original.stock["stock_source"] = {
        "schema": 1,
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "source_units": "mm",
        "minimum_mm": [0, 0, 0],
        "maximum_mm": [3, 3, 2],
    }
    archive = save_package(original, tmp_path / "good.cvjob")
    loaded = load_package(archive)
    reference = loaded.package.stock["stock_source"]
    assert reference["source_path"] == "asset://" + reference["source_sha256"]
    assert loaded.asset_bytes[reference["source_path"]] == b"selected stock bytes"
    source.write_bytes(b"changed stock bytes")
    destination = tmp_path / "previous.cvjob"
    destination.write_bytes(b"previous archive retained")
    with pytest.raises(JobPackageError, match="stock geometry changed"):
        save_package(original, destination)
    assert destination.read_bytes() == b"previous archive retained"


def test_portable_preview_preserves_orientation_and_residual_material(tmp_path):
    from carveracontroller.addons.machine_simulation.model import MachineSetup
    from carveracontroller.addons.machine_simulation.stock_model import initial_stock
    from carveracontroller.desktop_job_packages import prepare_job_preview
    from carveracontroller.machine.job_packages import resolve_setup_assets

    setup = MachineSetup(
        stock_size_mm=(4, 6, 2), stock_origin_mm=(1, 2, 3), stock_rotation_deg=41, stock_tilt_deg=(23, -32)
    )
    residual = initial_stock(setup, 0.5)
    residual_path = tmp_path / "rest.cvstock"
    residual_path.write_text(json.dumps(residual.snapshot()))
    original = JobPackage(
        "Tilted",
        b"G21 G90\n",
        stock={
            "size_mm": list(setup.stock_size_mm),
            "origin_mm": list(setup.stock_origin_mm),
            "work_offset_mm": list(setup.work_offset_mm),
            "rotation_deg": 41,
            "tilt_deg": [23, -32],
            "residual_stock_path": str(residual_path),
        },
        assets={str(residual_path): residual_path},
    )
    archive = save_package(original, tmp_path / "tilted.cvjob")
    loaded = load_package(archive, tmp_path / "retained")
    resolved = resolve_setup_assets(loaded)
    destination = tmp_path / "preview"
    destination.mkdir()
    restored, _tools, _machine, _fixtures, _bank, _program, rest = prepare_job_preview(loaded, resolved, destination)
    assert restored.stock_orientation.degrees == (23, -32, 41)
    assert rest.orientation == residual.orientation and rest._occupied == residual._occupied
    resolved["stock"]["tilt_deg"] = [24, -32]
    with pytest.raises(ValueError, match="placement differs"):
        prepare_job_preview(loaded, resolved, destination)
