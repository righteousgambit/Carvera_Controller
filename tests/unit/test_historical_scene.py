import gzip
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.historical_scene import definitions_from_snapshot, prepare_historical_scene
from carveracontroller.machine.job_packages import JobPackage
from carveracontroller.machine.recording_setup import bind_recording_setup
from carveracontroller.machine.run_recording import RecordingReplay
from tests.unit.test_machine_profile import profile_data


def historical_fixture(tmp_path, *, crlf=False, angles=None):
    program = tmp_path / "source.nc"
    program.write_bytes(b"G21 G90\r\nG1 X1 F100\r\n" if crlf else b"G21 G90\nG1 X1 F100\n")
    cad = tmp_path / "machine.json.gz"
    data = profile_data()
    data["components"].append({**data["components"][0], "group": "fixture"})
    cad.write_bytes(gzip.compress(json.dumps(data).encode()))
    cutter = tmp_path / "cutter.json.gz"
    cutter.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "schema": "carvera-tool-mesh-v1",
                    "units": "mm",
                    "axis": "+Z",
                    "origin": "tip",
                    "triangles": [0, 0, 0, 1, 0, 2, 0, 1, 2],
                }
            ).encode()
        )
    )
    tool = asdict(
        ToolDefinition(
            2,
            tool_type=ToolType.FLAT_END_MILL,
            diameter=6,
            length=20,
            geometry_path=str(cutter),
            geometry_sha256=hashlib.sha256(cutter.read_bytes()).hexdigest(),
        )
    )
    tool["tool_type"] = tool["tool_type"].value
    setup = {
        "work_offset_mm": [-10, -20, -30],
        "stock_size_mm": [10, 20, 8],
        "stock_origin_mm": [0, 0, 0],
        "alignment_confirmed": True,
    }
    job = JobPackage(
        "Historical",
        b"",
        machine={"cad_path": str(cad)},
        fixtures=[{"group": "fixture", "cad_path": str(cad)}],
        stock={
            "size_mm": setup["stock_size_mm"],
            "origin_mm": [0, 0, 0],
            "work_offset_mm": setup["work_offset_mm"],
            "alignment_confirmed": True,
        },
        vise={"offset_mm": [1, 2, 3], "rotation_deg": 90, "jaw_offset_mm": 4},
        inspection_plan={"tool_definitions_mm": [tool]},
        assets={str(cad): cad, str(cutter): cutter},
    )
    if angles is not None:
        setup.update(stock_rotation_deg=angles[2], stock_tilt_deg=angles[:2])
        job.stock.update(rotation_deg=angles[2], tilt_deg=list(angles[:2]))
    record, archive = bind_recording_setup(program, setup, job, tmp_path / "snapshots")
    return program, RecordingReplay(record.export_bytes()), archive, cutter


@pytest.mark.parametrize("crlf", [False, True])
def test_retained_cad_and_tools_restore_independently_of_original_sources(tmp_path, crlf):
    program, replay, archive, cutter = historical_fixture(tmp_path, crlf=crlf)
    cutter.write_bytes(b"changed original")
    inspection_hash = hashlib.sha256(program.read_text().encode()).hexdigest()
    prepared = prepare_historical_scene(replay, archive, tmp_path / "preview", {}, 1, 0.1, program, inspection_hash)
    assert prepared.profile is not None and prepared.components["fixture"].groups["fixture"].indices
    assert prepared.geometry["stock"].indices
    assert prepared.setup.work_offset_mm == (-10, -20, -30)
    assert not prepared.setup.alignment_confirmed  # Retained declarations do not become measured proof.
    assert prepared.offset == (1, 2, 3) and prepared.rotation == 90 and prepared.jaw == 4
    assert set(prepared.definitions) == {2} and prepared.meshes[2][1] == [0, 1, 2]
    assert prepared.definitions[2].geometry_path != str(cutter)
    assert Path(prepared.definitions[2].geometry_path).read_bytes() != cutter.read_bytes()
    assert prepared.context["session_id"] == replay.payload["session_id"]


def test_corrupt_archive_or_wrong_program_withholds_preparation(tmp_path):
    program, replay, archive, _ = historical_fixture(tmp_path)
    inspection_hash = hashlib.sha256(program.read_text().encode()).hexdigest()
    program.write_bytes(b"G21\nG1 X99\n")
    with pytest.raises(ValueError, match="exact recorded program"):
        prepare_historical_scene(replay, archive, tmp_path / "wrong", {}, 1, 1, program, inspection_hash)
    archive.write_bytes(b"changed archive")
    with pytest.raises(ValueError, match="bytes differ"):
        prepare_historical_scene(replay, archive, tmp_path / "corrupt", {}, 1, 1, program, inspection_hash)
    assert not (tmp_path / "corrupt").exists()


