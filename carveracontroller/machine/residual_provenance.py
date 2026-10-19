"""Portable residual dependencies; archive integrity is not physical qualification."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from carveracontroller.machine.geometry_changes import GeometryContext, digest_context
from carveracontroller.machine.program_bytes import preview_digest

if TYPE_CHECKING:
    from carveracontroller.addons.machine_simulation.model import Geometry
    from carveracontroller.addons.manufacturing_simulation import StockVolume

MAX_CONTEXT_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class RetainedResidual:
    stock: StockVolume
    context: dict[str, Any] | None
    geometry: Geometry | None = None


def portable_context(context: GeometryContext) -> dict[str, Any]:
    """Replace only verified asset locations, retaining every semantic declaration."""
    paths: dict[str, str] = {}

    def collect(value: object) -> None:
        if isinstance(value, dict):
            if "loaded_sha256" in value and "path" in value:
                path, loaded, current = value["path"], value["loaded_sha256"], value.get("current_sha256")
                if value.get("error") or not isinstance(loaded, str) or len(loaded) != 64 or loaded != current:
                    raise ValueError("Residual context has unverified CAD bytes")
                if not isinstance(path, str) or not path:
                    raise ValueError("Residual context has no CAD location")
                if path in paths and paths[path] != loaded:
                    raise ValueError("Residual context CAD references disagree")
                paths[path] = loaded
            for child in value.values():
                collect(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                collect(child)

    collect(context)

    def replace(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: replace(child) for key, child in value.items()}
        if isinstance(value, (tuple, list)):
            return [replace(child) for child in value]
        if isinstance(value, str) and value in paths:
            return "sha256:" + paths[value]
        return value

    return {key: replace(value) for key, value in context.items()}


def encode_provenance(context: GeometryContext, program: bytes, grid: bytes) -> bytes:
    normalized = preview_digest(program)
    detached = portable_context(context)
    if detached.get("schema") != 2 or not isinstance(detached.get("interpretation"), dict):
        raise ValueError("Residual stock requires retained program interpretation")
    if detached.get("program") not in (normalized, hashlib.sha256(program).hexdigest()):
        raise ValueError("Residual context program differs from archive")
    # Universal newline decoding is the desktop parser's source identity.
    detached["program"] = normalized
    result = json.dumps(
        {"schema": 1, "context": detached, "grid_sha256": hashlib.sha256(grid).hexdigest()},
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    if len(result) > MAX_CONTEXT_BYTES:
        raise ValueError("Residual context exceeds 2 MB budget")
    return result


def decode_provenance(payload: bytes, program: bytes, grid: bytes) -> dict[str, Any]:
    if len(payload) > MAX_CONTEXT_BYTES:
        raise ValueError("Residual context exceeds 2 MB budget")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate residual context key")
            result[key] = value
        return result

    try:
        record = json.loads(payload, object_pairs_hook=pairs)
        if not isinstance(record, dict) or type(record.get("schema")) is not int or record["schema"] != 1:
            raise ValueError("Unsupported residual provenance schema")
        context = record["context"]
        if (
            record.get("grid_sha256") != hashlib.sha256(grid).hexdigest()
            or not isinstance(context, dict)
            or context.get("schema") != 2
            or not isinstance(context.get("interpretation"), dict)
            or context.get("program") != preview_digest(program)
        ):
            raise ValueError("Residual provenance does not match grid, program or interpretation")
        digest_context(context)  # Reject NaN/Infinity before any UI publication.
        return context
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("Invalid residual provenance") from exc


def match_provenance(retained: dict[str, Any] | None, current: GeometryContext) -> None:
    if retained is None:
        raise ValueError("Retained grid has no interpretation provenance; recompute simulation before continuing")
    if digest_context(retained) != digest_context(portable_context(current)):
        raise ValueError("Retained grid interpretation, tooling or setup differs; recompute simulation")
