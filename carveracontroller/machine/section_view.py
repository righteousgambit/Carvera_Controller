"""Plane/triangle intersections of rendered CAD; no transport or solid inference."""

from dataclasses import dataclass
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

    @property
    def axes(self):
        return tuple(i for i in range(3) if i != self.axis)

    @property
    def bounds(self):
        points = [p for segment in self.segments for p in segment]
        return tuple((min(p[i] for p in points), max(p[i] for p in points)) for i in self.axes) if points else None


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
