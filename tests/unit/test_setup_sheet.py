"""Setup-sheet identity, custody and inert printable output."""

import hashlib

import pytest

from carveracontroller.machine.job_packages import JobPackage
from carveracontroller.machine.setup_sheet import render_setup_sheet, save_setup_sheet, setup_sheet


def job():
    return JobPackage(
        name="sample",
        program=b"G21\nG0 X1\n",
        program_name='<script>alert("x")</script>.nc',
        machine={"id": "machine-a", "name": "Workshop Carvera"},
        stock={"size_mm": [127, 69, 51], "origin_mm": [0, 0, -51], "alignment_confirmed": False},
        vise={"offset_mm": [5, 10, 0], "rotation_deg": 90, "jaw_offset_mm": 12},
        tools=[{"id": "cutter-a", "diameter": 6.35}],
        toolsets=[{"slots": {"1": "cutter-a"}}],
        inspection_plan={"assembly_binding": {"revision_id": "revision-a"}},
    )


def test_sheet_binds_exact_program_and_deep_copies_setup_checks():
    source = job()
    checks = [{"key": "stock", "state": "stale", "receipt": {"source": "caliper receipt"}}]
    sheet = setup_sheet(source, checks, "2026-10-06T15:00:00+00:00")
    assert sheet["program"]["sha256"] == hashlib.sha256(source.program).hexdigest()
    source.stock["size_mm"][0] = 999
    checks[0]["state"] = "measured"
    assert sheet["declarations"]["stock"]["size_mm"][0] == 127
    assert sheet["reported_checks"][0]["state"] == "stale"
    changed = setup_sheet(source, checks, sheet["captured_at_utc"])
    assert sheet["snapshot_sha256"] != changed["snapshot_sha256"]
    assert sheet["declarations"]["assembly_binding"]["revision_id"] == "revision-a"


def test_printable_html_is_inert_escaped_complete_and_readback_verified(tmp_path):
    sheet = setup_sheet(job(), [], "2026-10-06T15:00:00+00:00")
    rendered = render_setup_sheet(sheet)
    assert "<script>" not in rendered and "&lt;script&gt;" in rendered
    assert "@media print" in rendered and "@media(max-width:600px)" in rendered
    assert "Mounting holes" in rendered and "No reported checks retained" in rendered
    for group in ("machine", "stock", "vise", "fixtures", "tools", "toolsets", "assembly binding"):
        assert f"<h2>{group}</h2>" in rendered
    path = tmp_path / "sheet.html"
    digest = save_setup_sheet(sheet, path)
    assert path.read_text() == rendered
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert not list(tmp_path.glob(".setup-sheet-*"))


def test_invalid_or_oversized_metadata_does_not_write(tmp_path):
    source = job()
    source.stock["size_mm"] = [float("nan"), 1, 1]
    with pytest.raises(ValueError):
        setup_sheet(source, [], "time")
    source = job()
    source.machine["notes"] = "a" * (4 * 1024 * 1024)
    with pytest.raises(ValueError, match="metadata"):
        setup_sheet(source, [], "time")
    source.program = b""
    with pytest.raises(ValueError, match="nonempty"):
        setup_sheet(source, [], "time")


def test_sheet_rejects_changed_loaded_preview_and_accepts_newline_normalization():
    source = job()
    source.program = b"G21\r\nG0 X1\r\n"
    source.inspection_plan["loaded_preview_sha256"] = hashlib.sha256(b"G21\nG0 X1\n").hexdigest()
    sheet = setup_sheet(source, [], "time")
    assert sheet["program"]["loaded_preview"] == "Matched normalized source text"
    assert sheet["program"]["sha256"] == hashlib.sha256(source.program).hexdigest()
    source.program = b"G21\nG0 X2\n"
    with pytest.raises(ValueError, match="loaded preview"):
        setup_sheet(source, [], "time")
