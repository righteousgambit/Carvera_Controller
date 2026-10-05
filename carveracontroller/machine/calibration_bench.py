"""Calibration evidence summaries, never physical identity or wear diagnoses."""

import math
import statistics


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def sample_statistics(report):
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


def assembly_calibrations(events, assembly_id):
    """Keep capture order and provenance; never merge groups or repair clocks.

    Numeric applied-offset differences are only computed within a versioned
    assembly/source/tool group with increasing measurement timestamps. Missing
    offsets or unknown timing break the previous baseline for that group.
    """
    links = {
        event["report_id"]: event for event in events if event["kind"] == "link" and event["assembly_id"] == assembly_id
    }
    previous = {}
    rows = []
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
                "previous_receipt_id": baseline["id"] if delta is not None else None,
                "applied_change_mm": delta if finite(delta) else None,
            }
        )
        # A non-increasing clock invalidates this baseline, rather than sorting
        # reports and pretending their capture ordering was different.
        previous[key] = event if comparable and (not baseline or timestamp > baseline["report"]["timestamp"]) else None
    return rows


def post_placement_receipts(rows, assembly, placement, endpoint):
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
