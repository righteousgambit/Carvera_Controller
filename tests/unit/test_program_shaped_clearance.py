"""Loaded profile binding, shaped primitive exchange and historical cylinders."""

import hashlib
import json
from pathlib import Path

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolType
from carveracontroller.machine.program_clearance_archive import encoded
from carveracontroller.machine.program_surface_archive import (
    ROTATING_METHOD,
    SHAPED_GROUP_METHOD,
    SHAPED_METHOD,
    load_surface_review,
    save_surface_review,
    surface_report_record,
)
from carveracontroller.machine.rotating_shape import RotatingShape
from tests.unit.test_program_rotating_clearance import rotating_example


@pytest.mark.parametrize("tool_type", [ToolType.BALL_END_MILL, ToolType.DRILL, ToolType.CHAMFER_MILL])
@pytest.mark.parametrize("grouped", [False, True])
def test_loaded_shaped_profiles_recompute_and_resave_all_sections(tmp_path, tool_type, grouped):
    source, offsets, report = rotating_example(grouped=grouped, tool_type=tool_type)
    sections = report.rotating_envelopes[1]["T1 cutter"]
    assert any(isinstance(s, RotatingShape) for s in sections)
    assert sections[0].low_mm == 0 and sections[-1].high_mm == 10
    assert "quadratic minima" in report.qualification
    path = tmp_path / "shaped.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    raw = path.read_bytes()
    assert json.loads(raw)["method"] == (SHAPED_GROUP_METHOD if grouped else SHAPED_METHOD)
    loaded = load_surface_review(path)
    assert encoded(surface_report_record(loaded.report)) == encoded(surface_report_record(report))
    assert loaded.report.rotating_envelopes == report.rotating_envelopes
    save_surface_review(path, loaded.source, loaded.work_offsets, loaded.report)
    assert raw == path.read_bytes()


@pytest.mark.parametrize("change", ["primitive", "center", "bool", "fields", "method", "radius"])
def test_rehashed_shaped_declarations_cannot_reuse_cylinder_or_old_witnesses(tmp_path, change):
    source, offsets, report = rotating_example(tool_type=ToolType.BALL_END_MILL)
    path = tmp_path / "shaped.cvsurfacereview"
    save_surface_review(path, source, offsets, report)
    payload = json.loads(path.read_bytes())
    row = payload["geometry"]["rotating"]["1"]["T1 cutter"][0]
    if change == "primitive":
        row["primitive"] = "cone"
    elif change == "center":
        row["center_mm"] = 1
    elif change == "bool":
        row["low_radius_mm"] = False
    elif change == "fields":
        row.pop("low_radius_mm")
    elif change == "method":
        payload["method"] = ROTATING_METHOD
    else:
        row["radius_mm"] = 2
    geometry = payload["geometry"]
    geometry["sha256"] = hashlib.sha256(encoded({k: v for k, v in geometry.items() if k != "sha256"})).hexdigest()
    payload.pop("sha256")
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    path.write_bytes(encoded(payload))
    with pytest.raises(ValueError):
        load_surface_review(path)


@pytest.mark.parametrize(
    "version,digest",
    [
        ("v6", "4489d494cd6ad0c6c354db682be76228ac84c7176c452377ceabbd6624c01fd5"),
        ("v7", "1a62b8985e6abc4749af2252879c5cb0913a9e9e7afc67bff867add74c289849"),
    ],
)
def test_unmodified_published_rotating_writer_retains_cylinder_semantics(tmp_path, version, digest):
    path = Path(__file__).parents[1] / "fixtures" / f"program-surface-ffcb2c5-{version}.cvsurfacereview"
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == digest
    loaded = load_surface_review(path)
    assert loaded.report.nodes == 4 and loaded.report.triangle_pairs == 2
    assert len(loaded.report.rotating) == 2
    assert not any(
        isinstance(s, RotatingShape)
        for rows in loaded.report.rotating_envelopes.values()
        for ss in rows.values()
        for s in ss
    )
    out = tmp_path / "retained.cvsurfacereview"
    save_surface_review(out, loaded.source, loaded.work_offsets, loaded.report)
    assert out.read_bytes() == raw
