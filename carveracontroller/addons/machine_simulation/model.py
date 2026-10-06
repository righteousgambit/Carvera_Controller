"""Pure geometry and coordinate frames for the machine viewer.

Published C1 travels: https://global.makera.com/products/carvera
The chassis/component dimensions below are illustrative, not manufacturer CAD.
No collision checking, stock subtraction or rotary-axis simulation is implied.
MCS convention is a nominal negative-travel frame; configure the WCS offset
explicitly before interpreting a program's placement relative to the machine.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import cos, isfinite, pi, sin

VERTEX_FORMAT = [(b"v_pos", 3, "float"), (b"v_normal", 3, "float"), (b"v_color", 4, "float")]


def vector(value: Sequence[float], name: str) -> tuple[float, float, float]:
    result = tuple(float(v) for v in value)
    if len(result) != 3 or not all(isfinite(v) for v in result):
        raise ValueError(f"{name} must contain three finite millimetre values")
    return result[0], result[1], result[2]


@dataclass(frozen=True)
class MachineSetup:
    work_offset_mm: tuple = (-180.0, -120.0, -110.0)
    stock_size_mm: tuple | None = None
    stock_origin_mm: tuple = (0.0, 0.0, 0.0)
    alignment_confirmed: bool = False
    stock_rotation_deg: float = 0.0

    def __post_init__(self):
        if type(self.stock_rotation_deg) not in (int, float) or not isfinite(self.stock_rotation_deg):
            raise ValueError("Stock rotation must be finite degrees")
        object.__setattr__(self, "stock_rotation_deg", (self.stock_rotation_deg + 180) % 360 - 180)
        object.__setattr__(self, "work_offset_mm", vector(self.work_offset_mm, "Work offset"))
        object.__setattr__(self, "stock_origin_mm", vector(self.stock_origin_mm, "Stock lower corner"))
        if self.stock_size_mm is not None:
            size = vector(self.stock_size_mm, "Stock dimensions")
            if min(size) <= 0:
                raise ValueError("Stock dimensions must be positive")
            object.__setattr__(self, "stock_size_mm", size)

    def stock_point(self, program_point: Sequence[float]) -> tuple[float, float, float]:
        """Rotate declared stock about its program-space center, without changing WCS."""
        point = vector(program_point, "Stock point")
        if self.stock_size_mm is None or not self.stock_rotation_deg:
            return point
        pivot = tuple(a + b / 2 for a, b in zip(self.stock_origin_mm, self.stock_size_mm))
        angle = self.stock_rotation_deg * pi / 180
        c, s = cos(angle), sin(angle)
        x, y = point[0] - pivot[0], point[1] - pivot[1]
        return pivot[0] + c * x - s * y, pivot[1] + s * x + c * y, point[2]

    def stock_mesh(
        self,
        color: Sequence[float] = (0.70, 0.49, 0.25, 0.20),
        *,
        wireframe: bool = False,
    ) -> Geometry:
        geometry = Geometry()
        if self.stock_size_mm is None:
            return geometry
        low = self.stock_origin_mm
        high = tuple(a + b for a, b in zip(low, self.stock_size_mm))
        if wireframe:
            geometry = box_wireframe(low, high, color)
        else:
            geometry.box(low, high, color)
        angle = self.stock_rotation_deg * pi / 180
        c, s = cos(angle), sin(angle)
        for index in range(0, len(geometry.vertices), 10):
            geometry.vertices[index : index + 3] = self.machine_point(
                self.stock_point(geometry.vertices[index : index + 3])
            )
            nx, ny, nz = geometry.vertices[index + 3 : index + 6]
            geometry.vertices[index + 3 : index + 6] = (c * nx - s * ny, s * nx + c * ny, nz)
        return geometry

    def machine_point(self, work_point: Sequence[float]) -> tuple[float, float, float]:
        point = vector(work_point, "Tool position")
        return point[0] + self.work_offset_mm[0], point[1] + self.work_offset_mm[1], point[2] + self.work_offset_mm[2]

    def work_point(self, machine_point: Sequence[float]) -> tuple[float, float, float]:
        point = vector(machine_point, "Machine position")
        return point[0] - self.work_offset_mm[0], point[1] - self.work_offset_mm[1], point[2] - self.work_offset_mm[2]

    def pose(self, work_point):
        """Y table moves opposite program Y; fixed spindle centreline is Y=-120.

        In table coordinates the tooltip is the program point. In chassis
        coordinates it becomes (MCS X, -120, MCS Z), while stock and the path
        move with the table. This preserves tool-to-stock relative motion.
        """
        mx, my, mz = self.machine_point(work_point)
        return {
            "table": (0.0, -120.0 - my, 0.0),
            "carriage": (mx + 180.0, 0.0, 0.0),
            "spindle": (mx + 180.0, 0.0, mz + 110.0),
            "tool_machine_mm": (mx, -120.0, mz),
            "in_nominal_travel": -360 <= mx <= 0 and -240 <= my <= 0 and -140 <= mz <= 0,
        }


class Geometry:
    def __init__(self) -> None:
        self.vertices: list[float] = []
        self.indices: list[int] = []

    def triangle(self, points: Sequence[Sequence[float]], normal: Sequence[float], color: Sequence[float]) -> None:
        first = len(self.vertices) // 10
        for point in points:
            self.vertices.extend((*point, *normal, *color))
        self.indices.extend((first, first + 1, first + 2))

    def box(self, low: Sequence[float], high: Sequence[float], color: Sequence[float]) -> None:
        x0, y0, z0 = low
        x1, y1, z1 = high
        faces = (
            (((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0)), (-1, 0, 0)),
            (((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1)), (1, 0, 0)),
            (((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1)), (0, -1, 0)),
            (((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0)), (0, 1, 0)),
            (((x0, y0, z0), (x0, y1, z0), (x1, y1, z0), (x1, y0, z0)), (0, 0, -1)),
            (((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)), (0, 0, 1)),
        )
        for points, normal in faces:
            self.triangle(points[:3], normal, color)
            self.triangle((points[0], points[2], points[3]), normal, color)

    def cylinder(self, centre, radius, bottom, top, color, sides=20):
        cx, cy = centre
        for i in range(sides):
            a, b = 2 * pi * i / sides, 2 * pi * (i + 1) / sides
            p0, p1 = (cx + radius * cos(a), cy + radius * sin(a)), (cx + radius * cos(b), cy + radius * sin(b))
            normal = (cos((a + b) / 2), sin((a + b) / 2), 0)
            self.triangle(((*p0, bottom), (*p1, bottom), (*p1, top)), normal, color)
            self.triangle(((*p0, bottom), (*p1, top), (*p0, top)), normal, color)
            self.triangle(((cx, cy, top), (*p0, top), (*p1, top)), (0, 0, 1), color)
            self.triangle(((cx, cy, bottom), (*p1, bottom), (*p0, bottom)), (0, 0, -1), color)


def box_wireframe(
    low: Sequence[float],
    high: Sequence[float],
    color: Sequence[float] = (0.96, 0.72, 0.34, 1.0),
) -> Geometry:
    """Twelve actual volume edges, using the same vertex format as scene meshes."""
    low, high = vector(low, "Box lower corner"), vector(high, "Box upper corner")
    if any(a >= b for a, b in zip(low, high)):
        raise ValueError("Box upper corner must exceed its lower corner")
    geometry = Geometry()
    for axis in range(3):
        others = [i for i in range(3) if i != axis]
        for a in (0, 1):
            for b in (0, 1):
                first = list(low)
                first[others[0]] = (low, high)[a][others[0]]
                first[others[1]] = (low, high)[b][others[1]]
                second = list(first)
                second[axis] = high[axis]
                for point in (first, second):
                    geometry.indices.append(len(geometry.vertices) // 10)
                    geometry.vertices.extend((*point, 0, 0, 1, *color))
    return geometry


def build_scene(setup):
    """Small opaque component meshes in nominal chassis millimetres."""
    groups = {name: Geometry() for name in ("fixed", "table", "carriage", "spindle", "stock")}
    dark, metal, accent = (0.16, 0.23, 0.31, 1), (0.54, 0.62, 0.70, 1), (0.16, 0.57, 0.72, 1)
    fixed = groups["fixed"]
    fixed.box((-430, -330, -195), (70, 90, -175), dark)
    for x in (-405, 35):
        fixed.box((x, -230, -175), (x + 25, -50, 130), dark)
    fixed.box((-405, -155, 100), (60, -85, 140), dark)
    for z in (108, 130):
        fixed.box((-380, -164, z), (40, -158, z + 5), metal)
    # Y rails lie below the translating table.
    for x in (-310, -50):
        fixed.box((x, -295, -168), (x + 12, 45, -157), metal)
    table = groups["table"]
    table.box((-370, -245, -155), (10, 5, -140), metal)
    for x in range(-350, 1, 25):
        table.box((x, -243, -139.8), (x + 1.5, 3, -139.3), dark)
    # Carriage and vertical slide are independent of spindle Z travel.
    groups["carriage"].box((-215, -177, -65), (-145, -155, 138), accent)
    spindle = groups["spindle"]
    spindle.box((-210, -171, -58), (-150, -144, 36), metal)
    spindle.cylinder((-180, -120), 23, -70, 20, dark)
    spindle.cylinder((-180, -120), 12, -82, -70, metal)
    groups["stock"] = setup.stock_mesh()
    return groups
