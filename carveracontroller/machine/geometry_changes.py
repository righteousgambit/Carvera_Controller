"""Content-bound simulation context and explained setup/tool consequences.

Operation dependencies are conservative. They are not spatial collision regions
and cannot establish physical clearance or invalidate a controller's offsets.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from dataclasses import asdict, dataclass
from typing import Protocol, TypedDict, cast

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.program_operations import Operation, ProgramOperations

Vec3 = tuple[float, float, float]


class AssetState(TypedDict):
    path: str
    loaded_sha256: str | None
    current_sha256: str | None
    error: str


class AssemblyIdentity(TypedDict):
    assembly_id: str
    revision_id: str
    profile_id: str
    design_fingerprint: str
    number: int


class GeometryContext(TypedDict):
    schema: int
    program: str | None
    stock: dict[str, object]
    work_offset_mm: Vec3
    workholding: dict[str, object]
    tools: dict[str, dict[str, object] | None]
    assembly: AssemblyIdentity | None
    components: dict[str, ComponentContext]


class ComponentContext(TypedDict):
    source_revision: str
    source_sha256: str
    asset: AssetState | None


class GeometrySetup(Protocol):
    @property
    def stock_size_mm(self) -> Vec3 | None: ...
    @property
    def stock_origin_mm(self) -> Vec3: ...
    @property
    def work_offset_mm(self) -> Vec3: ...


class GeometryProfile(Protocol):
    @property
    def source_revision(self) -> str: ...
    @property
    def source_sha256(self) -> str: ...


class GeometryViewer(Protocol):
    @property
    def library_tool_table_mm(self) -> Mapping[int | None, ToolDefinition]: ...
    @property
    def machine_component_profiles(self) -> Mapping[str, GeometryProfile]: ...
    @property
    def machine_profile(self) -> GeometryProfile | None: ...
    @property
    def machine_setup(self) -> GeometrySetup: ...
    @property
    def assembly_preview_binding(self) -> AssemblyIdentity | None: ...
    @property
    def workholding_offset_mm(self) -> Vec3: ...
    @property
    def workholding_rotation_deg(self) -> float: ...
    @property
    def jaw_offset_mm(self) -> float: ...


def digest_context(context: object) -> str:
    return hashlib.sha256(json.dumps(context, sort_keys=True, allow_nan=False).encode()).hexdigest()


def asset_state(
    path: str,
    loaded_digest: str | None,
    limit: int = 24 * 1024 * 1024,
    *,
    verify: bool = True,
    cancelled: Callable[[], bool] | None = None,
) -> AssetState | None:
    if not path:
        return None
    if not verify:
        return {"path": path, "loaded_sha256": loaded_digest, "current_sha256": loaded_digest, "error": ""}
    current: str | None
    try:
        current = asset_digest(path, limit, cancelled=cancelled) if cancelled is not None else asset_digest(path, limit)
        error = ""
    except InterruptedError:
        raise
    except (OSError, ValueError) as exc:
        current, error = None, str(exc)
    return {"path": path, "loaded_sha256": loaded_digest, "current_sha256": current, "error": error}


def capture_context(
    viewer: GeometryViewer, program: ProgramOperations | None, *, verify_assets: bool = True
) -> GeometryContext:
    """Detach selected definitions, optionally observing their exact CAD bytes."""
    tools: dict[str, dict[str, object] | None] = {}
    required = program.motion_tool_ids() if program else set(viewer.library_tool_table_mm)
    for number in sorted(required, key=str):
        definition = viewer.library_tool_table_mm.get(number)
        if definition is None:
            tools[str(number)] = None
            continue
        record: dict[str, object] = asdict(definition)
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
    components: dict[str, ComponentContext] = {}
    for group, profile in profiles.items():
        path = getattr(profile, "asset_path", "")
        components[group] = {
            "source_revision": profile.source_revision,
            "source_sha256": profile.source_sha256,
            "asset": asset_state(path, getattr(profile, "asset_sha256", ""), 8 * 1024 * 1024, verify=verify_assets),
        }
    binding = viewer.assembly_preview_binding
    result: GeometryContext = {
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
            "assembly_id": binding["assembly_id"],
            "revision_id": binding["revision_id"],
            "profile_id": binding["profile_id"],
            "design_fingerprint": binding["design_fingerprint"],
            "number": binding["number"],
        }
        if binding
        else None,
        "components": components,
    }
    model = getattr(viewer.machine_setup, "stock_model", None)
    if model is not None:
        result["stock"]["source"] = {
            **model.reference,
            "asset": asset_state(model.source_path, model.source_sha256, verify=verify_assets),
        }
    return deepcopy(result)


def verify_context_assets(context: GeometryContext, *, cancelled: Callable[[], bool] | None = None) -> GeometryContext:
    """Rehash a detached context without consulting mutable viewer/UI state."""
    result = deepcopy(context)

    def verify(asset: AssetState | None, limit: int) -> AssetState | None:
        if cancelled is not None and cancelled():
            raise InterruptedError("CAD verification cancelled")
        return asset_state(asset["path"], asset["loaded_sha256"], limit, cancelled=cancelled) if asset else None

    for definition in result["tools"].values():
        if definition:
            for kind in ("cutter_asset", "holder_asset"):
                definition[kind] = verify(cast("AssetState | None", definition[kind]), 24 * 1024 * 1024)
    for component in result["components"].values():
        component["asset"] = verify(component["asset"], 8 * 1024 * 1024)
    source = result["stock"].get("source")
    if isinstance(source, dict):
        source["asset"] = verify(cast("AssetState | None", source.get("asset")), 24 * 1024 * 1024)
    if cancelled is not None and cancelled():
        raise InterruptedError("CAD verification cancelled")
    return result


def asset_problems(context: GeometryContext) -> tuple[str, ...]:
    problems: list[str] = []
    entries: list[tuple[str, AssetState | None]] = []
    for number, definition in context["tools"].items():
        if definition:
            # capture_context always adds these two typed asset entries while
            # retaining the other dataclass fields in their existing format.
            entries.extend(
                (f"T{number} {kind}", cast("AssetState | None", definition[kind + "_asset"]))
                for kind in ("cutter", "holder")
            )
    entries.extend((group, value["asset"]) for group, value in context["components"].items())
    source = context["stock"].get("source")
    if isinstance(source, dict):
        entries.append(("Stock source", cast("AssetState | None", source.get("asset"))))
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


def _display(value: object) -> str:
    if value is None:
        return "unknown / absent"
    if isinstance(value, dict) and "loaded_sha256" in value:
        return f"{value['path']} · loaded {value['loaded_sha256'] or 'unknown'} · current {value['current_sha256'] or 'unreadable'}"
    return json.dumps(value, sort_keys=True)


def context_changes(before: GeometryContext, after: GeometryContext) -> tuple[GeometryChange, ...]:
    """Return full prior/current values, with a tool-specific dependency where known."""
    changes: list[GeometryChange] = []
    prior_values, current_values = cast(Mapping[str, object], before), cast(Mapping[str, object], after)
    for key, title in (
        ("program", "Program revision"),
        ("stock", "Stock size / placement"),
        ("work_offset_mm", "Preview work offset"),
        ("workholding", "Vise placement / jaw"),
        ("assembly", "Physical assembly revision"),
        ("components", "Machine / fixture / vise CAD"),
    ):
        if digest_context({"value": prior_values[key]}) != digest_context({"value": current_values[key]}):
            assembly = after["assembly"] or before["assembly"]
            assembly_number = assembly["number"] if key == "assembly" and assembly else None
            changes.append(
                GeometryChange(title, _display(prior_values[key]), _display(current_values[key]), assembly_number)
            )
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


def affected_operations(changes: Iterable[GeometryChange], operations: Iterable[Operation]) -> tuple[Operation, ...]:
    changes = tuple(changes)
    if not changes:
        return ()
    all_operations = any(change.tool_number is None for change in changes)
    numbers = {change.tool_number for change in changes}
    return tuple(operation for operation in operations if all_operations or numbers.intersection(operation.tool_ids))
