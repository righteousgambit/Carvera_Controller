"""Actual source surfaces, placement, persistence identity and residual admission."""

import copy
import json
import math
from dataclasses import replace

import pytest

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_model import StockModel, stock_reference, validate_residual_stock
from carveracontroller.addons.manufacturing_simulation import SweptTool, ToolGeometry, Vec3
from tests.unit.test_stock_solid import box, l_stock, mesh


def model(tmp_path, triangles=None):
    source = mesh(tmp_path, l_stock() if triangles is None else triangles)
    return StockModel.load(source.source_path, "mm")


@pytest.mark.parametrize("rotation", [0, 37, 90, -125])
def test_preview_uses_actual_source_triangles_with_independent_placement(tmp_path, rotation):
    source = model(tmp_path)
    setup = MachineSetup((10, 20, 30), source.size_mm, (4, 5, 6), False, rotation, source)
    geometry = setup.stock_mesh()
    assert isinstance(geometry, GeometrySnapshot)
    assert len(geometry.indices) == len(l_stock()) * 3
    c, s = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))

    def expected(p):
        x, y, z = p[0] - 1.5, p[1] - 1.5, p[2]
        return 10 + 4 + 1.5 + c * x - s * y, 20 + 5 + 1.5 + s * x + c * y, 30 + 6 + z

    actual = [geometry.vertices[i * 10 : i * 10 + 3] for i in geometry.indices]
    expected_points = [expected(p) for triangle in l_stock() for p in triangle]
    for point, expected_point in zip(actual, expected_points):
        assert point == pytest.approx(expected_point)
    for i in range(0, len(geometry.vertices), 10):
        assert math.hypot(*geometry.vertices[i + 3 : i + 6]) == pytest.approx(1)
    assert source.geometry(setup, (0.70, 0.49, 0.25, 0.20)) is geometry
    wire = setup.stock_mesh(wireframe=True)
    edges = {
        tuple(sorted((expected(a), expected(b))))
        for tri in l_stock()
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0]))
    }
    assert len(wire.indices) == 2 * len(edges)


def test_record_and_deepcopy_do_not_serialize_or_copy_internal_geometry(tmp_path):
    source = model(tmp_path)
    setup = MachineSetup(stock_size_mm=source.size_mm, stock_model=source)
    source.prepare_preview(setup, 1)
    assert copy.deepcopy(setup).stock_model is source
    record = json.loads(json.dumps(setup.record()))
    assert record["stock_source"]["source_sha256"] == source.source_sha256
    assert "solid" not in json.dumps(record) and "_cache" not in json.dumps(record)
    assert StockModel.from_reference(source.reference) == source
    detached = source.reference
    detached["source_path"] = "other"
    assert source.reference["source_path"] != detached["source_path"]
    with pytest.raises(ValueError, match="dimensions"):
        replace(setup, stock_size_mm=(1, 1, 1))


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", 2),
        ("source_units", "auto"),
        ("source_sha256", "x" * 64),
        ("source_path", ""),
        ("minimum_mm", [math.nan, 0, 0]),
        ("maximum_mm", [0, 0, 0]),
    ],
)
def test_invalid_source_reference_cannot_fall_back_to_a_box(tmp_path, key, value):
    source = model(tmp_path)
    reference = source.reference
    reference[key] = value
    with pytest.raises(ValueError):
        stock_reference(reference)


def test_changed_bytes_or_forged_source_bounds_are_refused(tmp_path):
    source = model(tmp_path)
    forged = source.reference
    forged["maximum_mm"] = (10, 10, 10)
    with pytest.raises(ValueError, match="bounds"):
        StockModel.from_reference(forged)
    mesh(tmp_path, box((0, 0, 0), (3, 3, 2)))
    with pytest.raises(ValueError, match="bytes changed"):
        StockModel.from_reference(source.reference)


@pytest.mark.parametrize("rotation", [0, 37])
def test_residual_shape_and_initial_material_count_are_both_required(tmp_path, rotation):
    source = model(tmp_path)
    setup = MachineSetup(stock_size_mm=source.size_mm, stock_rotation_deg=rotation, stock_model=source)
    stock = source.solid.voxelize(0.5, rotation_deg=rotation).stock
    validate_residual_stock(setup, stock)
    cutter = ToolGeometry(0.6, 2, 0.6, 5)
    stock.subtract(SweptTool(stock.program_point(Vec3(-1, 0.5, 0)), stock.program_point(Vec3(4, 0.5, 0)), cutter))
    validate_residual_stock(setup, stock)
    forged = stock.clone()
    empty = next(
        i
        for i, (a, b) in enumerate(
            zip(forged._occupied, source.solid.voxelize(0.5, rotation_deg=rotation).stock._occupied)
        )
        if not a and not b
    )
    forged._occupied[empty] = 1
    forged._remaining_count += 1
    with pytest.raises(ValueError, match="outside"):
        validate_residual_stock(setup, forged)
    forged = stock.clone()
    forged._initial_count += 1
    with pytest.raises(ValueError, match="initial material count"):
        validate_residual_stock(setup, forged)
    with pytest.raises(ValueError, match="placement"):
        validate_residual_stock(replace(setup, stock_origin_mm=(1, 0, 0)), stock)


