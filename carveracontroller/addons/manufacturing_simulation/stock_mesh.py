"""Bounded stock STL input with explicit units and manifold topology.

Topology checks do not establish a non-self-intersecting solid. This detached
input deliberately does not initialize simulator occupancy or claim measured
stock. Geometric validation, placement and occupancy acceptance remain separate.
"""

from __future__ import annotations

import hashlib
import math
import struct
from collections import Counter, defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from carveracontroller.addons.cad_identity import read_asset_bytes

Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]
MAX_BYTES = 24 * 1024 * 1024
MAX_TRIANGLES = 100_000
MAX_COORDINATE_MM = 100_000


def _cancel(cancelled: Callable[[], bool] | None) -> None:
    if cancelled and cancelled():
        raise InterruptedError("Stock mesh preparation cancelled")


def _ascii_points(raw: bytes, cancelled: Callable[[], bool] | None) -> list[Point]:
    """Read STL grammar strictly; ignored extra vertices cannot change topology."""
    try:
        lines = iter(raw.decode("ascii").splitlines())
    except UnicodeDecodeError as exc:
        raise ValueError("Stock STL must be complete binary or ASCII STL") from exc
    points: list[Point] = []
    state = "solid"
    vertex_count = 0
    for count, line in enumerate(lines):
        if count % 128 == 0:
            _cancel(cancelled)
        tokens = line.split()
        if not tokens:
            continue
        if state == "solid" and tokens[0] == "solid":
            state = "facet"
        elif state == "facet" and tokens[0] == "endsolid":
            state = "done"
        elif state == "facet" and len(tokens) == 5 and tokens[:2] == ["facet", "normal"]:
            if not all(math.isfinite(float(v)) for v in tokens[2:]):
                raise ValueError("Stock STL has a nonfinite normal")
            state = "loop"
        elif state == "loop" and tokens == ["outer", "loop"]:
            vertex_count = 0
            state = "vertices"
        elif state == "vertices" and len(tokens) == 4 and tokens[0] == "vertex" and vertex_count < 3:
            x, y, z = (float(v) for v in tokens[1:])
            points.append((x, y, z))
            vertex_count += 1
            if len(points) > MAX_TRIANGLES * 3:
                raise ValueError("Stock mesh exceeds triangle budget")
        elif state == "vertices" and vertex_count == 3 and tokens == ["endloop"]:
            state = "endfacet"
        elif state == "endfacet" and tokens == ["endfacet"]:
            state = "facet"
        else:
            raise ValueError("Malformed or incomplete ASCII stock STL")
    if state != "done" or not points:
        raise ValueError("Malformed or incomplete ASCII stock STL")
    return points


def _topology(triangles: Sequence[Triangle], cancelled: Callable[[], bool] | None) -> None:
    edges: Counter[tuple[Point, Point]] = Counter()
    directed: Counter[tuple[Point, Point]] = Counter()
    faces: set[tuple[Point, ...]] = set()
    links: dict[Point, dict[Point, set[Point]]] = defaultdict(lambda: defaultdict(set))
    for index, (a, b, c) in enumerate(triangles):
        if index % 128 == 0:
            _cancel(cancelled)
        ab = tuple(b[i] - a[i] for i in range(3))
        ac = tuple(c[i] - a[i] for i in range(3))
        cross = (ab[1] * ac[2] - ab[2] * ac[1], ab[2] * ac[0] - ab[0] * ac[2], ab[0] * ac[1] - ab[1] * ac[0])
        if a == b or b == c or c == a or not any(cross):
            raise ValueError("Stock mesh contains a degenerate triangle")
        face = tuple(sorted((a, b, c)))
        if face in faces:
            raise ValueError("Stock mesh contains a duplicate face")
        faces.add(face)
        for vertex, p, q in ((a, b, c), (b, c, a), (c, a, b)):
            links[vertex][p].add(q)
            links[vertex][q].add(p)
            edges[(p, q) if p < q else (q, p)] += 1
            directed[(p, q)] += 1
    for index, ((p, q), count) in enumerate(edges.items()):
        if index % 128 == 0:
            _cancel(cancelled)
        if count != 2:
            raise ValueError("Stock mesh is open or has a nonmanifold edge")
        if directed[(p, q)] != 1 or directed[(q, p)] != 1:
            raise ValueError("Stock mesh has inconsistent face winding")
    # Two closed shells touching at a single vertex pass edge-incidence checks,
    # but their disconnected vertex link is not a manifold surface.
    for index, neighbours in enumerate(links.values()):
        if index % 128 == 0:
            _cancel(cancelled)
        if any(len(adjacent) != 2 for adjacent in neighbours.values()):
            raise ValueError("Stock mesh has a nonmanifold vertex")
        pending = [next(iter(neighbours))]
        seen: set[Point] = set()
        while pending:
            if len(seen) % 128 == 0:
                _cancel(cancelled)
            point = pending.pop()
            if point not in seen:
                seen.add(point)
                pending.extend(neighbours[point] - seen)
        if len(seen) != len(neighbours):
            raise ValueError("Stock mesh has a nonmanifold vertex")
    _cancel(cancelled)


