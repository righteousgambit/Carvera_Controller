import copy
import hashlib
import json
import zipfile

import pytest

from carveracontroller.machine.camera_calibration_file import decode_calibration
from carveracontroller.machine.job_packages import (
    JobPackage,
    JobPackageError,
    load_package,
    retained_camera_calibration,
    save_package,
)
from tests.unit.test_camera_calibration_file import data


def job():
    calibration = decode_calibration(data())
    return JobPackage("Camera setup", b"G21\n", camera_calibration=calibration)


def test_job_roundtrip_retains_exact_reference_without_mutating_ui_snapshot(tmp_path):
    original = job()
    pending = original.camera_calibration
    archive = save_package(original, tmp_path / "first.cvjob")
    assert original.camera_calibration is pending and original.assets == {} and original.inspection_plan == {}
    loaded = load_package(archive, tmp_path / "installed")
    key = loaded.package.inspection_plan["camera_calibration_path"]
    assert key.startswith("asset://") and loaded.asset_paths[key].suffix == ".cvcal"
    _, observations, reference, y = retained_camera_calibration(loaded)
    assert reference.frame.jpeg == pending[2].frame.jpeg
    assert reference.machine_mm == pending[2].machine_mm and y == -100
    assert observations == pending[1]
    second = save_package(loaded.package, tmp_path / "second.cvjob")
    assert retained_camera_calibration(load_package(second))[2].to_dict() == reference.to_dict()


def test_corrupt_calibration_with_updated_archive_hash_is_rejected_before_install(tmp_path):
    archive = save_package(job(), tmp_path / "original.cvjob")
    with zipfile.ZipFile(archive) as source:
        files = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(files["manifest.json"])
    old_ref = manifest["setup"]["inspection_plan"]["camera_calibration_path"]
    old_hash = old_ref.removeprefix("asset://")
    calibration = json.loads(files.pop("assets/" + old_hash))
    calibration["reference"]["jpeg_sha256"] = "0" * 64
    raw = json.dumps(calibration).encode()
    digest = hashlib.sha256(raw).hexdigest()
    manifest["assets"].pop(old_hash)
    manifest["assets"][digest] = {"size": len(raw), "suffix": ".cvcal"}
    manifest["setup"]["inspection_plan"]["camera_calibration_path"] = "asset://" + digest
    files["assets/" + digest] = raw
    files["manifest.json"] = json.dumps(manifest).encode()
    corrupted = tmp_path / "corrupt.cvjob"
    with zipfile.ZipFile(corrupted, "w") as destination:
        for name, payload in files.items():
            destination.writestr(name, payload)
    with pytest.raises(JobPackageError, match="JPEG hash"):
        load_package(corrupted, tmp_path / "rejected")
    assert not (tmp_path / "rejected").exists()


def test_legacy_numeric_registration_has_no_reference_and_inline_budget_is_enforced(tmp_path, monkeypatch):
    registration = copy.deepcopy(data())
    registration.pop("reference")
    registration.pop("schema")
    original = JobPackage("Legacy", b"G21", inspection_plan={"camera_registration": registration})
    restored = load_package(save_package(original, tmp_path / "legacy.cvjob"))
    assert retained_camera_calibration(restored)[2] is None
    monkeypatch.setattr("carveracontroller.machine.job_packages.MAX_MEMBER", 100)
    with pytest.raises(JobPackageError, match="Oversized"):
        save_package(JobPackage("Bytes", b"G21", assets={"large.cvcal": b"x" * 101}), tmp_path / "large.cvjob")
