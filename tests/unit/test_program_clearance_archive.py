"""Exact-source replay, retained evidence integrity and bounded atomic exchange."""

import hashlib
import json
from dataclasses import replace

import pytest

from carveracontroller.machine.program_clearance_archive import (
    encoded,
    load_program_review,
    parse_source,
    report_record,
    save_program_review,
)
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource, review_program_clearance
from carveracontroller.machine.program_operations import ProgramOperations
from tests.unit.test_program_joint_clearance import captures, program


@pytest.fixture(scope="module")
def example():
    text = "G21 G90 G91.1 G17 G94 G54\r\n(Unicode μ comment)\r\nT1 M6\r\nG0 X0 Y0 Z0\r\nG2 X10 Y0 I5 J0 F100\r\n"
    p = ProgramOperations.from_text(
        text,
        arc_tolerance_mm=0.025,
        max_arc_segments=300,
        spline_tolerance_mm=0.003,
        max_spline_segments=250,
        rapid_mm_min=2000,
        dwell_p_seconds=1,
    )
    source = ProgramClearanceSource.capture(p)
    offsets = {"G54": (-180, -120, -110)}
    result = review_program_clearance(source, captures(), offsets)
    return source, offsets, result


def sample(tmp_path, example):
    path = tmp_path / "program.cvprogramclearance"
    save_program_review(path, *example)
    return path


def resign(payload):
    payload.pop("sha256", None)
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    return encoded(payload)


def test_roundtrip_reparses_exact_crlf_unicode_source_and_nondefault_tolerances(tmp_path, example):
    path = sample(tmp_path, example)
    loaded = load_program_review(path)
    source, offsets, result = example
    assert loaded.source.text == source.text and loaded.source.file_hash == source.file_hash
    assert loaded.source.parse_settings == source.parse_settings
    assert loaded.source.motion == source.motion
    assert dict(loaded.work_offsets) == offsets
    assert encoded(report_record(loaded.report)) == encoded(report_record(result))
    assert loaded.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert loaded.report.uncovered_lines == (4,) and loaded.report.tool_change_lines == (3,)
    assert loaded.report.curved_lines == (5,)
    with pytest.raises(TypeError):
        loaded.work_offsets["G54"] = (0, 0, 0)


@pytest.mark.parametrize(
    "field",
    [
        "contacts",
        "status",
        "intervals",
        "source_fraction",
        "gaps",
        "motion",
        "geometry",
        "range",
        "offset",
        "source",
        "tolerance",
        "parser",
    ],
)
def test_rehashed_changes_cannot_reuse_retained_calculation(tmp_path, example, field):
    path = sample(tmp_path, example)
    payload = json.loads(path.read_bytes())
    if field == "contacts":
        payload["report"]["contacts"] = []
    elif field == "status":
        payload["report"]["status"] = "clear_resolved_polylines"
    elif field == "intervals":
        payload["report"]["intervals"] += 1
    elif field == "source_fraction":
        payload["report"]["contacts"][0]["source_upper_ratio"] += 0.01
    elif field == "gaps":
        payload["report"]["uncovered_lines"] = []
    elif field == "motion":
        payload["report"]["motion_sha256"] = "0" * 64
    elif field == "geometry":
        payload["machines"]["1"]["collision_bodies"][-1]["maximum_mm"][2] += 2
    elif field == "range":
        payload["start_line"] = 5
    elif field == "offset":
        payload["work_offsets"]["G54"][0] -= 1
    elif field == "source":
        payload["source"]["text"] += "\nG1 X11\n"
        payload["source"]["sha256"] = hashlib.sha256(payload["source"]["text"].encode()).hexdigest()
    elif field == "tolerance":
        payload["tolerance_mm"] = 0.1
    else:
        payload["source"]["settings"]["arc_tolerance_mm"] = 0.3
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError, match="reparsed|recomputed"):
        load_program_review(path)


