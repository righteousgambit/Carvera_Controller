import copy
import json
import os
from types import SimpleNamespace

import pytest

from carveracontroller.addons.cad_identity import asset_digest, read_asset_bytes
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.tool_visualization.cad_assets import load_tool_asset
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.geometry_changes import (
    affected_operations,
    asset_problems,
    capture_context,
    context_changes,
    digest_context,
)
from carveracontroller.machine.program_operations import ProgramOperations


def viewer():
    return SimpleNamespace(
        machine_setup=MachineSetup(stock_size_mm=(10, 20, 30)),
        library_tool_table_mm={
            1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=3, flute_length=5, stickout=10),
            2: ToolDefinition(2, ToolType.BALL_END_MILL, diameter=2),
        },
        machine_component_profiles={},
        machine_profile=None,
        assembly_preview_binding=None,
        workholding_offset_mm=(1, 2, 3),
        workholding_rotation_deg=90,
        jaw_offset_mm=4,
    )


def program():
    return ProgramOperations.from_text(
        "G21 G90 G17 G94\n(rough)\nT1 M6\nG0 X0 Y0 Z5\nG1 Z0 F100\nG1 X5\n(finish)\nT2 M6\nG0 X0 Y0 Z5\nG1 Z0 F100\nG1 Y5\n"
    )


def test_refresh_context_uses_index_without_hiding_tool_edits(monkeypatch):
    loaded = program()
    state = viewer()
    baseline = capture_context(state, loaded, verify_assets=False)
    monkeypatch.setattr(
        ProgramOperations, "motion_segments", property(lambda _: pytest.fail("Context refresh scanned motion"))
    )
    assert capture_context(state, loaded, verify_assets=False) == baseline
    state.library_tool_table_mm[1].stickout = 12
    changed = capture_context(state, loaded, verify_assets=False)
    assert digest_context(changed) != digest_context(baseline)
    assert any(change.title == "T1 stickout" for change in context_changes(baseline, changed))


def test_exact_bytes_detect_same_path_size_and_timestamp_replacement(tmp_path):
    path = tmp_path / "tool.json"
    path.write_text(
        json.dumps(
            {
                "schema": "carvera-tool-mesh-v1",
                "units": "mm",
                "axis": "+Z",
                "origin": "tip",
                "triangles": [0, 0, 0, 1, 0, 2, 0, 1, 2],
            }
        )
    )
    tool = viewer()
    tool.library_tool_table_mm[1].geometry_path = str(path)
    tool.library_tool_table_mm[1].geometry_sha256 = asset_digest(path)
    baseline = capture_context(tool, program())
    old_stat = path.stat()
    path.write_text(path.read_text().replace("1, 0, 2", "2, 0, 2"))
    os.utime(path, ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns))
    assert path.stat().st_size == old_stat.st_size
    changed = capture_context(tool, program())
    assert digest_context(changed) != digest_context(baseline)
    assert "CAD bytes changed" in asset_problems(changed)[0]
    changes = context_changes(baseline, changed)
    assert any(change.title == "T1 cutter asset" for change in changes)
    assert all(1 in operation.tool_ids for operation in affected_operations(changes, program().operations))
    with pytest.raises(ValueError, match="CAD bytes changed"):
        load_tool_asset(path, tool.library_tool_table_mm[1].geometry_sha256)
    path.unlink()
    assert "unreadable" in asset_problems(capture_context(tool, program()))[0]


@pytest.mark.parametrize("field", ["stock", "work_offset_mm", "workholding", "components", "program"])
def test_setup_changes_affect_all_operations_and_retain_old_and_new_values(field):
    baseline = capture_context(viewer(), program())
    changed = copy.deepcopy(baseline)
    changed[field] = {"changed": True}
    changes = context_changes(baseline, changed)
    assert changes and changes[0].before != changes[0].after
    assert affected_operations(changes, program().operations) == program().operations


def test_tool_change_scopes_dependencies_and_json_roundtrip_preserves_identity():
    baseline = capture_context(viewer(), program())
    restored = json.loads(json.dumps(baseline))
    assert digest_context(restored) == digest_context(baseline)
    assert context_changes(baseline, restored) == ()
    changed = copy.deepcopy(baseline)
    changed["tools"]["2"]["diameter"] = 4
    changes = context_changes(baseline, changed)
    assert changes[0].title == "T2 diameter"
    assert changes[0].before == "2" and changes[0].after == "4"
    affected = affected_operations(changes, program().operations)
    assert affected and all(2 in operation.tool_ids for operation in affected)
    assert len(affected) < len(program().operations)


def test_asset_read_is_bounded_and_pins_the_bytes_used_for_parsing(tmp_path):
    path = tmp_path / "asset.json"
    path.write_bytes(b"abcd")
    with pytest.raises(ValueError, match="size limit"):
        read_asset_bytes(path, 3)
    assert asset_digest("") == ""


def test_metadata_does_not_invalidate_machining_but_holder_and_assembly_do():
    state = viewer()
    baseline = capture_context(state, program())
    state.library_tool_table_mm[1].description = "renamed catalog item"
    assert digest_context(capture_context(state, program())) == digest_context(baseline)
    state.library_tool_table_mm[1].stickout = 12
    assert context_changes(baseline, capture_context(state, program()))[0].title == "T1 stickout"
    state.assembly_preview_binding = {
        "assembly_id": "assembly",
        "revision_id": "revision-2",
        "profile_id": "design",
        "design_fingerprint": "abc",
        "number": 1,
    }
    changes = context_changes(baseline, capture_context(state, program()))
    assert any(change.title == "Physical assembly revision" for change in changes)


def test_machine_asset_change_and_unversioned_bytes_require_reload(tmp_path):
    state = viewer()
    path = tmp_path / "machine.json.gz"
    path.write_bytes(b"old converted mesh")
    state.machine_component_profiles["fixture"] = SimpleNamespace(
        asset_path=str(path),
        asset_sha256=asset_digest(path),
        source_revision="vendor-1",
        source_sha256="manufacturer-source",
    )
    baseline = capture_context(state, program())
    path.write_bytes(b"new converted mesh")
    changed = capture_context(state, program())
    assert "fixture: CAD bytes changed" in asset_problems(changed)[0]
    assert affected_operations(context_changes(baseline, changed), program().operations) == program().operations
    state.machine_component_profiles["fixture"].asset_sha256 = ""
    assert "unversioned" in asset_problems(capture_context(state, program()))[0]


def test_periodic_definition_check_performs_no_file_io(monkeypatch):
    from carveracontroller.machine import geometry_changes

    state = viewer()
    state.library_tool_table_mm[1].geometry_path = "/not-read-in-refresh.json"
    state.library_tool_table_mm[1].geometry_sha256 = "loaded-bytes"
    monkeypatch.setattr(geometry_changes, "asset_digest", lambda *_args: pytest.fail("CAD file read in refresh loop"))
    context = capture_context(state, program(), verify_assets=False)
    assert context["tools"]["1"]["cutter_asset"]["current_sha256"] == "loaded-bytes"
