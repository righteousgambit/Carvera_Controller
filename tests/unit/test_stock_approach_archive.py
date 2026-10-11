"""Complete route replay, detached bytes, source identity and forged evidence controls."""

import hashlib
import json
from dataclasses import replace
from types import MappingProxyType

import pytest

from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource, review_program_body_records
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_stock_evolution import review_stock_evolution
from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
from carveracontroller.machine.stock_allowance import inspect_target_cell
from carveracontroller.machine.stock_approach_archive import load_approach_review, save_approach_review
from carveracontroller.machine.stock_approach_clearance import review_stock_approach
from carveracontroller.machine.stock_approach_path import ApproachStart, capture_start
from carveracontroller.machine.stock_approach_record import approach_record
from carveracontroller.machine.stock_finishing import compare_stock_continuation
from carveracontroller.machine.stock_target import analyze_stock_target, prepare_stock_target
from carveracontroller.machine.surface_motion import SurfaceMesh
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_solid import box


def prepared(tmp_path, *, captured=False, groups=False):
    parent, analysis = example(tmp_path)
    text = "G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG0 X1\nG1 X0 F100\nG0 X1\nT2 M6\nG0 X0\nG1 X1 F100"
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(text))
    offsets = {"G54": (-9, -5, -10)}
    assert source.file_hash == parent.body_review.program_hash
    if groups:
        meshes = {tool: dict(rows) for tool, rows in parent.meshes.items()}
        for tool, record in parent.body_review.records.items():
            for name, lo, hi in (("Rigid A", (10, 10, 10), (12, 12, 12)), ("Rigid B", (11, 11, 11), (13, 13, 13))):
                record["collision_bodies"].append(
                    {"name": name, "frame": "world", "joint_count": 0, "minimum_mm": lo, "maximum_mm": hi}
                )
                meshes[tool][name] = SurfaceMesh.create(box(lo, hi), index_method="surface-directions-v3")
        body = review_program_body_records(source, parent.body_review.records, offsets)
        history = review_stock_evolution(body, parent.stock_evolution.inputs, parent.rotating_envelopes)
        parent = replace(parent, body_review=body, stock_evolution=history, meshes=MappingProxyType(meshes))
    name = analysis.target.stock
    state = reconstruct_stock_move(parent.body_review, parent.stock_evolution, parent.rotating_envelopes, name, 0)
    comparison = compare_stock_continuation(
        parent.body_review, parent.stock_evolution, parent.rotating_envelopes, state, name, 2, 6
    )
    target = prepare_stock_target(state, name, analysis.target.source_path, units="mm")
    analysis = analyze_stock_target(target, state, comparison)
    cell = inspect_target_cell(analysis, "T2 continuation", (1, 1, 0), tool=2)
    origin = ApproachStart((-9.0, -5.0, -8.0))
    if captured:
        pose = ObservedPose(10, "Idle", origin.machine_mm, (0.0, 0.0, 2.0), 2, 30.0, 0.0, 0, 0.0)
        origin = capture_start(pose, connected=True, tool=2, now=10.1)
    result = review_stock_approach(cell, parent, route_start=origin)
    return source, offsets, result, comparison


@pytest.mark.parametrize("captured", [False, True])
def test_source_replay_embedded_target_shared_groups_and_byte_identical_resave(tmp_path, captured):
    source, offsets, result, comparison = prepared(tmp_path, captured=captured, groups=True)
    path = tmp_path / "route.cvapproachreview"
    digest = save_approach_review(path, source, offsets, result, comparison=comparison)
    raw = path.read_bytes()
    assert digest == hashlib.sha256(raw).hexdigest()
    payload = json.loads(raw)
    pool, wrappers = payload["report"]["scene"]["group_pool"], payload["report"]["scene"]["group_wrappers"]
    assert pool and len(wrappers) > len(pool)
    assert len({r["group"] for r in wrappers}) == len(pool)
    # Opening reads embedded bytes; the provenance path is not an external read.
    from pathlib import Path

    Path(result.inspection.analysis.target.source_path).unlink()
    loaded = load_approach_review(path)
    assert encoded(approach_record(loaded.report, cancelled=lambda: False)) == encoded(
        approach_record(result, cancelled=lambda: False)
    )
    assert loaded.source.text == source.text and dict(loaded.work_offsets) == offsets
    assert loaded.report.start_evidence == result.start_evidence
    assert loaded.comparison.candidate_tool == 2 and loaded.comparison.end_line == 6
    assert loaded.sha256 == digest
    again = tmp_path / "again.cvapproachreview"
    save_approach_review(
        again,
        loaded.source,
        loaded.work_offsets,
        loaded.report,
        comparison=loaded.comparison,
        clearance_mm=loaded.clearance_mm,
        target_raw=loaded.target_raw,
    )
    assert again.read_bytes() == raw


def resign(payload):
    payload.pop("sha256", None)
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    return encoded(payload)


