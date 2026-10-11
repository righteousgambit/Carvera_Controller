"""Provenance-bound nominal-normal least-squares plane review, without transport."""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any

from carveracontroller.machine.scene_interaction import cross, dot, subtract
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore, digest, restore_plan


def plane_review(features: Sequence[dict[str, Any]], anchor_id: str, policy: str = "latest") -> dict[str, Any]:
    """Fit one chosen receipt per compatible feature; never fall back past raw data.

    This is a least-squares height plane, not a minimum-zone flatness evaluation.
    Ball centers project by each retained nominal normal/radius. References are
    operator assertions; no contact direction, uncertainty or registration is inferred.
    """
    if policy not in ("latest", "earliest"):
        raise ValueError("Choose latest or earliest retained receipt")
    validated = SurfaceInspectionStore.validate({"schema": 1, "features": list(features)})
    anchor = next((f for f in validated if f["id"] == anchor_id), None)
    if anchor is None:
        raise ValueError("Select a retained nominal feature")
    anchor_plan = restore_plan(anchor["plan"])
    normal = anchor_plan.outward_normal
    origin = anchor_plan.reference.component_point_mm
    context_hash = digest(anchor["context"])
    rows: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    references: set[tuple[str, str, str]] = set()
    other_groups = 0
    for feature in validated:
        plan = restore_plan(feature["plan"])
        if (
            feature["part"] != anchor["part"]
            or digest(feature["context"]) != context_hash
            or plan.reference.component != anchor_plan.reference.component
            or dot(plan.outward_normal, normal) < 1 - 1e-10
            or abs(dot(subtract(plan.reference.component_point_mm, origin), normal)) > 1e-6
        ):
            other_groups += 1
            continue
        sample = feature["samples"][-1 if policy == "latest" else 0] if feature["samples"] else None
        base = {
            "feature_id": feature["id"],
            "feature_name": feature["name"],
            "nominal_sha256": feature["nominal_sha256"],
        }
        reason = (
            "No retained receipt"
            if sample is None
            else "Raw trigger is not a compensated ball center"
            if sample["kind"] != "compensated_ball_center"
            else "Registration and compensation references are required"
            if not sample["registration_ref"] or not sample["calibration_ref"]
            else None
        )
        if reason:
            excluded.append({**base, "receipt_id": sample["id"] if sample else None, "reason": reason})
            continue
        assert sample is not None
        contact = [sample["position_mm"][i] - plan.tip_radius_mm * plan.outward_normal[i] for i in range(3)]
        if any(not math.isfinite(v) or abs(v) > 1e6 for v in contact):
            raise ValueError("Plane contact coordinates must be finite and within ±1,000,000 mm")
        references.add((sample["registration_ref"], sample["calibration_ref"], sample["frame"]))
        rows.append({**base, "receipt": sample, "contact_mm": contact})
    if len(references) > 1:
        raise ValueError(
            "Selected receipts have different registration or compensation references; review them separately"
        )
    report: dict[str, Any] = {
        "schema": 1,
        "method": "least_squares_nominal_normal_height_plane",
        "evidence_note": "Operator-entered references and nominal-normal radius projection; least-squares sample residual range is not minimum-zone flatness, uncertainty or physical conformance.",
        "policy": policy,
        "anchor_id": anchor_id,
        "part": anchor["part"],
        "component": anchor_plan.reference.component,
        "context_sha256": context_hash,
        "input_sha256": digest(validated),
        "input_features": validated,
        "normal": list(normal),
        "nominal_origin_mm": list(origin),
        "samples": rows,
        "excluded": excluded,
        "other_group_features": other_groups,
        "fit": None,
        "reason": "At least three non-collinear selected receipts are required",
    }
    if len(rows) < 3:
        return report
    # A deterministic orthonormal basis avoids favoring the machine XY plane.
    axis = tuple(1.0 if i == min(range(3), key=lambda j: abs(normal[j])) else 0.0 for i in range(3))
    u0 = cross(axis, normal)
    u = tuple(v / math.sqrt(dot(u0, u0)) for v in u0)
    v = cross(normal, u)
    centroid = tuple(statistics.fmean(row["contact_mm"][i] for row in rows) for i in range(3))
    coords = [tuple(dot(subtract(row["contact_mm"], centroid), basis) for basis in (u, v, normal)) for row in rows]
    scale = max(abs(c) for xyz in coords for c in xyz[:2])
    if scale < 1e-9:
        return report
    normalized = [(x / scale, y / scale, z / scale) for x, y, z in coords]
    xx, yy, xy, xz, yz = (
        math.fsum(pair[i] * pair[j] for pair in normalized) for i, j in ((0, 0), (1, 1), (0, 1), (0, 2), (1, 2))
    )
    determinant = xx * yy - xy * xy
    if determinant <= 1e-10 * (xx + yy) ** 2:
        report["reason"] = "Selected contact points are collinear or too poorly spread for a stable plane"
        return report
    a, b = (xz * yy - yz * xy) / determinant, (yz * xx - xz * xy) / determinant
    length = math.sqrt(1 + a * a + b * b)
    fitted_normal = tuple((normal[i] - a * u[i] - b * v[i]) / length for i in range(3))
    residuals = [dot(subtract(row["contact_mm"], centroid), fitted_normal) for row in rows]
    for row, residual in zip(rows, residuals):
        row["residual_mm"] = residual
    report["fit"] = {
        "centroid_mm": list(centroid),
        "normal": list(fitted_normal),
        "centroid_normal_offset_mm": dot(subtract(centroid, origin), normal),
        "nominal_normal_offset_mm": dot(subtract(centroid, origin), fitted_normal) / dot(normal, fitted_normal),
        "tilt_deg": math.degrees(math.atan(math.hypot(a, b))),
        "residual_range_mm": max(residuals) - min(residuals),
        "residual_rms_mm": math.sqrt(statistics.fmean(r * r for r in residuals)),
        "residual_min_mm": min(residuals),
        "residual_max_mm": max(residuals),
        "spread_condition_ratio": determinant / (xx + yy) ** 2,
        "degrees_of_freedom": len(rows) - 3,
    }
    report["reason"] = None
    return report


