"""Data-only community CAD profile loading, independent of Kivy and hardware."""

import gzip
import json
import math
from pathlib import Path

from .model import Geometry

DEFAULT_PROFILE = Path.home() / ".carvera" / "machine-profiles" / "c1-v9.json.gz"
CAD_OFFSET = (-360.0, -240.0, -140.0)
# Collet attachment from the matching v9 Fusion simulation.mch (millimetres).
CAD_HEAD = (6.045943476712754, 18.40841093402391, 118.44951969207052)
GROUPS = {"fixed", "table", "carriage", "spindle"}


class MachineProfile:
    def __init__(self, data):
        if data.get("schema") != 1 or data.get("units") != "mm":
            raise ValueError("Unsupported machine profile format")
        self.model = str(data["model"])[:120]
        self.source_url = str(data["source_url"])
        self.source_revision = str(data["source_revision"])
        self.source_sha256 = str(data["source_sha256"])
        fixture = data.get("fixture")
        self.fixture_registration = str(fixture.get("registration", "draft"))[:240] if isinstance(fixture, dict) else None
        self.groups = {name: Geometry() for name in GROUPS}
        count = 0
        for component in data["components"]:
            group = component["group"]
            values = component["vertices"]
            if group not in GROUPS or not values or len(values) % 30:
                raise ValueError("Invalid CAD triangles")
            count += len(values)
            if count > 6_000_000 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError("Invalid or oversized CAD geometry")
            geometry = self.groups[group]
            for index in range(0, len(values), 10):
                geometry.vertices.extend(values[index + axis] + CAD_OFFSET[axis] for axis in range(3))
                geometry.vertices.extend(values[index + 3 : index + 10])
            geometry.indices = list(range(len(geometry.vertices) // 10))
        if any(not mesh.indices for mesh in self.groups.values()):
            raise ValueError("Machine profile is missing a motion group")

    @classmethod
    def load(cls, path=DEFAULT_PROFILE):
        # Bound the expanded data as well as the on-disk archive.
        if Path(path).stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Machine profile is too large")
        with gzip.open(path, "rb") as source:
            raw = source.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("Expanded machine profile is too large")
        return cls(json.loads(raw))

    def pose(self, setup, point, tool_length_mm=50.0):
        """Preserve profile X->Z/head and negative-Y/table motion.

        CAD zero is registered to the nominal negative-travel bed frame.
        This is visual registration, not a measured physical machine origin.
        The spindle follows the length of the tool mesh currently drawn.
        """
        mx, my, mz = setup.machine_point(point)
        hx, hy, hz = (CAD_HEAD[i] + CAD_OFFSET[i] for i in range(3))
        return {
            "table": (0.0, hy - my, 0.0),
            "carriage": (mx - hx, 0.0, 0.0),
            "spindle": (mx - hx, 0.0, mz + tool_length_mm - hz),
            "tool_machine_mm": (mx, hy, mz),
            "in_nominal_travel": -360 <= mx <= 0 and -240 <= my <= 0 and -140 <= mz <= 0,
        }

    def scene(self, setup):
        groups = dict(self.groups)
        stock = Geometry()
        if setup.stock_size_mm is not None:
            low = setup.machine_point(setup.stock_origin_mm)
            high = tuple(a + b for a, b in zip(low, setup.stock_size_mm))
            stock.box(low, high, (0.70, 0.49, 0.25, 0.20))
        groups["stock"] = stock
        return groups


def triangle_batches(geometry, max_vertices=65535):
    """Kivy indices are unsigned shorts; never wrap a larger CAD mesh."""
    if max_vertices < 3:
        raise ValueError("Batch must hold a triangle")
    max_vertices -= max_vertices % 3
    for start in range(0, len(geometry.indices), max_vertices):
        indices = geometry.indices[start : start + max_vertices]
        vertices = []
        for index in indices:
            vertices.extend(geometry.vertices[index * 10 : index * 10 + 10])
        yield vertices, list(range(len(indices)))
