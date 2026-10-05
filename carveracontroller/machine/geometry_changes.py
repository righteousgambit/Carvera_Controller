"""Content-bound simulation context and explained setup/tool consequences.

Operation dependencies are conservative. They are not spatial collision regions
and cannot establish physical clearance or invalidate a controller's offsets.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from carveracontroller.addons.cad_identity import asset_digest


def digest_context(context):
    return hashlib.sha256(json.dumps(context, sort_keys=True, allow_nan=False).encode()).hexdigest()


def asset_state(path, loaded_digest, limit=24 * 1024 * 1024, *, verify=True):
    if not path:
        return None
    if not verify:
        return {"path": path, "loaded_sha256": loaded_digest, "current_sha256": loaded_digest, "error": ""}
    try:
        current = asset_digest(path, limit)
        error = ""
    except (OSError, ValueError) as exc:
        current, error = None, str(exc)
    return {"path": path, "loaded_sha256": loaded_digest, "current_sha256": current, "error": error}


def capture_context(viewer, program, *, verify_assets=True):
    """Fresh exact-byte observation on an explicit calculation/review/export action."""
    tools = {}
    required = program.motion_tool_ids() if program else set(viewer.library_tool_table_mm)
    for number in sorted(required, key=str):
        definition = viewer.library_tool_table_mm.get(number)
        if definition is None:
            tools[str(number)] = None
            continue
        record = asdict(definition)
        record["tool_type"] = definition.tool_type.value
        # Drawing/catalog metadata has no effect on stock or clearance models.
        for key in ("description", "vendor", "product_id", "type_name", "drawing_path", "source_url"):
            record.pop(key)
        record["cutter_asset"] = asset_state(definition.geometry_path, definition.geometry_sha256, verify=verify_assets)
        record["holder_asset"] = asset_state(
            definition.holder_geometry_path, definition.holder_geometry_sha256, verify=verify_assets
        )
        tools[str(number)] = record
    profiles = dict(viewer.machine_component_profiles)
    if viewer.machine_profile:
        profiles["base_machine"] = viewer.machine_profile
    components = {}
    for group, profile in profiles.items():
        path = getattr(profile, "asset_path", "")
        components[group] = {
            "source_revision": profile.source_revision,
            "source_sha256": profile.source_sha256,
            "asset": asset_state(path, getattr(profile, "asset_sha256", ""), 8 * 1024 * 1024, verify=verify_assets),
        }
    binding = viewer.assembly_preview_binding
    return {
        "schema": 1,
        "program": program.file_hash if program else None,
        "stock": {
            "size_mm": viewer.machine_setup.stock_size_mm,
            "origin_mm": viewer.machine_setup.stock_origin_mm,
            "rotation_deg": getattr(viewer.machine_setup, "stock_rotation_deg", 0),
        },
        "work_offset_mm": viewer.machine_setup.work_offset_mm,
        "workholding": {
            "offset_mm": viewer.workholding_offset_mm,
            "rotation_deg": viewer.workholding_rotation_deg,
            "jaw_offset_mm": viewer.jaw_offset_mm,
        },
        "tools": tools,
        "assembly": {
            key: binding[key] for key in ("assembly_id", "revision_id", "profile_id", "design_fingerprint", "number")
        }
        if binding
        else None,
        "components": components,
    }


def asset_problems(context):
    problems = []
    entries = []
    for number, definition in context["tools"].items():
        if definition:
            entries.extend((f"T{number} {kind}", definition[kind + "_asset"]) for kind in ("cutter", "holder"))
    entries.extend((group, value["asset"]) for group, value in context["components"].items())
    for title, asset in entries:
        if asset is None:
            continue
        if asset["error"]:
            problems.append(f"{title}: asset unreadable; reload or repair the selected CAD file")
        elif not asset["loaded_sha256"]:
            problems.append(f"{title}: loaded CAD bytes are unversioned; reload the selected asset")
        elif asset["loaded_sha256"] != asset["current_sha256"]:
            problems.append(f"{title}: CAD bytes changed at the same path; reload the selected asset")
    return tuple(problems)


@dataclass(frozen=True)
class GeometryChange:
    title: str
    before: str
    after: str
    tool_number: int | None = None


def _display(value):
    if value is None:
        return "unknown / absent"
    if isinstance(value, dict) and "loaded_sha256" in value:
        return f"{value['path']} · loaded {value['loaded_sha256'] or 'unknown'} · current {value['current_sha256'] or 'unreadable'}"
    return json.dumps(value, sort_keys=True)


def context_changes(before, after):
    """Return full prior/current values, with a tool-specific dependency where known."""
    changes = []
    for key, title in (
        ("program", "Program revision"),
        ("stock", "Stock size / placement"),
        ("work_offset_mm", "Preview work offset"),
        ("workholding", "Vise placement / jaw"),
        ("assembly", "Physical assembly revision"),
        ("components", "Machine / fixture / vise CAD"),
    ):
        if digest_context({"value": before[key]}) != digest_context({"value": after[key]}):
            number = (after[key] or before[key]).get("number") if key == "assembly" else None
            changes.append(GeometryChange(title, _display(before[key]), _display(after[key]), number))
    for number in sorted(before["tools"].keys() | after["tools"].keys(), key=str):
        old, new = before["tools"].get(number), after["tools"].get(number)
        if old is None or new is None:
            if old != new:
                changes.append(
                    GeometryChange(
                        f"T{number} definition", _display(old), _display(new), int(number) if number != "None" else None
                    )
                )
            continue
        for key in old.keys() | new.keys():
            if old.get(key) != new.get(key):
                changes.append(
                    GeometryChange(
                        f"T{number} {key.replace('_', ' ')}",
                        _display(old.get(key)),
                        _display(new.get(key)),
                        int(number),
                    )
                )
    return tuple(sorted(changes, key=lambda change: change.title))


def affected_operations(changes, operations):
    if not changes:
        return ()
    all_operations = any(change.tool_number is None for change in changes)
    numbers = {change.tool_number for change in changes}
    return tuple(operation for operation in operations if all_operations or numbers.intersection(operation.tool_ids))
