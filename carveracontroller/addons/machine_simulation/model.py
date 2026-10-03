"""Pure geometry and coordinate frames for the machine viewer.

Published C1 travels: https://global.makera.com/products/carvera
The chassis/component dimensions below are illustrative, not manufacturer CAD.
No collision checking, stock subtraction or rotary-axis simulation is implied.
MCS convention is a nominal negative-travel frame; configure the WCS offset
explicitly before interpreting a program's placement relative to the machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi, sin

VERTEX_FORMAT = [(b"v_pos", 3, "float"), (b"v_normal", 3, "float"), (b"v_color", 4, "float")]


def vector(value, name):
    result = tuple(float(v) for v in value)
    if len(result) != 3 or not all(isfinite(v) for v in result):
        raise ValueError(f"{name} must contain three finite millimetre values")
    return result


@dataclass(frozen=True)
class MachineSetup:
    work_offset_mm: tuple = (-180.0, -120.0, -110.0)
    stock_size_mm: tuple | None = None
    stock_origin_mm: tuple = (0.0, 0.0, 0.0)
    alignment_confirmed: bool = False

    def __post_init__(self):
        object.__setattr__(self, "work_offset_mm", vector(self.work_offset_mm, "Work offset"))
        object.__setattr__(self, "stock_origin_mm", vector(self.stock_origin_mm, "Stock lower corner"))
        if self.stock_size_mm is not None:
            size = vector(self.stock_size_mm, "Stock dimensions")
            if min(size) <= 0:
                raise ValueError("Stock dimensions must be positive")
            object.__setattr__(self, "stock_size_mm", size)

    def machine_point(self, work_point):
        return tuple(a + b for a, b in zip(vector(work_point, "Tool position"), self.work_offset_mm))

    def work_point(self, machine_point):
        return tuple(a - b for a, b in zip(vector(machine_point, "Machine position"), self.work_offset_mm))

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
    def __init__(self):
        self.vertices = []
        self.indices = []

    def triangle(self, points, normal, color):
        first = len(self.vertices) // 10
        for point in points:
            self.vertices.extend((*point, *normal, *color))
        self.indices.extend((first, first + 1, first + 2))

    def box(self, low, high, color):
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


def box_wireframe(low, high, color=(0.96, 0.72, 0.34, 1.0)):
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
    if setup.stock_size_mm is not None:
        low = setup.machine_point(setup.stock_origin_mm)
        high = tuple(a + b for a, b in zip(low, setup.stock_size_mm))
        groups["stock"].box(low, high, (0.70, 0.49, 0.25, 0.20))
    return groups
