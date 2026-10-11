"""Content-bound conservative rotating envelopes from registered assembly CAD.

Triangle surfaces are clipped into bounded axial bands. The maximum radius of
each clipped polygon encloses its rotation at every spindle angle. This loses
holes, concavities and fixed-angle details; it is not exact mesh collision.
"""

from __future__ import annotations

from math import hypot, isfinite
from pathlib import Path
from typing import Literal

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.tool_visualization.cad_assets import load_tool_asset
from carveracontroller.addons.tool_visualization.mesh_builder import tool_profile
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition

Point3 = tuple[float, float, float]


def _clip(polygon: list[Point3], height: float, above: bool) -> list[Point3]:
    result: list[Point3] = []
    for p, q in zip(polygon, polygon[1:] + polygon[:1]):
        inside_p = p[2] >= height if above else p[2] <= height
        inside_q = q[2] >= height if above else q[2] <= height
        if inside_p:
            result.append(p)
        if inside_p != inside_q:
            t = (height - p[2]) / (q[2] - p[2])
            result.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]), height))
    return result


def cad_envelopes(
    path: str | Path,
    digest: str,
    component: Literal["shank", "holder"],
    *,
    unit_scale: float = 1.0,
    offset: float = 0.0,
    low: float = 0.0,
    high: float | None = None,
    bands: int = 64,
) -> tuple[AxialEnvelope, ...]:
    if not digest:
        raise ValueError("Reload assembly CAD to establish its exact byte identity")
    if not isfinite(unit_scale) or unit_scale <= 0:
        raise ValueError("CAD unit scale must be finite and positive")
    if component not in ("shank", "holder"):
        raise ValueError("Assembly envelope component must be shank or holder")
    if not isfinite(offset) or not isfinite(low) or (high is not None and not isfinite(high)):
        raise ValueError("Assembly registration and clipping heights must be finite")
    if not isinstance(bands, int) or isinstance(bands, bool) or not 1 <= bands <= 128:
        raise ValueError("Assembly envelope needs a bounded axial band count")
    data = load_tool_asset(path, expected_sha256=digest)
    origin = "collet" if component == "holder" else "tip"
    if data["origin"] != origin:
        raise ValueError(f"{component} CAD must use {origin} origin")
    raw = data["triangles"]
    minimum = min(raw[2::3]) * unit_scale + offset
    maximum = max(raw[2::3]) * unit_scale + offset
    if component == "holder" and minimum < 0:
        raise ValueError("Holder registration extends below the cutter tip; correct stickout or CAD origin")
    low = max(low, minimum, 0)
    high = min(high, maximum) if high is not None else maximum
    if high <= low:
        raise ValueError(f"{component} CAD contains no exposed axial span")
    width = (high - low) / bands
    radii = [0.0] * bands
    for i in range(0, len(raw), 9):
        triangle = [
            (raw[i + j] * unit_scale, raw[i + j + 1] * unit_scale, raw[i + j + 2] * unit_scale + offset)
            for j in (0, 3, 6)
        ]
        zmin, zmax = min(p[2] for p in triangle), max(p[2] for p in triangle)
        if zmax < low or zmin > high:
            continue
        first = max(0, min(bands - 1, int((zmin - low) / width)))
        last = max(0, min(bands - 1, int((zmax - low) / width)))
        for band in range(first, last + 1):
            clipped = _clip(_clip(triangle, low + band * width, True), low + (band + 1) * width, False)
            radii[band] = max(radii[band], max((hypot(p[0], p[1]) for p in clipped), default=0))
    source = f"CAD SHA256 {digest} · rotating envelope · axial bands ≤ {width:g} mm"
    sections = tuple(
        AxialEnvelope(component, low + i * width, low + (i + 1) * width, radius, source)
        for i, radius in enumerate(radii)
        if radius > 0
    )
    if not sections:
        raise ValueError(f"{component} CAD has no nonzero radial surface")
    return sections


def assembly_envelopes(
    definition: ToolDefinition, flute_length: float
) -> tuple[tuple[AxialEnvelope, ...], tuple[str, ...]]:
    stickout = definition.stickout
    if stickout is None or not isfinite(stickout) or stickout <= 0:
        raise ValueError("Assembly envelope needs a finite positive exposed stickout")
    if not isfinite(flute_length) or not 0 < flute_length <= stickout:
        raise ValueError("Assembly cutting length must be positive and within exposed stickout")
    sections: list[AxialEnvelope] = []
    notes: list[str] = []
    if definition.geometry_path and stickout > flute_length:
        sections.extend(
            cad_envelopes(
                definition.geometry_path,
                definition.geometry_sha256,
                "shank",
                unit_scale=definition.geometry_unit_scale,
                low=flute_length,
                high=stickout,
            )
        )
        notes.append("Non-cutting cutter body: content-bound CAD rotating envelope")
    elif stickout > flute_length:
        for name in ("diameter", "shank_diameter"):
            value = getattr(definition, name)
            if value is None or isinstance(value, bool) or not isfinite(value) or value <= 0:
                raise ValueError(f"Non-cutting procedural envelope needs a declared finite positive {name}")
        profile = tool_profile(definition, length=stickout)
        for (z0, r0), (z1, r1) in zip(profile, profile[1:]):
            lower, upper = max(flute_length, z0), min(stickout, z1)
            if upper <= lower:
                continue
            ra = r0 + (r1 - r0) * (lower - z0) / (z1 - z0)
            rb = r0 + (r1 - r0) * (upper - z0) / (z1 - z0)
            sections.append(
                AxialEnvelope(
                    "shank",
                    lower,
                    upper,
                    max(ra, rb),
                    "Declared procedural shoulder/shank envelope; transition detail conservative",
                )
            )
        notes.append("Non-cutting cutter body: declared procedural shoulder/shank envelope")
    if definition.holder_geometry_path:
        sections.extend(
            cad_envelopes(
                definition.holder_geometry_path,
                definition.holder_geometry_sha256,
                "holder",
                unit_scale=definition.geometry_unit_scale,
                offset=stickout,
            )
        )
        notes.append("Holder: content-bound CAD registered at the declared collet face")
    else:
        notes.append("Holder geometry missing: holder clearance is unknown")
    notes.append(
        "Obstacle boxes and rotating axial bands can overestimate contact; complete machine clearance remains unknown"
    )
    return tuple(sections), tuple(notes)
