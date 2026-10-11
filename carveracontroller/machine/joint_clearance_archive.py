"""Content-bound articulated-clearance exchange; reload recomputes the geometry."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from carveracontroller.machine.joint_clearance import JointClearance, bodies_from_record, review_joint_clearance
from carveracontroller.machine.kinematic_profile_io import retain_geometry_bytes
from carveracontroller.machine.kinematic_review import machine_from_record

MAX_REVIEW_BYTES = 2 * 1024 * 1024
METHOD = "joint-chain-displacement-enclosure-v1"


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True)
class JointClearanceArchive:
    record: dict[str, Any]
    waypoints: list[dict[str, float]]
    report: JointClearance
    sha256: str


def save_joint_review(
    path: str | Path,
    record: dict[str, Any],
    waypoints: list[dict[str, float]],
    report: JointClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> str:
    machine_from_record(record)
    payload = {
        "schema": 1,
        "kind": "joint_clearance",
        "method": METHOD,
        "machine": record,
        "waypoints": waypoints,
        "tolerance_mm": report.tolerance_mm,
        "report": asdict(report),
    }
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    data = encoded(payload) + b"\n"
    if len(data) > MAX_REVIEW_BYTES:
        raise ValueError("Joint-clearance review exceeds 2 MiB")
    return retain_geometry_bytes(path, data, cancelled=cancelled)


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for key, value in pairs:
        if key in record:
            raise ValueError("Duplicate joint-clearance JSON field")
        record[key] = value
    return record


def load_joint_review(path: str | Path, *, cancelled: Callable[[], bool] = lambda: False) -> JointClearanceArchive:
    if cancelled():
        raise InterruptedError("Joint-clearance loading cancelled")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_REVIEW_BYTES + 1)
    if len(raw) > MAX_REVIEW_BYTES:
        raise ValueError("Joint-clearance review exceeds 2 MiB")
    try:
        payload = json.loads(raw, object_pairs_hook=_unique)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Expected bounded UTF-8 joint-clearance review") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "kind", "method", "machine", "waypoints", "tolerance_mm", "report", "sha256"}
        or type(payload["schema"]) is not int
        or payload["schema"] != 1
        or payload["kind"] != "joint_clearance"
        or payload["method"] != METHOD
    ):
        raise ValueError("Unsupported joint-clearance review schema or method")
    digest = payload.pop("sha256")
    if digest != hashlib.sha256(encoded(payload)).hexdigest():
        raise ValueError("Joint-clearance review integrity mismatch")
    record = payload["machine"]
    machine = machine_from_record(record)
    bodies, excluded = bodies_from_record(record, machine)
    waypoints = payload["waypoints"]
    report = review_joint_clearance(
        machine, waypoints, bodies, excluded, tolerance_mm=payload["tolerance_mm"], cancelled=cancelled
    )
    if encoded(asdict(report)) != encoded(payload["report"]):
        raise ValueError("Saved clearance report differs from recomputed declared geometry")
    if cancelled():
        raise InterruptedError("Joint-clearance loading cancelled")
    return JointClearanceArchive(record, waypoints, report, hashlib.sha256(raw).hexdigest())
