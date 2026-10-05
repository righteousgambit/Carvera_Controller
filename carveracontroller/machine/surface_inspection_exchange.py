"""Portable nominal/receipt bundles and human-readable inspection reports."""

import csv
import hashlib
import html
import io
import json
import os
import tempfile
import time
from pathlib import Path

from carveracontroller.machine.surface_inspection import (
    SurfaceInspectionStore,
    canonical,
    digest,
    number,
    restore_plan,
    sample_result,
    summary,
)

FORMAT = "carvera.surface-inspections"
MAX_BUNDLE_BYTES = SurfaceInspectionStore.MAX_BYTES + 2048
MAX_REPORT_BYTES = 64 * 1024 * 1024
EVIDENCE_NOTE = "Operator-entered coordinates and references; nominal CAD and declared setup. Numerical comparisons do not verify registration, compensation, measurement accuracy or certification."


def bundle(features):
    features = SurfaceInspectionStore.validate({"schema": 1, "features": features})
    return canonical(
        {"format": FORMAT, "version": 1, "exported_at": time.time(), "features": features, "sha256": digest(features)}
    )


def read_bundle(payload):
    if len(payload.encode() if isinstance(payload, str) else payload) > MAX_BUNDLE_BYTES:
        raise ValueError("Inspection bundle exceeds size limit")
    try:
        data = json.loads(payload, object_pairs_hook=SurfaceInspectionStore._object)
    except (RecursionError, UnicodeError) as exc:
        raise ValueError("Unreadable inspection bundle encoding or nesting") from exc
    if not isinstance(data, dict) or set(data) != {"format", "version", "exported_at", "features", "sha256"}:
        raise ValueError("Invalid inspection bundle fields")
    if data["format"] != FORMAT or type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported inspection bundle")
    number(data["exported_at"], "Export time")
    if data["sha256"] != digest(data["features"]):
        raise ValueError("Inspection bundle content identity mismatch")
    return SurfaceInspectionStore.validate({"schema": 1, "features": data["features"]})


def merge_features(existing, incoming):
    """Preserve definitions; merge independent receipts, reject identity conflicts."""
    existing = SurfaceInspectionStore.validate({"schema": 1, "features": existing})
    incoming = SurfaceInspectionStore.validate({"schema": 1, "features": incoming})
    by_id = {f["id"]: f for f in existing}
    added_features, added_samples = 0, 0
    for feature in incoming:
        if feature["id"] not in by_id:
            existing.append(feature)
            by_id[feature["id"]] = feature
            added_features += 1
            added_samples += len(feature["samples"])
            continue
        current = by_id[feature["id"]]
        if canonical({k: v for k, v in current.items() if k != "samples"}) != canonical(
            {k: v for k, v in feature.items() if k != "samples"}
        ):
            raise ValueError("Conflicting inspection feature identity: " + feature["id"])
        samples = {s["id"]: s for s in current["samples"]}
        for sample in feature["samples"]:
            if sample["id"] in samples:
                if canonical(sample) != canonical(samples[sample["id"]]):
                    raise ValueError("Conflicting measurement receipt identity: " + sample["id"])
            else:
                current["samples"].append(sample)
                samples[sample["id"]] = sample
                added_samples += 1
    SurfaceInspectionStore.validate({"schema": 1, "features": existing})
    return existing, {"features_added": added_features, "receipts_added": added_samples}


def preview_import(store, path):
    if store.error:
        raise ValueError("Local inspection records need repair before importing")
    path = Path(path)
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Inspection bundle exceeds size limit")
    payload = path.read_bytes()
    _features, counts = merge_features(store.features, read_bundle(payload))
    return {**counts, "source_sha256": hashlib.sha256(payload).hexdigest(), "path": str(path)}


def import_file(store, path, expected_sha256=None):
    if store.error:
        raise ValueError("Local inspection records need repair before importing")
    path = Path(path)
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError("Inspection bundle exceeds size limit")
    payload = path.read_bytes()
    source_hash = hashlib.sha256(payload).hexdigest()
    if expected_sha256 is not None and source_hash != expected_sha256:
        raise ValueError("Inspection bundle changed after review · review it again")
    features, counts = merge_features(store.features, read_bundle(payload))
    if counts["features_added"] or counts["receipts_added"]:
        store._save(features)
    return {**counts, "source_sha256": source_hash, "path": str(path)}


