"""Content-bound declared joint studies, isolated from machine transport."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from pathlib import Path
from typing import Callable, cast

from carveracontroller.machine.inverse_time import (
    JointSample,
    JointVelocityLimit,
    MappedJointMotion,
    analyze_mapped_joint_motion,
)
from carveracontroller.machine.joint_feedback import review_joint_feedback
from carveracontroller.machine.kinematic_review import machine_from_record, number, profile_digest

MAX_STUDY_BYTES = 256 * 1024


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate joint-study JSON field: " + key)
        result[key] = value
    return result


def _finite(value: object) -> float:
    if type(value) not in (int, float):
        raise ValueError("Joint-study values require finite numbers, not strings or booleans")
    try:
        result = float(cast(float, value))
    except (ValueError, OverflowError):
        raise ValueError("Joint-study number is outside the finite range") from None
    if not math.isfinite(result):
        raise ValueError("Joint-study numbers must be finite")
    return result


def read_joint_study(
    path: Path,
    *,
    program_sha256: str,
    line: int,
    seconds: float,
    cancelled: Callable[[], bool] = lambda: False,
) -> MappedJointMotion:
    """Require the file's exact program/block identity before any pose review.

    Imported sources remain declarations. Fractions explicitly describe timing;
    coordinates are unwrapped joints, not inferred from program XYZ/ABC words.
    """
    if cancelled():
        raise InterruptedError("Joint study cancelled")
    with path.open("rb") as stream:
        raw = stream.read(MAX_STUDY_BYTES + 1)
    if len(raw) > MAX_STUDY_BYTES:
        raise ValueError("Joint-study file exceeds 256 KiB")
    try:
        record = json.loads(raw.decode("utf-8"), object_pairs_hook=_object)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Joint study requires bounded UTF-8 JSON") from exc
    required = {
        "schema",
        "program_sha256",
        "line",
        "seconds",
        "machine",
        "model_source",
        "trajectory_source",
        "tool_length_mm",
        "samples",
        "velocity_limits",
    }
    if not isinstance(record, dict) or not required <= set(record) <= required | {
        "linear_step_mm",
        "rotary_step_degrees",
        "observed_feedback",
    }:
        raise ValueError("Joint study has missing or unknown fields")
    if type(record["schema"]) is not int or record["schema"] != 1:
        raise ValueError("Expected joint-study schema 1")
    if (
        not isinstance(program_sha256, str)
        or len(program_sha256) != 64
        or any(c not in "0123456789abcdef" for c in program_sha256)
        or type(line) is not int
        or line < 1
        or record["program_sha256"] != program_sha256
        or type(record["line"]) is not int
        or record["line"] != line
    ):
        raise ValueError("Joint study belongs to a different program revision or source line")
    duration, expected = _finite(record["seconds"]), _finite(seconds)
    if min(duration, expected) <= 0 or not math.isclose(duration, expected, rel_tol=1e-9, abs_tol=1e-12):
        raise ValueError("Joint study duration does not match the selected inverse-time block")
    sources = []
    for key in ("model_source", "trajectory_source"):
        value = record[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 240:
            raise ValueError("Declare model and trajectory sources in 1–240 characters")
        sources.append(value.strip())
    machine = machine_from_record(record["machine"])
    rows = record["velocity_limits"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 9:
        raise ValueError("Declare velocity limits for one to nine joints")
    limits = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "kind", "per_second", "source"}:
            raise ValueError("Each velocity limit needs name, kind, per_second and source")
        if not isinstance(row["name"], str) or len(row["name"]) > 32:
            raise ValueError("Velocity-limit name must be at most 32 characters")
        if not isinstance(row["source"], str) or not row["source"].strip() or len(row["source"]) > 240:
            raise ValueError("Each velocity limit requires a source of 1–240 characters")
        limits.append(JointVelocityLimit(row["name"], row["kind"], _finite(row["per_second"]), row["source"]))
    rows = record["samples"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= 2001:
        raise ValueError("Declare two to 2001 timed joint samples")
    samples = []
    for row in rows:
        if cancelled():
            raise InterruptedError("Joint study cancelled")
        if not isinstance(row, dict) or set(row) != {"fraction", "positions"} or not isinstance(row["positions"], dict):
            raise ValueError("Each sample needs a fraction and named joint positions")
        samples.append(
            JointSample(
                _finite(row["fraction"]), tuple((key, number(value)) for key, value in row["positions"].items())
            )
        )
    length = number(record["tool_length_mm"])
    if length < 0:
        raise ValueError("Declared tool length must be nonnegative")
    report = analyze_mapped_joint_motion(
        duration,
        tuple(samples),
        tuple(limits),
        machine,
        length,
        model_source=f"{sources[0]} · model SHA256 {profile_digest(record['machine'])}",
        trajectory_source=f"{sources[1]} · study SHA256 {hashlib.sha256(raw).hexdigest()}",
        linear_step_mm=number(record.get("linear_step_mm", 1)),
        rotary_step_degrees=number(record.get("rotary_step_degrees", 1)),
        cancelled=cancelled,
    )
    if "observed_feedback" in record:
        feedback = review_joint_feedback(
            record["observed_feedback"],
            duration,
            tuple((limit.name, limit.kind) for limit in limits),
            cancelled=cancelled,
        )
        report = replace(report, feedback=feedback)
    return report
