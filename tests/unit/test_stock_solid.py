"""Analytic solids, cavities and actual machining occupancy, without hardware."""

import math
from dataclasses import FrozenInstanceError
from itertools import product

import pytest

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, ToolGeometry, Vec3
from carveracontroller.addons.manufacturing_simulation.stock_mesh import StockMeshInput
from carveracontroller.addons.manufacturing_simulation.stock_solid import StockSolid


def faces(low, high):
    x, y, z = low
    X, Y, Z = high
    return (
        ((x, y, z), (x, y, Z), (x, Y, Z), (x, Y, z)),
        ((X, y, z), (X, Y, z), (X, Y, Z), (X, y, Z)),
        ((x, y, z), (X, y, z), (X, y, Z), (x, y, Z)),
        ((x, Y, z), (x, Y, Z), (X, Y, Z), (X, Y, z)),
        ((x, y, z), (x, Y, z), (X, Y, z), (X, y, z)),
        ((x, y, Z), (X, y, Z), (X, Y, Z), (x, Y, Z)),
    )


def triangulate(quads):
    return [t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))]


def box(low=(0, 0, 0), high=(2, 2, 2)):
    return triangulate(faces(low, high))


def reverse(triangles):
    return [(a, c, b) for a, b, c in triangles]


def l_stock():
    cells = {(x, y) for x in range(3) for y in range(3) if x == 0 or y == 0}
    quads = []
    for x, y in sorted(cells):
        neighbors = ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1), None, None)
        quads.extend(f for f, neighbor in zip(faces((x, y, 0), (x + 1, y + 1, 2)), neighbors) if neighbor not in cells)
    return triangulate(quads)


def wedge():
    p = ((0, 0, 0), (4, 0, 0), (0, 3, 0), (0, 0, 5), (4, 0, 5), (0, 3, 5))
    return [
        tuple(p[i] for i in ids)
        for ids in ((0, 2, 1), (3, 4, 5), (0, 1, 4), (0, 4, 3), (1, 2, 5), (1, 5, 4), (2, 0, 3), (2, 3, 5))
    ]


def mesh(tmp_path, triangles, units="mm"):
    path = tmp_path / "stock.stl"
    lines = ["solid stock"]
    for triangle in triangles:
        lines += ["facet normal 0 0 0", "outer loop"]
        lines += ["vertex " + " ".join(str(v) for v in p) for p in triangle]
        lines += ["endloop", "endfacet"]
    path.write_text("\n".join(lines + ["endsolid stock"]) + "\n")
    return StockMeshInput.load(path, units=units)


@pytest.mark.parametrize("inverted", [False, True])
@pytest.mark.parametrize(
    "triangles,volume,shells",
    [
        (box(), 8, 1),
        (wedge(), 30, 1),
        (l_stock(), 10, 1),
        (box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4))), 98, 2),
        (box() + reverse(box((3, 0, 0), (5, 2, 2))), 16, 2),
        (box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4))) + box((2, 2, 2), (3, 3, 3)), 99, 3),
    ],
)
def test_constructive_shapes_and_global_winding(tmp_path, triangles, volume, shells, inverted):
    solid = StockSolid.validate(mesh(tmp_path, reverse(triangles) if inverted else triangles))
    assert solid.material_volume_mm3 == pytest.approx(volume)
    assert solid.shell_count == shells
    with pytest.raises(FrozenInstanceError):
        solid.shell_count = 100


@pytest.mark.parametrize(
    "triangles,inside",
    [
        (box(), lambda x, y, z: 0 <= x <= 2 and 0 <= y <= 2 and 0 <= z <= 2),
        (wedge(), lambda x, y, z: x >= 0 and y >= 0 and 3 * x + 4 * y <= 12 and 0 <= z <= 5),
        (l_stock(), lambda x, y, z: 0 <= x <= 3 and 0 <= y <= 3 and 0 <= z <= 2 and (x <= 1 or y <= 1)),
        (
            box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4))),
            lambda x, y, z: all(0 <= v <= 5 for v in (x, y, z)) and not all(1 < v < 4 for v in (x, y, z)),
        ),
    ],
)
def test_membership_matches_analytic_shape_including_edges_and_vertices(tmp_path, triangles, inside):
    solid = StockSolid.validate(mesh(tmp_path, triangles))
    for point in product((-0.5, 0, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5), repeat=3):
        assert solid.contains(point) == inside(*point), point


