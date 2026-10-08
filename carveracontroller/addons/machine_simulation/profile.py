"""Data-only community CAD profile loading, independent of Kivy and hardware."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import threading
from collections import OrderedDict
from collections.abc import Callable, Iterator, Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import NoReturn, TypedDict, cast

from carveracontroller.addons.cad_identity import read_asset_bytes

from .geometry_snapshot import GeometrySnapshot
from .model import Geometry, MachinePose, MachineSetup, vector
from .workholding import placed_point

DEFAULT_PROFILE = Path.home() / ".carvera" / "machine-profiles" / "c1-v9.json.gz"
CAD_OFFSET = (-360.0, -240.0, -140.0)
# Collet attachment from the matching v9 Fusion simulation.mch (millimetres).
CAD_HEAD = (6.045943476712754, 18.40841093402391, 118.44951969207052)
MOTION_GROUPS = {"fixed", "table", "carriage", "spindle"}
GROUPS = MOTION_GROUPS | {"fixture", "workholding", "atc"}


class CadComponentRequired(TypedDict):
    group: str
    vertices: tuple[float, ...]


class CadComponent(CadComponentRequired, total=False):
    role: object
    workholding_role: object
    assembly: object


Placement = tuple[Sequence[float], float, float]
PlacementKey = tuple[tuple[float, ...], float, float]


class _FrozenMetadata(dict[str, object]):
    """JSON-compatible loaded metadata; edits require a replacement profile."""

    def _readonly(self, *_args: object, **_kwargs: object) -> NoReturn:
        raise TypeError("Loaded CAD metadata is immutable; load a replacement profile")

    __setitem__ = __delitem__ = clear = pop = popitem = setdefault = update = __ior__ = _readonly


def _freeze(value: object) -> object:
    if isinstance(value, dict):
        return _FrozenMetadata({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _metadata(value: object, name: str) -> Mapping[str, object]:
    if value is None:
        return _FrozenMetadata()
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} metadata must be an object with textual keys")
    return cast(_FrozenMetadata, _freeze(value))


def _metadata_point(value: object, name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three finite millimetre values")
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError(f"{name} must contain three finite millimetre values")
    return vector(value, name)


class MachineProfile:
    # Identity is attached by load() after validating the bounded archive.
    asset_path: str
    asset_sha256: str

    def __init__(self, data: Mapping[str, object]) -> None:
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
        workholding = _metadata(data.get("workholding"), "Workholding")
        for name in ("pivot_mm", "cad_translation_mm"):
            if name in workholding:
                _metadata_point(workholding[name], name)
        self._workholding = workholding
        self._workholding_pivot = _metadata_point(
            workholding.get("pivot_mm", workholding.get("cad_translation_mm", (0, 0, 0))), "Workholding pivot"
        )
        self._atc = _metadata(data.get("atc"), "ATC")
        components: list[CadComponent] = []
        groups = {name: Geometry() for name in GROUPS}
        count = 0
        raw_components = data.get("components")
        if not isinstance(raw_components, (list, tuple)):
            raise ValueError("CAD components must be a sequence")
        for raw_component in raw_components:
            if not isinstance(raw_component, dict) or any(not isinstance(key, str) for key in raw_component):
                raise ValueError("CAD component must be an object with textual keys")
            component = cast(Mapping[str, object], raw_component)
            group = component.get("group")
            raw_values = component.get("vertices")
            if not isinstance(group, str) or group not in GROUPS or not isinstance(raw_values, (list, tuple)):
                raise ValueError("Invalid CAD component group or vertices")
            if not raw_values or len(raw_values) % 30:
                raise ValueError("Invalid CAD triangles")
            count += len(raw_values)
            if count > 6_000_000 or any(type(v) not in (int, float) or not math.isfinite(v) for v in raw_values):
                raise ValueError("Invalid or oversized CAD geometry")
            values = cast(Sequence[float], raw_values)
            # Older profiles put the Saunders mesh in the generic table group.
            if group == "table" and component.get("assembly") == "INCH Plate":
                group = "fixture"
            # The numeric stream has already been validated above. Copy it once
            # rather than recursively dispatching _freeze for millions of scalars.
            components.append(
                cast(
                    CadComponent,
                    _FrozenMetadata(
                        {
                            key: tuple(values) if key == "vertices" else _freeze(value)
                            for key, value in {**component, "group": group}.items()
                        }
                    ),
                )
            )
            geometry = groups[group]
            for index in range(0, len(values), 10):
                geometry.vertices.extend(values[index + axis] + CAD_OFFSET[axis] for axis in range(3))
                geometry.vertices.extend(values[index + 3 : index + 10])
            geometry.indices = list(range(len(geometry.vertices) // 10))
        if any(not groups[name].indices for name in MOTION_GROUPS):
            raise ValueError("Machine profile is missing a motion group")
        self._groups = MappingProxyType(
            {name: GeometrySnapshot(geometry.vertices, geometry.indices) for name, geometry in groups.items()}
        )
        self._components = tuple(components)
        self._placement_lock = threading.Lock()
        self._placements: OrderedDict[PlacementKey, GeometrySnapshot] = OrderedDict(
            {((0.0, 0.0, 0.0), 0.0, 0.0): self.groups["workholding"]}
        )
        self._geometry_json = json.dumps(
            {"components": self.components, "workholding": self.workholding, "atc": self.atc},
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        self._geometry_sha256 = hashlib.sha256(self._geometry_json.encode()).hexdigest()

    @property
    def groups(self) -> Mapping[str, GeometrySnapshot]:
        return self._groups

    @property
    def geometry_sha256(self) -> str:
        """Immutable CAD fingerprint computed in the background load, never on tab clicks."""
        return self._geometry_sha256

    @property
    def components(self) -> tuple[CadComponent, ...]:
        return self._components

    @property
    def workholding(self) -> Mapping[str, object]:
        return self._workholding

    @property
    def workholding_pivot_mm(self) -> tuple[float, float, float]:
        return self._workholding_pivot

    @property
    def atc(self) -> Mapping[str, object]:
        return self._atc

    @property
    def geometry_json(self) -> str:
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
    def reuse_or_load(cls, path: str | Path, previous: MachineProfile | None = None) -> MachineProfile:
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

    def pose(self, setup: MachineSetup, point: Sequence[float], tool_length_mm: float = 50.0) -> MachinePose:
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

    def configured_atc_target(
        self, position_mm: Sequence[float], table_motion_mm: Sequence[float]
    ) -> tuple[float, float, float]:
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
        return vector(tuple(position_mm[i] + table_motion_mm[i] for i in range(3)), "ATC placed target")

    def prepare_workholding(
        self,
        workholding_offset_mm: Sequence[float] = (0, 0, 0),
        workholding_rotation_deg: float = 0,
        jaw_offset_mm: float = 0,
        *,
        cancelled: Callable[[], bool] | None = None,
    ) -> GeometrySnapshot:
        """Return immutable placement geometry; retain only two exact placements.

        Profile selection warms this on its worker. Stock and work coordinates
        are excluded from the key because this geometry is in machine space.
        """
        if cancelled is not None and cancelled():
            raise InterruptedError("Workholding placement cancelled")
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
        geometry = (
            self._placed_workholding(offset, angle, jaw)
            if cancelled is None
            else self._placed_workholding(offset, angle, jaw, cancelled=cancelled)
        )
        if cancelled is not None and cancelled():
            raise InterruptedError("Workholding placement cancelled")
        with self._placement_lock:
            existing = self._placements.get(key)
            if existing is not None:
                return existing
            self._placements[key] = geometry
            while len(self._placements) > 2:
                self._placements.popitem(last=False)
        return geometry

    def _placed_workholding(
        self, offset: Sequence[float], angle: float, jaw: float, *, cancelled: Callable[[], bool] | None = None
    ) -> GeometrySnapshot:
        if not self.groups["workholding"].indices:
            return self.groups["workholding"]
        geometry = Geometry()
        pivot = self.workholding_pivot_mm
        cosine, sine = math.cos(math.radians(angle)), math.sin(math.radians(angle))
        placed_offset = tuple(CAD_OFFSET[i] + offset[i] for i in range(3))
        for component in self.components:
            if component["group"] != "workholding":
                continue
            values = component["vertices"]
            jaw_shift = jaw if component.get("workholding_role", component.get("role")) == "movable" else 0
            for index in range(0, len(values), 10):
                if index % 1280 == 0 and cancelled is not None and cancelled():
                    raise InterruptedError("Workholding placement cancelled")
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
        result = GeometrySnapshot(geometry.vertices, geometry.indices)
        if cancelled is not None and cancelled():
            raise InterruptedError("Workholding placement cancelled")
        return result

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

    def prepare_render_buffers(
        self,
        work_offset_mm: Sequence[float],
        scale: float = 1.0,
        placement: Placement = ((0, 0, 0), 0, 0),
    ) -> None:
        """Warm pure CAD buffers on the profile worker, including the placed vise."""
        groups = dict(self.groups)
        groups["workholding"] = self.prepare_workholding(*placement)
        for geometry in groups.values():
            geometry.prepare_surface_index()
            geometry.render_batches(work_offset_mm, scale)


def triangle_batches(
    geometry: Geometry | GeometrySnapshot, max_vertices: int = 65535
) -> Iterator[tuple[list[float], list[int]]]:
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
