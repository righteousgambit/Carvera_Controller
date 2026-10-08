"""Calibration evidence summaries, never physical identity or wear diagnoses."""

from __future__ import annotations

import math
import statistics
from collections.abc import Mapping, Sequence
from typing import Any


def finite(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def sample_statistics(report: Mapping[str, Any]) -> dict[str, Any]:
    samples = tuple(report.get("measurements", ()))
    result = {
        "count": len(samples),
        "mean_mm": None,
        "range_mm": None,
        "stdev_mm": None,
        "reported_spread_mm": report.get("max_delta") if finite(report.get("max_delta")) else None,
        "applied_mm": report.get("applied") if finite(report.get("applied")) else None,
        "spread_agrees": None,
    }
    if not samples or not all(finite(value) for value in samples):
        return result
    try:
        mean, spread = statistics.mean(samples), max(samples) - min(samples)
        stdev = statistics.stdev(samples) if len(samples) > 1 else None
    except (ArithmeticError, ValueError):
        return result
    if not finite(mean) or not finite(spread) or stdev is not None and not finite(stdev):
        return result
    result.update(mean_mm=mean, range_mm=spread, stdev_mm=stdev)
    if result["reported_spread_mm"] is not None:
        result["spread_agrees"] = math.isclose(spread, result["reported_spread_mm"], rel_tol=0, abs_tol=1e-6)
    return result


def assembly_calibrations(events: Sequence[dict[str, Any]], assembly_id: str) -> list[dict[str, Any]]:
    """Keep capture order and provenance; never merge groups or repair clocks.

    Numeric applied-offset differences are only computed within a versioned
    assembly/source/tool group with increasing measurement timestamps. Missing
    offsets or unknown timing break the previous baseline for that group.
    """
    links = {
        event["report_id"]: event for event in events if event["kind"] == "link" and event["assembly_id"] == assembly_id
    }
    previous: dict[tuple[object, ...], dict[str, Any] | None] = {}
    rows: list[dict[str, Any]] = []
    for event in events:
        if event["kind"] != "report" or event["id"] not in links:
            continue
        link = links[event["id"]]
        report = event["report"]
        revision = link.get("revision_id")
        key = (revision, event["endpoint"], event["tool_number"])
        applied, timestamp = report.get("applied"), report.get("timestamp")
        comparable = bool(revision and event["endpoint"] and event["tool_number"] is not None)
        comparable = comparable and finite(applied) and finite(timestamp) and timestamp > 0
        baseline = previous.get(key)
        delta = (
            applied - baseline["report"]["applied"]
            if comparable and baseline and timestamp > baseline["report"]["timestamp"]
            else None
        )
        rows.append(
            {
                "receipt": event,
                "revision_id": revision,
                "attribution_note": link["note"],
                "statistics": sample_statistics(report),
                "previous_receipt_id": baseline["id"] if baseline and delta is not None else None,
                "applied_change_mm": delta if finite(delta) else None,
            }
        )
        # A non-increasing clock invalidates this baseline, rather than sorting
        # reports and pretending their capture ordering was different.
        previous[key] = event if comparable and (not baseline or timestamp > baseline["report"]["timestamp"]) else None
    return rows


def post_placement_receipts(
    rows: Sequence[dict[str, Any]],
    assembly: dict[str, Any] | None,
    placement: dict[str, Any] | None,
    endpoint: str,
) -> list[dict[str, Any]]:
    if (
        not assembly
        or not placement
        or not endpoint
        or placement["assembly_id"] != assembly["id"]
        or placement.get("revision_id") != assembly["revision_id"]
    ):
        return []
    return [
        row["receipt"]
        for row in rows
        if row["revision_id"] == assembly["revision_id"]
        and row["receipt"]["endpoint"] == endpoint
        and row["receipt"]["tool_number"] == placement["slot"]
        and row["receipt"]["at"] >= placement["at"]
        and row["receipt"]["report"]["timestamp"] >= placement["at"]
        and row["receipt"]["report"].get("applied") is not None
    ]


def calibration_trend(
    rows: Sequence[dict[str, Any]],
    metric: str,
    *,
    group: tuple[object, ...] | None = None,
    start: int = 0,
    limit: int = 60,
) -> dict[str, Any]:
    """Bounded capture-order points; joins require original comparable receipts.

    All-group and session-local views are scatter only. A missing value,
    truncated baseline or invalidated clock cannot acquire an interpolated line.
    """
    allowed = {"applied_mm", "mean_mm", "range_mm", "stdev_mm", "applied_change_mm"}
    if metric not in allowed or type(start) is not int or start < 0 or type(limit) is not int or not 1 <= limit <= 120:
        raise ValueError("Invalid calibration trend selection")
    filtered = [
        (index, row)
        for index, row in enumerate(rows)
        if group is None or (row["revision_id"], row["receipt"]["endpoint"], row["receipt"]["tool_number"]) == group
    ]
    points: list[dict[str, Any]] = []
    by_receipt: dict[str, int] = {}
    segments: list[tuple[int, int]] = []
    for index, row in filtered[start : start + limit]:
        receipt = row["receipt"]
        value = row.get(metric) if metric == "applied_change_mm" else row["statistics"].get(metric)
        value = value if finite(value) else None
        point = {"row_index": index, "receipt_id": receipt["id"], "value_mm": value}
        previous = by_receipt.get(row["previous_receipt_id"])
        if (
            group is not None
            and value is not None
            and previous is not None
            and points[previous]["value_mm"] is not None
        ):
            segments.append((previous, len(points)))
        points.append(point)
        # Session-local IDs are intentionally repeated and never connected.
        if receipt["id"] != "session-local":
            by_receipt[receipt["id"]] = len(points) - 1
    return {"points": points, "segments": segments, "total": len(filtered), "start": start}