@pytest.mark.parametrize(
    "change",
    [
        "method",
        "schema",
        "body_schema",
        "source",
        "waypoint",
        "cell",
        "tool",
        "state",
        "clearance",
        "continuation",
        "target_translation",
        "target_bytes",
        "stock_history",
        "pool",
        "wrapper",
        "material",
        "mask",
        "count",
        "rational",
    ],
)
def test_rehashed_context_or_evidence_changes_are_recomputed(tmp_path, change):
    source, offsets, result, comparison = prepared(tmp_path, groups=True)
    path = tmp_path / "route.cvapproachreview"
    save_approach_review(path, source, offsets, result, comparison=comparison)
    data = json.loads(path.read_bytes())
    if change == "method":
        data["method"] = "unknown"
    elif change == "schema":
        data["schema"] = True
    elif change == "body_schema":
        data["body"]["schema"] = 3
    elif change == "source":
        data["body"]["source"]["text"] += "\nG1 X12"
    elif change == "waypoint":
        data["selection"]["start"]["machine_mm"][0] += 0.5
    elif change == "cell":
        data["selection"]["cell"][0] = True
    elif change == "tool":
        data["selection"]["tool"] = 1
    elif change == "state":
        data["selection"]["label"] = "Initial stock"
    elif change == "clearance":
        data["selection"]["clearance_mm"] = 2
    elif change == "continuation":
        data["selection"]["continuation"]["end_line"] = 3
    elif change == "target_translation":
        data["target"]["translation_mm"][0] = 0.25
    elif change == "target_bytes":
        data["target"]["raw_base64"] = "AAAA"
    elif change == "stock_history":
        data["history"]["cell_work"] += 1
    elif change == "pool":
        data["report"]["scene"]["group_pool"][0]["triangle_pairs"].pop()
    elif change == "wrapper":
        data["report"]["scene"]["group_wrappers"][0]["group"] = True
    elif change == "material":
        data["report"]["material"]["legs"][0]["cutting"] = True
    elif change == "mask":
        data["report"]["target_analysis"]["fits"]["Initial stock"]["excess_mm3"] += 1
    elif change == "count":
        data["report"]["scene"]["rigid_reused_pairs"] += 1
    elif change == "rational":
        data["report"]["inspection"]["nearest"]["distance_squared"]["denominator"] = "0"
    path.write_bytes(resign(data))
    with pytest.raises(ValueError):
        load_approach_review(path)


def test_cancelled_or_inconsistent_save_preserves_destination(tmp_path):
    source, offsets, result, comparison = prepared(tmp_path)
    path = tmp_path / "route.cvapproachreview"
    path.write_bytes(b"previous independent artifact")
    with pytest.raises(InterruptedError):
        save_approach_review(path, source, offsets, result, comparison=comparison, cancelled=lambda: True)
    assert path.read_bytes() == b"previous independent artifact"
    with pytest.raises(ValueError):
        save_approach_review(path, source, offsets, result)
    assert path.read_bytes() == b"previous independent artifact"


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":1}', b'{"x":NaN}', b'{"x":111111111111111111111}', b"[]"])
def test_bounded_wire_refusals(tmp_path, raw):
    path = tmp_path / "invalid.cvapproachreview"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        load_approach_review(path)


@pytest.mark.parametrize("field", ["timestamp", "tool_length_mm", "work_mm", "state"])
def test_historical_pose_metadata_is_recomputed_without_claiming_freshness(tmp_path, field):
    source, offsets, result, comparison = prepared(tmp_path, captured=True)
    path = tmp_path / "historical.cvapproachreview"
    save_approach_review(path, source, offsets, result, comparison=comparison)
    payload = json.loads(path.read_bytes())
    packet = payload["selection"]["start"]["observed"]
    if field == "work_mm":
        packet[field][0] += 0.5
    elif field == "state":
        packet[field] = "Run"
    else:
        packet[field] += 1
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError):
        load_approach_review(path)


@pytest.mark.parametrize("operation", ["save", "load"])
def test_wire_size_refusal_preserves_existing_destination(tmp_path, monkeypatch, operation):
    import carveracontroller.machine.stock_approach_archive as archive

    source, offsets, result, comparison = prepared(tmp_path)
    path = tmp_path / "bounded.cvapproachreview"
    previous = b"x" * 513
    path.write_bytes(previous)
    monkeypatch.setattr(archive, "MAX_BYTES", 512)
    with pytest.raises(ValueError, match="MiB"):
        if operation == "save":
            save_approach_review(path, source, offsets, result, comparison=comparison)
        else:
            load_approach_review(path)
    assert path.read_bytes() == previous


def test_actual_phase_observations_and_last_publication_cancellation(tmp_path):
    source, offsets, result, comparison = prepared(tmp_path)
    path = tmp_path / "cancel-at-publish.cvapproachreview"
    path.write_bytes(b"old complete artifact")
    phases, stop = [], [False]

    def phase(name):
        phases.append(name)
        if name == "Publish verified route bytes":
            stop[0] = True

    with pytest.raises(InterruptedError):
        save_approach_review(
            path, source, offsets, result, comparison=comparison, phase=phase, cancelled=lambda: stop[0]
        )
    assert path.read_bytes() == b"old complete artifact"
    assert "Reparse source and machine bodies" in phases
    assert "Review complete machine approach" in phases
    assert phases[-1] == "Publish verified route bytes"
    assert not list(tmp_path.glob(".cancel-at-publish.cvapproachreview.*"))
