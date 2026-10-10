"""Declared cutter integration, original world-frame registration and portable replay."""

import hashlib
import json
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path

import pytest

from carveracontroller.addons.machine_simulation.model import Geometry
from carveracontroller.addons.machine_simulation.profile import CAD_HEAD, CAD_OFFSET, MachineProfile
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_surface_archive import (
    DIRECTION_METHOD,
    ROTATING_GROUP_METHOD,
    ROTATING_METHOD,
    load_surface_review,
    save_surface_review,
    surface_report_record,
)
from carveracontroller.machine.program_surface_clearance import (
    review_program_surfaces,
    rotating_witness,
    validate_rotating_envelopes,
)
from tests.unit.test_scene_joint_clearance import capture, scene_viewer


def rotating_example(*, grouped=False, tool_type=None):
    viewer = scene_viewer()
    if tool_type is not None:
        viewer.library_tool_table_mm[1].tool_type = tool_type
    original = viewer.machine_profile
    hy = CAD_HEAD[1] + CAD_OFFSET[1]
    shape = Geometry()
    shape.box(
        (-5.1 - CAD_OFFSET[0], hy - 0.1 - CAD_OFFSET[1], 0.5 - CAD_OFFSET[2]),
        (-4.9 - CAD_OFFSET[0], hy + 0.1 - CAD_OFFSET[1], 1.5 - CAD_OFFSET[2]),
        (1, 1, 1, 1),
    )
    components = [dict(c) for c in original.components]
    components[0]["vertices"] = shape.vertices
    viewer.machine_profile = MachineProfile(
        {
            "schema": 1,
            "units": "mm",
            "model": "Carvera C1 rotating analytic fixture",
            "source_url": "",
            "source_revision": "analytic",
            "source_sha256": "analytic",
            "components": components,
            "workholding": {"pivot_mm": [50, 20, 30]},
        }
    )
    source = ProgramClearanceSource.capture(
        ProgramOperations.from_text("G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X8 F100")
    )
    offsets = {"G54": (-9.0, 0.0, 0.0)}
    report = review_program_surfaces(source, {1: capture(viewer)}, offsets, grouped=grouped)
    return source, offsets, report


def test_loaded_tool_has_interior_contact_at_the_independent_carvera_tool_base():
    source, offsets, report = rotating_example()
    rows = [r for r in report.rotating if r.first == "T1 cutter" and r.second.startswith("fixed")]
    assert len(rows) == 1
    row = rows[0]
    assert row.result.state == "possible_contact" and 0 < row.result.sample < 1
    geometry, point = rotating_witness(report, row)
    assert geometry and point is not None
    assert -5.1 <= point[0] <= -4.9 and 0.5 <= point[2] <= 1.5
    assert point[1] == pytest.approx(CAD_HEAD[1] + CAD_OFFSET[1], abs=0.1)
    assert row.source_sample_ratio == row.result.sample and row.line == 4
    # Both endpoints are outside the declared cutter radius; the body interior
    # reaches a complete obstacle face between them. The witness is not entry.
    assert min(abs(x - point[0]) for x in (-9, -1)) > 3
    assert all("T1" not in g.first + g.second for g in report.gaps)
    assert report.rotating_envelopes[1]["T1 cutter"][0].radius_mm == 3
    assert "manufactured flutes" not in report.qualification or "unqualified" in report.qualification
    assert source.file_hash == report.body_review.program_hash and offsets["G54"] == (-9, 0, 0)


@pytest.mark.parametrize("grouped", [False, True])
def test_portable_declared_rotating_results_recompute_without_active_profiles(tmp_path, grouped):
    source, offsets, report = rotating_example(grouped=grouped)
    path = tmp_path / "rotating.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    raw = path.read_bytes()
    payload = json.loads(raw)
    assert payload["method"] == (ROTATING_GROUP_METHOD if grouped else ROTATING_METHOD)
    loaded = load_surface_review(path)
    assert encoded(surface_report_record(loaded.report)) == encoded(surface_report_record(report))
    assert loaded.report.rotating_envelopes == report.rotating_envelopes
    save_surface_review(path, loaded.source, loaded.work_offsets, loaded.report)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "change", ["drop_result", "witness", "radius", "body", "source", "method", "bool", "extra", "drop_tool"]
)
def test_rehashed_declarations_and_results_cannot_reuse_old_evidence(tmp_path, change):
    source, offsets, report = rotating_example()
    path = tmp_path / "review.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    payload = json.loads(path.read_bytes())
    if change == "drop_result":
        payload["report"]["rotating"] = []
    elif change == "witness":
        payload["report"]["rotating"][0]["source_sample_ratio"] = {"numerator": "1", "denominator": "17"}
    elif change == "radius":
        payload["geometry"]["rotating"]["1"]["T1 cutter"][0]["radius_mm"] = 4
    elif change == "body":
        payload["geometry"]["rotating"]["1"]["wrong"] = payload["geometry"]["rotating"]["1"].pop("T1 cutter")
    elif change == "source":
        payload["geometry"]["rotating"]["1"]["T1 cutter"][0]["source"] = "changed source declaration"
    elif change == "method":
        payload["method"] = DIRECTION_METHOD
    elif change == "bool":
        payload["geometry"]["rotating"]["1"]["T1 cutter"][0]["radius_mm"] = True
    elif change == "extra":
        payload["geometry"]["rotating"]["1"]["T1 cutter"][0]["extra"] = "not allowed"
    elif change == "drop_tool":
        payload["geometry"]["rotating"] = {}
    geometry = payload["geometry"]
    geometry["sha256"] = hashlib.sha256(encoded({k: v for k, v in geometry.items() if k != "sha256"})).hexdigest()
    payload.pop("sha256")
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    path.write_bytes(encoded(payload))
    with pytest.raises(ValueError):
        load_surface_review(path)


def test_rotating_declarations_cannot_be_shifted_or_tilted_outside_the_body():
    _, _, report = rotating_example()
    rows = {1: dict(report.rotating_envelopes[1])}
    rows[1]["T1 cutter"] = (replace(rows[1]["T1 cutter"][0], high_mm=20),)
    with pytest.raises(ValueError, match="outside"):
        validate_rotating_envelopes(report.body_review.records, rows)
    record = dict(report.body_review.records[1])
    record["tool_base"] = {"rotation": [0, 0, 1, 0, 1, 0, -1, 0, 0], "translation": [0, 0, 0]}
    with pytest.raises(ValueError, match="unrotated"):
        validate_rotating_envelopes({1: record}, report.rotating_envelopes)


@pytest.mark.parametrize(
    "version,digest,contacts,groups",
    [
        ("v4", "8e12423b58942f10d8a6e61a1f4ec1722e2598b77d92eb1c538df2d6ce453dc6", 144, (0, 0)),
        ("v5", "97c746c46d34cc624d4da49995ee6283a170fdcc8b2dc40558de0f17bd0e3a43", 0, (2, 144)),
    ],
)
def test_unmodified_published_directional_writers_resave_original_dense_evidence(
    tmp_path, version, digest, contacts, groups
):
    path = Path(__file__).parents[1] / "fixtures" / f"program-surface-69cdd2b-{version}.cvsurfacereview"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    loaded = load_surface_review(path)
    report = loaded.report
    assert not report.rotating and not report.rotating_envelopes
    assert report.nodes == 286 and report.triangle_pairs == 144 and len(report.gaps) == 6
    assert len(report.contacts) == contacts and report.group_counts == groups
    out = tmp_path / "retained.cvsurfacereview"
    save_surface_review(out, loaded.source, loaded.work_offsets, report)
    assert out.read_bytes() == raw