@pytest.mark.parametrize(
    "triangles,inside,volume",
    [
        (l_stock(), lambda x, y, z: x < 1 or y < 1, 10),
        (
            box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4))),
            lambda x, y, z: not all(1 < v < 4 for v in (x, y, z)),
            98,
        ),
        (box() + box((3, 0, 0), (5, 2, 2)), lambda x, y, z: x < 2 or x > 3, 16),
    ],
)
def test_initial_occupancy_matches_material_and_not_bounding_box(tmp_path, triangles, inside, volume):
    imported = StockSolid.validate(mesh(tmp_path, triangles)).voxelize(0.5)
    stock = imported.stock
    nx, ny, nz = stock.shape
    for x, y, z in product(range(nx), range(ny), range(nz)):
        assert stock.occupied(x, y, z) == inside(*stock.center(x, y, z).tuple)
    assert stock.remaining_volume_mm3 == volume
    assert stock.removed_volume_mm3 == 0  # Source cavities were never machined material.
    restored = StockVolume.from_snapshot(stock.snapshot())
    assert restored._occupied == stock._occupied
    assert restored.removed_volume_mm3 == 0


def test_closed_cavity_empty_motion_removes_nothing_and_solid_motion_removes_material(tmp_path):
    triangles = box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4)))
    imported = StockSolid.validate(mesh(tmp_path, triangles)).voxelize(0.25)
    cutter = ToolGeometry(0.5, 1, 0.5, 3)
    stock = imported.stock
    baseline = stock.snapshot()
    empty = stock.subtract(SweptTool(Vec3(2, 2.5, 2), Vec3(3, 2.5, 2), cutter))
    assert empty.removed_voxels == 0
    assert stock.snapshot() == baseline
    cut = stock.subtract(SweptTool(Vec3(0.5, 2, 2), Vec3(0.5, 3, 2), cutter))
    assert cut.removed_voxels > 0
    assert cut.remaining_volume_mm3 == 98 - cut.removed_volume_mm3
    assert stock.subtract(SweptTool(Vec3(0.5, 2, 2), Vec3(0.5, 3, 2), cutter)).removed_voxels == 0


@pytest.mark.parametrize("rotation", [0, 37, 90, -125])
def test_placement_cuts_clone_and_detached_identity(tmp_path, rotation):
    solid = StockSolid.validate(mesh(tmp_path, l_stock()))
    original = solid.voxelize(0.5)
    placed = solid.voxelize(0.5, translation_mm=(12, -7, 3), rotation_deg=rotation, pivot=Vec3(4, 5, 0))
    assert placed.stock._occupied == original.stock._occupied
    cutter = ToolGeometry(0.5, 2, 0.5, 5)
    original.stock.subtract(SweptTool(Vec3(-1, 0.5, 0), Vec3(4, 0.5, 0), cutter))
    # Independent 2D rotation of the translated program points around (4, 5).
    angle = math.radians(rotation)

    def map_point(point):
        x, y, z = point.x + 12 - 4, point.y - 7 - 5, point.z + 3
        return Vec3(4 + math.cos(angle) * x - math.sin(angle) * y, 5 + math.sin(angle) * x + math.cos(angle) * y, z)

    start, end = (map_point(p) for p in (Vec3(-1, 0.5, 0), Vec3(4, 0.5, 0)))
    assert placed.stock.center(0, 0, 0).tuple == pytest.approx(map_point(Vec3(0.25, 0.25, 0.25)).tuple)
    placed.stock.subtract(SweptTool(start, end, cutter))
    assert placed.stock._occupied == original.stock._occupied
    clone = placed.clone()
    assert clone.identity == placed.identity
    assert clone.stock._occupied == placed.stock._occupied
    assert clone.stock._occupied is not placed.stock._occupied
    assert clone.stock.removed_volume_mm3 == placed.stock.removed_volume_mm3
    restored = StockVolume.from_snapshot(placed.stock.snapshot())
    assert restored.removed_volume_mm3 == placed.stock.removed_volume_mm3
    detached = placed.identity
    detached["source_sha256"] = "changed"
    assert placed.identity["source_sha256"] == solid.mesh.source_sha256
    assert placed.identity["translation_mm"] == (12, -7, 3)
    assert "unverified" in placed.identity["qualification"]


@pytest.mark.parametrize(
    "triangles",
    [
        box() + box((1, 1, 1), (3, 3, 3)),  # Crossing closed shells.
        box() + box((2, 0.5, 0.5), (4, 1.5, 1.5)),  # Coplanar face contact, no shared vertex.
        box() + box((2, 2, 0.5), (4, 4, 1.5)),  # Contact along an edge segment.
        # Pulling this corner down crosses the bottom face along y=2/3, z=0.
        [tuple((1, 1, -1) if p == (2, 2, 2) else p for p in triangle) for triangle in box()],
        box((0, 0, 0), (5, 5, 5)) + box((1, 1, 1), (4, 4, 4)),  # Wrong cavity orientation.
    ],
)
def test_topologically_closed_but_geometrically_invalid_meshes_refused(tmp_path, triangles):
    source = mesh(tmp_path, triangles)  # Topology alone must not admit these solids.
    with pytest.raises(ValueError, match="intersect|touch|winding"):
        StockSolid.validate(source)


