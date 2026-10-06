"""Data-only community CAD profile loading, independent of Kivy and hardware."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType

from carveracontroller.addons.cad_identity import read_asset_bytes

from .geometry_snapshot import GeometrySnapshot
from .model import Geometry, MachineSetup
from .workholding import placed_point

DEFAULT_PROFILE = Path.home() / ".carvera" / "machine-profiles" / "c1-v9.json.gz"
CAD_OFFSET = (-360.0, -240.0, -140.0)
# Collet attachment from the matching v9 Fusion simulation.mch (millimetres).
CAD_HEAD = (6.045943476712754, 18.40841093402391, 118.44951969207052)
MOTION_GROUPS = {"fixed", "table", "carriage", "spindle"}
GROUPS = MOTION_GROUPS | {"fixture", "workholding", "atc"}


class _FrozenMetadata(dict):
    """JSON-compatible loaded metadata; edits require a replacement profile."""

    def _readonly(self, *_args, **_kwargs):
        raise TypeError("Loaded CAD metadata is immutable; load a replacement profile")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _readonly


def _freeze(value):
    if isinstance(value, dict):
        return _FrozenMetadata({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


class MachineProfile:
    # Identity is attached by load() after validating the bounded archive.
    asset_path: str
    asset_sha256: str

    def __init__(self, data):
        if data.get("schema") != 1 or data.get("units") != "mm":
            raise ValueError("Unsupported machine profile format")
        self.model = str(data["model"])[:120]
        self.source_url = str(data["source_url"])
        self.source_revision = str(data["source_revision"])
        self.source_sha256 = str(data["source_sha256"])
        fixture = data.get("fixture")
        self.fixture_registration = (
            str(fixture.get("registration", "draft"))[:240] if isinstance(fixture, dict) else None
        )
        self._workholding = _freeze(data.get("workholding") or {})
        self._atc = _freeze(data.get("atc") or {})
        self._components = []
        self._groups = {name: Geometry() for name in GROUPS}
        count = 0
        for component in data["components"]:
            group = component["group"]
            values = component["vertices"]
            if group not in GROUPS or not values or len(values) % 30:
                raise ValueError("Invalid CAD triangles")
            count += len(values)
            if count > 6_000_000 or any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError("Invalid or oversized CAD geometry")
            # Older profiles put the Saunders mesh in the generic table group.
            if group == "table" and component.get("assembly") == "INCH Plate":
                group = "fixture"
            # The numeric stream has already been validated above. Copy it once
            # rather than recursively dispatching _freeze for millions of scalars.
            self._components.append(
                _FrozenMetadata(
                    {
                        key: tuple(values) if key == "vertices" else _freeze(value)
                        for key, value in {**component, "group": group}.items()
                    }
                )
            )
            geometry = self.groups[group]
            for index in range(0, len(values), 10):
                geometry.vertices.extend(values[index + axis] + CAD_OFFSET[axis] for axis in range(3))
                geometry.vertices.extend(values[index + 3 : index + 10])
            geometry.indices = list(range(len(geometry.vertices) // 10))
        if any(not self.groups[name].indices for name in MOTION_GROUPS):
            raise ValueError("Machine profile is missing a motion group")
        self._groups = MappingProxyType(
            {name: GeometrySnapshot(geometry.vertices, geometry.indices) for name, geometry in self.groups.items()}
        )
        self._components = tuple(self._components)
        self._placement_lock = threading.Lock()
        self._placements = OrderedDict({((0.0, 0.0, 0.0), 0.0, 0.0): self.groups["workholding"]})
        self._geometry_json = json.dumps(
            {"components": self.components, "workholding": self.workholding, "atc": self.atc},
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        self._geometry_sha256 = hashlib.sha256(self._geometry_json.encode()).hexdigest()

    @property
    def groups(self):
        return self._groups

    @property
    def geometry_sha256(self):
        """Immutable CAD fingerprint computed in the background load, never on tab clicks."""
        return self._geometry_sha256

    @property
    def components(self):
        return self._components

    @property
    def workholding(self):
        return self._workholding

    @property
    def atc(self):
        return self._atc

    @property
    def geometry_json(self):
        """Canonical geometry serialized once during background profile loading."""
        return self._geometry_json

    @classmethod
    def load(cls, path: str | Path = DEFAULT_PROFILE) -> MachineProfile:
        # Bound the expanded data as well as the on-disk archive.
        encoded = read_asset_bytes(path, 8 * 1024 * 1024)
        with gzip.GzipFile(fileobj=io.BytesIO(encoded)) as source:
            raw = source.read(32 * 1024 * 1024 + 1)
        if len(raw) > 32 * 1024 * 1024:
            raise ValueError("Expanded machine profile is too large")
        profile = cls(json.loads(raw))
        profile.asset_path = str(Path(path).expanduser().resolve())
        profile.asset_sha256 = hashlib.sha256(encoded).hexdigest()
        return profile

    @classmethod
    def reuse_or_load(cls, path, previous=None):
        """Reuse a loaded assembly only after verifying the current bounded bytes.

        Metadata timestamps cannot establish CAD identity. Component selection
        often references the machine's own assembly; do not decompress/validate
        its millions of coordinates again when those exact bytes still match.
        """
        source = Path(path).expanduser().resolve()
        if previous is not None and getattr(previous, "asset_path", None) == str(source):
            encoded = read_asset_bytes(source, 8 * 1024 * 1024)
            if hashlib.sha256(encoded).hexdigest() == previous.asset_sha256:
                return previous
        return cls.load(source)

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

    def configured_atc_target(self, position_mm, table_motion_mm):
        """Map a G53 axis-reference target into this nominal CAD scene.

        These XYZ values drive pickup/drop moves. This is the axis reference
        at the configured target, not a measured pocket surface or tool tip.
        The bed carries the target with current table motion; using the
        target's own table motion places it under the nominal head reference.
        No cutter length, work offset, or arbitrary CAD offset is added.
        """
        if len(position_mm) != 3 or len(table_motion_mm) != 3:
            raise ValueError("ATC target and table motion require XYZ")
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in (*position_mm, *table_motion_mm)):
            raise ValueError("ATC target and table motion must be finite")
        return tuple(position_mm[i] + table_motion_mm[i] for i in range(3))

    def prepare_workholding(self, workholding_offset_mm=(0, 0, 0), workholding_rotation_deg=0, jaw_offset_mm=0):
        """Return immutable placement geometry; retain only two exact placements.

        Profile selection warms this on its worker. Stock and work coordinates
        are excluded from the key because this geometry is in machine space.
        """
        offset = tuple(float(v) for v in workholding_offset_mm)
        angle, jaw = float(workholding_rotation_deg), float(jaw_offset_mm)
        if len(offset) != 3 or not all(math.isfinite(v) and abs(v) <= 1000 for v in (*offset, angle, jaw)):
            raise ValueError("Invalid workholding placement")
        key = (offset, angle, jaw)
        with self._placement_lock:
            cached = self._placements.get(key)
            if cached is not None:
                self._placements.move_to_end(key)
                return cached
        # Do not hold a lock while transforming CAD: UI cache hits never wait
        # for another placement's worker computation.
        geometry = self._placed_workholding(offset, angle, jaw)
        with self._placement_lock:
            existing = self._placements.get(key)
            if existing is not None:
                return existing
            self._placements[key] = geometry
            while len(self._placements) > 2:
                self._placements.popitem(last=False)
        return geometry

    def _placed_workholding(self, offset, angle, jaw):
        if not self.groups["workholding"].indices:
            return self.groups["workholding"]
        geometry = Geometry()
        pivot = self.workholding.get("pivot_mm", self.workholding.get("cad_translation_mm", (0, 0, 0)))
        cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        placed_offset = tuple(CAD_OFFSET[i] + offset[i] for i in range(3))
        for component in self.components:
            if component["group"] != "workholding":
                continue
            values = component["vertices"]
            jaw_shift = jaw if component.get("workholding_role", component.get("role")) == "movable" else 0
            for index in range(0, len(values), 10):
                point = placed_point(values[index : index + 3], pivot, placed_offset, cosine, sine, jaw_shift)
                nx, ny, nz = values[index + 3 : index + 6]
                geometry.vertices.extend(
                    (
                        *point,
                        nx * cosine - ny * sine,
                        nx * sine + ny * cosine,
                        nz,
                        *values[index + 6 : index + 10],
                    )
                )
        geometry.indices = list(range(len(geometry.vertices) // 10))
        return GeometrySnapshot(geometry.vertices, geometry.indices)

    def scene(
        self,
        setup: MachineSetup,
        workholding_offset_mm: Sequence[float] = (0, 0, 0),
        workholding_rotation_deg: float = 0,
        jaw_offset_mm: float = 0,
    ) -> dict[str, Geometry | GeometrySnapshot]:
        groups: dict[str, Geometry | GeometrySnapshot] = dict(self.groups)
        groups["workholding"] = self.prepare_workholding(workholding_offset_mm, workholding_rotation_deg, jaw_offset_mm)
        groups["stock"] = setup.stock_mesh()
        return groups

    def prepare_render_buffers(self, work_offset_mm, scale=1.0, placement=((0, 0, 0), 0, 0)):
        """Warm pure CAD buffers on the profile worker, including the placed vise."""
        groups = dict(self.groups)
        groups["workholding"] = self.prepare_workholding(*placement)
        for geometry in groups.values():
            geometry.render_batches(work_offset_mm, scale)


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
