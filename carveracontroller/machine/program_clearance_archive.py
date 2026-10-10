"""Bounded source/body exchange; loading reparses and recomputes every claim."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from carveracontroller.machine.kinematic_profile_io import retain_geometry_bytes
from carveracontroller.machine.program_joint_clearance import (
    ProgramBodyClearance,
    ProgramClearanceSource,
    review_program_body_records,
)
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import WCS_NAMES, vector

MAX_REVIEW_BYTES = 32 * 1024 * 1024
MAX_SOURCE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_LINES = 100_000
LEGACY_METHOD = "c1-program-polylines-common-link-enclosure-v1"
METHOD = "c1-program-curves-common-link-enclosure-v2"


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


def report_record(report: ProgramBodyClearance, *, cancelled: Callable[[], bool] = lambda: False) -> dict[str, object]:
    if len(report.segments) > 100000 or len(report.contacts) > 10000:
        raise ValueError("Retained review exceeds segment/contact budgets")
    motion = hashlib.sha256()
    for index, segment in enumerate(report.segments):
        if index % 64 == 0 and cancelled():
            raise InterruptedError("Program-clearance exchange cancelled")
        motion.update(encoded(asdict(segment)) + b"\n")
    result = {
        "program_hash": report.program_hash,
        "start_line": report.start_line,
        "end_line": report.end_line,
        "motion_sha256": motion.hexdigest(),
        "segments": len(report.segments),
        "scene_digests": report.scene_digests,
        "bodies_sha256": hashlib.sha256(encoded({str(t): r for t, r in report.records.items()})).hexdigest(),
        "contacts": [asdict(c) for c in report.contacts],
        "uncovered_lines": report.uncovered_lines,
        "curved_lines": report.curved_lines,
        "tool_change_lines": report.tool_change_lines,
        "tested_pairs": report.tested_pairs,
        "intervals": report.intervals,
        "tolerance_mm": report.tolerance_mm,
        "status": report.status,
        "qualification": report.qualification,
    }
    if report.curve_coverage:
        result["curve_enclosures"] = report.curve_enclosures
        result["curve_coverage"] = True
    return result


def parse_source(source: object, *, cancelled: Callable[[], bool] = lambda: False) -> ProgramClearanceSource:
    """Parser input is exact UTF-8 text, not an assertion about disk encoding."""
    if not isinstance(source, dict) or set(source) != {"text", "sha256", "settings"}:
        raise ValueError("Program review needs exact parser input text, SHA256 and settings")
    text, digest, settings = source["text"], source["sha256"], source["settings"]
    if not isinstance(text, str) or len(text) > MAX_SOURCE_BYTES or len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError("Retained parser input exceeds 16 MiB UTF-8")
    if text.count("\n") > MAX_SOURCE_LINES or len(text.splitlines()) > MAX_SOURCE_LINES:
        raise ValueError("Retained parser input exceeds 100000 source lines")
    if any(len(row) > 65536 for row in text.splitlines()):
        raise ValueError("Retained parser input line exceeds 65536 characters")
    if digest != hashlib.sha256(text.encode("utf-8")).hexdigest():
        raise ValueError("Retained parser input integrity mismatch")
    names = {
        "rapid_mm_min",
        "dwell_p_seconds",
        "arc_tolerance_mm",
        "max_arc_segments",
        "spline_tolerance_mm",
        "max_spline_segments",
        "work_offsets",
        "dialect",
    }
    if not isinstance(settings, dict) or set(settings) != names:
        raise ValueError("Unsupported retained parser settings")
    for key in ("max_arc_segments", "max_spline_segments"):
        if type(settings[key]) is not int or not 1 <= settings[key] <= 100000:
            raise ValueError("Retained parser segment budgets must be integers from one to100000")
    from math import isfinite

    for key in ("rapid_mm_min", "dwell_p_seconds", "arc_tolerance_mm", "spline_tolerance_mm"):
        value = settings[key]
        if value is None and key in ("rapid_mm_min", "dwell_p_seconds"):
            continue
        if type(value) not in (int, float) or not isfinite(value) or value <= 0:
            raise ValueError("Retained parser tolerances/rates must be finite and positive")
        if type(value) is int and len(str(value)) > 20:
            raise ValueError("Retained parser integer exceeds20 characters; use an explicit finite float")
    rows = settings["work_offsets"]
    if not isinstance(rows, (list, tuple)) or len(rows) > 6:
        raise ValueError("Retained parser offsets need at most six named datums")
    offsets = {}
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 2 or row[0] not in WCS_NAMES or row[0] in offsets:
            raise ValueError("Retained parser offsets need distinct G54–G59 datums")
        offsets[row[0]] = vector(row[1])
    if settings["dialect"] not in ("carvera", "linuxcnc"):
        raise ValueError("Unsupported retained parser dialect")
    if cancelled():
        raise InterruptedError("Program-clearance source loading cancelled")
    parsed = ProgramOperations.from_text(
        text,
        rapid_mm_min=settings["rapid_mm_min"],
        dwell_p_seconds=settings["dwell_p_seconds"],
        arc_tolerance_mm=settings["arc_tolerance_mm"],
        max_arc_segments=settings["max_arc_segments"],
        spline_tolerance_mm=settings["spline_tolerance_mm"],
        max_spline_segments=settings["max_spline_segments"],
        work_offsets=offsets or None,
        dialect=settings["dialect"],
        max_motion_segments=1_000_000,
        cancelled=cancelled,
    )
    return ProgramClearanceSource.capture(parsed)


@dataclass(frozen=True)
class ProgramClearanceArchive:
    source: ProgramClearanceSource
    work_offsets: Mapping[str, tuple[float, float, float]]
    report: ProgramBodyClearance
    sha256: str


def _review(payload: dict[str, Any], *, cancelled: Callable[[], bool]) -> ProgramClearanceArchive:
    if type(payload["start_line"]) is not int or type(payload["end_line"]) is not int:
        raise ValueError("Retained review source range needs explicit integer endpoints")
    source = parse_source(payload["source"], cancelled=cancelled)
    offsets = payload["work_offsets"]
    if not isinstance(offsets, dict) or not offsets or any(k not in WCS_NAMES for k in offsets):
        raise ValueError("Program review needs explicit G54–G59 work offsets")
    offsets = {key: vector(value) for key, value in offsets.items()}
    records = payload["machines"]
    if not isinstance(records, dict) or not 1 <= len(records) <= 32:
        raise ValueError("Program review needs at most32 explicit tool/body declarations")
    declarations = {}
    for name, record in records.items():
        if (
            not isinstance(name, str)
            or len(name) > 20
            or not name.isascii()
            or not name.isdigit()
            or str(int(name)) != name
        ):
            raise ValueError("Tool keys must be canonical nonnegative integers")
        declarations[int(name)] = record
    result = review_program_body_records(
        source,
        declarations,
        offsets,
        start_line=payload["start_line"],
        end_line=payload["end_line"],
        tolerance_mm=payload["tolerance_mm"],
        cover_curves=payload["method"] == METHOD,
        cancelled=cancelled,
    )
    if set(declarations) != set(result.records):
        raise ValueError("Retained review has unused tool/body declarations")
    if encoded(report_record(result, cancelled=cancelled)) != encoded(payload["report"]):
        raise ValueError("Saved program clearance differs from reparsed source and recomputed declared geometry")
    if cancelled():
        raise InterruptedError("Program-clearance loading cancelled; previous report retained")
    return ProgramClearanceArchive(source, MappingProxyType(offsets), result, "")


def save_program_review(
    path: str | Path,
    source: ProgramClearanceSource,
    work_offsets: Mapping[str, tuple[float, float, float]],
    report: ProgramBodyClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> str:
    if source.text is None or source.parse_settings is None:
        raise ValueError(
            "Exact parser input/settings unavailable; reload and review the original program before saving"
        )
    payload = {
        "schema": 1,
        "kind": "program_machine_clearance",
        "method": METHOD if report.curve_coverage else LEGACY_METHOD,
        "source": {"text": source.text, "sha256": source.file_hash, "settings": asdict(source.parse_settings)},
        "work_offsets": dict(work_offsets),
        "machines": {str(tool): record for tool, record in report.records.items()},
        "start_line": report.start_line,
        "end_line": report.end_line,
        "tolerance_mm": report.tolerance_mm,
        "report": report_record(report, cancelled=cancelled),
    }
    # Saving also verifies that the retained parser source really produces this
    # report; edited parser tuples cannot acquire an exact-source receipt.
    _review(payload, cancelled=cancelled)
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    data = encoded(payload) + b"\n"
    if len(data) > MAX_REVIEW_BYTES:
        raise ValueError("Program-clearance review exceeds32 MiB")
    return retain_geometry_bytes(path, data, cancelled=cancelled)


def load_program_review(path: str | Path, *, cancelled: Callable[[], bool] = lambda: False) -> ProgramClearanceArchive:
    if cancelled():
        raise InterruptedError("Program-clearance loading cancelled")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_REVIEW_BYTES + 1)
    if len(raw) > MAX_REVIEW_BYTES:
        raise ValueError("Program-clearance review exceeds32 MiB")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if cancelled():
            raise InterruptedError("Program-clearance loading cancelled")
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate program-clearance JSON field")
            result[key] = value
        return result

    try:

        def integer(text: str) -> int:
            if len(text) > 20:
                raise ValueError("Program-clearance JSON integer exceeds20 characters")
            return int(text)

        def constant(text: str) -> None:
            raise ValueError("Nonfinite program-clearance JSON number: " + text)

        payload = json.loads(raw, object_pairs_hook=unique, parse_int=integer, parse_constant=constant)
        if (
            not isinstance(payload, dict)
            or set(payload)
            != {
                "schema",
                "kind",
                "method",
                "source",
                "work_offsets",
                "machines",
                "start_line",
                "end_line",
                "tolerance_mm",
                "report",
                "sha256",
            }
            or type(payload["schema"]) is not int
            or payload["schema"] != 1
            or payload["kind"] != "program_machine_clearance"
            or payload["method"] not in (METHOD, LEGACY_METHOD)
        ):
            raise ValueError("Unsupported program-clearance review schema or method")
        digest = payload.pop("sha256")
        if digest != hashlib.sha256(encoded(payload)).hexdigest():
            raise ValueError("Program-clearance review integrity mismatch")
        result = _review(payload, cancelled=cancelled)
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise ValueError("Expected bounded UTF-8 program-clearance review") from exc
    return ProgramClearanceArchive(result.source, result.work_offsets, result.report, hashlib.sha256(raw).hexdigest())
