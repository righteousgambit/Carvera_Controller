"""Profile persistence and preview conversion must never imply a physical setup."""

import json
import math

import pytest

from carveracontroller.machine.desktop_profiles import (
    ProfileError,
    ProfileStore,
    initial_library,
    to_tool_definition,
    validate_library,
)


def tool(**changes):
    record = initial_library()["tools"][0]
    record.update(changes)
    return record


def machine(**changes):
    record = {
        "id": "my-machine",
        "name": "Garage Carvera",
        "model": "C1",
        "host": "192.168.0.79",
        "port": 2222,
        "camera_url": "http://localhost:18091/snapshot.jpg",
        "cad_path": "",
    }
    record.update(changes)
    return record


def test_atomic_restart_and_detached_reads(tmp_path):
    path = tmp_path / "library.json"
    store = ProfileStore(path)
    saved = store.save_machine(machine())
    saved["name"] = "changed copy"
    readback = store.data
    readback["machines"].clear()
    assert ProfileStore(path).data["machines"][0]["name"] == "Garage Carvera"
    assert not list(tmp_path.glob(".library.json.*"))


@pytest.mark.parametrize(
    "changes",
    [
        {"diameter": -1},
        {"diameter": math.inf},
        {"diameter": math.nan},
        {"number": True},
        {"shape": "spoon"},
        {"length": 10, "flute_length": 20},
        {"corner_radius": 4},
        {"shank_diameter": None},
        {"name": ""},
        {"thread_pitch": 0},
    ],
)
def test_bad_tool_cannot_overwrite_library(tmp_path, changes):
    store = ProfileStore(tmp_path / "library.json")
    store.save_machine(machine())
    before = store.path.read_bytes()
    with pytest.raises(ProfileError):
        store.save_tool(tool(**changes))
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "other"},
        {"host": "http://cnc/"},
        {"port": 0},
        {"camera_url": "file:///etc/passwd"},
        {"camera_url": "http://name:password@host/camera"},
    ],
)
def test_bad_machine_rejected(tmp_path, changes):
    with pytest.raises(ProfileError):
        ProfileStore(tmp_path / "lib.json").save_machine(machine(**changes))


def test_toolsets_preserve_slots_and_reference_integrity(tmp_path):
    store = ProfileStore(tmp_path / "library.json")
    tools = store.data["tools"]
    record = store.save_toolset({"name": "Aluminum cycle", "slots": {"2": tools[0]["id"], "6": tools[2]["id"]}})
    definitions = store.toolset_definitions(record)
    assert [t.number for t in definitions] == [2, 6]
    with pytest.raises(ProfileError, match="missing tool"):
        store.delete("tools", tools[0]["id"])
    store.delete("toolsets", record["id"])
    store.delete("tools", tools[0]["id"])
    assert len(store.data["tools"]) == 2


@pytest.mark.parametrize(
    "slots", [{"7": "bad"}, {"1": "bad"}, {"1": "inventory-square-quarter", "2": "inventory-square-quarter"}]
)
def test_invalid_slots_rejected(tmp_path, slots):
    store = ProfileStore(tmp_path / "library.json")
    with pytest.raises(ProfileError):
        store.save_toolset({"name": "Broken", "slots": slots})


def test_import_merge_updates_by_identity_and_exports(tmp_path):
    store = ProfileStore(tmp_path / "library.json")
    store.save_machine(machine())
    imported = initial_library()
    imported["tools"][0]["name"] = "Renamed cutter"
    imported["machines"] = [machine(id="other", name="Second machine")]
    source = tmp_path / "import.json"
    source.write_text(json.dumps(imported))
    counts = store.import_file(source)
    assert counts == {"machines": 1, "tools": 3, "toolsets": 0}
    assert len(store.data["machines"]) == 2
    assert len(store.data["tools"]) == 3
    assert store.data["tools"][0]["name"] == "Renamed cutter"
    exported = tmp_path / "export.json"
    store.export_file(exported)
    assert ProfileStore(exported).data == store.data