def test_forged_clear_result_is_rejected_before_overwriting_target(tmp_path, example):
    source, offsets, report = example
    path = tmp_path / "preserved.cvprogramclearance"
    path.write_bytes(b"previous review")
    with pytest.raises(ValueError, match="recomputed"):
        save_program_review(path, source, offsets, replace(report, contacts=(), status="clear_resolved_polylines"))
    assert path.read_bytes() == b"previous review"
    assert sorted(p.name for p in tmp_path.iterdir()) == [path.name]


def test_missing_exact_source_and_edited_parser_rows_cannot_be_saved(tmp_path, example):
    source, offsets, report = example
    path = tmp_path / "never-written"
    with pytest.raises(ValueError, match="Exact parser input"):
        save_program_review(path, replace(source, text=None), offsets, report)
    p = program()
    edited = ProgramClearanceSource.capture(p)
    edited = replace(edited, motion=(replace(edited.motion[0], end_mm=(20, 0, 0)),))
    edited_result = review_program_clearance(edited, captures(), offsets)
    with pytest.raises(ValueError, match="recomputed"):
        save_program_review(path, edited, offsets, edited_result)
    assert not path.exists()


def test_cancellation_size_duplicate_schema_integrity_and_unused_tools(tmp_path, example, monkeypatch):
    import carveracontroller.machine.program_clearance_archive as archive

    path = sample(tmp_path, example)
    raw = path.read_bytes()
    for action in (
        lambda: load_program_review(path, cancelled=lambda: True),
        lambda: save_program_review(path, *example, cancelled=lambda: True),
    ):
        with pytest.raises(InterruptedError):
            action()
        assert path.read_bytes() == raw
    payload = json.loads(raw)
    payload["report"]["contacts"] = []
    path.write_bytes(encoded(payload))
    with pytest.raises(ValueError, match="integrity"):
        load_program_review(path)
    path.write_bytes(raw.replace(b'"schema":1', b'"schema":1,"schema":1', 1))
    with pytest.raises(ValueError, match="Duplicate"):
        load_program_review(path)
    payload = json.loads(raw)
    payload["schema"] = True
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError, match="schema"):
        load_program_review(path)
    payload = json.loads(raw)
    payload["machines"]["2"] = payload["machines"]["1"]
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError, match="unused"):
        load_program_review(path)
    monkeypatch.setattr(archive, "MAX_REVIEW_BYTES", 100)
    path.write_bytes(raw)
    with pytest.raises(ValueError, match="32 MiB"):
        load_program_review(path)
    with pytest.raises(ValueError, match="32 MiB"):
        save_program_review(path, *example)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["settings"].update(max_arc_segments=True),
        lambda p: p["settings"].update(max_spline_segments=100001),
        lambda p: p["settings"].update(arc_tolerance_mm=float("nan")),
        lambda p: p["settings"].update(dialect="unknown"),
        lambda p: p["settings"].update(work_offsets=[["G54", [0, 0, 0]], ["G54", [0, 0, 0]]]),
        lambda p: p.update(sha256="0" * 64),
    ],
)
def test_retained_parser_input_contract_refuses_unbounded_or_ambiguous_settings(example, mutation):
    from dataclasses import asdict

    source = example[0]
    payload = {"text": source.text, "sha256": source.file_hash, "settings": asdict(source.parse_settings)}
    mutation(payload)
    with pytest.raises(ValueError):
        parse_source(payload)


def test_bounded_parser_refuses_complete_motion_overflow_and_cancels():
    text = "G21 G90 G91.1 G17 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X1\nG1 X2"
    with pytest.raises(ValueError, match="no partial parse"):
        ProgramOperations.from_text(text, max_motion_segments=1)
    with pytest.raises(ValueError, match="integer"):
        ProgramOperations.from_text(text, max_motion_segments=True)
    with pytest.raises(InterruptedError):
        ProgramOperations.from_text(text, max_motion_segments=100, cancelled=lambda: True)
    assert len(ProgramOperations.from_text(text, max_motion_segments=2).motion_segments) == 2


def test_source_range_integer_and_json_numeric_limits_are_strict(tmp_path, example):
    path = sample(tmp_path, example)
    payload = json.loads(path.read_bytes())
    payload["end_line"] = None
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError, match="integer endpoints"):
        load_program_review(path)
    path.write_bytes(b'{"schema":123456789012345678901}')
    with pytest.raises(ValueError, match="integer exceeds"):
        load_program_review(path)
    path.write_bytes(b'{"schema":NaN}')
    with pytest.raises(ValueError, match="Nonfinite"):
        load_program_review(path)


