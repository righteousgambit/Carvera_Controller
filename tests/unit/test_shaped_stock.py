"""The same finite ball cutting reach applies to evolving voxel stock."""

from math import sqrt

import pytest

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, SweptTool, ToolGeometry, Vec3


@pytest.mark.parametrize("axis", [Vec3(0, 0, 1), Vec3(1, 0, 0), Vec3(0, 1, 0), Vec3(sqrt(0.5), 0, sqrt(0.5))])
def test_ball_stock_keeps_cell_centers_above_declared_flute_reach(axis):
    tool = ToolGeometry(4, 2.2, 4, 10, shape="ball")
    stock = StockVolume(AABB(Vec3(-1.5, -1.5, -1.5), Vec3(4.5, 4.5, 4.5)), 1)
    stock.subtract(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool, axis))
    changed = 0
    for z in range(6):
        for y in range(6):
            for x in range(6):
                p = stock.center(x, y, z)
                height = sum(a * b for a, b in zip(p.tuple, axis.tuple))
                radial = sum(v * v for v in p.tuple) - height * height
                radius_squared = 4 - (height - 2) ** 2 if height < 2 else 4
                expected = 0 <= height <= 2.2 and radial <= radius_squared + 1e-12
                assert stock.occupied(x, y, z) == (not expected), (p, height)
                changed += expected
    assert changed > 0 and stock.removed_volume_mm3 == changed


def test_diagonal_ball_sphere_and_cutting_caps_share_the_same_time():
    # The full moving sphere intersects this center, but only above the finite
    # cutting reach. The lower cap and upper cylinder never reach it together.
    p = Vec3(0, 0, 8.5)
    stock = StockVolume(AABB(p - Vec3(0.1, 0.1, 0.1), p + Vec3(0.1, 0.1, 0.1)), 1)
    tool = ToolGeometry(4, 2.2, 4, 10, shape="ball")
    result = stock.subtract(SweptTool(Vec3(-4, 0, 0), Vec3(4, 0, 8), tool))
    assert result.removed_voxels == 0 and stock.occupied(0, 0, 0)


def test_retained_ball_cap_material_reaches_the_next_ordered_rapid_review():
    from carveracontroller.addons.manufacturing_simulation import CollisionScene, SimulationSegment, simulate

    p = Vec3(0, 0, 8.5)
    stock = StockVolume(AABB(p - Vec3(0.1, 0.1, 0.1), p + Vec3(0.1, 0.1, 0.1)), 1)
    tools = {"1": ToolGeometry(4, 2.2, 4, 10, shape="ball"), "2": ToolGeometry(1, 1, 1, 2)}
    scene = CollisionScene(stock=stock.bounds, allowed_cut_region=AABB(Vec3(-20, -20, -20), Vec3(20, 20, 20)))
    segments = (
        SimulationSegment(Vec3(-4, 0, 0), Vec3(4, 0, 8), "1", line=10),
        SimulationSegment(Vec3(0, 0, 8), Vec3(0, 0, 8), "2", cutting=False, line=11),
    )
    report = simulate(segments, tools, stock, scene)
    assert report.segments_processed == 2 and report.removed_volume_mm3 == 0
    assert (11, "cutter", "remaining stock") in report.candidates
    assert stock.occupied(0, 0, 0)