@dataclass(frozen=True, init=False)
class StockMeshInput:
    """Immutable, topology-checked stock-local mm triangles from exact STL bytes.

    No automatic welding, scaling guess, centering or orientation repair occurs.
    Self-intersection and shell containment are deliberately still unverified.
    """

    source_path: str
    source_sha256: str
    source_units: Literal["mm", "inch"]
    triangles_mm: tuple[Triangle, ...]
    minimum_mm: Point
    maximum_mm: Point

    def __init__(self) -> None:
        raise TypeError("Use StockMeshInput.load to validate detached source bytes")

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        units: Literal["mm", "inch"],
        expected_sha256: str | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> StockMeshInput:
        if units not in ("mm", "inch"):
            raise ValueError("Stock mesh requires explicit mm or inch source units")
        source = Path(path).expanduser()
        if source.suffix.lower() != ".stl":
            raise ValueError("Stock mesh input currently requires STL")
        source = source.resolve()
        raw = read_asset_bytes(source, MAX_BYTES, cancelled=cancelled)
        digest = hashlib.sha256(raw).hexdigest()
        if expected_sha256 is not None and expected_sha256 != digest:
            raise ValueError("Stock mesh bytes changed; reload the selected asset")
        _cancel(cancelled)
        count = struct.unpack_from("<I", raw, 80)[0] if len(raw) >= 84 else 0
        points: list[Point] = []
        if len(raw) >= 84 and len(raw) == 84 + count * 50:
            if not 1 <= count <= MAX_TRIANGLES:
                raise ValueError("Stock mesh exceeds triangle budget or is empty")
            for index in range(count):
                if index % 128 == 0:
                    _cancel(cancelled)
                normal = struct.unpack_from("<3f", raw, 84 + index * 50)
                if not all(math.isfinite(v) for v in normal):
                    raise ValueError("Stock STL has a nonfinite normal")
                values = struct.unpack_from("<9f", raw, 84 + index * 50 + 12)
                points.extend((values[i], values[i + 1], values[i + 2]) for i in (0, 3, 6))
        else:
            points = _ascii_points(raw, cancelled)
        scale = 1.0 if units == "mm" else 25.4
        scaled: list[Point] = []
        minimum = [math.inf] * 3
        maximum = [-math.inf] * 3
        for index, point in enumerate(points):
            if index % 128 == 0:
                _cancel(cancelled)
            x, y, z = (v * scale for v in point)
            if any(not math.isfinite(v) or abs(v) > MAX_COORDINATE_MM for v in (x, y, z)):
                raise ValueError("Stock mesh coordinates must be finite and within 100000 mm")
            scaled.append((x, y, z))
            for axis, value in enumerate((x, y, z)):
                minimum[axis] = min(minimum[axis], value)
                maximum[axis] = max(maximum[axis], value)
        triangles = tuple((scaled[i], scaled[i + 1], scaled[i + 2]) for i in range(0, len(scaled), 3))
        _topology(triangles, cancelled)
        if any(low >= high for low, high in zip(minimum, maximum)):
            raise ValueError("Stock mesh needs positive extent on every axis")
        _cancel(cancelled)
        result = object.__new__(cls)
        for name, field_value in (
            ("source_path", str(source)),
            ("source_sha256", digest),
            ("source_units", units),
            ("triangles_mm", triangles),
            ("minimum_mm", (minimum[0], minimum[1], minimum[2])),
            ("maximum_mm", (maximum[0], maximum[1], maximum[2])),
        ):
            object.__setattr__(result, name, field_value)
        return result
