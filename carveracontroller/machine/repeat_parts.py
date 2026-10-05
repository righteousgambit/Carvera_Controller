"""Declared repeat-part frames. Planning never writes machine offsets."""

from __future__ import annotations

import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

WCS_NAMES = tuple(f"G{i}" for i in range(54, 60))


def vector(value):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Coordinates need three millimetre values")
    if any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 1000 for v in value):
        raise ValueError("Coordinates must be finite and within 1000 mm")
    return tuple(float(v) for v in value)


@dataclass(frozen=True)
class StockInstance:
    name: str
    wcs: str
    work_offset_mm: tuple
    stock_origin_mm: tuple
    stock_size_mm: tuple

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip() or len(self.name) > 120:
            raise ValueError("Part name must contain 1–120 characters")
        if self.wcs not in WCS_NAMES:
            raise ValueError("Choose a frame from G54 through G59")
        for key in ("work_offset_mm", "stock_origin_mm", "stock_size_mm"):
            object.__setattr__(self, key, vector(getattr(self, key)))
        if min(self.stock_size_mm) <= 0:
            raise ValueError("Stock dimensions must be positive")
        vector(self.bounds[0])
        vector(self.bounds[1])

    @property
    def bounds(self):
        low = tuple(a + b for a, b in zip(self.work_offset_mm, self.stock_origin_mm))
        return low, tuple(a + b for a, b in zip(low, self.stock_size_mm))

    def machine_point(self, local_point):
        return tuple(a + b for a, b in zip(vector(local_point), self.work_offset_mm))


@dataclass(frozen=True)
class RepeatPartPlan:
    parts: tuple

    def __post_init__(self):
        object.__setattr__(self, "parts", tuple(self.parts))
        if not 1 <= len(self.parts) <= 6 or any(not isinstance(p, StockInstance) for p in self.parts):
            raise ValueError("A plan needs 1–6 stock instances")
        if len({p.wcs for p in self.parts}) != len(self.parts):
            raise ValueError("Each part needs a distinct work coordinate system")
        if len({p.name.casefold() for p in self.parts}) != len(self.parts):
            raise ValueError("Each part needs a distinct name")
        for i, first in enumerate(self.parts):
            for second in self.parts[i + 1 :]:
                a, b = first.bounds, second.bounds
                if all(max(a[0][axis], b[0][axis]) < min(a[1][axis], b[1][axis]) for axis in range(3)):
                    raise ValueError(f"Declared stocks overlap: {first.name} and {second.name}")

    @classmethod
    def grid(cls, rows, columns, pitch_mm, work_offset_mm, stock_origin_mm, stock_size_mm, first_wcs="G54"):
        if type(rows) is not int or type(columns) is not int or rows <= 0 or columns <= 0:
            raise ValueError("Rows and columns must be positive whole numbers")
        if first_wcs not in WCS_NAMES or rows * columns > 6 - WCS_NAMES.index(first_wcs):
            raise ValueError("The array exceeds the available G54–G59 frames")
        pitch, offset = vector(pitch_mm), vector(work_offset_mm)
        if pitch[2] != 0:
            raise ValueError("A planar array uses zero Z pitch")
        parts = []
        start = WCS_NAMES.index(first_wcs)
        for row in range(rows):
            for column in range(columns):
                position = (offset[0] + column * pitch[0], offset[1] + row * pitch[1], offset[2])
                parts.append(
                    StockInstance(
                        f"Part {len(parts) + 1}",
                        WCS_NAMES[start + len(parts)],
                        position,
                        stock_origin_mm,
                        stock_size_mm,
                    )
                )
        return cls(tuple(parts))

    def to_dict(self):
        return {"schema": 1, "parts": [asdict(part) for part in self.parts]}

    @classmethod
    def from_dict(cls, value):
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "parts"}
            or type(value["schema"]) is not int
            or value["schema"] != 1
        ):
            raise ValueError("Unsupported repeat-part plan schema")
        if not isinstance(value["parts"], list) or not 1 <= len(value["parts"]) <= 6:
            raise ValueError("A plan needs 1–6 stock instances")
        fields = {"name", "wcs", "work_offset_mm", "stock_origin_mm", "stock_size_mm"}
        if any(not isinstance(part, dict) or set(part) != fields for part in value["parts"]):
            raise ValueError("Unknown or missing stock instance fields")
        return cls(tuple(StockInstance(**part) for part in value["parts"]))


class RepeatPartStore:
    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/repeat-parts.json")

    def _read(self):
        if not self.path.exists():
            return {}
        with self.path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Repeat-part library exceeds 1 MiB")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("Duplicate repeat-part field")
                result[key] = value
            return result

        try:
            value = json.loads(data, object_pairs_hook=unique)
        except RecursionError as exc:
            raise ValueError("Repeat-part library is excessively nested") from exc
        if not isinstance(value, dict) or len(value) > 64:
            raise ValueError("Invalid repeat-part library")
        for key, plan in value.items():
            self._identity(key)
            RepeatPartPlan.from_dict(plan)
        return value

    @staticmethod
    def _identity(profile_id):
        if not isinstance(profile_id, str) or not profile_id.strip() or len(profile_id) > 160:
            raise ValueError("Choose a saved machine profile first")

    def load(self, profile_id):
        self._identity(profile_id)
        value = self._read().get(profile_id)
        return RepeatPartPlan.from_dict(value) if value is not None else None

    def save(self, profile_id, plan):
        self._identity(profile_id)
        plan = RepeatPartPlan.from_dict(plan.to_dict())
        value = self._read()
        value[profile_id] = plan.to_dict()
        if len(value) > 64:
            raise ValueError("Repeat-part library exceeds 64 machines")
        data = json.dumps(value, indent=2).encode()
        if len(data) > 1024 * 1024:
            raise ValueError("Repeat-part library exceeds 1 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".repeat-parts-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
