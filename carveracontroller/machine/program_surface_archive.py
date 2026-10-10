"""Portable prepared triangle declarations; every source/result is recomputed."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from types import MappingProxyType
from typing import Any

from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_profile_io import retain_geometry_bytes
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_clearance_archive import (
    encoded,
    program_review_payload,
    recompute_program_review,
)
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance, ProgramClearanceSource
from carveracontroller.machine.program_stock_evolution import (
    evolution_record,
    input_record,
    restore_inputs,
    review_stock_evolution,
)
from carveracontroller.machine.program_surface_clearance import (
    ProgramSurfaceClearance,
    refine_program_surfaces,
    validate_rotating_envelopes,
)
from carveracontroller.machine.repeat_parts import vector
from carveracontroller.machine.rotating_shape import RotatingShape
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh

MAX_REVIEW_BYTES = 64 * 1024 * 1024
MAX_TRIANGLES = 250_000
MAX_MESHES = 4096
LEGACY_METHOD = "c1-prepared-triangles-continuous-surfaces-solids-v1"
METHOD = "c1-prepared-triangles-continuous-surfaces-solids-v2"
GROUP_METHOD = "c1-exact-interval-groups-continuous-surfaces-solids-v3"
DIRECTION_METHOD = "c1-direction-bounds-continuous-surfaces-solids-v4"
DIRECTION_GROUP_METHOD = "c1-direction-bound-groups-continuous-surfaces-solids-v5"
ROTATING_METHOD = "c1-continuous-declared-rotating-surfaces-solids-v6"
ROTATING_GROUP_METHOD = "c1-declared-rotating-exact-groups-surfaces-solids-v7"
SHAPED_METHOD = "c1-declared-quadric-rotating-surfaces-solids-v8"
SHAPED_GROUP_METHOD = "c1-declared-quadric-rotating-groups-surfaces-solids-v9"
STOCK_METHOD = "c1-declared-surfaces-ordered-stock-v10"
STOCK_GROUP_METHOD = "c1-declared-groups-ordered-stock-v11"
INDEX_METHODS = {
    LEGACY_METHOD: "median-v1",
    METHOD: "surface-area-v2",
    GROUP_METHOD: "surface-area-v2",
    DIRECTION_METHOD: "surface-directions-v3",
    DIRECTION_GROUP_METHOD: "surface-directions-v3",
    ROTATING_METHOD: "surface-directions-v3",
    ROTATING_GROUP_METHOD: "surface-directions-v3",
    SHAPED_METHOD: "surface-directions-v3",
    SHAPED_GROUP_METHOD: "surface-directions-v3",
    STOCK_METHOD: "surface-directions-v3",
    STOCK_GROUP_METHOD: "surface-directions-v3",
}
BODY_FIELDS = {
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
}


def exact_record(value: Any) -> Any:
    """Rational evidence stays exact; readers compare freshly computed records."""
    if isinstance(value, Fraction):
        return {"numerator": str(value.numerator), "denominator": str(value.denominator)}
    if isinstance(value, dict):
        return {k: exact_record(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [exact_record(v) for v in value]
    return value


def surface_report_record(
    report: ProgramSurfaceClearance, *, cancelled: Callable[[], bool] = lambda: False
) -> dict[str, Any]:
    if len(report.contacts) > 10_000 or len(report.occupancy) > 100_000 or len(report.gaps) > 10_000:
        raise ValueError("Surface review exceeds complete result budgets")
    if len(report.rotating) > 100_000 or (report.rotating and not report.rotating_envelopes):
        raise ValueError("Rotating result requires complete bounded section declarations")
    if report.contact_mode not in ("triangles", "groups"):
        raise ValueError("Unsupported surface contact representation")
    if report.contact_mode == "triangles" and (report.groups or report.group_counts != (0, 0)):
        raise ValueError("Individual-contact report cannot retain ambiguous group evidence")
    if report.contact_mode == "groups" and report.contacts:
        raise ValueError("Grouped report cannot retain ambiguous individual contact evidence")
    if len(report.groups) > 10_000 or sum(len(g.group.triangle_pairs) for g in report.groups) > 100_000:
        raise ValueError("Grouped review exceeds complete representation budgets")
    result: dict[str, Any] = {}
    names = (
        ("contacts", "occupancy", "gaps", "groups")
        if report.contact_mode == "groups"
        else ("contacts", "occupancy", "gaps")
    )
    for name in names:
        rows = []
        for i, row in enumerate(getattr(report, name)):
            if i % 64 == 0 and cancelled():
                raise InterruptedError("Surface-review exchange cancelled")
            rows.append(exact_record(asdict(row)))
        result[name] = rows
    if report.rotating_envelopes:
        rows = []
        for i, row in enumerate(report.rotating):
            if i % 64 == 0 and cancelled():
                raise InterruptedError("Rotating-review exchange cancelled")
            rows.append(exact_record(asdict(row)))
        result["rotating"] = rows
    if report.stock_evolution is not None:
        result["ordered_stock"] = evolution_record(report.stock_evolution, cancelled=cancelled)
    if report.contact_mode == "groups":
        result.update(contact_mode=report.contact_mode, group_counts=report.group_counts)
    result["geometry_sha256"] = mesh_record(report, cancelled=cancelled)["sha256"]
    result.update(
        {
            name: getattr(report, name)
            for name in (
                "refined_pairs",
                "nodes",
                "triangle_pairs",
                "triangles",
                "solid_counts",
                "qualification",
            )
        }
    )
    return result


def mesh_record(report: ProgramSurfaceClearance, *, cancelled: Callable[[], bool]) -> dict[str, Any]:
    pool, refs, identities = [], {}, {}
    count = 0
    for tool in sorted(report.meshes):
        meshes = report.meshes[tool]
        refs[str(tool)] = {}
        for name in sorted(meshes):
            mesh = meshes[name]
            if cancelled():
                raise InterruptedError("Surface-review geometry capture cancelled")
            key = id(mesh)
            if key not in identities:
                count += len(mesh.triangles)
                if count > MAX_TRIANGLES or len(pool) >= MAX_MESHES:
                    raise ValueError("Surface-review shared geometry budget exceeded; no faces omitted")
                identities[key] = len(pool)
                # Immutable complete tuples are retained until worker encoding.
                pool.append(mesh.triangles)
            refs[str(tool)][name] = identities[key]
    geometry = {"pool": pool, "tools": refs}
    if report.rotating_envelopes:
        validate_rotating_envelopes(report.body_review.records, report.rotating_envelopes)
        geometry["rotating"] = {
            str(tool): {name: [asdict(s) for s in sections] for name, sections in rows.items()}
            for tool, rows in report.rotating_envelopes.items()
        }
    return {**geometry, "sha256": hashlib.sha256(encoded(geometry)).hexdigest()}


def restore_meshes(
    value: Any,
    body: ProgramBodyClearance,
    *,
    cancelled: Callable[[], bool],
    index_method: str = "surface-directions-v3",
) -> Mapping[int, Mapping[str, SurfaceMesh]]:
    if not isinstance(value, dict) or set(value) not in (
        {"pool", "tools", "sha256"},
        {"pool", "tools", "sha256", "rotating"},
    ):
        raise ValueError("Surface review needs explicit prepared mesh pool and tool bindings")
    pool, tools = value["pool"], value["tools"]
    if not isinstance(pool, list) or not 1 <= len(pool) <= MAX_MESHES:
        raise ValueError("Surface-review mesh pool exceeds bounded contract")
    if not isinstance(tools, dict) or set(tools) != {str(t) for t in body.records}:
        raise ValueError("Surface-review mesh tools differ from reparsed program tools")
    count = 0
    for rows in pool:
        if not isinstance(rows, (list, tuple)):
            raise ValueError("Surface mesh needs complete triangle rows")
        count += len(rows)
        if count > MAX_TRIANGLES:
            raise ValueError("Surface-review shared triangle budget exceeded; no faces omitted")
    if value["sha256"] != hashlib.sha256(encoded({k: v for k, v in value.items() if k != "sha256"})).hexdigest():
        raise ValueError("Prepared surface geometry integrity mismatch")
    restored = [SurfaceMesh.create(rows, cancelled=cancelled, index_method=index_method) for rows in pool]
    result, used = {}, set()
    for tool, record in body.records.items():
        names = tools[str(tool)]
        if not isinstance(names, dict) or len(names) > MAX_MESHES:
            raise ValueError("Surface-review body bindings exceed bounded contract")
        machine = machine_from_record(record)
        bodies, _ = bodies_from_record(record, machine)
        by_name = {b.name: b for b in bodies}
        zero = {joint.name: 0.0 for joint in machine.tool_chain + machine.work_chain}
        meshes = {}
        for name, index in names.items():
            if name not in by_name or type(index) is not int or not 0 <= index < len(restored):
                raise ValueError("Surface mesh has unknown body or invalid pool reference")
            body_transform_zero = body_transform(machine, by_name[name], zero)
            bounds = by_name[name].bounds
            corners = [
                body_transform_zero.apply(Vec3(x, y, z)).tuple
                for x in (bounds.minimum.x, bounds.maximum.x)
                for y in (bounds.minimum.y, bounds.maximum.y)
                for z in (bounds.minimum.z, bounds.maximum.z)
            ]
            lo = tuple(min(p[a] for p in corners) for a in range(3))
            hi = tuple(max(p[a] for p in corners) for a in range(3))
            mesh = restored[index]
            for i, triangle in enumerate(mesh.triangles):
                if i % 64 == 0 and cancelled():
                    raise InterruptedError("Surface-review geometry binding cancelled")
                if any(not lo[a] - 1e-6 <= p[a] <= hi[a] + 1e-6 for p in triangle for a in range(3)):
                    raise ValueError("Prepared surface lies outside its declared body envelope")
            meshes[name] = mesh
            used.add(index)
        result[tool] = MappingProxyType(meshes)
    if used != set(range(len(pool))):
        raise ValueError("Surface review has unused mesh declarations")
    return MappingProxyType(result)


def restore_rotating(
    value: Any, body: ProgramBodyClearance, cancelled: Callable[[], bool], *, shaped: bool = False
) -> Mapping[int, Mapping[str, tuple[AxialEnvelope, ...]]]:
    if not isinstance(value, dict) or set(value) != {str(tool) for tool in body.records}:
        raise ValueError("Rotating review needs complete program-tool declarations")
    result = {}
    for tool, rows in value.items():
        if not isinstance(rows, dict) or len(rows) > 3:
            raise ValueError("Rotating review needs bounded cutter/shank/holder declarations")
        sections = {}
        for name, values in rows.items():
            if not isinstance(values, list) or not 1 <= len(values) <= 257:
                raise ValueError("Rotating review exceeds complete section budget")
            retained = []
            for row in values:
                if cancelled():
                    raise InterruptedError("Rotating declarations cancelled")
                base_fields = {"component", "low_mm", "high_mm", "radius_mm", "source"}
                shape_fields = base_fields | {"primitive", "low_radius_mm", "center_mm"}
                if not isinstance(row, dict) or (set(row) != base_fields and (not shaped or set(row) != shape_fields)):
                    raise ValueError("Rotating section requires complete declared dimensions and source")
                if any(type(row[k]) not in (float, int) for k in ("low_mm", "high_mm", "radius_mm")):
                    raise ValueError("Rotating section dimensions must be finite numbers")
                retained.append(RotatingShape(**row) if "primitive" in row else AxialEnvelope(**row))
            sections[name] = tuple(retained)
        result[int(tool)] = MappingProxyType(sections)
    validate_rotating_envelopes(body.records, result)
    return MappingProxyType(result)


@dataclass(frozen=True)
class ProgramSurfaceArchive:
    source: ProgramClearanceSource
    work_offsets: Mapping[str, tuple[float, float, float]]
    report: ProgramSurfaceClearance
    sha256: str


def replay(payload: dict[str, Any], *, cancelled: Callable[[], bool]) -> ProgramSurfaceArchive:
    method = payload.get("method")
    if not isinstance(method, str) or method not in INDEX_METHODS:
        raise ValueError("Unsupported surface-review method")
    body_payload = payload["body"]
    if (
        not isinstance(body_payload, dict)
        or set(body_payload) != BODY_FIELDS
        or type(body_payload["schema"]) is not int
        or body_payload["schema"] != 1
        or body_payload["kind"] != "program_machine_clearance"
    ):
        raise ValueError("Unsupported nested program body review")
    from carveracontroller.machine.program_clearance_archive import LEGACY_METHOD
    from carveracontroller.machine.program_clearance_archive import METHOD as BODY_METHOD

    if body_payload["method"] not in (LEGACY_METHOD, BODY_METHOD):
        raise ValueError("Unsupported nested program body method")
    body = recompute_program_review(body_payload, cancelled=cancelled)
    ordered_stock = method in (STOCK_METHOD, STOCK_GROUP_METHOD)
    if ("stock" in payload) != ordered_stock:
        raise ValueError("Ordered stock declarations differ from the retained method")
    shaped = ordered_stock or method in (SHAPED_METHOD, SHAPED_GROUP_METHOD)
    has_rotating = shaped or method in (ROTATING_METHOD, ROTATING_GROUP_METHOD)
    if not isinstance(payload["geometry"], dict) or ("rotating" in payload["geometry"]) != has_rotating:
        raise ValueError("Rotating declarations differ from the retained review method")
    meshes = restore_meshes(payload["geometry"], body.report, cancelled=cancelled, index_method=INDEX_METHODS[method])
    envelopes = (
        restore_rotating(payload["geometry"]["rotating"], body.report, cancelled, shaped=shaped)
        if has_rotating
        else None
    )
    if (
        shaped
        and not ordered_stock
        and not any(
            isinstance(s, RotatingShape)
            for rows in (envelopes or {}).values()
            for sections in rows.values()
            for s in sections
        )
    ):
        raise ValueError("Shaped method requires a complete shaped cutting declaration")
    result = refine_program_surfaces(
        body.report,
        meshes,
        budget=SurfaceBudget(cancelled=cancelled),
        grouped=method
        in (GROUP_METHOD, DIRECTION_GROUP_METHOD, ROTATING_GROUP_METHOD, SHAPED_GROUP_METHOD, STOCK_GROUP_METHOD),
        rotating_envelopes=envelopes,
    )
    if ordered_stock:
        from dataclasses import replace

        result = replace(
            result,
            stock_evolution=review_stock_evolution(
                body.report,
                restore_inputs(payload["stock"]),
                envelopes or {},
                cancelled=cancelled,
            ),
        )
    if encoded(surface_report_record(result, cancelled=cancelled)) != encoded(payload["report"]):
        raise ValueError("Saved surface/solid evidence differs from reparsed source and recomputed geometry")
    if cancelled():
        raise InterruptedError("Surface-review loading cancelled; previous review retained")
    return ProgramSurfaceArchive(body.source, body.work_offsets, result, "")


def save_surface_review(
    path: str | Path,
    source: ProgramClearanceSource,
    work_offsets: Mapping[str, tuple[float, float, float]],
    report: ProgramSurfaceClearance,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> str:
    indices = {mesh.index_method for rows in report.meshes.values() for mesh in rows.values()}
    if len(indices) != 1 or next(iter(indices)) not in INDEX_METHODS.values():
        raise ValueError("Surface review needs one supported index method for unambiguous accounting")
    if report.contact_mode == "groups":
        if indices == {"median-v1"}:
            raise ValueError("Grouped surface review requires a supported surface-area index method")
        method = GROUP_METHOD if indices == {"surface-area-v2"} else DIRECTION_GROUP_METHOD
    elif report.contact_mode == "triangles":
        method = {"median-v1": LEGACY_METHOD, "surface-area-v2": METHOD, "surface-directions-v3": DIRECTION_METHOD}[
            next(iter(indices))
        ]
    else:
        raise ValueError("Unsupported surface contact representation")
    if report.rotating_envelopes:
        if indices != {"surface-directions-v3"}:
            raise ValueError("Rotating review requires the declared directional surface method")
        shaped = any(
            isinstance(s, RotatingShape)
            for rows in report.rotating_envelopes.values()
            for sections in rows.values()
            for s in sections
        )
        method = (
            (SHAPED_GROUP_METHOD if report.contact_mode == "groups" else SHAPED_METHOD)
            if shaped
            else (ROTATING_GROUP_METHOD if report.contact_mode == "groups" else ROTATING_METHOD)
        )
    if report.stock_evolution is not None:
        if not report.rotating_envelopes or indices != {"surface-directions-v3"}:
            raise ValueError("Ordered stock needs complete directional rotating surface declarations")
        method = STOCK_GROUP_METHOD if report.contact_mode == "groups" else STOCK_METHOD
    body_payload = program_review_payload(source, work_offsets, report.body_review, cancelled=cancelled)
    body_payload["work_offsets"] = {name: vector(value) for name, value in work_offsets.items()}
    payload = {
        "schema": 1,
        "kind": "program_surface_clearance",
        "method": method,
        "body": body_payload,
        "geometry": mesh_record(report, cancelled=cancelled),
        "report": surface_report_record(report, cancelled=cancelled),
    }
    if report.stock_evolution is not None:
        payload["stock"] = input_record(report.stock_evolution.inputs)
    # Verify complete bounded readability BEFORE allocating solver indices.
    if len(encoded(payload)) > MAX_REVIEW_BYTES - 100:
        raise ValueError("Surface review exceeds64 MiB")
    replay(payload, cancelled=cancelled)
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    raw = encoded(payload) + b"\n"
    if len(raw) > MAX_REVIEW_BYTES:
        raise ValueError("Surface review exceeds64 MiB")
    return retain_geometry_bytes(path, raw, cancelled=cancelled)


def load_surface_review(path: str | Path, *, cancelled: Callable[[], bool] = lambda: False) -> ProgramSurfaceArchive:
    if cancelled():
        raise InterruptedError("Surface-review loading cancelled")
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_REVIEW_BYTES + 1)
    if len(raw) > MAX_REVIEW_BYTES:
        raise ValueError("Surface review exceeds64 MiB")

    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        if cancelled():
            raise InterruptedError("Surface-review loading cancelled")
        result = {}
        for key, val in pairs:
            if key in result:
                raise ValueError("Duplicate surface-review JSON field")
            result[key] = val
        return result

    def integer(text: str) -> int:
        if len(text) > 20:
            raise ValueError("Surface-review JSON integer exceeds20 characters")
        return int(text)

    def constant(text: str) -> None:
        raise ValueError("Nonfinite surface-review JSON number: " + text)

    try:
        payload = json.loads(raw, object_pairs_hook=unique, parse_int=integer, parse_constant=constant)
        if (
            not isinstance(payload, dict)
            or set(payload)
            not in (
                {"schema", "kind", "method", "body", "geometry", "report", "sha256"},
                {"schema", "kind", "method", "body", "geometry", "report", "sha256", "stock"},
            )
            or type(payload["schema"]) is not int
            or payload["schema"] != 1
            or payload["kind"] != "program_surface_clearance"
            or payload["method"] not in INDEX_METHODS
        ):
            raise ValueError("Unsupported surface-review schema or method")
        digest = payload.pop("sha256")
        if digest != hashlib.sha256(encoded(payload)).hexdigest():
            raise ValueError("Surface-review integrity mismatch")
        result = replay(payload, cancelled=cancelled)
    except (
        UnicodeError,
        json.JSONDecodeError,
        RecursionError,
        OverflowError,
        TypeError,
        KeyError,
        AttributeError,
    ) as exc:
        raise ValueError("Expected bounded UTF-8 surface review") from exc
    return ProgramSurfaceArchive(result.source, result.work_offsets, result.report, hashlib.sha256(raw).hexdigest())
