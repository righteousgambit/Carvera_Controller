"""Declared repeat-part frames. Planning never writes machine offsets."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TypedDict

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel, StockReference, stock_reference

Vec3 = tuple[float, float, float]
Bounds = tuple[Vec3, Vec3]


class RequiredStockPayload(TypedDict):
    name: str
    wcs: str
    work_offset_mm: Vec3
    stock_origin_mm: Vec3
    stock_size_mm: Vec3


class StockPayload(RequiredStockPayload, total=False):
    stock_source: StockReference


class PlanPayload(TypedDict):
    schema: int
    parts: list[StockPayload]


class FrameReview(TypedDict):
    name: str
    wcs: str
    datum_mm: Vec3
    bounds_mm: Bounds
    nearest_stock_gap_mm: float | None


WCS_NAMES = tuple(f"G{i}" for i in range(54, 60))


def vector(value: object) -> Vec3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Coordinates need three millimetre values")
    result: list[float] = []
    for component in value:
        if isinstance(component, bool) or not isinstance(component, (int, float)):
            raise ValueError("Coordinates must be finite and within 1000 mm")
        try:
            number = float(component)
        except OverflowError as exc:
            raise ValueError("Coordinates must be finite and within 1000 mm") from exc
        if not math.isfinite(number) or abs(number) > 1000:
            raise ValueError("Coordinates must be finite and within 1000 mm")
        result.append(number)
    return result[0], result[1], result[2]


@dataclass(frozen=True)
class StockSource:
    """Immutable source reference; parsing plans performs no filesystem I/O."""

    encoded: str

    def __post_init__(self) -> None:
        if not isinstance(self.encoded, str) or len(self.encoded) > 16384:
            raise ValueError("Imported stock reference exceeds its bounded representation")
        reference = stock_reference(json.loads(self.encoded))
        object.__setattr__(self, "encoded", json.dumps(reference, sort_keys=True))

    @classmethod
    def from_model(cls, model: StockModel) -> StockSource:
        return cls(json.dumps(model.reference))

    @property
    def reference(self) -> StockReference:
        return stock_reference(json.loads(self.encoded))

    @property
    def size_mm(self) -> Vec3:
        ref = self.reference
        return vector(tuple(b - a for a, b in zip(ref["minimum_mm"], ref["maximum_mm"])))


@dataclass(frozen=True)
class StockInstance:
    name: str
    wcs: str
    work_offset_mm: Vec3
    stock_origin_mm: Vec3
    stock_size_mm: Vec3
    stock_source: StockSource | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or len(self.name) > 120
            or any(ord(c) < 32 for c in self.name)
        ):
            raise ValueError("Part name must contain 1–120 characters")
        if self.wcs not in WCS_NAMES:
            raise ValueError("Choose a frame from G54 through G59")
        for key in ("work_offset_mm", "stock_origin_mm", "stock_size_mm"):
            object.__setattr__(self, key, vector(getattr(self, key)))
        if self.stock_source is not None and (
            not isinstance(self.stock_source, StockSource) or self.stock_source.size_mm != self.stock_size_mm
        ):
            raise ValueError("Imported array stock dimensions must match the exact source")
        if min(self.stock_size_mm) <= 0:
            raise ValueError("Stock dimensions must be positive")
        vector(self.bounds[0])
        vector(self.bounds[1])

    @property
    def bounds(self) -> Bounds:
        low = vector(tuple(a + b for a, b in zip(self.work_offset_mm, self.stock_origin_mm)))
        return low, vector(tuple(a + b for a, b in zip(low, self.stock_size_mm)))

    def machine_point(self, local_point: Sequence[float]) -> Vec3:
        point = vector(local_point)
        return (point[0] + self.work_offset_mm[0], point[1] + self.work_offset_mm[1], point[2] + self.work_offset_mm[2])


@dataclass(frozen=True)
class RepeatPartPlan:
    parts: tuple[StockInstance, ...]
    stock_models: Mapping[str, StockModel] = field(default_factory=dict, compare=False, repr=False)
    prepared_index: int | None = field(default=None, compare=False, repr=False)
    prepared_revision: str | None = field(default=None, compare=False, repr=False)
    nominal_geometry: tuple[GeometrySnapshot, GeometrySnapshot] | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.parts, (tuple, list)):
            raise ValueError("A plan needs 1–6 stock instances")
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
    def grid(
        cls,
        rows: int,
        columns: int,
        pitch_mm: Sequence[float],
        work_offset_mm: Sequence[float],
        stock_origin_mm: Sequence[float],
        stock_size_mm: Sequence[float],
        first_wcs: str = "G54",
        stock_source: StockSource | None = None,
    ) -> RepeatPartPlan:
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
                        vector(stock_origin_mm),
                        vector(stock_size_mm),
                        stock_source,
                    )
                )
        return cls(tuple(parts))

    def to_dict(self) -> PlanPayload:
        records: list[StockPayload] = []
        for part in self.parts:
            record: StockPayload = {
                "name": part.name,
                "wcs": part.wcs,
                "work_offset_mm": part.work_offset_mm,
                "stock_origin_mm": part.stock_origin_mm,
                "stock_size_mm": part.stock_size_mm,
            }
            if part.stock_source is not None:
                record["stock_source"] = part.stock_source.reference
            records.append(record)
        return {"schema": 2 if any(p.stock_source is not None for p in self.parts) else 1, "parts": records}

    @classmethod
    def from_dict(cls, value: object) -> RepeatPartPlan:
        if (
            not isinstance(value, dict)
            or set(value) != {"schema", "parts"}
            or type(value["schema"]) is not int
            or value["schema"] not in (1, 2)
        ):
            raise ValueError("Unsupported repeat-part plan schema")
        if not isinstance(value["parts"], list) or not 1 <= len(value["parts"]) <= 6:
            raise ValueError("A plan needs 1–6 stock instances")
        fields = {"name", "wcs", "work_offset_mm", "stock_origin_mm", "stock_size_mm"}
        if any(
            not isinstance(part, dict)
            or set(part) not in (fields, fields | {"stock_source"})
            or (value["schema"] == 1 and "stock_source" in part)
            for part in value["parts"]
        ):
            raise ValueError("Unknown or missing stock instance fields")
        return cls(
            tuple(
                StockInstance(
                    part["name"],
                    part["wcs"],
                    vector(part["work_offset_mm"]),
                    vector(part["stock_origin_mm"]),
                    vector(part["stock_size_mm"]),
                    StockSource(json.dumps(part["stock_source"])) if "stock_source" in part else None,
                )
                for part in value["parts"]
            )
        )

    def prepared(
        self,
        *,
        scale: float = 1,
        selected_index: int | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> RepeatPartPlan:
        """Load exact sources and prime every instance on a background worker.

        Each placement gets its own small preview cache, sharing validated solids.
        No reference-only shape ever falls back to a rectangular block.
        """
        models: dict[str, StockModel] = {}
        loaded: dict[StockSource, StockModel] = {}
        triangles = 0
        for part in self.parts:
            if cancelled is not None and cancelled():
                raise InterruptedError("Array stock preparation cancelled")
            if part.stock_source is None:
                continue
            if part.stock_source not in loaded:
                loaded[part.stock_source] = StockModel.from_reference(part.stock_source.reference, cancelled=cancelled)
            triangles += len(loaded[part.stock_source].solid.mesh.triangles_mm)
            if triangles > 100_000:
                raise ValueError("Array exceeds the shared 100,000 source-triangle budget")
            model = loaded[part.stock_source].fork_preview_cache()
            models[part.wcs] = model
            if selected_index is None:
                continue
            setup = MachineSetup(part.work_offset_mm, part.stock_size_mm, part.stock_origin_mm, stock_model=model)
            model.prepare_preview(setup, scale, cancelled=cancelled)
            for color, wireframe in (((0.42, 0.62, 0.72, 0.24), False), ((0.52, 0.76, 0.86, 1.0), True)):
                geometry = model.geometry(setup, color, wireframe=wireframe, cancelled=cancelled)
                if wireframe:
                    geometry.render_line_batches(setup.work_offset_mm, scale, cancelled=cancelled)
                else:
                    geometry.render_batches(setup.work_offset_mm, scale, cancelled=cancelled)
        for source in loaded:
            ref = source.reference
            if asset_digest(ref["source_path"], 24 * 1024 * 1024, cancelled=cancelled) != ref["source_sha256"]:
                raise ValueError("Imported array stock bytes changed during preparation")
        prepared = replace(
            self, stock_models=models, prepared_index=None, prepared_revision=None, nominal_geometry=None
        )
        if selected_index is not None:
            solids, edges = repeat_stock_geometry(prepared, selected_index, _preparing=True)
            solid = GeometrySnapshot(solids.vertices, solids.indices, cancelled=cancelled)
            edge = GeometrySnapshot(edges.vertices, edges.indices, cancelled=cancelled)
            offset = self.parts[selected_index].work_offset_mm
            solid.render_batches(offset, scale, cancelled=cancelled)
            edge.render_line_batches(offset, scale, cancelled=cancelled)
            prepared = replace(
                prepared,
                prepared_index=selected_index,
                prepared_revision=plan_revision(self),
                nominal_geometry=(solid, edge),
            )
        return prepared

    def setup(self, part: StockInstance, *, machine_space: bool = False) -> MachineSetup:
        model = self.stock_models.get(part.wcs) if part.stock_source is not None else None
        if part.stock_source is not None and (model is None or model.reference != part.stock_source.reference):
            raise ValueError("Prepare the exact imported array stock before preview or simulation")
        return MachineSetup(
            (0, 0, 0) if machine_space else part.work_offset_mm,
            part.stock_size_mm,
            part.bounds[0] if machine_space else part.stock_origin_mm,
            stock_model=model,
        )


@dataclass(frozen=True)
class GridDraft:
    rows: int
    columns: int
    pitch_mm: Vec3
    work_offset_mm: Vec3
    stock_origin_mm: Vec3
    stock_size_mm: Vec3
    first_wcs: str


def grid_draft(plan: RepeatPartPlan) -> GridDraft | None:
    """Recover a regular row-major layout without changing its saved geometry.

    Unused pitch axes use the UI's 60 mm default. A 1e-9 mm arithmetic comparison
    accommodates subtraction roundoff; this is not a physical tolerance.
    """
    first = plan.parts[0]
    count = len(plan.parts)
    for columns in range(count, 0, -1):
        if count % columns:
            continue
        rows = count // columns
        pitch_x = plan.parts[1].work_offset_mm[0] - first.work_offset_mm[0] if columns > 1 else 60.0
        pitch_y = plan.parts[columns].work_offset_mm[1] - first.work_offset_mm[1] if rows > 1 else 60.0
        try:
            candidate = RepeatPartPlan.grid(
                rows,
                columns,
                (pitch_x, pitch_y, 0),
                first.work_offset_mm,
                first.stock_origin_mm,
                first.stock_size_mm,
                first.wcs,
                first.stock_source,
            )
        except ValueError:
            continue
        matches = all(
            actual.name == expected.name
            and actual.wcs == expected.wcs
            and actual.stock_origin_mm == expected.stock_origin_mm
            and actual.stock_size_mm == expected.stock_size_mm
            and actual.stock_source == expected.stock_source
            and all(
                math.isclose(a, b, rel_tol=0, abs_tol=1e-9)
                for a, b in zip(actual.work_offset_mm, expected.work_offset_mm)
            )
            for actual, expected in zip(plan.parts, candidate.parts)
        )
        if matches:
            return GridDraft(
                rows,
                columns,
                (pitch_x, pitch_y, 0.0),
                first.work_offset_mm,
                first.stock_origin_mm,
                first.stock_size_mm,
                first.wcs,
            )
    return None


def replace_part(plan: RepeatPartPlan, index: int, replacement: StockInstance) -> RepeatPartPlan:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(plan.parts):
        raise ValueError("Select a part in this plan")
    parts = list(plan.parts)
    parts[index] = replacement
    return RepeatPartPlan(tuple(parts))


class RepeatPartStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/repeat-parts.json")

    def _read(self) -> dict[str, PlanPayload]:
        if not self.path.exists():
            return {}
        with self.path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Repeat-part library exceeds 1 MiB")

        def unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
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
        validated: dict[str, PlanPayload] = {}
        for key, plan in value.items():
            self._identity(key)
            validated[key] = RepeatPartPlan.from_dict(plan).to_dict()
        return validated

    @staticmethod
    def _identity(profile_id: object) -> None:
        if not isinstance(profile_id, str) or not profile_id.strip() or len(profile_id) > 160:
            raise ValueError("Choose a saved machine profile first")

    def load(self, profile_id: str) -> RepeatPartPlan | None:
        self._identity(profile_id)
        value = self._read().get(profile_id)
        return RepeatPartPlan.from_dict(value) if value is not None else None

    def revision(self, profile_id: str) -> str | None:
        plan = self.load(profile_id)
        return plan_revision(plan)

    def save(self, profile_id: str, plan: RepeatPartPlan, expected_revision: str | None = None) -> str:
        self._identity(profile_id)
        plan = RepeatPartPlan.from_dict(plan.to_dict())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix(".lock")
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        name: str | None = None
        try:
            value = self._read()
            previous = value.get(profile_id)
            previous_plan = RepeatPartPlan.from_dict(previous) if previous is not None else None
            if plan_revision(previous_plan) != expected_revision:
                raise ValueError("Repeat-part plan changed elsewhere; restore before saving")
            value[profile_id] = plan.to_dict()
            if len(value) > 64:
                raise ValueError("Repeat-part library exceeds 64 machines")
            data = json.dumps(value, indent=2, allow_nan=False).encode()
            if len(data) > 1024 * 1024:
                raise ValueError("Repeat-part library exceeds 1 MiB")
            fd, name = tempfile.mkstemp(dir=self.path.parent, prefix=".repeat-parts-", suffix=".tmp")
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
            name = None
            revision = plan_revision(plan)
            assert revision is not None
            return revision
        finally:
            if name is not None and os.path.exists(name):
                os.unlink(name)
            lock.unlink(missing_ok=True)


def plan_revision(plan: RepeatPartPlan | None) -> str | None:
    if plan is None:
        return None
    return hashlib.sha256(json.dumps(plan.to_dict(), sort_keys=True, allow_nan=False).encode()).hexdigest()


def frame_review(plan: RepeatPartPlan, index: int) -> FrameReview:
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(plan.parts):
        raise ValueError("Select a part in this plan")
    part = plan.parts[index]
    gaps = []
    for other_index, other in enumerate(plan.parts):
        if other_index == index:
            continue
        first, second = part.bounds, other.bounds
        gap = math.sqrt(sum(max(first[0][a] - second[1][a], second[0][a] - first[1][a], 0) ** 2 for a in range(3)))
        gaps.append(gap)
    return {
        "name": part.name,
        "wcs": part.wcs,
        "datum_mm": part.work_offset_mm,
        "bounds_mm": part.bounds,
        "nearest_stock_gap_mm": min(gaps) if gaps else None,
    }


def repeat_stock_geometry(
    plan: RepeatPartPlan | None,
    selected_index: int | None,
    rest_geometries: Mapping[str, Geometry | GeometrySnapshot] | None = None,
    *,
    _preparing: bool = False,
) -> tuple[Geometry | GeometrySnapshot, Geometry | GeometrySnapshot]:
    """Non-active nominal stocks and edges in machine mm; never simulation input.

    Keep these separate from active stock picking, handles, clearance and rest
    stock. The viewer applies the same moving-table transform to every instance.
    """
    solids, edges = Geometry(), Geometry()
    if plan is None:
        if selected_index is not None:
            raise ValueError("A selected repeat part needs a plan")
        return solids, edges
    if (
        not isinstance(plan, RepeatPartPlan)
        or type(selected_index) is not int
        or not 0 <= selected_index < len(plan.parts)
    ):
        raise ValueError("Select an instance from the declared repeat-part plan")
    if any(p.stock_source is not None for p in plan.parts) and not _preparing:
        if (
            plan.prepared_index != selected_index
            or plan.prepared_revision != plan_revision(plan)
            or plan.nominal_geometry is None
        ):
            raise ValueError("Prepare the selected imported array stock before preview")
        if rest_geometries is None:
            return plan.nominal_geometry
    for index, part in enumerate(plan.parts):
        if index == selected_index:
            continue
        setup = plan.setup(part)
        for target, source in (
            (
                solids,
                rest_geometries[part.wcs]
                if rest_geometries is not None
                else setup.stock_mesh((0.42, 0.62, 0.72, 0.24)),
            ),
            (edges, setup.stock_mesh((0.52, 0.76, 0.86, 1.0), wireframe=True)),
        ):
            base = len(target.vertices) // 10
            target.vertices.extend(source.vertices)
            target.indices.extend(i + base for i in source.indices)
    return solids, edges
