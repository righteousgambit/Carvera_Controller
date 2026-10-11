"""Immutable imported stock, source identity and bounded derived preview caches."""

from __future__ import annotations

import math
import threading
from _thread import LockType
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypedDict

from carveracontroller.addons.manufacturing_simulation import AABB, StockMeshInput, StockSolid, StockVolume, Vec3

from .geometry_snapshot import GeometrySnapshot

if TYPE_CHECKING:
    from .model import MachineSetup


class StockReference(TypedDict):
    schema: int
    source_path: str
    source_sha256: str
    source_units: Literal["mm", "inch"]
    minimum_mm: list[float]
    maximum_mm: list[float]


def stock_reference(value: object) -> StockReference:
    """Validate a serialized reference without opening a file or guessing units."""
    keys = {"schema", "source_path", "source_sha256", "source_units", "minimum_mm", "maximum_mm"}
    if not isinstance(value, dict) or set(value) != keys or type(value["schema"]) is not int or value["schema"] != 1:
        raise ValueError("Unsupported imported-stock source reference")
    path, digest, units = value["source_path"], value["source_sha256"], value["source_units"]
    if not isinstance(path, str) or not path.strip() or len(path) > 2048 or "\0" in path:
        raise ValueError("Imported stock requires a source path")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Imported stock requires exact source SHA-256")
    if units not in ("mm", "inch") or type(units) is not str:
        raise ValueError("Imported stock requires explicit mm or inch units")
    points = []
    for name in ("minimum_mm", "maximum_mm"):
        point = value[name]
        if (
            not isinstance(point, (list, tuple))
            or len(point) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 100000 for v in point)
        ):
            raise ValueError("Imported stock bounds require finite source-local millimetres")
        points.append((float(point[0]), float(point[1]), float(point[2])))
    low, high = points
    if any(a >= b for a, b in zip(low, high)):
        raise ValueError("Imported stock bounds must have positive extents")
    return StockReference(
        schema=1,
        source_path=path,
        source_sha256=digest,
        source_units="mm" if units == "mm" else "inch",
        minimum_mm=list(low),
        maximum_mm=list(high),
    )