def test_malformed_and_oversize_import_leave_bytes_untouched(tmp_path):
    store = ProfileStore(tmp_path / "library.json")
    store.save_machine(machine())
    before = store.path.read_bytes()
    source = tmp_path / "bad.json"
    for content in ("not JSON", '{"schema":2}', " " * (2 * 1024 * 1024 + 1)):
        source.write_text(content)
        with pytest.raises(ProfileError):
            store.import_file(source)
        assert store.path.read_bytes() == before


def test_duplicate_ids_and_nonfinite_schema_rejected():
    library = initial_library()
    library["tools"].append(library["tools"][0])
    with pytest.raises(ProfileError, match="Duplicate"):
        validate_library(library)


def test_preview_conversion_uses_units_without_modifying_profile():
    profile = tool()
    definition = to_tool_definition(profile, number=6, units="in")
    assert definition.diameter == pytest.approx(0.25)
    assert definition.length == pytest.approx(3)
    assert definition.number == 6
    assert profile["number"] == 1
    assert profile["diameter"] == 6.35
    with pytest.raises(ProfileError):
        to_tool_definition(profile, units="cm")


def test_seed_has_no_assumed_slots_or_machine_configuration():
    data = initial_library()
    assert data["machines"] == []
    assert data["toolsets"] == []
    assert len(data["tools"]) == 3
    assert all("unverified" in t["notes"] for t in data["tools"])


def test_failed_atomic_replace_preserves_disk_and_memory(tmp_path, monkeypatch):
    store = ProfileStore(tmp_path / "library.json")
    store.save_machine(machine())
    before_bytes, before_data = store.path.read_bytes(), store.data

    def fail_replace(*_args):
        raise OSError("Disk write interrupted")

    monkeypatch.setattr("carveracontroller.machine.desktop_profiles.os.replace", fail_replace)
    with pytest.raises(OSError):
        store.save_machine(machine(name="Uncommitted change"))
    assert store.path.read_bytes() == before_bytes
    assert store.data == before_data
    assert not list(tmp_path.glob(".library.json.*"))


def test_corrupt_existing_store_is_preserved(tmp_path):
    path = tmp_path / "library.json"
    path.write_text('{"schema": true}')
    with pytest.raises(ProfileError):
        ProfileStore(path)
    assert path.read_text() == '{"schema": true}'


def test_tool_assets_stickout_and_source_survive_save_and_unit_conversion(tmp_path):
    store = ProfileStore(tmp_path / "lib.json")
    item = store.save_tool(tool(geometry_path="/tool.json.gz", holder_geometry_path="/holder.json.gz",
                                drawing_path="/tool.dxf", source_url="https://vendor.example/tool", stickout=35))
    reread = next(record for record in ProfileStore(store.path).data["tools"] if record["id"] == item["id"])
    assert reread["stickout"] == 35
    definition = to_tool_definition(item, units="in")
    assert definition.stickout == pytest.approx(35 / 25.4)
    assert definition.geometry_unit_scale == pytest.approx(1 / 25.4)
    assert definition.geometry_path == "/tool.json.gz"
    assert definition.drawing_path == "/tool.dxf"


@pytest.mark.parametrize("change", [{"stickout": 80}, {"stickout": 20}, {"stickout": math.nan},
                                    {"source_url": "file:///private"}, {"source_url": "https://user:secret@vendor.test"}])
def test_invalid_stickout_and_asset_source_rejected(change):
    with pytest.raises(ProfileError):
        validate_library({"schema": 1, "tools": [tool(**change)]})


def test_machine_vise_draft_placement_persists(tmp_path):
    store = ProfileStore(tmp_path / "lib.json")
    store.save_machine(machine(vise_x=20, vise_rotation=90, vise_jaw_offset=5))
    result = ProfileStore(store.path).data["machines"][0]
    assert (result["vise_x"], result["vise_y"], result["vise_rotation"], result["vise_jaw_offset"]) == (20, 0, 90, 5)
    with pytest.raises(ProfileError):
        store.save_machine(machine(vise_x=float("inf")))
