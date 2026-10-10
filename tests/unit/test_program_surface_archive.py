"""Exact source, prepared geometry and independently recomputed surface/solid exchange."""

import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource, review_program_body_records
from carveracontroller.machine.program_surface_archive import (
    load_surface_review,
    save_surface_review,
    surface_report_record,
)
from carveracontroller.machine.program_surface_clearance import refine_program_surfaces, review_program_surfaces
from carveracontroller.machine.surface_motion import SurfaceMesh
from tests.unit.test_program_joint_clearance import captures, program, review
from tests.unit.test_stock_solid import box, reverse


@pytest.fixture(scope="module")
def example():
    source = ProgramClearanceSource.capture(program("T2 M6\nG1 X11"))
    offsets = {"G54": (-180, -120, -110)}
    return source, offsets, review_program_surfaces(source, captures(1, 2), offsets)


def resign(payload, *, geometry=False):
    payload.pop("sha256", None)
    if geometry:
        geo = payload["geometry"]
        geo["sha256"] = hashlib.sha256(encoded({k: geo[k] for k in ("pool", "tools")})).hexdigest()
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    return encoded(payload)


def saved(tmp_path, example):
    path = tmp_path / "review.cvsurfacereview"
    save_surface_review(path, *example)
    return path


def test_complete_roundtrip_recomputes_body_surfaces_solids_and_preserves_shared_meshes(tmp_path, example):
    path = saved(tmp_path, example)
    archive = load_surface_review(path)
    source, offsets, report = example
    assert archive.source.text == source.text and archive.source.parse_settings == source.parse_settings
    assert dict(archive.work_offsets) == offsets
    assert encoded(surface_report_record(archive.report)) == encoded(surface_report_record(report))
    assert archive.report.body_review.scene_digests == report.body_review.scene_digests
    assert archive.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert report.gaps and archive.report.gaps == report.gaps
    assert archive.report.body_review.tool_change_lines == report.body_review.tool_change_lines
    for name, mesh in archive.report.meshes[1].items():
        assert mesh.triangles == report.meshes[1][name].triangles
        assert (mesh is archive.report.meshes[2][name]) == (not name.startswith("spindle "))
    with pytest.raises(TypeError):
        archive.report.meshes[1]["extra"] = next(iter(archive.report.meshes[1].values()))
    again = tmp_path / "again.cvsurfacereview"
    save_surface_review(again, archive.source, archive.work_offsets, archive.report)
    assert again.read_bytes() == path.read_bytes()


@pytest.mark.parametrize(
    "field",
    [
        "geometry",
        "faces",
        "binding",
        "unknown",
        "unused",
        "contact",
        "occupancy",
        "gap",
        "count",
        "rational",
        "body",
        "source",
        "method",
        "schema",
    ],
)
def test_rehashed_edits_cannot_reuse_retained_evidence(tmp_path, example, field):
    path = saved(tmp_path, example)
    data = json.loads(path.read_bytes())
    geo = data["geometry"]
    if field == "geometry":
        geo["pool"][0][0][0][0] += 0.01
    elif field == "faces":
        geo["pool"][0].pop()
    elif field == "binding":
        tool = geo["tools"]["1"]
        tool[next(iter(tool))] = True
    elif field == "unknown":
        geo["tools"]["1"]["unknown"] = 0
    elif field == "unused":
        geo["pool"].append(geo["pool"][0])
    elif field == "contact":
        data["report"]["contacts"].append({"forged": True})
    elif field == "occupancy":
        data["report"]["occupancy"].append({"forged": True})
    elif field == "gap":
        data["report"]["gaps"] = []
    elif field == "count":
        data["report"]["solid_counts"][0] += 1
    elif field == "rational":
        data["report"]["contacts"].append({"numerator": "1", "denominator": "0"})
    elif field == "body":
        data["body"]["report"]["status"] = "clear"
    elif field == "source":
        data["body"]["source"]["text"] += "\nG1 X12"
        data["body"]["source"]["sha256"] = hashlib.sha256(data["body"]["source"]["text"].encode()).hexdigest()
    elif field == "method":
        data["method"] = "unknown"
    else:
        data["schema"] = True
    path.write_bytes(resign(data, geometry=True))
    with pytest.raises(ValueError):
        load_surface_review(path)


def occupancy_example(*, hollow=False, open_shell=False):
    source = ProgramClearanceSource.capture(program("G1 X0"))
    offsets = {"G54": (-180, -120, -110)}
    record = deepcopy(review(program("G1 X0")).records[1])
    moving = next(b for b in record["collision_bodies"] if b["name"].startswith("carriage"))
    fixed = next(b for b in record["collision_bodies"] if b["name"].startswith("fixed"))
    from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
    from carveracontroller.machine.kinematic_review import machine_from_record

    machine = machine_from_record(record)
    bodies, _ = bodies_from_record(record, machine)
    zero_shift = body_transform(
        machine, next(b for b in bodies if b.name == moving["name"]), {"X": 0, "Y": 0, "Z": 0}
    ).translation
    moving.update(
        minimum_mm=(179 - zero_shift.x, -1 - zero_shift.y, -1 - zero_shift.z),
        maximum_mm=(181 - zero_shift.x, 1 - zero_shift.y, 1 - zero_shift.z),
    )
    fixed.update(minimum_mm=(-2, -2, -2), maximum_mm=(2, 2, 2))
    body = review_program_body_records(source, {1: record}, offsets)
    outer = box((-2, -2, -2), (2, 2, 2))
    if hollow:
        outer += reverse(box((-1.5, -1.5, -1.5), (1.5, 1.5, 1.5)))
    if open_shell:
        outer = outer[:-1]
    meshes = {
        1: {
            moving["name"]: SurfaceMesh.create(box((179, -1, -1), (181, 1, 1))),
            fixed["name"]: SurfaceMesh.create(outer),
        }
    }
    return source, offsets, refine_program_surfaces(body, meshes)


