"""Plane/triangle intersections of rendered CAD; no transport or solid inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from math import isfinite


class SectionCancelled(ValueError):
    pass


@dataclass(frozen=True)
class SectionResult:
    axis: int
    coordinate_mm: float
    segments: tuple
    triangle_count: int
    tolerance_mm: float
    _bounds: tuple | None = field(init=False, repr=False)

    def __post_init__(self):
        if type(self.axis) is not int or self.axis not in range(3) or not isfinite(self.coordinate_mm):
            raise ValueError("Invalid captured section plane")
        segments = tuple(tuple(tuple(point) for point in segment) for segment in self.segments)
        if any(
            len(segment) != 2 or any(len(point) != 3 or not all(isfinite(v) for v in point) for point in segment)
            for segment in segments
        ):
            raise ValueError("Invalid captured section contour")
        object.__setattr__(self, "segments", segments)
        # Calculated on the section worker, reused for redraw/layout/export.
        # Selection results are deeply immutable, so these bounds cannot drift.
        bounds = (
            tuple(
                (
                    min(point[i] for segment in segments for point in segment),
                    max(point[i] for segment in segments for point in segment),
                )
                for i in self.axes
            )
            if segments
            else None
        )
        object.__setattr__(self, "_bounds", bounds)

    @property
    def axes(self):
        return tuple(i for i in range(3) if i != self.axis)

    @property
    def bounds(self):
        return self._bounds


def section_svg(result, title):
    """A millimetre-scale vector drawing of the captured open contour segments."""
    if (
        not isinstance(result, SectionResult)
        or type(result.axis) is not int
        or result.axis not in range(3)
        or not isfinite(result.coordinate_mm)
        or not result.segments
    ):
        raise ValueError("Calculate a nonempty section before exporting its drawing")
    for segment in result.segments:
        if len(segment) != 2 or any(len(point) != 3 or not all(isfinite(v) for v in point) for point in segment):
            raise ValueError("Invalid section contour")
    (u0, u1), (v0, v1) = result.bounds
    u, v = result.axes
    su, sv = u1 - u0, v1 - v0
    width, height = max(su + 24, 140), max(sv + 48, 75)
    left, top = (width - su) / 2, 24
    path = " ".join(
        f"M {a[u] - u0 + left:.9g},{v1 - a[v] + top:.9g} L {b[u] - u0 + left:.9g},{v1 - b[v] + top:.9g}"
        for a, b in result.segments
    )
    plane = f"{'XYZ'[result.axis]} = {result.coordinate_mm:g} mm"
    description = (
        f"{plane}; horizontal {'XYZ'[u]}, vertical {'XYZ'[v]}; "
        f"{result.triangle_count:,} CAD triangles; {len(result.segments):,} contour segments. "
        "Nominal CAD frame before live joint transforms. Open meshes remain open; physical placement unverified."
    )
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{width:.9g}mm" height="{height:.9g}mm" viewBox="0 0 {width:.9g} {height:.9g}">
  <title>{escape(str(title))} — {escape(plane)}</title>
  <desc>{escape(description)}</desc>
  <rect width="100%" height="100%" fill="white"/>
  <g fill="#17252d" font-family="sans-serif" font-size="3">
    <text x="6" y="7">{escape(str(title))}</text>
    <text x="6" y="13">{escape(plane)} · axes {"XYZ"[u]} / {"XYZ"[v]} · units mm</text>
    <text x="6" y="19">Nominal CAD; physical placement unverified</text>
  </g>
  <path id="section-contours" d="{path}" fill="none" stroke="#164e48" stroke-width="0.15"/>
  <g fill="#17252d" font-family="sans-serif" font-size="3">
    <text x="6" y="{top + sv + 8:.9g}">{"XYZ"[u]}: {u0:.6g} to {u1:.6g} mm · span {su:.6g} mm</text>
    <text x="6" y="{top + sv + 14:.9g}">{"XYZ"[v]}: {v0:.6g} to {v1:.6g} mm · span {sv:.6g} mm</text>
    <text x="6" y="{top + sv + 20:.9g}">Open contours; no solid area or clearance inferred</text>
  </g>
</svg>
'''


def section_geometry(
    geometries,
    axis,
    coordinate_mm,
    *,
    cancelled=lambda: False,
    progress=lambda n: None,
    tolerance_mm=1e-6,
    max_segments=200000,
):
    """Return actual triangle intersections, including coplanar surface boundaries.

    Coplanar triangulation diagonals cancel within each geometry. Other shared
    edges deduplicate. Open/nonmanifold meshes remain line segments; no area,
    solid closure, physical placement or clearance claim is made.
    """
    if type(axis) is not int or axis not in range(3) or not isfinite(coordinate_mm):
        raise ValueError("Choose X, Y or Z and a finite plane coordinate")
    if not isfinite(tolerance_mm) or tolerance_mm <= 0 or type(max_segments) is not int or max_segments < 1:
        raise ValueError("Section tolerance and segment budget must be positive")
    result, total = {}, 0

    def point_key(p):
        return tuple(round(v / tolerance_mm) for v in p)

    def edge_key(a, b):
        return tuple(sorted((point_key(a), point_key(b))))

    for geometry in geometries:
        vertices, indices = geometry.vertices, geometry.indices
        if len(vertices) % 10 or len(indices) % 3:
            raise ValueError("Section requires indexed triangle geometry")
        coplanar, regular = {}, {}
        for offset in range(0, len(indices), 3):
            if total % 1024 == 0:
                if cancelled():
                    raise SectionCancelled("Section calculation cancelled")
                progress(total)
            total += 1
            points = []
            for index in indices[offset : offset + 3]:
                if type(index) is not int or not 0 <= index < len(vertices) // 10:
                    raise ValueError("Invalid section triangle index")
                p = tuple(vertices[10 * index : 10 * index + 3])
                if not all(isfinite(v) for v in p):
                    raise ValueError("Nonfinite section geometry")
                points.append(p)
            distances = [p[axis] - coordinate_mm for p in points]
            if min(distances) > tolerance_mm or max(distances) < -tolerance_mm:
                continue
            if all(abs(d) <= tolerance_mm for d in distances):
                for i in range(3):
                    a, b = points[i], points[(i + 1) % 3]
                    key = edge_key(a, b)
                    count, _ = coplanar.get(key, (0, (a, b)))
                    coplanar[key] = count + 1, (a, b)
                if len(coplanar) > max_segments * 3:
                    raise ValueError("Section exceeds display budget; choose a smaller component")
                continue
            hits = {}
            for i in range(3):
                a, b = points[i], points[(i + 1) % 3]
                da, db = distances[i], distances[(i + 1) % 3]
                if abs(da) <= tolerance_mm:
                    hits[point_key(a)] = a
                if da * db < 0 and abs(da) > tolerance_mm and abs(db) > tolerance_mm:
                    ratio = da / (da - db)
                    p = tuple(a[j] + ratio * (b[j] - a[j]) for j in range(3))
                    hits[point_key(p)] = p
            if len(hits) == 2:
                a, b = hits.values()
                regular[edge_key(a, b)] = a, b
            if len(regular) > max_segments or len(coplanar) > max_segments * 3:
                raise ValueError("Section exceeds display budget; choose a smaller component")
        for key, (count, edge) in coplanar.items():
            if count == 1:
                regular[key] = edge
        result.update(regular)
        if len(result) > max_segments:
            raise ValueError("Section exceeds display budget; choose a smaller component")
    if cancelled():
        raise SectionCancelled("Section calculation cancelled")
    progress(total)
    return SectionResult(axis, float(coordinate_mm), tuple(result.values()), total, tolerance_mm)