@dataclass(frozen=True, init=False)
class StockModel:
    source_path: str
    source_sha256: str
    source_units: Literal["mm", "inch"]
    minimum_mm: tuple[float, float, float]
    maximum_mm: tuple[float, float, float]
    solid: StockSolid = field(repr=False, compare=False)
    _cache: OrderedDict[tuple[object, ...], GeometrySnapshot] = field(repr=False, compare=False)
    _lock: LockType = field(repr=False, compare=False)

    def __init__(self) -> None:
        raise TypeError("Use StockModel.load or from_reference")

    @classmethod
    def load(
        cls,
        path: str,
        units: Literal["mm", "inch"],
        *,
        expected_sha256: str | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> StockModel:
        solid = StockSolid.validate(
            StockMeshInput.load(path, units=units, expected_sha256=expected_sha256, cancelled=cancelled),
            cancelled=cancelled,
        )
        mesh = solid.mesh
        result = object.__new__(cls)
        for name, value in (
            ("source_path", mesh.source_path),
            ("source_sha256", mesh.source_sha256),
            ("source_units", mesh.source_units),
            ("minimum_mm", mesh.minimum_mm),
            ("maximum_mm", mesh.maximum_mm),
            ("solid", solid),
            ("_cache", OrderedDict()),
            ("_lock", threading.Lock()),
        ):
            object.__setattr__(result, name, value)
        return result

    @classmethod
    def from_reference(
        cls, reference: Mapping[str, object], *, cancelled: Callable[[], bool] | None = None
    ) -> StockModel:
        ref = stock_reference(dict(reference))
        result = cls.load(
            ref["source_path"], ref["source_units"], expected_sha256=ref["source_sha256"], cancelled=cancelled
        )
        if result.reference != ref:
            raise ValueError("Imported stock source bounds differ from the retained reference")
        return result

    @property
    def size_mm(self) -> tuple[float, float, float]:
        return (
            self.maximum_mm[0] - self.minimum_mm[0],
            self.maximum_mm[1] - self.minimum_mm[1],
            self.maximum_mm[2] - self.minimum_mm[2],
        )

    @property
    def reference(self) -> StockReference:
        return StockReference(
            schema=1,
            source_path=self.source_path,
            source_sha256=self.source_sha256,
            source_units=self.source_units,
            minimum_mm=list(self.minimum_mm),
            maximum_mm=list(self.maximum_mm),
        )

    def __deepcopy__(self, memo: dict[int, object]) -> StockModel:
        memo[id(self)] = self
        return self

    def fork_preview_cache(self) -> StockModel:
        """Share immutable validated source data with a separate bounded placement cache."""
        result = object.__new__(type(self))
        for name in ("source_path", "source_sha256", "source_units", "minimum_mm", "maximum_mm", "solid"):
            object.__setattr__(result, name, getattr(self, name))
        object.__setattr__(result, "_cache", OrderedDict())
        object.__setattr__(result, "_lock", threading.Lock())
        return result

    def geometry(
        self,
        setup: MachineSetup,
        color: Sequence[float],
        *,
        wireframe: bool = False,
        cancelled: Callable[[], bool] | None = None,
    ) -> GeometrySnapshot:
        def check() -> None:
            if cancelled is not None and cancelled():
                raise InterruptedError("Imported stock preview cancelled")

        check()
        key = (setup.work_offset_mm, setup.stock_origin_mm, setup.stock_orientation.degrees, tuple(color), wireframe)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached
        from .model import Geometry

        geometry = Geometry()
        shift = tuple(a - b for a, b in zip(setup.stock_origin_mm, self.minimum_mm))
        edges = set()
        for index, (a, b, d) in enumerate(self.solid.mesh.triangles_mm):
            if index % 128 == 0:
                check()
            points = [
                setup.machine_point(setup.stock_point(tuple(p[i] + shift[i] for i in range(3)))) for p in (a, b, d)
            ]
            if wireframe:
                for i, j in ((0, 1), (1, 2), (2, 0)):
                    edge = tuple(sorted(((a, b, d)[i], (a, b, d)[j])))
                    if edge in edges:
                        continue
                    edges.add(edge)
                    for p in (points[i], points[j]):
                        geometry.indices.append(len(geometry.vertices) // 10)
                        geometry.vertices.extend((*p, 0, 0, 1, *color))
            else:
                u, v = tuple(b[i] - a[i] for i in range(3)), tuple(d[i] - a[i] for i in range(3))
                nx, ny, nz = u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]
                length = math.hypot(nx, ny, nz)
                if not length:
                    raise ValueError("Stock surface normal cannot be represented")
                geometry.triangle(points, setup.stock_orientation.apply((nx / length, ny / length, nz / length)), color)
        result = GeometrySnapshot(geometry.vertices, geometry.indices, cancelled=cancelled)
        check()
        with self._lock:
            self._cache[key] = result
            while len(self._cache) > 4:
                self._cache.popitem(last=False)
        return result

    def prepare_preview(
        self, setup: MachineSetup, scale: float, *, cancelled: Callable[[], bool] | None = None
    ) -> None:
        geometry = self.geometry(setup, (0.70, 0.49, 0.25, 0.20), cancelled=cancelled)
        geometry.render_batches(setup.work_offset_mm, scale, cancelled=cancelled)
        edges = self.geometry(setup, (0.96, 0.72, 0.34, 1), wireframe=True, cancelled=cancelled)
        edges.render_line_batches(setup.work_offset_mm, scale, cancelled=cancelled)


def initial_stock(
    setup: MachineSetup,
    resolution_mm: float,
    *,
    cancelled: Callable[[], bool] | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> StockVolume:
    if setup.stock_size_mm is None:
        raise ValueError("Declare initial stock before simulating")
    model = setup.stock_model
    if model is not None:
        return model.solid.voxelize(
            resolution_mm,
            translation_mm=(Vec3(*setup.stock_origin_mm) - Vec3(*model.minimum_mm)).tuple,
            rotation_deg=setup.stock_rotation_deg,
            tilt_deg=setup.stock_tilt_deg,
            cancelled=cancelled,
            progress=progress,
        ).stock
    bounds = AABB(
        Vec3(*setup.stock_origin_mm), Vec3(*(a + b for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm)))
    )
    return StockVolume(
        bounds,
        resolution_mm,
        max_voxels=2_000_000,
        rotation_deg=setup.stock_rotation_deg,
        tilt_deg=setup.stock_tilt_deg,
        cancelled=cancelled,
    )


def validate_residual_stock(
    setup: MachineSetup, stock: StockVolume, *, cancelled: Callable[[], bool] | None = None
) -> None:
    """Refuse residual grids or material that do not belong to this initial shape."""
    if setup.stock_size_mm is None:
        raise ValueError("Residual stock requires declared initial stock")
    expected = AABB(
        Vec3(*setup.stock_origin_mm), Vec3(*(a + b for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm)))
    )
    model = setup.stock_model
    if model is not None:
        # Match the source-to-program arithmetic used by voxelize, including
        # its representable rounding at nonzero source coordinates.
        shift = Vec3(*setup.stock_origin_mm) - Vec3(*model.minimum_mm)
        expected = AABB(Vec3(*model.minimum_mm) + shift, Vec3(*model.maximum_mm) + shift)
    if (
        stock.grid_bounds != expected
        or stock.rotation_deg != setup.stock_rotation_deg
        or stock.tilt_deg != setup.stock_tilt_deg
        or stock.pivot != (expected.minimum + expected.maximum).scaled(0.5)
    ):
        raise ValueError("Residual stock placement differs from the declared initial stock")
    initial_count = len(stock._occupied)
    if model is not None:
        initial = initial_stock(setup, stock.resolution_mm, cancelled=cancelled)
        initial_count = initial._remaining_count
        for start in range(0, len(stock._occupied), 65536):
            if cancelled is not None and cancelled():
                raise InterruptedError("Residual stock validation cancelled")
            if any(
                a and not b
                for a, b in zip(stock._occupied[start : start + 65536], initial._occupied[start : start + 65536])
            ):
                raise ValueError("Residual contains material outside the imported initial shape")
    if stock._initial_count != initial_count:
        raise ValueError("Residual initial material count differs from the selected stock source")