def export_plane_report(
    report: dict[str, Any], destination: str, residual_limit_mm: float | None = None
) -> dict[str, Any]:
    """Write and independently read back the exact reproducible review snapshot."""
    import hashlib
    import json
    import os
    import tempfile
    from pathlib import Path

    from carveracontroller.machine.surface_inspection import canonical, read_bounded

    if plane_review(report["input_features"], report["anchor_id"], report["policy"]) != report:
        raise ValueError("Plane review no longer matches its retained input snapshot")
    from carveracontroller.machine.surface_inspection import number

    if residual_limit_mm is not None and number(residual_limit_mm, "Residual range limit") < 0:
        raise ValueError("Residual range limit cannot be negative")
    fit = report["fit"]
    comparison = {
        "maximum_residual_range_mm": residual_limit_mm,
        "state": "unevaluated"
        if fit is None
        else "untoleranced"
        if residual_limit_mm is None
        else "within_entered_limit"
        if fit["residual_range_mm"] <= residual_limit_mm
        else "outside_entered_limit",
        "basis": "numerical sample residual range only",
    }
    body = {"report": report, "comparison": comparison}
    payload = canonical({"format": "carvera.inspection-plane", "version": 1, **body, "sha256": digest(body)}).encode()
    maximum = 16 * 1024 * 1024
    if len(payload) > maximum:
        raise ValueError("Plane report exceeds 16 MiB bound")
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".inspection-plane-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    loaded = read_bounded(path, maximum)
    if loaded != payload or json.loads(loaded)["sha256"] != digest(body):
        raise ValueError("Plane report readback differs from reviewed snapshot")
    return {"path": str(path), "sha256": hashlib.sha256(loaded).hexdigest(), "bytes": len(loaded)}