@pytest.mark.parametrize("stop", [1, 3, 6])
def test_cancelled_preview_does_not_replace_previous_cached_geometry(tmp_path, stop):
    source = model(tmp_path)
    previous = MachineSetup(stock_size_mm=source.size_mm, stock_model=source)
    geometry = previous.stock_mesh()
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == stop

    with pytest.raises(InterruptedError):
        source.geometry(replace(previous, stock_origin_mm=(4, 5, 6)), (0.70, 0.49, 0.25, 0.20), cancelled=cancelled)
    assert previous.stock_mesh() is geometry
    assert source.reference["source_sha256"] == source.solid.mesh.source_sha256


def test_edge_batches_keep_pairs_and_unsigned_short_limits():
    values = [v for i in range(65538) for v in (i, 0, 0, 0, 0, 1, 1, 1, 1, 1)]
    geometry = GeometrySnapshot(values, list(range(65538)))
    batches = geometry.render_line_batches((2, 0, 0), 0.5)
    assert [len(indices) for _, indices in batches] == [65534, 4]
    assert all(len(indices) % 2 == 0 and max(indices) < 65535 for _, indices in batches)
    assert batches[0][0][0] == -1
    assert batches[1][0][0] == (65534 - 2) * 0.5
    assert geometry.render_line_batches((2, 0, 0), 0.5) is batches


def test_render_buffer_cancellation_preserves_prepared_frame():
    geometry = GeometrySnapshot([v for i in range(600) for v in (i, 0, 0, 0, 0, 1, 1, 1, 1, 1)], list(range(600)))
    before = geometry.render_batches((0, 0, 0))
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == 3

    with pytest.raises(InterruptedError):
        geometry.render_batches((1, 0, 0), cancelled=cancelled)
    assert geometry.render_batches((0, 0, 0)) is before


def test_nonzero_source_and_fractional_placement_use_identical_residual_grid(tmp_path):
    from carveracontroller.addons.machine_simulation.stock_model import initial_stock

    source = model(tmp_path, box((0.1, 0.3, 0.7), (3.1, 3.3, 2.7)))
    setup = MachineSetup(stock_size_mm=source.size_mm, stock_origin_mm=(0.2, 0.4, 0.8), stock_model=source)
    stock = initial_stock(setup, 0.5)
    validate_residual_stock(setup, stock)
    validate_residual_stock(setup, type(stock).from_snapshot(stock.snapshot()))


def test_imported_tilt_keeps_actual_vertices_normals_voids_and_residual_identity(tmp_path):
    from carveracontroller.addons.machine_simulation.stock_model import initial_stock
    from tests.unit.test_stock_orientation import oracle

    source = model(tmp_path)
    setup = MachineSetup((10, 20, 30), source.size_mm, (4, 5, 6), False, 41, source, (23, -32))
    base = replace(setup, stock_rotation_deg=0, stock_tilt_deg=(0, 0))
    independent = oracle((23, -32, 41), Vec3(*(a + b / 2 for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm))))
    plain, tilted = base.stock_mesh(), setup.stock_mesh()
    for offset in range(0, len(plain.vertices), 10):
        program = Vec3(*(plain.vertices[offset + axis] - setup.work_offset_mm[axis] for axis in range(3)))
        wanted = independent.apply(program) + Vec3(*setup.work_offset_mm)
        assert tilted.vertices[offset : offset + 3] == pytest.approx(wanted.tuple)
        assert tilted.vertices[offset + 3 : offset + 6] == pytest.approx(
            independent.direction(Vec3(*plain.vertices[offset + 3 : offset + 6])).tuple
        )
    unrotated, oriented = initial_stock(base, 0.5), initial_stock(setup, 0.5)
    assert 0 < sum(oriented._occupied) < len(oriented._occupied)  # Preserve the L-stock void.
    assert oriented._occupied == unrotated._occupied
    validate_residual_stock(setup, oriented)
    with pytest.raises(ValueError, match="placement differs"):
        validate_residual_stock(base, oriented)
    assert source.geometry(replace(setup, stock_tilt_deg=(24, -32)), (0.70, 0.49, 0.25, 0.20)) is not tilted
