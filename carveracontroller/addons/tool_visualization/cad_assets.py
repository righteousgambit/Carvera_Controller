"""Bounded, data-only tool meshes. Asset coordinates are millimetres, tip at zero.

CAD conversion is offline. Loading never imports CAD libraries or executes code.
The asset is a visual envelope, not collision or stock-removal qualification.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypedDict, cast

from carveracontroller.addons.cad_identity import read_asset_bytes

if TYPE_CHECKING:
    from .mesh_builder import ToolMesh
    from .tool_definition import ToolDefinition

MAX_BYTES = 24 * 1024 * 1024
MAX_VERTICES = 65535  # Kivy Mesh indices are unsigned 16-bit.


class ToolAsset(TypedDict):
    schema: Literal["carvera-tool-mesh-v1"]
    units: Literal["mm"]
    axis: Literal["+Z"]
    origin: Literal["tip", "collet"]
    triangles: list[float]
    _converted_sha256: str


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise InterruptedError("Tool mesh preparation cancelled")


def load_tool_asset(
    path: str | Path, expected_sha256: str | None = None, *, cancelled: Callable[[], bool] | None = None
) -> ToolAsset:
    source = Path(path).expanduser()
    encoded = read_asset_bytes(source, MAX_BYTES, cancelled=cancelled)
    _check_cancelled(cancelled)
    digest = hashlib.sha256(encoded).hexdigest()
    if expected_sha256 and expected_sha256 != digest:
        raise ValueError("CAD bytes changed; reload the tool preview before using this geometry")
    if source.suffix == ".gz":
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
            chunks, count = [], 0
            while True:
                _check_cancelled(cancelled)
                chunk = stream.read(min(65536, MAX_BYTES + 1 - count))
                count += len(chunk)
                if count > MAX_BYTES:
                    raise ValueError("Expanded tool asset exceeds size limit")
                if not chunk:
                    break
                chunks.append(chunk)
            raw = b"".join(chunks)
    else:
        raw = encoded
    if len(raw) > MAX_BYTES:
        raise ValueError("Expanded tool asset exceeds size limit")
    _check_cancelled(cancelled)
    data = json.loads(raw)
    _check_cancelled(cancelled)
    if not isinstance(data, dict) or data.get("schema") != "carvera-tool-mesh-v1":
        raise ValueError("Unsupported tool asset schema")
    if data.get("units") != "mm" or data.get("axis") != "+Z" or data.get("origin") not in ("tip", "collet"):
        raise ValueError("Tool asset needs explicit mm units, +Z axis and tip/collet origin")
    points = data.get("triangles")
    if not isinstance(points, list) or not points or len(points) % 9 or len(points) // 3 > MAX_VERTICES:
        raise ValueError("Tool triangles exceed index limit or are incomplete")
    minimum_z = math.inf
    for index, value in enumerate(points):
        if index % 128 == 0:
            _check_cancelled(cancelled)
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or abs(value) > 10000
        ):
            raise ValueError("Tool mesh contains invalid coordinates")
        if index % 3 == 2:
            minimum_z = min(minimum_z, value)
    _check_cancelled(cancelled)
    if data["origin"] == "tip" and minimum_z < -0.01:
        raise ValueError("Tip mesh extends below its registered tip")
    data["_converted_sha256"] = digest
    # The checks above establish the required data-only schema; optional vendor
    # metadata remains in the returned mapping without becoming trusted geometry.
    return cast(ToolAsset, data)


def asset_mesh(
    path: str | Path,
    scale: float,
    unit_scale: float = 1.0,
    z_offset: float = 0.0,
    origin: Literal["tip", "collet"] = "tip",
    clip_height: float | None = None,
    expected_sha256: str | None = None,
    *,
    cancelled: Callable[[], bool] | None = None,
) -> ToolMesh:
    """Return viewer's twelve-float vertex format without visibility enlargement.

    Clipping retains triangles below the collet plane and clips crossing faces;
    overall cutter length is never treated as installed stickout.
    """
    from .mesh_builder import VERTEX_FORMAT

    if not math.isfinite(scale) or scale <= 0 or not math.isfinite(unit_scale) or unit_scale <= 0:
        raise ValueError("Tool mesh scale must be positive")
    data = load_tool_asset(path, expected_sha256, cancelled=cancelled)
    if data["origin"] != origin:
        raise ValueError(f"Expected {origin} asset origin")
    color = (0.75, 0.77, 0.80, 1.0) if origin == "collet" else (0.85, 0.65, 0.15, 1.0)
    vertices = []
    points = data["triangles"]
    for offset in range(0, len(points), 9):
        if offset % (9 * 128) == 0:
            _check_cancelled(cancelled)
        polygon = [points[offset + i : offset + i + 3] for i in (0, 3, 6)]
        if clip_height is not None:
            limit = clip_height / unit_scale
            clipped = []
            for p, q in zip(polygon, polygon[1:] + polygon[:1]):
                if p[2] <= limit:
                    clipped.append(p)
                if (p[2] <= limit) != (q[2] <= limit):
                    t = (limit - p[2]) / (q[2] - p[2])
                    clipped.append([p[i] + t * (q[i] - p[i]) for i in range(3)])
            polygon = clipped
        for i in range(1, len(polygon) - 1):
            tri = [polygon[0], polygon[i], polygon[i + 1]]
            a = [tri[1][j] - tri[0][j] for j in range(3)]
            b = [tri[2][j] - tri[0][j] for j in range(3)]
            normal = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
            magnitude = math.sqrt(sum(n * n for n in normal))
            if magnitude < 1e-12:
                continue
            for p in tri:
                vertices.extend(
                    (
                        p[0] * unit_scale * scale,
                        p[1] * unit_scale * scale,
                        (p[2] * unit_scale + z_offset) * scale,
                        *(n / magnitude for n in normal),
                        *color,
                        0.0,
                        0.0,
                    )
                )
    _check_cancelled(cancelled)
    count = len(vertices) // 12
    if not count or count > MAX_VERTICES:
        raise ValueError("Visible tool mesh empty or exceeds index limit")
    return vertices, list(range(count)), VERTEX_FORMAT


def build_asset_tool_mesh(
    tool: ToolDefinition, scale: float, *, cancelled: Callable[[], bool] | None = None
) -> ToolMesh:
    unit_scale = tool.geometry_unit_scale
    cutter = asset_mesh(
        tool.geometry_path,
        scale,
        unit_scale,
        clip_height=tool.stickout,
        expected_sha256=tool.geometry_sha256,
        cancelled=cancelled,
    )
    return attach_holder_mesh(cutter, tool, scale, cancelled=cancelled)


def attach_holder_mesh(
    cutter: ToolMesh, tool: ToolDefinition, scale: float, *, cancelled: Callable[[], bool] | None = None
) -> ToolMesh:
    """Attach a CAD holder to either a CAD or dimension-based cutter."""
    _check_cancelled(cancelled)
    if not tool.holder_geometry_path:
        return cutter
    unit_scale = tool.geometry_unit_scale
    if tool.stickout is None or not math.isfinite(tool.stickout) or tool.stickout <= 0:
        raise ValueError("Holder geometry requires a measured positive stickout")
    holder = asset_mesh(
        tool.holder_geometry_path,
        scale,
        unit_scale,
        z_offset=tool.stickout,
        origin="collet",
        expected_sha256=tool.holder_geometry_sha256,
        cancelled=cancelled,
    )
    _check_cancelled(cancelled)
    vertices = cutter[0] + holder[0]
    _check_cancelled(cancelled)
    count = len(vertices) // 12
    if count > MAX_VERTICES:
        raise ValueError("Combined cutter/holder exceeds index limit")
    return vertices, list(range(count)), cutter[2]


def asset_summary(path: str | Path) -> dict[str, object]:
    """Readback for library UI: bounds, provenance and exact converted bytes."""
    data = load_tool_asset(path)
    p = data["triangles"]
    return {
        "vertices": len(p) // 3,
        "triangles": len(p) // 9,
        "bounds_mm": [[min(p[i::3]) for i in range(3)], [max(p[i::3]) for i in range(3)]],
        "origin": data["origin"],
        "source": data.get("source", {}),
        "sha256": data["_converted_sha256"],
    }


validate_asset = load_tool_asset
load_asset = load_tool_asset
