from dataclasses import replace

import pytest

from carveracontroller.machine.scene_interaction import SurfaceHit
from carveracontroller.machine.surface_measurement import plan_surface_measurement


def reference(normal=(0, 0, 1)):
    return SurfaceHit("stock", "stock", 7, 10, (11, 22, 33), (1, 2, 3), normal, ((0, 0, 3), (10, 0, 3), (0, 10, 3)))


def plan(hit=None, **kwargs):
    return plan_surface_measurement(
        hit or reference(), **{"tip_diameter_mm": 2, "clearance_mm": 5, "overtravel_mm": 1, **kwargs}
    )


def test_ball_center_nominal_frame_and_signed_deviation():
    p = plan()
    assert p.contact_center_mm == (1, 2, 4)
    assert p.approach_mm == p.retract_mm == (1, 2, 9)
    assert p.search_limit_mm == (1, 2, 3)
    assert p.normal_deviation_mm((1, 2, 4.1)) == pytest.approx(0.1)
    assert p.normal_deviation_mm((8, 9, 3.9)) == pytest.approx(-0.1)


def test_sloped_surface_with_axis_approach_offsets_ball_along_normal():
    p = plan(reference((0, 3, 4)), direction=(0, 0, -5))
    assert p.outward_normal == pytest.approx((0, 0.6, 0.8))
    assert p.contact_center_mm == pytest.approx((1, 2.6, 3.8))
    assert p.approach_mm == pytest.approx((1, 2.6, 8.8))
    assert p.search_limit_mm == pytest.approx((1, 2.6, 2.8))


def test_explicit_reverse_winding_reverses_probe_side():
    p = plan(flip=True)
    assert p.direction == (0, 0, 1)
    assert p.contact_center_mm == (1, 2, 2)
    assert p.approach_mm == (1, 2, -3)


@pytest.mark.parametrize("direction", [(0, 0, 1), (1, 0, 0), (0, 0, 0)])
def test_outward_tangent_or_zero_approach_rejected(direction):
    with pytest.raises(ValueError):
        plan(direction=direction)


@pytest.mark.parametrize(
    "field,value",
    [("tip_diameter_mm", 0), ("clearance_mm", -1), ("overtravel_mm", float("nan")), ("tip_diameter_mm", True)],
)
def test_invalid_probe_geometry_rejected(field, value):
    with pytest.raises(ValueError):
        plan(**{field: value})


def test_moving_cutter_cannot_be_measurement_target():
    with pytest.raises(ValueError, match="moving cutter"):
        plan(replace(reference(), component="cutter"))
