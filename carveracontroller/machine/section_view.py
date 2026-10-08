"""Plane/triangle intersections of rendered CAD; no transport or solid inference."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from html import escape
from math import hypot, isfinite
from typing import Protocol

Point = tuple[float, float, float]
Contour = tuple[Point, Point]
ProjectedBounds = tuple[tuple[float, float], tuple[float, float]]
PointKey = tuple[int, int, int]
EdgeKey = tuple[PointKey, PointKey]


@dataclass(frozen=True)
class SectionClip:
    """Visible nominal CAD half-space; does not cap or modify a mesh."""

    axis: int
    coordinate_mm: float
    keep_above: bool = False
    normal: Point | None = None

    def __post_init__(self) -> None:
        if (
            type(self.axis) is not int
            or self.axis not in range(3)
            or type(self.coordinate_mm) not in (int, float)
            or not isfinite(self.coordinate_mm)
            or abs(self.coordinate_mm) > 1e7
            or type(self.keep_above) is not bool
        ):
            raise ValueError("Cutaway requires an axis and finite bounded CAD plane coordinate")

        if self.normal is not None:
            if len(self.normal) != 3 or any(type(v) not in (int, float) or not isfinite(v) for v in self.normal):
                raise ValueError("Section normal must contain three finite numbers")
            length = hypot(*self.normal)
            if not isfinite(length) or length < 1e-12:
                raise ValueError("Section normal must have a nonzero finite length")
            if abs(length - 1) < 1e-14:
                length = 1
            object.__setattr__(self, "normal", tuple(v / length for v in self.normal))

    @property
    def direction(self) -> Point:
        return self.normal or ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))[self.axis]

    @property
    def basis(self) -> tuple[Point, Point]:
        if self.normal is None:
            ua, va = ((1, 2), (0, 2), (0, 1))[self.axis]
            directions = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
            return directions[ua], directions[va]
        n = self.direction
        reference = min(range(3), key=lambda i: abs(n[i]))
        e = tuple(1.0 if i == reference else 0.0 for i in range(3))
        u = (e[1] * n[2] - e[2] * n[1], e[2] * n[0] - e[0] * n[2], e[0] * n[1] - e[1] * n[0])
        length = hypot(*u)
        u = (u[0] / length, u[1] / length, u[2] / length)
        v = (n[1] * u[2] - n[2] * u[1], n[2] * u[0] - n[0] * u[2], n[0] * u[1] - n[1] * u[0])
        return u, v

    def contains(self, point: Sequence[float]) -> bool:
        value = sum(a * b for a, b in zip(point, self.direction)) - self.coordinate_mm
        return value >= 0 if self.keep_above else value <= 0

    def shader_plane(self, work_offset: Sequence[float], scale: float) -> tuple[float, float, float, float]:
        """Equation in untransformed rendered vertices; keep signed distance <= 0."""
        if (
            len(work_offset) != 3
            or any(type(v) not in (int, float) or not isfinite(v) for v in work_offset)
            or type(scale) not in (int, float)
            or not isfinite(scale)
            or scale <= 0
        ):
            raise ValueError("Cutaway render frame must be finite with a positive scale")
        sign = -1.0 if self.keep_above else 1.0
        normal = tuple(sign * value for value in self.direction)
        constant = -sign * (self.coordinate_mm - sum(a * b for a, b in zip(work_offset, self.direction))) * scale
        if not isfinite(constant) or abs(constant) > 1e30:
            raise ValueError("Cutaway exceeds the shader coordinate range")
        return normal[0], normal[1], normal[2], constant


class IndexedTriangles(Protocol):
    @property
    def vertices(self) -> Sequence[float]: ...

    @property
    def indices(self) -> Sequence[int]: ...


class SectionCancelled(ValueError):
    pass


@dataclass(frozen=True)
class SectionResult:
    axis: int
    coordinate_mm: float
    segments: tuple[Contour, ...]
    triangle_count: int
    tolerance_mm: float
    normal: Point | None = None
    _bounds: ProjectedBounds | None = field(init=False, repr=False)
    _basis: tuple[Point, Point] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if type(self.axis) is not int or self.axis not in range(3) or not isfinite(self.coordinate_mm):
            raise ValueError("Invalid captured section plane")
        if type(self.triangle_count) is not int or self.triangle_count < 0:
            raise ValueError("Invalid captured section triangle count")
        if isinstance(self.tolerance_mm, bool) or not isfinite(self.tolerance_mm) or self.tolerance_mm <= 0:
            raise ValueError("Invalid captured section tolerance")
        plane = SectionClip(self.axis, self.coordinate_mm, normal=self.normal)
        object.__setattr__(self, "normal", plane.normal)
        object.__setattr__(self, "_basis", plane.basis)
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
                    min(self.project(point)[i] for segment in segments for point in segment),
                    max(self.project(point)[i] for segment in segments for point in segment),
                )
                for i in range(2)
            )
            if segments
            else None
        )
        object.__setattr__(self, "_bounds", bounds)

    def project(self, point: Sequence[float]) -> tuple[float, float]:
        u, v = self._basis
        return sum(a * b for a, b in zip(point, u)), sum(a * b for a, b in zip(point, v))

    @property
    def captions(self) -> tuple[str, str]:
        return ("U", "V") if self.normal is not None else ("XYZ"[self.axes[0]], "XYZ"[self.axes[1]])

    @property
    def plane_label(self) -> str:
        if self.normal is None:
            return f"{'XYZ'[self.axis]} = {self.coordinate_mm:g} mm"
        return f"n = ({', '.join(f'{v:.6g}' for v in self.normal)}); distance = {self.coordinate_mm:g} mm"

    @property
    def axes(self) -> tuple[int, int]:
        return ((1, 2), (0, 2), (0, 1))[self.axis]

    @property
    def bounds(self) -> ProjectedBounds | None:
        return self._bounds


def section_svg(result: SectionResult, title: str) -> str:
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
    bounds = result.bounds
    if bounds is None:
        raise ValueError("Calculate a nonempty section before exporting its drawing")
    (u0, u1), (v0, v1) = bounds
    su, sv = u1 - u0, v1 - v0
    width, height = max(su + 24, 140), max(sv + 48, 75)
    left, top = (width - su) / 2, 24
    path = " ".join(
        f"M {result.project(a)[0] - u0 + left:.9g},{v1 - result.project(a)[1] + top:.9g} L {result.project(b)[0] - u0 + left:.9g},{v1 - result.project(b)[1] + top:.9g}"
        for a, b in result.segments
    )
    plane = result.plane_label
    basis_description = f"U basis {result._basis[0]}; V basis {result._basis[1]}. " if result.normal else ""
    description = (
        basis_description + f"{plane}; horizontal {result.captions[0]}, vertical {result.captions[1]}; "
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
    <text x="6" y="13">{escape(plane)} · axes {result.captions[0]} / {result.captions[1]} · units mm</text>
    <text x="6" y="19">Nominal CAD; physical placement unverified</text>
  </g>
  <path id="section-contours" d="{path}" fill="none" stroke="#164e48" stroke-width="0.15"/>
  <g fill="#17252d" font-family="sans-serif" font-size="3">
    <text x="6" y="{top + sv + 8:.9g}">{result.captions[0]}: {u0:.6g} to {u1:.6g} mm · span {su:.6g} mm</text>
    <text x="6" y="{top + sv + 14:.9g}">{result.captions[1]}: {v0:.6g} to {v1:.6g} mm · span {sv:.6g} mm</text>
    <text x="6" y="{top + sv + 20:.9g}">Open contours; no solid area or clearance inferred</text>
  </g>
</svg>
'''


def section_geometry(
    geometries: Iterable[IndexedTriangles],
    axis: int,
    coordinate_mm: float,
    *,
    normal: Point | None = None,
    cancelled: Callable[[], bool] = lambda: False,
    progress: Callable[[int], None] = lambda n: None,
    tolerance_mm: float = 1e-6,
    max_segments: int = 200000,
) -> SectionResult:
    """Return actual triangle intersections, including coplanar surface boundaries.

    Coplanar triangulation diagonals cancel within each geometry. Other shared
    edges deduplicate. Open/nonmanifold meshes remain line segments; no area,
    solid closure, physical placement or clearance claim is made.
    """
    if type(axis) is not int or axis not in range(3) or not isfinite(coordinate_mm):
        raise ValueError("Choose X, Y or Z and a finite plane coordinate")
    if not isfinite(tolerance_mm) or tolerance_mm <= 0 or type(max_segments) is not int or max_segments < 1:
        raise ValueError("Section tolerance and segment budget must be positive")
    plane = SectionClip(axis, coordinate_mm, normal=normal)
    result: dict[EdgeKey, Contour] = {}
    total = 0

    def point_key(p: Point) -> PointKey:
        return (round(p[0] / tolerance_mm), round(p[1] / tolerance_mm), round(p[2] / tolerance_mm))

    def edge_key(a: Point, b: Point) -> EdgeKey:
        first, second = sorted((point_key(a), point_key(b)))
        return first, second

    for geometry in geometries:
        vertices, indices = geometry.vertices, geometry.indices
        if len(vertices) % 10 or len(indices) % 3:
            raise ValueError("Section requires indexed triangle geometry")
        coplanar: dict[EdgeKey, tuple[int, Contour]] = {}
        regular: dict[EdgeKey, Contour] = {}
        for offset in range(0, len(indices), 3):
            if total % 1024 == 0:
                if cancelled():
                    raise SectionCancelled("Section calculation cancelled")
                progress(total)
            total += 1
            points: list[Point] = []
            for index in indices[offset : offset + 3]:
                if type(index) is not int or not 0 <= index < len(vertices) // 10:
                    raise ValueError("Invalid section triangle index")
                p = (vertices[10 * index], vertices[10 * index + 1], vertices[10 * index + 2])
                if not all(isfinite(v) for v in p):
                    raise ValueError("Nonfinite section geometry")
                points.append(p)
            distances = [sum(a * b for a, b in zip(p, plane.direction)) - coordinate_mm for p in points]
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
            hits: dict[PointKey, Point] = {}
            for i in range(3):
                a, b = points[i], points[(i + 1) % 3]
                da, db = distances[i], distances[(i + 1) % 3]
                if abs(da) <= tolerance_mm:
                    hits[point_key(a)] = a
                if da * db < 0 and abs(da) > tolerance_mm and abs(db) > tolerance_mm:
                    ratio = da / (da - db)
                    p = (a[0] + ratio * (b[0] - a[0]), a[1] + ratio * (b[1] - a[1]), a[2] + ratio * (b[2] - a[2]))
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
    return SectionResult(axis, float(coordinate_mm), tuple(result.values()), total, tolerance_mm, plane.normal)
