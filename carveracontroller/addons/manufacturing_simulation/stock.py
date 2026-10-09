"""Continuous swept cutting against bounded voxel stock; no time-step gaps."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from math import ceil, cos, floor, isfinite, radians, sin
from typing import Any

from .geometry import AABB, CollisionContact, SweptTool, ToolGeometry, Vec3, localized_contact


@dataclass(frozen=True)
class RemovalResult:
    removed_voxels: int
    removed_volume_mm3: float
    remaining_volume_mm3: float
    resolution_mm: float
    method: str = "continuous sweep against voxel centers"


def _interval(value: float, change: float, low: float, high: float) -> tuple[float, float] | None:
    if abs(change) < 1e-15:
        return (0.0, 1.0) if low <= value <= high else None
    a, b = (low - value) / change, (high - value) / change
    lo, hi = max(0.0, min(a, b)), min(1.0, max(a, b))
    return (lo, hi) if lo <= hi else None


def _cylinder_hit(point: Vec3, start: Vec3, end: Vec3, radius: float, bottom: float, top: float) -> bool:
    """Analytic continuous Z cylinder sweep, including diagonal XYZ moves."""
    delta = end - start
    interval = _interval(point.z - start.z, -delta.z, bottom, top)
    if interval is None:
        return False
    dx, dy = point.x - start.x, point.y - start.y
    denominator = delta.x * delta.x + delta.y * delta.y
    t = (dx * delta.x + dy * delta.y) / denominator if denominator else interval[0]
    t = min(interval[1], max(interval[0], t))
    return (dx - delta.x * t) ** 2 + (dy - delta.y * t) ** 2 <= radius * radius + 1e-12


def _sphere_hit(point: Vec3, start: Vec3, end: Vec3, radius: float) -> bool:
    delta = end - start
    relative = point - start
    denominator = sum(v * v for v in delta.tuple)
    t = sum(a * b for a, b in zip(relative.tuple, delta.tuple)) / denominator if denominator else 0
    t = min(1.0, max(0.0, t))
    distance = relative - delta.scaled(t)
    return sum(v * v for v in distance.tuple) <= radius * radius + 1e-12


def _profile_hit(point: Vec3, start: Vec3, end: Vec3, tool: ToolGeometry) -> bool:
    """Continuous sweep of piecewise axial radii, no temporal point sampling.

    Cones have quadratic radial clearance and are solved analytically. Rounded
    corners have concave radial clearance; bounded golden-section maximization
    resolves the entire time interval to floating-point precision. Every endpoint
    is included. Each voxel is still classified by its center, not its full box.
    """
    delta = end - start
    dx, dy, height = point.x - start.x, point.y - start.y, point.z - start.z
    if abs(delta.z) < 1e-15:
        if not 0 <= height <= tool.flute_length_mm:
            return False
        return _cylinder_hit(point, start, end, tool.axial_radius(height), 0, tool.flute_length_mm)
    breaks = tool.profile_breaks_mm
    for bottom, top in zip(breaks, breaks[1:]):
        interval = _interval(height, -delta.z, bottom, top)
        if interval is None:
            continue
        lo, hi = interval
        r0, r1 = tool.axial_radius(bottom), tool.axial_radius(top)
        if abs(r0 - r1) < 1e-12:
            if _cylinder_hit(point, start, end, r0, bottom, top):
                return True
            continue

        def clearance(t: float, bottom: float = bottom, top: float = top) -> float:
            axial = min(top, max(bottom, height - delta.z * t))
            radius = tool.axial_radius(axial)
            return radius * radius - (dx - delta.x * t) ** 2 - (dy - delta.y * t) ** 2

        f0, f1 = clearance(lo), clearance(hi)
        if max(f0, f1) >= -1e-12:
            return True
        if hi <= lo:
            continue
        rounded = (tool.shape == "bull" and top <= tool.corner_radius_mm) or (
            tool.shape == "tapered" and tool.corner_radius_mm and top <= tool.corner_radius_mm
        )
        if not rounded:
            # Parameter q spans this interval. Linear radius yields a quadratic.
            fm = clearance((lo + hi) / 2)
            a = 2 * (f1 + f0 - 2 * fm)
            b = f1 - f0 - a
            if a < -1e-14:
                q = min(1.0, max(0.0, -b / (2 * a)))
                if clearance(lo + (hi - lo) * q) >= -1e-12:
                    return True
        else:
            # Bull radius squared is concave on its rounded lower section.
            ratio = (5**0.5 - 1) / 2
            left, right = hi - ratio * (hi - lo), lo + ratio * (hi - lo)
            fl, fr = clearance(left), clearance(right)
            for _ in range(60):
                if max(fl, fr) >= -1e-12:
                    return True
                if fl < fr:
                    lo, left, fl = left, right, fr
                    right = lo + ratio * (hi - lo)
                    fr = clearance(right)
                else:
                    hi, right, fr = right, left, fl
                    left = hi - ratio * (hi - lo)
                    fl = clearance(left)
            if clearance((lo + hi) / 2) >= -1e-12:
                return True
    return False


class StockVolume:
    """Occupied regular cells with exact cell volume and center-sampled boundary.

    Grid divides each requested stock dimension evenly; cell sizes may be a
    little smaller than requested resolution. Memory and iteration are bounded.
    Sweeps accept any fixed tool orientation. Changing rotary orientation must
    be divided into orientation-qualified segments by the path producer.
    """

    MAX_VOXELS = 8_000_000

    def __init__(
        self,
        bounds: AABB,
        resolution_mm: float = 1.0,
        max_voxels: int = MAX_VOXELS,
        *,
        rotation_deg: float = 0.0,
        pivot: Vec3 | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> None:
        if not isfinite(resolution_mm) or resolution_mm <= 0:
            raise ValueError("Resolution must be finite and positive")
        if not 1 <= max_voxels <= self.MAX_VOXELS:
            raise ValueError("Voxel budget exceeds bounded engine capacity")
        if type(rotation_deg) not in (int, float) or not isfinite(rotation_deg):
            raise ValueError("Stock rotation must be finite degrees")
        self.rotation_deg = (rotation_deg + 180) % 360 - 180
        self.pivot = pivot if pivot is not None else (bounds.minimum + bounds.maximum).scaled(0.5)
        if not isinstance(self.pivot, Vec3) or not all(isfinite(v) for v in self.pivot.tuple):
            raise ValueError("Stock pivot must contain finite program millimetres")
        self.grid_bounds = bounds
        self.bounds = self._mapped_bounds(bounds)
        self.resolution_mm = resolution_mm
        extents = bounds.maximum - bounds.minimum
        self.shape = tuple(ceil(v / resolution_mm) for v in extents.tuple)
        count = self.shape[0] * self.shape[1] * self.shape[2]
        if count > max_voxels:
            raise ValueError(f"Stock needs {count} voxels; budget is {max_voxels}. Increase resolution.")
        self.cell_size = Vec3(*(v / n for v, n in zip(extents.tuple, self.shape)))
        self.cell_volume_mm3 = self.cell_size.x * self.cell_size.y * self.cell_size.z
        self._occupied = self._copy_cells(count, cancelled=cancelled)
        self._remaining_count = count
        self._initial_count = count

    @staticmethod
    def _copy_cells(
        count: int, source: bytearray | None = None, *, cancelled: Callable[[], bool] | None = None
    ) -> bytearray:
        if cancelled is None:
            return source.copy() if source is not None else bytearray([1]) * count
        result = bytearray()
        for start in range(0, count, 65536):
            if cancelled():
                raise InterruptedError("Stock preparation cancelled")
            end = min(count, start + 65536)
            result.extend(source[start:end] if source is not None else b"\x01" * (end - start))
        if cancelled():
            raise InterruptedError("Stock preparation cancelled")
        return result

    def _map(self, point: Vec3, inverse: bool = False) -> Vec3:
        if not self.rotation_deg:
            return point
        angle = radians(-self.rotation_deg if inverse else self.rotation_deg)
        c, s = cos(angle), sin(angle)
        delta = point - self.pivot
        return self.pivot + Vec3(c * delta.x - s * delta.y, s * delta.x + c * delta.y, delta.z)

    def program_point(self, point: Vec3) -> Vec3:
        """Map a grid-frame millimetre point into the program frame."""
        return self._map(point)

    def program_direction(self, direction: Vec3) -> Vec3:
        """Rotate a vector without translating it around the stock pivot."""
        angle = radians(self.rotation_deg)
        c, s = cos(angle), sin(angle)
        return Vec3(c * direction.x - s * direction.y, s * direction.x + c * direction.y, direction.z)

    def _mapped_bounds(self, bounds: AABB, inverse: bool = False) -> AABB:
        corners = [
            self._map(Vec3(x, y, z), inverse)
            for x in (bounds.minimum.x, bounds.maximum.x)
            for y in (bounds.minimum.y, bounds.maximum.y)
            for z in (bounds.minimum.z, bounds.maximum.z)
        ]
        return AABB(
            Vec3(*(min(p.tuple[i] for p in corners) for i in range(3))),
            Vec3(*(max(p.tuple[i] for p in corners) for i in range(3))),
        )

    def grid_center(self, x: int, y: int, z: int) -> Vec3:
        return Vec3(
            *(
                lo + (i + 0.5) * size
                for lo, i, size in zip(self.grid_bounds.minimum.tuple, (x, y, z), self.cell_size.tuple)
            )
        )

    def _index(self, x: int, y: int, z: int) -> int:
        nx, ny, _ = self.shape
        return x + nx * (y + ny * z)

    def center(self, x: int, y: int, z: int) -> Vec3:
        return self._map(self.grid_center(x, y, z))

    @property
    def remaining_volume_mm3(self) -> float:
        return self._remaining_count * self.cell_volume_mm3

    @property
    def removed_volume_mm3(self) -> float:
        return (self._initial_count - self._remaining_count) * self.cell_volume_mm3

    @property
    def memory_bytes(self) -> int:
        return len(self._occupied)

    def occupied(self, x: int, y: int, z: int) -> bool:
        if not all(0 <= i < n for i, n in zip((x, y, z), self.shape)):
            return False
        return bool(self._occupied[self._index(x, y, z)])

    def subtract(self, sweep: SweptTool, *, cancelled: Callable[[], bool] | None = None) -> RemovalResult:
        """Publish a whole completed sweep; cancellation retains prior occupancy.

        Stage mutations in one bounded grid copy, allocated only on the first
        hit. Check every 128 candidate cells, including unoccupied cells, and
        once more before publishing. No partial segment enters rest stock.
        """
        if cancelled and cancelled():
            raise InterruptedError("Stock removal cancelled")
        cutter_bounds = sweep.component_bounds()[0][1]
        if not self.bounds.intersects(cutter_bounds):
            return RemovalResult(0, 0, self.remaining_volume_mm3, self.resolution_mm)
        ranges = []
        local_bounds = self._mapped_bounds(cutter_bounds, inverse=True)
        for lo, hi, base, size, n in zip(
            local_bounds.minimum.tuple,
            local_bounds.maximum.tuple,
            self.grid_bounds.minimum.tuple,
            self.cell_size.tuple,
            self.shape,
        ):
            ranges.append(range(max(0, floor((lo - base) / size)), min(n, ceil((hi - base) / size))))
        removed = 0
        visited = 0
        proposed = None
        radius = sweep.tool.diameter_mm / 2
        sphere_offset = sweep.axis.scaled(radius)
        # Express every candidate point and translation in a tool-axis basis.
        # Axial cylinders retain analytic continuous-sweep tests after rotation.
        axis = sweep.axis
        reference = Vec3(1, 0, 0) if abs(axis.x) < 0.9 else Vec3(0, 1, 0)
        perpendicular = Vec3(
            axis.y * reference.z - axis.z * reference.y,
            axis.z * reference.x - axis.x * reference.z,
            axis.x * reference.y - axis.y * reference.x,
        )
        u = perpendicular.scaled(1 / perpendicular.length)
        v = Vec3(axis.y * u.z - axis.z * u.y, axis.z * u.x - axis.x * u.z, axis.x * u.y - axis.y * u.x)

        def local(point: Vec3) -> Vec3:
            return Vec3(*(sum(a * b for a, b in zip(point.tuple, basis.tuple)) for basis in (u, v, axis)))

        local_start, local_end = local(sweep.start), local(sweep.end)
        for z in ranges[2]:
            for y in ranges[1]:
                for x in ranges[0]:
                    if visited % 128 == 0 and cancelled and cancelled():
                        raise InterruptedError("Stock removal cancelled")
                    visited += 1
                    index = self._index(x, y, z)
                    if not self._occupied[index]:
                        continue
                    p = self.center(x, y, z)
                    if sweep.tool.shape == "flat":
                        hit = _cylinder_hit(local(p), local_start, local_end, radius, 0, sweep.tool.flute_length_mm)
                    elif sweep.tool.shape == "ball":
                        hit = _sphere_hit(p, sweep.start + sphere_offset, sweep.end + sphere_offset, radius)
                        hit = hit or _cylinder_hit(
                            local(p), local_start, local_end, radius, radius, sweep.tool.flute_length_mm
                        )
                    else:
                        hit = _profile_hit(local(p), local_start, local_end, sweep.tool)
                    if hit:
                        if proposed is None:
                            proposed = self._occupied.copy()
                        proposed[index] = 0
                        removed += 1
        if cancelled and cancelled():
            raise InterruptedError("Stock removal cancelled")
        if proposed is not None:
            self._occupied = proposed
        self._remaining_count -= removed
        return RemovalResult(removed, removed * self.cell_volume_mm3, self.remaining_volume_mm3, self.resolution_mm)

    def compare_target(self, target: StockVolume) -> dict[str, float]:
        """Rest material (extra stock) and gouges (missing target cells)."""
        if (self.grid_bounds, self.shape, self.rotation_deg, self.pivot) != (
            target.grid_bounds,
            target.shape,
            target.rotation_deg,
            target.pivot,
        ):
            raise ValueError("Target and machined stock must use identical grids")
        extra = sum(a and not b for a, b in zip(self._occupied, target._occupied))
        missing = sum(b and not a for a, b in zip(self._occupied, target._occupied))
        return {
            "rest_volume_mm3": extra * self.cell_volume_mm3,
            "gouge_volume_mm3": missing * self.cell_volume_mm3,
            "resolution_mm": self.resolution_mm,
        }

    def top_surface(self, max_points: int = 100_000) -> tuple[tuple[float, float, float], ...]:
        """Height map of top occupied cell surfaces, omitting empty columns."""
        result = []
        nx, ny, nz = self.shape
        for y in range(ny):
            for x in range(nx):
                for z in range(nz - 1, -1, -1):
                    if self.occupied(x, y, z):
                        p = self.center(x, y, z)
                        if len(result) >= max_points:
                            raise ValueError("Height map output budget exceeded; increase resolution")
                        result.append((p.x, p.y, p.z + self.cell_size.z / 2))
                        break
        return tuple(result)

    def boundary_boxes(self, max_boxes: int = 100000) -> tuple[AABB, ...]:
        """Render exposed occupied cells; bounded output fails explicitly."""
        result = []
        nx, ny, nz = self.shape
        half = self.cell_size.scaled(0.5)
        neighbours = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))
        for z in range(nz):
            for y in range(ny):
                for x in range(nx):
                    if self.occupied(x, y, z) and any(
                        not self.occupied(x + dx, y + dy, z + dz) for dx, dy, dz in neighbours
                    ):
                        if len(result) >= max_boxes:
                            raise ValueError("Boundary render budget exceeded; increase voxel resolution")
                        center = self.grid_center(x, y, z)
                        result.append(self._mapped_bounds(AABB(center - half, center + half)))
        return tuple(result)

    def clone(self, *, cancelled: Callable[[], bool] | None = None) -> StockVolume:
        """Independent stock state for second setup or cancellable UI previews."""
        result = StockVolume(
            self.grid_bounds, self.resolution_mm, rotation_deg=self.rotation_deg, pivot=self.pivot, cancelled=cancelled
        )
        result._occupied = self._copy_cells(len(self._occupied), self._occupied, cancelled=cancelled)
        result._remaining_count = self._remaining_count
        result._initial_count = self._initial_count
        return result

    def occupied_boxes(
        self,
        bounds: AABB | None = None,
        *,
        cancelled: Callable[[], bool] | None = None,
        max_boxes: int = 100_000,
    ) -> Iterator[AABB]:
        """Occupied cell envelopes, compressed into contiguous grid-X runs.

        Rotated runs use conservative program-axis bounds, not exact oriented
        boxes. These are collision candidates; boundary rendering uses actual
        transformed vertices instead of those enclosing boxes.

        Removal still classifies cell centers. Empty cells therefore do not
        establish that all physical material in their volume has been removed.
        A bounds query limits enumeration, never discards a contacting cell.
        """
        if isinstance(max_boxes, bool) or not isinstance(max_boxes, int) or not 1 <= max_boxes <= 100_000:
            raise ValueError("Occupied stock box budget must be 1..100000")
        if bounds and not self.bounds.intersects(bounds):
            return
        if not self._remaining_count:
            return
        if self._remaining_count == len(self._occupied):
            if cancelled and cancelled():
                raise InterruptedError("Stock query cancelled")
            yield self.bounds
            return
        ranges = []
        query = self._mapped_bounds(bounds, inverse=True) if bounds else self.grid_bounds
        for lo, hi, base, size, n in zip(
            query.minimum.tuple, query.maximum.tuple, self.grid_bounds.minimum.tuple, self.cell_size.tuple, self.shape
        ):
            # Include cells touching a query boundary, including exact grid planes.
            ranges.append(range(max(0, ceil((lo - base) / size) - 1), min(n, floor((hi - base) / size) + 1)))
        count = 0
        for z in ranges[2]:
            for y in ranges[1]:
                if cancelled and cancelled():
                    raise InterruptedError("Stock query cancelled")
                begin = self._index(ranges[0].start, y, z)
                end = self._index(ranges[0].stop, y, z)
                cursor = begin
                while cursor < end:
                    first = self._occupied.find(b"\x01", cursor, end)
                    if first < 0:
                        break
                    stop = self._occupied.find(b"\x00", first, end)
                    if stop < 0:
                        stop = end
                    if count >= max_boxes:
                        raise ValueError("Occupied stock box budget exceeded; increase resolution or isolate motion")
                    x = ranges[0].start + first - begin
                    low = self.grid_bounds.minimum + Vec3(
                        x * self.cell_size.x, y * self.cell_size.y, z * self.cell_size.z
                    )
                    high = low + Vec3((stop - first) * self.cell_size.x, self.cell_size.y, self.cell_size.z)
                    yield self._mapped_bounds(AABB(low, high))
                    count += 1
                    cursor = stop

    def collision_contacts(
        self,
        sweep: SweptTool,
        *,
        cutting: bool = True,
        cancelled: Callable[[], bool] | None = None,
    ) -> tuple[CollisionContact, ...]:
        """Check bodies/rapid cutters against occupancy before this motion cuts."""
        contacts = []
        for section in sweep.sections():
            if section.component == "cutter" and cutting:
                continue
            earliest = None
            for box in self.occupied_boxes(sweep.section_bounds(section), cancelled=cancelled):
                if sweep.intersects_section(section, box):
                    contact = localized_contact(
                        sweep,
                        (section,),
                        "remaining stock",
                        box,
                        "Continuous cylinder envelopes against occupied cells; center-classified removal",
                    )
                    if earliest is None or (
                        contact.first_fraction is not None
                        and earliest.first_fraction is not None
                        and contact.first_fraction < earliest.first_fraction
                    ):
                        earliest = contact
                    if contact.first_fraction is None or contact.first_fraction == 0:
                        break  # Unknown tilt or contact at the start cannot be improved.
            if earliest is not None:
                contacts.append(earliest)
        return tuple(contacts)

    def snapshot(self, *, cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
        """JSON-safe compressed occupancy with integrity digest, not provenance."""
        import base64
        import hashlib
        import zlib

        data = bytes(self._copy_cells(len(self._occupied), self._occupied, cancelled=cancelled))
        if cancelled and cancelled():
            raise InterruptedError("Stock snapshot cancelled")
        compressor = zlib.compressobj()
        compressed = bytearray()
        digest = hashlib.sha256()
        for start in range(0, len(data), 65536):
            if cancelled and cancelled():
                raise InterruptedError("Stock snapshot cancelled")
            chunk = data[start : start + 65536]
            compressed.extend(compressor.compress(chunk))
            digest.update(chunk)
        compressed.extend(compressor.flush())
        if cancelled and cancelled():
            raise InterruptedError("Stock snapshot cancelled")
        result = {
            "schema": 3 if self._initial_count != len(self._occupied) else (2 if self.rotation_deg else 1),
            "units": "mm",
            "minimum": self.grid_bounds.minimum.tuple,
            "maximum": self.grid_bounds.maximum.tuple,
            "resolution_mm": self.resolution_mm,
            "occupancy_zlib_base64": base64.b64encode(compressed).decode("ascii"),
            "occupancy_sha256": digest.hexdigest(),
        }

        if self.rotation_deg or result["schema"] == 3:
            result.update(rotation_deg=self.rotation_deg, pivot_mm=self.pivot.tuple)
        if result["schema"] == 3:
            result["initial_occupied_voxels"] = self._initial_count
        return result

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any], *, cancelled: Callable[[], bool] | None = None) -> StockVolume:
        import base64
        import hashlib
        import zlib

        if cancelled and cancelled():
            raise InterruptedError("Stock snapshot cancelled")

        if (
            type(snapshot.get("schema")) is not int
            or snapshot.get("schema") not in (1, 2, 3)
            or snapshot.get("units") != "mm"
        ):
            raise ValueError("Unsupported stock snapshot schema or units")
        pose_keys = {"rotation_deg", "pivot_mm"}
        if (snapshot["schema"] == 1 and pose_keys.intersection(snapshot)) or (
            snapshot["schema"] in (2, 3) and not pose_keys.issubset(snapshot)
        ):
            raise ValueError("Stock snapshot orientation does not match its schema")
        if snapshot["schema"] != 3 and "initial_occupied_voxels" in snapshot:
            raise ValueError("Stock snapshot initial material does not match its schema")
        result = cls(
            AABB(Vec3(*snapshot["minimum"]), Vec3(*snapshot["maximum"])),
            snapshot["resolution_mm"],
            rotation_deg=snapshot["rotation_deg"] if snapshot["schema"] in (2, 3) else 0,
            pivot=Vec3(*snapshot["pivot_mm"]) if snapshot["schema"] in (2, 3) else None,
            cancelled=cancelled,
        )
        payload = snapshot["occupancy_zlib_base64"]
        if not isinstance(payload, str) or len(payload) > cls.MAX_VOXELS * 2:
            raise ValueError("Stock snapshot payload exceeds bounded input")
        compressed = base64.b64decode(payload, validate=True)
        decoder = zlib.decompressobj()
        data = bytearray()
        digest = hashlib.sha256()
        count = 0
        for start in range(0, len(compressed), 65536):
            if cancelled and cancelled():
                raise InterruptedError("Stock snapshot cancelled")
            chunk = decoder.decompress(compressed[start : start + 65536], len(result._occupied) + 1 - len(data))
            if len(data) + len(chunk) > len(result._occupied) or decoder.unused_data or decoder.unconsumed_tail:
                raise ValueError("Invalid or oversized stock occupancy")
            # Highly compressible chunks can expand to millions of cells. Keep
            # validation/digest work bounded independently of compressed size.
            for offset in range(0, len(chunk), 65536):
                if cancelled and cancelled():
                    raise InterruptedError("Stock snapshot cancelled")
                part = chunk[offset : offset + 65536]
                if any(v not in (0, 1) for v in part):
                    raise ValueError("Invalid or oversized stock occupancy")
                digest.update(part)
                count += sum(part)
                data.extend(part)
        if len(data) != len(result._occupied) or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError("Invalid or oversized stock occupancy")
        if digest.hexdigest() != snapshot["occupancy_sha256"]:
            raise ValueError("Stock snapshot integrity mismatch")
        initial = snapshot.get("initial_occupied_voxels") if snapshot["schema"] == 3 else len(result._occupied)
        if type(initial) is not int or not count <= initial <= len(result._occupied):
            raise ValueError("Stock snapshot initial material count is invalid")
        if cancelled and cancelled():
            raise InterruptedError("Stock snapshot cancelled")
        result._occupied = data
        result._remaining_count = count
        result._initial_count = initial
        return result