@pytest.mark.parametrize("kind", ["multiple tools and WCS", "cubic", "NURBS"])
def test_replay_named_transitions_tool_changes_and_native_curve_closures(tmp_path, kind):
    offsets = {"G54": (-180, -120, -110), "G55": (-200, -100, -100)}
    header = "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\n"
    if kind == "multiple tools and WCS":
        text = header + "G1 X1 F100\nG55\nT2 M6\nG1 X2"
        p = ProgramOperations.from_text(text, work_offsets=offsets)
    elif kind == "cubic":
        text = header + "G5 I0 J3 P0 Q-3 X1 Y1 F100"
        p = ProgramOperations.from_text(text, dialect="linuxcnc", spline_tolerance_mm=0.025)
    else:
        from tests.unit.test_linuxcnc_nurbs_program import BLOCK

        text = header + BLOCK
        p = ProgramOperations.from_text(text, dialect="linuxcnc", spline_tolerance_mm=0.025)
    source = ProgramClearanceSource.capture(p)
    report = review_program_clearance(source, captures(1, 2), offsets)
    path = tmp_path / "study.cvprogramclearance"
    save_program_review(path, source, offsets, report)
    loaded = load_program_review(path)
    assert encoded(report_record(loaded.report)) == encoded(report_record(report))
    if kind == "multiple tools and WCS":
        assert set(loaded.report.records) == {1, 2}
        assert loaded.report.segments[0].end == loaded.report.segments[1].start
    else:
        assert loaded.report.curved_lines == (len(p.lines),)
        assert loaded.source.parse_settings.dialect == "linuxcnc"


def test_cancellation_during_actual_recomputation_preserves_existing_file(tmp_path, example):
    path = tmp_path / "retained.cvprogramclearance"
    path.write_bytes(b"prior retained bytes")
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls >= 12

    with pytest.raises(InterruptedError):
        save_program_review(path, *example, cancelled=cancelled)
    assert calls >= 12 and path.read_bytes() == b"prior retained bytes"
    assert len(list(tmp_path.iterdir())) == 1


def test_motion_budget_also_applies_to_completed_nurbs_blocks():
    from tests.unit.test_linuxcnc_nurbs_program import BLOCK, HEADER

    with pytest.raises(ValueError, match="total motion segment budget"):
        ProgramOperations.from_text(HEADER + BLOCK, dialect="linuxcnc", max_motion_segments=1)


def test_selected_operation_retains_full_source_but_only_required_tool_geometry(tmp_path):
    offsets = {"G54": (-180, -120, -110), "G55": (-200, -100, -100)}
    text = "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\nG1 X1 F100\nG55\nT2 M6\nG1 X2"
    source = ProgramClearanceSource.capture(ProgramOperations.from_text(text, work_offsets=offsets))
    result = review_program_clearance(source, captures(1, 2), offsets, start_line=7, end_line=7)
    path = tmp_path / "operation.cvprogramclearance"
    save_program_review(path, source, offsets, result)
    loaded = load_program_review(path)
    assert loaded.source.text == text
    assert loaded.report.start_line == loaded.report.end_line == 7
    assert len(loaded.report.segments) == 1 and loaded.report.segments[0].tool_id == "2"
    assert set(loaded.report.records) == {2}
    assert loaded.report.uncovered_lines == loaded.report.tool_change_lines == ()


def test_save_cannot_publish_numbers_that_the_bounded_reader_would_refuse(tmp_path, example):
    source, offsets, report = example
    source = replace(source, parse_settings=replace(source.parse_settings, rapid_mm_min=10**25))
    path = tmp_path / "preserved.cvprogramclearance"
    path.write_bytes(b"previous bytes")
    with pytest.raises(ValueError, match="integer exceeds"):
        save_program_review(path, source, offsets, report)
    assert path.read_bytes() == b"previous bytes"
