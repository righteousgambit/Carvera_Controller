import json
from dataclasses import replace

import pytest

from carveracontroller.machine.geometry_changes import digest_context
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_archive import load_repeat_result, save_repeat_result
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts

from .test_repeat_simulation import TEXT, definitions, plan


def sample():
    program = ProgramOperations.from_text(TEXT)
    result = simulate_repeat_parts(program, plan(), definitions(), {}, 1)
    context = {
        "program": program.file_hash,
        "repeat_plan": plan().to_dict(),
        "tools": {},
        "components": {},
        "machine_profile_id": "test",
        "resolution_mm": 1,
    }
    return program, result, context


def test_roundtrip_preserves_every_stock_occupancy_geometry_and_summary(tmp_path):
    program, result, context = sample()
    path = tmp_path / "array.cvstocks"
    save_repeat_result(path, result, context)
    loaded = load_repeat_result(path, program, context)
    assert loaded.plan == result.plan
    assert loaded.snapshots == tuple(json.loads(json.dumps(result.snapshots)))
    assert loaded.reports == tuple(replace(report, clearance_details=()) for report in result.reports)
    assert loaded.segments == result.segments
    assert loaded.geometries == result.geometries
    assert loaded.unresolved_lines == (3,)


def test_changed_context_corruption_and_cancel_do_not_load(tmp_path):
    program, result, context = sample()
    path = tmp_path / "array.cvstocks"
    save_repeat_result(path, result, context)
    with pytest.raises(ValueError, match="does not match"):
        load_repeat_result(path, program, {**context, "machine_profile_id": "other"})
    with pytest.raises(InterruptedError, match="cancelled"):
        load_repeat_result(path, program, context, cancelled=lambda: True)
    data = json.loads(path.read_text())
    data["stocks"][1]["occupancy_sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity"):
        load_repeat_result(path, program, context)
    data.pop("sha256")
    data["sha256"] = digest_context(data)
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="integrity"):
        load_repeat_result(path, program, context)


@pytest.mark.parametrize("change", ["placement", "volume", "missing", "duplicate", "resolution", "compression"])
def test_resigned_malformed_data_is_still_rejected(tmp_path, change):
    program, result, context = sample()
    path = tmp_path / "array.cvstocks"
    save_repeat_result(path, result, context)
    data = json.loads(path.read_text())
    data.pop("sha256")
    if change == "placement":
        data["stocks"][0]["minimum"][0] += 1
    elif change == "volume":
        data["reports"][1]["removed_volume_mm3"] += 1
    elif change == "missing":
        data["stocks"].pop()
    elif change == "resolution":
        data["stocks"][0]["resolution_mm"] = 2
    elif change == "compression":
        data["stocks"][0]["occupancy_zlib_base64"] = "YmFk"
    data["sha256"] = digest_context(data)
    encoded = json.dumps(data)
    if change == "duplicate":
        encoded = encoded.replace('"schema": 1', '"schema": 1, "schema": 1', 1)
    path.write_text(encoded)
    with pytest.raises(ValueError):
        load_repeat_result(path, program, context)


def test_changed_asset_bytes_rejected_before_save(tmp_path):
    program, result, context = sample()
    asset = tmp_path / "fixture.json"
    asset.write_text("changed")
    context["components"] = {
        "fixture": {"asset": {"path": str(asset), "loaded_sha256": "0" * 64, "current_sha256": "0" * 64, "error": ""}}
    }
    with pytest.raises(ValueError, match="changed"):
        save_repeat_result(tmp_path / "array.cvstocks", result, context)


def test_cancelled_save_preserves_previous_file_and_cleans_staging(tmp_path):
    _, result, context = sample()
    path = tmp_path / "array.cvstocks"
    path.write_bytes(b"original")
    calls = iter((False, True))
    with pytest.raises(InterruptedError, match="previous file retained"):
        save_repeat_result(path, result, context, cancelled=lambda: next(calls))
    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]
