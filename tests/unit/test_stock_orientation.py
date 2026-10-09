"""Independent rigid-transform oracle and material covariance for full stock placement."""

import json
from dataclasses import replace

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_projection import facing_envelope, project_block
from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    StockVolume,
    SweptTool,
    ToolGeometry,
    Transform,
    Vec3,
)
from carveracontroller.addons.manufacturing_simulation.orientation import StockOrientation


def oracle(angles, pivot=None):
    # Rodrigues axis rotations provide an independent implementation of Euler placement.
    return (
        Transform.rotation_about(Vec3(0, 0, 1), angles[2], pivot)
        .compose(Transform.rotation_about(Vec3(0, 1, 0), angles[1], pivot))
        .compose(Transform.rotation_about(Vec3(1, 0, 0), angles[0], pivot))
    )


@pytest.mark.parametrize("angles", [(90, 0, 0), (0, 90, 0), (0, 0, 90), (17, -33, 61), (90, 90, 90), (377, -393, 421)])
def test_fixed_xyz_order_matches_rodrigues_and_inverse_at_singular_angles(angles):
    orientation, independent = StockOrientation(angles), oracle(angles)
    for point in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (3, -5, 7)):
        wanted = independent.direction(Vec3(*point)).tuple
        assert orientation.apply(point) == pytest.approx(wanted, abs=1e-12)
        assert orientation.apply(wanted, inverse=True) == pytest.approx(point, abs=1e-12)


@pytest.mark.parametrize("angles", [(True, 0, 0), (0, float("nan"), 0), (0, 0, float("inf")), (0, 0), "xyz"])
def test_invalid_angles_are_refused(angles):
    with pytest.raises(ValueError):
        StockOrientation(angles)


@pytest.mark.parametrize("shape", ["flat", "ball", "bull", "drill"])
@pytest.mark.parametrize("angles", [(28, -37, 51), (90, 90, 0)])
def test_subtraction_is_covariant_under_full_orientation(shape, angles):
    bounds = AABB(Vec3(2, -1, 0), Vec3(12, 3, 4))
    pivot = Vec3(-3, 7, 2)
    straight = StockVolume(bounds, 0.5)
    oriented = StockVolume(bounds, 0.5, rotation_deg=angles[2], tilt_deg=angles[:2], pivot=pivot)
    transform = oracle(angles, pivot)
    cutter = ToolGeometry(2.2, 4, 2.2, 10, shape=shape, corner_radius_mm=0.3 if shape == "bull" else 0)
    start, end = Vec3(0, 0.77, 0.2), Vec3(14, 0.77, 0.2)
    straight.subtract(SweptTool(start, end, cutter))
    oriented.subtract(
        SweptTool(transform.apply(start), transform.apply(end), cutter, transform.direction(Vec3(0, 0, 1)))
    )
    assert 0 < straight.removed_volume_mm3 < bounds.volume_mm3
    assert oriented._occupied == straight._occupied
    assert oriented.remaining_volume_mm3 == straight.remaining_volume_mm3
    restored = StockVolume.from_snapshot(json.loads(json.dumps(oriented.snapshot())))
    assert restored.snapshot()["schema"] == 4
    assert restored._occupied == oriented._occupied
    assert restored.orientation.degrees == oriented.orientation.degrees
    assert restored.center(0, 0, 0).tuple == pytest.approx(transform.apply(straight.center(0, 0, 0)).tuple)
    assert oriented.clone().compare_target(oriented)["rest_volume_mm3"] == 0
    with pytest.raises(ValueError, match="identical grids"):
        oriented.compare_target(straight)


@pytest.mark.parametrize(
    "change",
    [{"schema": 2}, {"tilt_deg": [0]}, {"tilt_deg": [True, 0]}, {"tilt_deg": [0, float("inf")]}, {"tilt_deg": None}],
)
def test_snapshot_never_silently_discards_invalid_or_legacy_tilt(change):
    stock = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 2, 2)), tilt_deg=(20, 30))
    payload = stock.snapshot()
    payload.update(change)
    with pytest.raises(ValueError):
        StockVolume.from_snapshot(payload)


def test_block_edges_and_facing_envelope_cover_all_independently_transformed_corners():
    setup = MachineSetup((100, 200, 300), (20, 30, 10), (4, 5, 6), stock_rotation_deg=41, stock_tilt_deg=(23, -32))
    pivot = Vec3(14, 20, 11)
    independent = oracle((23, -32, 41), pivot)
    corners = [independent.apply(Vec3(x, y, z)).tuple for x in (4, 24) for y in (5, 35) for z in (6, 16)]
    for corner in ((4, 5, 6), (24, 35, 16)):
        assert setup.stock_point(corner) == pytest.approx(independent.apply(Vec3(*corner)).tuple)
    boundary, top = facing_envelope(setup)
    assert top == pytest.approx(max(p[2] for p in corners))
    assert len(boundary) == 6  # General projection of the box is a hexagon.
    for p in corners:
        for a, b in zip(boundary, boundary[1:] + boundary[:1]):
            assert (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= -1e-10
    drawing = project_block(setup.record())
    local = [tuple(p[i] - setup.stock_origin_mm[i] for i in range(3)) for p in corners]
    for view, vertical in zip(drawing.views, (1, 2)):
        assert len(view.batches[0][1]) == 24
        assert view.minimum == pytest.approx((min(p[0] for p in local), min(p[vertical] for p in local)))
        assert view.maximum == pytest.approx((max(p[0] for p in local), max(p[vertical] for p in local)))
    assert replace(setup, stock_tilt_deg=(0, 0)).record().get("stock_tilt_deg") is None
