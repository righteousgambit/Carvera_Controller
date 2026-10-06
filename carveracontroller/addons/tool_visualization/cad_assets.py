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
from pathlib import Path
from typing import Literal, TypedDict, cast

from carveracontroller.addons.cad_identity import read_asset_bytes

MAX_BYTES = 24 * 1024 * 1024
MAX_VERTICES = 65535  # Kivy Mesh indices are unsigned 16-bit.


class ToolAsset(TypedDict):
    schema: Literal["carvera-tool-mesh-v1"]
    units: Literal["mm"]
    axis: Literal["+Z"]
    origin: Literal["tip", "collet"]
    triangles: list[float]
    _converted_sha256: str


def load_tool_asset(path: str | Path, expected_sha256: str | None = None) -> ToolAsset:
    source = Path(path).expanduser()
    encoded = read_asset_bytes(source, MAX_BYTES)
    digest = hashlib.sha256(encoded).hexdigest()
    if expected_sha256 and expected_sha256 != digest:
        raise ValueError("CAD bytes changed; reload the tool preview before using this geometry")
    if source.suffix == ".gz":
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as stream:
            raw = stream.read(MAX_BYTES + 1)
    else:
        raw = encoded
    if len(raw) > MAX_BYTES:
        raise ValueError("Expanded tool asset exceeds size limit")
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get("schema") != "carvera-tool-mesh-v1":
        raise ValueError("Unsupported tool asset schema")
    if data.get("units") != "mm" or data.get("axis") != "+Z" or data.get("origin") not in ("tip", "collet"):
        raise ValueError("Tool asset needs explicit mm units, +Z axis and tip/collet origin")
    points = data.get("triangles")
    if not isinstance(points, list) or not points or len(points) % 9 or len(points) // 3 > MAX_VERTICES:
        raise ValueError("Tool triangles exceed index limit or are incomplete")
    if any(
        isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or abs(v) > 10000 for v in points
    ):
        raise ValueError("Tool mesh contains invalid coordinates")
    if data["origin"] == "tip" and min(points[2::3]) < -0.01:
        raise ValueError("Tip mesh extends below its registered tip")
    data["_converted_sha256"] = digest
    # The checks above establish the required data-only schema; optional vendor
    # metadata remains in the returned mapping without becoming trusted geometry.
    return cast(ToolAsset, data)


def asset_mesh(path, scale, unit_scale=1.0, z_offset=0.0, origin="tip", clip_height=None, expected_sha256=None):
    """Return viewer's twelve-float vertex format without visibility enlargement.

    Clipping retains triangles below the collet plane and clips crossing faces;
    overall cutter length is never treated as installed stickout.
    """
    from .mesh_builder import VERTEX_FORMAT

    if not math.isfinite(scale) or scale <= 0 or not math.isfinite(unit_scale) or unit_scale <= 0:
        raise ValueError("Tool mesh scale must be positive")
    data = load_tool_asset(path, expected_sha256)
    if data["origin"] != origin:
        raise ValueError(f"Expected {origin} asset origin")
    color = (0.75, 0.77, 0.80, 1.0) if origin == "collet" else (0.85, 0.65, 0.15, 1.0)
    vertices = []
    points = data["triangles"]
    for offset in range(0, len(points), 9):
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
    count = len(vertices) // 12
    if not count or count > MAX_VERTICES:
        raise ValueError("Visible tool mesh empty or exceeds index limit")
    return vertices, list(range(count)), VERTEX_FORMAT


def build_asset_tool_mesh(tool, scale):
    unit_scale = tool.geometry_unit_scale
    cutter = asset_mesh(
        tool.geometry_path, scale, unit_scale, clip_height=tool.stickout, expected_sha256=tool.geometry_sha256
    )
    return attach_holder_mesh(cutter, tool, scale)


def attach_holder_mesh(cutter, tool, scale):
    """Attach a CAD holder to either a CAD or dimension-based cutter."""
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
    )
    vertices = cutter[0] + holder[0]
    count = len(vertices) // 12
    if count > MAX_VERTICES:
        raise ValueError("Combined cutter/holder exceeds index limit")
    return vertices, list(range(count)), cutter[2]


def asset_summary(path):
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