@pytest.mark.parametrize("state", ["contained", "cavity", "open shell"])
def test_exact_solid_intervals_witnesses_and_open_shell_gaps_roundtrip(tmp_path, state):
    example = occupancy_example(hollow=state == "cavity", open_shell=state == "open shell")
    archive = load_surface_review(saved(tmp_path, example))
    assert archive.report.occupancy == example[2].occupancy
    assert archive.report.gaps == example[2].gaps
    if state == "open shell":
        assert any("solid_unavailable" in g.reason for g in archive.report.gaps)
    else:
        interval = next(c.interval for c in archive.report.occupancy)
        assert interval.state == ("contained" if state == "contained" else "separated")
        assert isinstance(interval.lower.numerator, int)
        if state == "contained":
            assert interval.witness_point and interval.witness_triangle is not None
            raw = json.loads((tmp_path / "review.cvsurfacereview").read_bytes())
            assert "numerator" in raw["report"]["occupancy"][0]["interval"]["lower"]


def test_failure_cancel_and_budget_refusal_preserve_existing_bytes(tmp_path, example, monkeypatch):
    import carveracontroller.machine.program_surface_archive as module

    path = tmp_path / "kept.cvsurfacereview"
    path.write_bytes(b"prior review")
    for kwargs in ({"cancelled": lambda: True}, {}):
        bad = replace(example[2], gaps=())
        with pytest.raises((InterruptedError, ValueError)):
            save_surface_review(path, example[0], example[1], bad, **kwargs)
        assert path.read_bytes() == b"prior review" and len(list(tmp_path.iterdir())) == 1
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 12

    with pytest.raises(InterruptedError):
        save_surface_review(path, *example, cancelled=cancelled)
    assert path.read_bytes() == b"prior review"
    monkeypatch.setattr(module, "MAX_TRIANGLES", 1)
    with pytest.raises(ValueError, match="budget"):
        save_surface_review(path, *example)
    assert path.read_bytes() == b"prior review"


def test_bounded_json_duplicate_nonfinite_schema_and_size_refuse(tmp_path, example, monkeypatch):
    import carveracontroller.machine.program_surface_archive as module

    path = saved(tmp_path, example)
    raw = path.read_bytes()
    for blob in (
        raw.replace(b'"schema":1', b'"schema":1,"schema":1', 1),
        b'{"schema":NaN}',
        b'{"schema":123456789012345678901}',
        b'{"schema":true}',
    ):
        path.write_bytes(blob)
        with pytest.raises(ValueError):
            load_surface_review(path)
    path.write_bytes(raw)
    with pytest.raises(InterruptedError):
        load_surface_review(path, cancelled=lambda: True)
    monkeypatch.setattr(module, "MAX_REVIEW_BYTES", 100)
    with pytest.raises(ValueError, match="64 MiB"):
        load_surface_review(path)
    with pytest.raises(ValueError, match="64 MiB"):
        save_surface_review(path, *example)
    assert path.read_bytes() == raw


@pytest.mark.parametrize("kind", ["arc", "multiple WCS", "NURBS"])
def test_portable_surface_replay_retains_bounded_curves_and_named_tool_datum_transitions(tmp_path, kind):
    from carveracontroller.machine.program_operations import ProgramOperations

    offsets = {"G54": (-180, -120, -110), "G55": (-200, -100, -100)}
    if kind == "arc":
        parsed = program(arc=True)
    elif kind == "multiple WCS":
        parsed = ProgramOperations.from_text(
            "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X1 F100\nG55\nT2 M6\nG1 X2", work_offsets=offsets
        )
    else:
        from tests.unit.test_linuxcnc_nurbs_program import BLOCK, HEADER

        parsed = ProgramOperations.from_text(
            HEADER.replace("G0", "T1 M6\nG0", 1) + BLOCK, dialect="linuxcnc", spline_tolerance_mm=0.025
        )
    source = ProgramClearanceSource.capture(parsed)
    report = review_program_surfaces(source, captures(1, 2), offsets)
    archive = load_surface_review(saved(tmp_path, (source, offsets, report)))
    assert archive.report.contacts == report.contacts and archive.report.occupancy == report.occupancy
    assert archive.source.text == parsed.source_text
    assert archive.report.body_review.curve_enclosures == report.body_review.curve_enclosures
    assert encoded(surface_report_record(archive.report)) == encoded(surface_report_record(report))
    if kind == "multiple WCS":
        assert set(archive.report.body_review.records) == {1, 2}
    else:
        assert archive.report.body_review.curve_enclosures and not archive.report.body_review.curved_lines