def test_tiny_separation_is_not_silently_welded(tmp_path):
    gap = math.nextafter(2.0, math.inf)
    solid = StockSolid.validate(mesh(tmp_path, box() + box((gap, 0, 0), (4, 2, 2))))
    assert solid.shell_count == 2
    assert solid.contains((2, 1, 1))
    assert solid.contains((gap, 1, 1))
    spaced = StockSolid.validate(mesh(tmp_path, box() + box((2 + 1e-9, 0, 0), (4, 2, 2))))
    assert not spaced.contains((2 + 0.5e-9, 1, 1))


def test_source_inches_and_world_placement_remain_distinct(tmp_path):
    solid = StockSolid.validate(mesh(tmp_path, box((1, 2, 3), (2, 3, 4)), units="inch"))
    imported = solid.voxelize(12.7, translation_mm=(-25.4, -50.8, -76.2))
    assert imported.stock.grid_bounds.minimum.tuple == pytest.approx((0, 0, 0))
    assert imported.stock.remaining_volume_mm3 == pytest.approx(25.4**3)
    assert imported.identity["source_units"] == "inch"
    assert solid.mesh.minimum_mm == pytest.approx((25.4, 50.8, 76.2))


@pytest.mark.parametrize("kwargs", [{"max_pairs": 1}, {"max_node_visits": 1}])
def test_validation_budget_fails_explicitly(tmp_path, kwargs):
    with pytest.raises(ValueError, match="budget"):
        StockSolid.validate(mesh(tmp_path, l_stock()), **kwargs)


@pytest.mark.parametrize("kwargs", [{"max_voxels": 1}, {"max_ray_tests": 1}, {"max_node_visits": 1}])
def test_voxel_work_budget_preserves_previous_result(tmp_path, kwargs):
    solid = StockSolid.validate(mesh(tmp_path, l_stock()))
    previous = solid.voxelize(0.5)
    before = previous.stock.snapshot()
    with pytest.raises(ValueError, match="budget"):
        solid.voxelize(0.5, **kwargs)
    assert previous.stock.snapshot() == before


@pytest.mark.parametrize("stop", [1, 3, 5, 8, 12, 20])
def test_cancelled_validation_and_voxelization_preserve_prior_input_and_stock(tmp_path, stop):
    source = mesh(tmp_path, l_stock())
    solid = StockSolid.validate(source)
    previous = solid.voxelize(0.5)
    snapshot = previous.stock.snapshot()
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == stop

    with pytest.raises(InterruptedError):
        solid.voxelize(0.25, cancelled=cancelled)
    assert calls == stop
    assert previous.stock.snapshot() == snapshot
    calls = 0
    with pytest.raises(InterruptedError):
        StockSolid.validate(source, cancelled=cancelled)
    assert source.triangles_mm == tuple(l_stock())


def test_cancellation_after_final_progress_abandons_publication(tmp_path):
    solid = StockSolid.validate(mesh(tmp_path, box()))
    progress = []
    with pytest.raises(InterruptedError):
        solid.voxelize(
            1,
            progress=lambda done, total: progress.append((done, total)),
            cancelled=lambda: bool(progress) and progress[-1][0] == progress[-1][1],
        )
    assert progress == [(1, 4), (2, 4), (3, 4), (4, 4)]


@pytest.mark.parametrize("point", [(math.nan, 0, 0), (math.inf, 0, 0), (True, 0, 0), (0, 0)])
def test_invalid_membership_query_refused(tmp_path, point):
    solid = StockSolid.validate(mesh(tmp_path, box()))
    with pytest.raises(ValueError, match="coordinates"):
        solid.contains(point)


def test_bypassing_geometric_validation_refused():
    with pytest.raises(TypeError, match="validate"):
        StockSolid()
    with pytest.raises(ValueError, match="topology"):
        StockSolid.validate(object())


@pytest.mark.parametrize("count", [None, True, -1, 1, 1000000, 5.5])
def test_imported_snapshot_refuses_invalid_initial_material_count(tmp_path, count):
    imported = StockSolid.validate(mesh(tmp_path, l_stock())).voxelize(0.5)
    snapshot = imported.stock.snapshot()
    assert snapshot["schema"] == 3
    snapshot["initial_occupied_voxels"] = count
    with pytest.raises(ValueError, match="initial material count"):
        StockVolume.from_snapshot(snapshot)


@pytest.mark.parametrize("schema", [1, 2])
def test_legacy_snapshot_cannot_silently_ignore_initial_material_count(tmp_path, schema):
    snapshot = (
        StockSolid.validate(mesh(tmp_path, box())).voxelize(1, rotation_deg=37 if schema == 2 else 0).stock.snapshot()
    )
    assert snapshot["schema"] == schema
    snapshot["initial_occupied_voxels"] = 1
    with pytest.raises(ValueError, match="does not match its schema"):
        StockVolume.from_snapshot(snapshot)


def test_voxel_position_precision_is_checked_before_sampling(tmp_path):
    solid = StockSolid.validate(mesh(tmp_path, box((0, 0, 0), (0.01, 0.01, 0.01))))
    with pytest.raises(ValueError, match="precision"):
        solid.voxelize(0.001, translation_mm=(1e13, 0, 0))