@pytest.mark.parametrize(
    "records",
    [
        [{"number": True}],
        [{"number": 1, "diameter": float("nan")}],
        [{"number": 1, "diameter": 10**1000}],
        [{"number": 1}, {"number": 1}],
        [{"number": 1, "geometry_unit_scale": 25.4}],
        [{"number": 1, "unexpected": "field"}],
    ],
)
def test_malformed_tool_definitions_are_rejected(records):
    with pytest.raises(ValueError):
        definitions_from_snapshot(records)


def test_publication_failure_restores_prior_metadata_and_render(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from carveracontroller.desktop_historical_scene import SCENE_FIELDS, apply_historical_scene, capture_scene

    program, replay, archive, _ = historical_fixture(tmp_path)
    prepared = prepare_historical_scene(
        replay,
        archive,
        tmp_path / "preview",
        {},
        1,
        1,
        program,
        hashlib.sha256(program.read_text().encode()).hexdigest(),
    )
    viewer = SimpleNamespace(**{name: object() for name in SCENE_FIELDS})
    viewer.move_scale_by_positon = 1
    viewer.machine_visible = True
    viewer.pointer_mesh_instrs = []
    viewer.refresh_declared_playback = Mock()
    viewer._machine_pose_for = Mock(return_value={})
    viewer._build_machine_scene = Mock(side_effect=[RuntimeError("renderer failed"), None])
    viewer.canvas = SimpleNamespace(ask_update=Mock())
    before = capture_scene(viewer)
    retained_edges = viewer._repeat_stock_edges
    with pytest.raises(RuntimeError, match="renderer failed"):
        apply_historical_scene(viewer, prepared)
    assert capture_scene(viewer) == before
    assert viewer._repeat_stock_edges is retained_edges
    assert viewer._build_machine_scene.call_count == 2


def test_inventory_distinguishes_retained_cad_and_unmeasured_setup(tmp_path):
    from carveracontroller.machine.historical_scene import scene_inventory

    program, replay, archive, _ = historical_fixture(tmp_path)
    prepared = prepare_historical_scene(
        replay,
        archive,
        tmp_path / "preview",
        {},
        1,
        1,
        program,
        hashlib.sha256(program.read_text().encode()).hexdigest(),
    )
    summary = scene_inventory(prepared)
    assert "Recorded machine:" in summary and "Fixture plate:" in summary
    assert "Stock: 10 × 20 × 8 mm · Work offset: -10, -20, -30 mm" in summary
    assert "Archived tools: 1 · Cutter CAD references: 1 · Holder CAD references: 0" in summary
    assert "alignment remains unmeasured" in summary
    assert not prepared.setup.alignment_confirmed


@pytest.mark.parametrize(
    "changes",
    [
        {"thread_teeth": 2.5},
        {"thread_teeth": 1},
        {"thread_teeth": 201},
        {"thread_pitch": None},
        {"thread_tip_offset": None},
        {"flute_length": 2},
        {"tool_type": "flat_end_mill"},
    ],
)
def test_recorded_multi_form_tools_reject_incomplete_or_impossible_teeth(changes):
    record = {
        "number": 3,
        "tool_type": "thread_mill",
        "thread_pitch": 1,
        "thread_teeth": 3,
        "thread_tip_offset": 0.5,
        "flute_length": 5,
    }
    before = {**record, **changes}
    with pytest.raises(ValueError, match="multi-form|tooth stack"):
        definitions_from_snapshot([before])
    assert before == {**record, **changes}


def test_recorded_complete_thread_stack_and_unbound_recording():
    from carveracontroller.machine.run_recording import RunRecording

    record = {
        "number": 3,
        "tool_type": "thread_mill",
        "thread_pitch": 1,
        "thread_teeth": 3,
        "thread_tip_offset": 0.5,
        "flute_length": 5,
    }
    assert definitions_from_snapshot([record])[3].thread_teeth == 3
    replay = RecordingReplay(RunRecording().export_bytes())
    with pytest.raises(ValueError, match="no retained setup archive"):
        prepare_historical_scene(replay, "unused", "unused", {}, 1, 1, "unused", "a" * 64)


def test_historical_preview_retains_all_three_stock_angles(tmp_path):
    angles = (23, -32, 41)
    program, replay, archive, _cutter = historical_fixture(tmp_path, angles=angles)
    inspection_hash = hashlib.sha256(program.read_text().encode()).hexdigest()
    prepared = prepare_historical_scene(
        replay, archive, tmp_path / "tilted-preview", {}, 1, 0.1, program, inspection_hash
    )
    assert prepared.setup.stock_orientation.degrees == angles
    assert prepared.geometry["stock"].indices
    assert not prepared.setup.alignment_confirmed
