"""Inert, revision-bound setup sheets for offline screen and print review."""

from __future__ import annotations

import copy
import hashlib
import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from carveracontroller.machine.job_packages import JobPackage


def setup_sheet(job: JobPackage, evidence: list[dict[str, Any]], captured_at: str) -> dict[str, Any]:
    """Retain declarations and reported checks, never machine execution authority."""
    if not job.program or len(job.program) > 64 * 1024 * 1024:
        raise ValueError("Choose a nonempty program of at most 64 MiB")
    preview = job.inspection_plan.get("loaded_preview_sha256")
    if preview is not None:
        normalized = job.program.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if hashlib.sha256(normalized.encode("utf-8")).hexdigest() != preview:
            raise ValueError("Selected program differs from the loaded preview; reload it before handoff")
    sheet = {
        "schema_version": 1,
        "captured_at_utc": captured_at,
        "program": {
            "name": job.program_name,
            "sha256": hashlib.sha256(job.program).hexdigest(),
            "size_bytes": len(job.program),
            "loaded_preview": "Matched normalized source text" if preview else "Not available; file bytes only",
            "loaded_preview_sha256": preview,
        },
        "declarations": copy.deepcopy(
            {
                "machine": job.machine,
                "stock": job.stock,
                "vise": job.vise,
                "fixtures": job.fixtures,
                "tools": job.tools,
                "toolsets": job.toolsets,
                "tool_definitions_mm": job.inspection_plan.get("tool_definitions_mm", []),
                "assembly_binding": job.inspection_plan.get("assembly_binding"),
            }
        ),
        "reported_checks": copy.deepcopy(evidence),
        "limitations": [
            "Declared preview geometry and operator-reported checks; no independent physical qualification.",
            "Mounting hole addresses, jaw contact and stock protrusion require a separate measured mounting record.",
            "This snapshot grants no run permission. Reconcile the current machine, program and setup before use.",
        ],
    }
    encoded = json.dumps(sheet, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    if len(encoded) > 4 * 1024 * 1024:
        raise ValueError("Setup sheet metadata exceeds 4 MiB")
    sheet["snapshot_sha256"] = hashlib.sha256(encoded).hexdigest()
    return sheet


def render_setup_sheet(sheet: dict[str, Any]) -> str:
    """Static self-contained HTML: no active scripts or remote resources."""

    def escape(value: object) -> str:
        return html.escape(str(value), quote=True)

    def value(item: object) -> str:
        if item is None or item == [] or item == {}:
            return "Not recorded"
        if isinstance(item, (dict, list, tuple)):
            return json.dumps(item, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2)
        return str(item)

    def table(record: dict[str, Any]) -> str:
        return (
            "<table>"
            + "".join(
                f"<tr><th>{escape(key.replace('_', ' '))}</th><td><pre>{escape(value(item))}</pre></td></tr>"
                for key, item in record.items()
            )
            + "</table>"
        )

    sections = []
    for group, data in sheet["declarations"].items():
        records = data if isinstance(data, list) else [data]
        content = "".join(
            table(record) if isinstance(record, dict) else f"<p>{escape(value(record))}</p>" for record in records
        )
        sections.append(
            f"<section><h2>{escape(group.replace('_', ' '))}</h2>{content or '<p>Not recorded</p>'}</section>"
        )
    checks = "".join(table(record) for record in sheet["reported_checks"]) or "<p>No reported checks retained.</p>"
    limits = "".join(f"<li>{escape(item)}</li>" for item in sheet["limitations"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Setup sheet · {escape(sheet["program"]["name"])}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:#edf1f5;color:#172432;font:16px/1.5 system-ui,sans-serif}}
main{{max-width:1000px;margin:auto;padding:24px}}h1{{margin:0;font-size:28px}}h2{{font-size:18px;text-transform:capitalize}}
section,.notice{{background:white;padding:20px;margin:16px 0;border:1px solid #ccd5de;border-radius:10px}}
.notice{{border-left:5px solid #ad651b}}table{{width:100%;border-collapse:collapse;margin:12px 0;table-layout:fixed}}
th,td{{padding:8px;text-align:left;vertical-align:top;border-bottom:1px solid #dde4eb}}th{{width:30%;font-weight:600}}
pre{{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,monospace}}li{{margin:8px 0}}
@media(max-width:600px){{main{{padding:12px}}section,.notice{{padding:12px}}th{{width:38%}}h1{{font-size:23px}}}}
@media print{{body{{background:white;font-size:11pt}}main{{padding:0;max-width:none}}section,.notice{{border-radius:0}}
h2{{break-after:avoid}}tr{{break-inside:avoid}}pre{{font-size:9pt}}}}
</style></head><body><main><h1>Setup handoff</h1><p>Captured {escape(sheet["captured_at_utc"])} · UTC</p>
<div class="notice"><strong>Review snapshot · physical setup requires reconciliation</strong><ul>{limits}</ul></div>
<section><h2>Revision identity</h2>{table({**sheet["program"], "setup snapshot SHA256": sheet["snapshot_sha256"]})}</section>
{"".join(sections)}<section><h2>Reported setup checks</h2>{checks}</section></main></body></html>"""


def save_setup_sheet(sheet: dict[str, Any], path: str | Path) -> str:
    """Atomic local write with byte readback; return the HTML digest."""
    path = Path(path).expanduser()
    data = render_setup_sheet(sheet).encode("utf-8")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".setup-sheet-", delete=False) as target:
            temporary = Path(target.name)
            target.write(data)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        if path.read_bytes() != data:
            raise OSError("Setup sheet readback differs")
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return hashlib.sha256(data).hexdigest()