def spreadsheet_text(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def csv_report(features):
    features = SurfaceInspectionStore.validate({"schema": 1, "features": features})
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(
        [
            "part",
            "feature",
            "feature_id",
            "nominal_sha256",
            "lower_mm",
            "upper_mm",
            "nominal_x_mm",
            "nominal_y_mm",
            "nominal_z_mm",
            "outward_normal_x",
            "outward_normal_y",
            "outward_normal_z",
            "tip_diameter_mm",
            "source_triangle_index",
            "receipt_id",
            "x_mm",
            "y_mm",
            "z_mm",
            "coordinate_kind",
            "frame",
            "source_class",
            "source_ref",
            "registration_ref",
            "calibration_ref",
            "observed_at",
            "recorded_at",
            "normal_deviation_mm",
            "comparison_state",
        ]
    )
    for feature in features:
        plan = restore_plan(feature["plan"])
        prefix = [
            spreadsheet_text(feature["part"]),
            spreadsheet_text(feature["name"]),
            spreadsheet_text(feature["id"]),
            feature["nominal_sha256"],
            *["" if v is None else v for v in feature["limits_mm"]],
            *plan.reference.component_point_mm,
            *plan.outward_normal,
            plan.tip_radius_mm * 2,
            plan.reference.triangle_index,
        ]
        if not feature["samples"]:
            writer.writerow([*prefix, *([""] * 13), "no_measurements"])
        for sample in feature["samples"]:
            result = sample_result(feature, sample)
            writer.writerow(
                [
                    *prefix,
                    spreadsheet_text(sample["id"]),
                    *sample["position_mm"],
                    sample["kind"],
                    sample["frame"],
                    sample["source_class"],
                    *[
                        spreadsheet_text(sample[k])
                        for k in ("source_ref", "registration_ref", "calibration_ref", "observed_at")
                    ],
                    sample["recorded_at"],
                    "" if result["deviation_mm"] is None else result["deviation_mm"],
                    result["state"],
                ]
            )
    return stream.getvalue()


def html_report(features):
    features = SurfaceInspectionStore.validate({"schema": 1, "features": features})

    def esc(value):
        return html.escape(str(value), quote=True)

    sections = []
    for f in features:
        s = summary(f)
        limits = (
            "Not specified" if f["limits_mm"][0] is None else f"{f['limits_mm'][0]:+.5f} to {f['limits_mm'][1]:+.5f} mm"
        )
        rows = []
        for sample in f["samples"]:
            r = sample_result(f, sample)
            deviation = "Unevaluated" if r["deviation_mm"] is None else f"{r['deviation_mm']:+.5f} mm"
            state = r["state"].replace("_", " ")
            rows.append(
                "<tr>"
                + "".join(
                    f"<td>{esc(v)}</td>"
                    for v in (
                        sample["id"],
                        sample["source_ref"],
                        ", ".join(f"{v:.5f}" for v in sample["position_mm"]),
                        deviation,
                        state,
                        sample["kind"].replace("_", " "),
                        sample["registration_ref"] or "Unknown",
                        sample["calibration_ref"] or "Unknown",
                        sample["observed_at"] or "Unknown",
                        sample["recorded_at"],
                    )
                )
                + "</tr>"
            )
        mean = "—" if s["mean_mm"] is None else f"{s['mean_mm']:+.5f} mm"
        spread = "—" if s["range_mm"] is None else f"{s['range_mm']:.5f} mm"
        stdev = "—" if s["sample_stdev_mm"] is None else f"{s['sample_stdev_mm']:.5f} mm"
        headers = (
            "Receipt ID",
            "Source receipt",
            "XYZ · mm",
            "Normal deviation",
            "Comparison",
            "Coordinate kind",
            "Registration",
            "Compensation",
            "Observed time",
            "Recorded Unix time",
        )
        sections.append(f"""<section><h2>{esc(f["part"])} <span> / {esc(f["name"])}</span></h2>
<p class="identity">Feature {esc(f["id"])}<br>Nominal {esc(f["nominal_sha256"])}</p>
<div class="metrics"><div><b>{s["recorded"]}</b>Receipts</div><div><b>{s["evaluated"]}</b>Evaluated</div><div><b>{s["unevaluated"]}</b>Unevaluated</div><div><b>{s["outside"]}</b>Outside declared limits</div></div>
<p>Normal limits: <strong>{esc(limits)}</strong><br>Mean: {esc(mean)} · Repeat range: {esc(spread)} · Sample standard deviation: {esc(stdev)}</p>
<div class="table"><table><thead><tr>{"".join("<th>" + esc(h) + "</th>" for h in headers)}</tr></thead><tbody>{"".join(rows) or '<tr><td colspan="10">No measurement receipts. Conformance is unknown.</td></tr>'}</tbody></table></div>
<details><summary>Nominal geometry and setup</summary><pre>{esc(canonical({"plan": f["plan"], "context": f["context"]}))}</pre></details></section>""")
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Surface inspection report</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;background:#f3f5f8;color:#182330;margin:0}}main{{max-width:1280px;margin:auto;padding:32px}}h1{{font-size:32px;margin-bottom:8px}}h2{{font-size:21px}}h2 span,.identity{{color:#627386}}section{{background:white;border:1px solid #dbe2ea;border-radius:14px;padding:24px;margin:24px 0}}.identity{{font:12px/1.6 monospace;overflow-wrap:anywhere}}.metrics{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}.metrics div{{background:#edf6f3;border-radius:8px;padding:12px}}b{{display:block;font-size:24px}}.table{{overflow:auto;margin-top:20px}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #dde4ec;vertical-align:top;overflow-wrap:anywhere;min-width:110px}}th{{background:#edf2f6}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}details{{margin:16px 0}}summary{{cursor:pointer}}@media print{{body{{background:white}}main{{padding:0}}section{{border:0;padding:12px 0}}details>pre{{display:block}}.table{{overflow:visible}}table{{font-size:9px}}th,td{{min-width:0;padding:4px}}}}@media(max-width:600px){{main{{padding:16px}}section{{padding:16px}}}}</style>
<style>@page{{size:A4 landscape;margin:14mm}}@media print{{body{{font-size:12px}}h1{{font-size:24px}}h2{{font-size:18px}}.metrics{{display:flex;gap:10px}}.metrics div{{flex:1;padding:8px;break-inside:avoid}}.metrics b{{font-size:20px}}table{{font-size:11px}}th,td{{padding:6px;overflow-wrap:normal;word-break:normal}}td:first-child{{overflow-wrap:anywhere}}tr{{break-inside:avoid}}details{{break-before:page}}summary{{font-size:18px;font-weight:bold}}pre{{font-size:11px;line-height:1.8;white-space:pre-wrap;overflow-wrap:anywhere}}}}</style>
<main><h1>Surface inspection report</h1><p>{esc(EVIDENCE_NOTE)}</p><p class="identity">Feature/receipt content SHA-256: {digest(features)}</p>{"".join(sections) or "<section>No inspection features. Conformance is unknown.</section>"}</main></html>"""


def export_file(features, path, format_name):
    renderers = {"Portable JSON": bundle, "CSV": csv_report, "HTML report": html_report}
    if format_name not in renderers:
        raise ValueError("Unknown inspection export format")
    payload = renderers[format_name](features).encode("utf-8")
    limit = MAX_BUNDLE_BYTES if format_name == "Portable JSON" else MAX_REPORT_BYTES
    if len(payload) > limit:
        raise ValueError("Inspection export exceeds size limit")
    target = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".inspection-export-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        saved = target.read_bytes()
        if saved != payload:
            raise ValueError("Saved inspection export readback mismatch")
        if format_name == "Portable JSON":
            read_bundle(saved)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {
        "path": str(target),
        "sha256": hashlib.sha256(saved).hexdigest(),
        "bytes": len(saved),
        "features": len(features),
        "receipts": sum(len(f["samples"]) for f in features),
        "format": format_name,
    }
