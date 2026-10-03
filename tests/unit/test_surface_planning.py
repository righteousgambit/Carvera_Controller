import math

import pytest

from carveracontroller.machine.surface_planning import (
    FacingParameters,
    FacingPlan,
    HeightMap,
    HeightSample,
)

BOUNDARY = ((0, 0), (10, 0), (10, 10), (0, 10))


def sample(x, y, z):
    return HeightSample(x, y, z, "probe serial 123", "2026-10-03T20:00:00Z", 0.01)


def test_height_map_interpolation_repeat_and_persistence(tmp_path):
    heights = HeightMap(BOUNDARY, [sample(0, 0, 1), sample(10, 0, 2), sample(0, 10, 3)], max_gap_mm=15)
    value = heights.query(2, 3)
    assert value is not None
    assert value.kind == "interpolated"
    assert value.z_mm == pytest.approx(1.8)
    assert value.uncertainty_mm == pytest.approx(0.01)
    assert heights.query(9, 9) is None  # Inside stock but outside measured support.
    assert heights.query(-1, 0) is None
    heights.samples.append(sample(0, 0, 1.2))
    repeat = heights.query(0, 0)
    assert repeat is not None and repeat.kind == "measured"
    assert repeat.z_mm == pytest.approx(1.1)
    assert repeat.uncertainty_mm == pytest.approx(0.11)
    path = tmp_path / "height-map.json"
    heights.save(path)
    assert HeightMap.load(path).to_dict() == heights.to_dict()


def test_map_does_not_bridge_gap_or_exclusion():
    heights = HeightMap(BOUNDARY, [sample(0, 0, 1), sample(10, 0, 2), sample(0, 10, 3)], max_gap_mm=5)
    assert heights.query(1, 1) is None
    heights.max_gap_mm = 15
    heights.exclusions = (((1, 1), (2, 1), (2, 2), (1, 2)),)
    assert heights.query(1.5, 1.5) is None
    assert heights.query(3, 3) is None  # Triangle crosses unmapped excluded island.


def parameters(boundary=BOUNDARY, **changes):
    values = {
        "boundary": boundary,
        "top_z_mm": 0,
        "final_z_mm": -0.7,
        "tool_diameter_mm": 4,
        "stepover_mm": 2,
        "pass_depth_mm": 0.3,
        "feed_mm_min": 300,
        "plunge_feed_mm_min": 80,
        "spindle_rpm": 12000,
        "clearance_z_mm": 5,
        "overtravel_mm": 0.5,
        "material": "6061",
        "tool_id": "quarter-inch aluminum",
    }
    values.update(changes)
    return FacingParameters(**values)


def test_facing_covers_edges_and_final_height_retracts_between_segments():
    plan = FacingPlan.from_params(parameters())
    assert {s.pass_index for s in plan.segments} == {1, 2, 3}
    assert min(s.start[2] for s in plan.segments) == pytest.approx(-0.7)
    assert min(s.start[0] for s in plan.segments) == pytest.approx(-2.5)
    assert max(s.end[0] for s in plan.segments) == pytest.approx(12.5)
    assert {s.start[1] for s in plan.segments} >= {0, 10}
    lines = plan.gcode().splitlines()
    assert lines[:3] == ["(POLYGON FACING PREVIEW - verify setup before execution)", "G21 G90 G17 G94", "G54"]
    for i, line in enumerate(lines):
        if line.startswith("G0 X"):
            assert lines[i - 1] == "G0 Z5.00000"
            assert lines[i + 1].startswith("G1 Z")
    assert "G1 Z-0.70000 F80.000" in lines
    assert lines[-3:] == ["G0 Z5.00000", "M5", "M2"]


def test_concave_boundary_creates_separate_spans():
    # Two arms separated by a 6 mm notch; no cutting line bridges the notch.
    boundary = ((0, 0), (20, 0), (20, 10), (13, 10), (13, 3), (7, 3), (7, 10), (0, 10))
    plan = FacingPlan.from_params(parameters(boundary, overtravel_mm=0))
    upper = [s for s in plan.segments if s.start[1] == 6 and s.pass_index == 1]
    assert len(upper) == 2
    assert all(abs(s.end[0] - s.start[0]) == pytest.approx(11) for s in upper)


@pytest.mark.parametrize(
    "changes",
    [{"clearance_z_mm": 0}, {"stepover_mm": 3}, {"spindle_rpm": math.nan}, {"final_z_mm": 1}, {"wcs": "G54 M3"}],
)
def test_facing_rejects_unsafe_or_nonfinite_parameters(changes):
    with pytest.raises(ValueError):
        parameters(**changes)


def test_rejects_self_crossing_polygon_and_unproven_measurement():
    with pytest.raises(ValueError):
        HeightMap(((0, 0), (10, 10), (0, 10), (10, 0)))
    with pytest.raises(ValueError):
        HeightSample(0, 0, 1, "", "", 0)


def test_repeat_uncertainty_is_preserved_in_interpolated_support():
    heights = HeightMap(BOUNDARY, [sample(0, 0, 0), sample(0, 0, 2), sample(10, 0, 2), sample(0, 10, 3)], max_gap_mm=15)
    result = heights.query(2, 3)
    assert result is not None
    assert result.z_mm == pytest.approx(1.8)
    assert result.uncertainty_mm == pytest.approx(0.51)
    assert len(result.supporting_samples) == 4


def test_facing_roundtrip_and_engagement_context():
    params = parameters()
    restored = FacingParameters.from_dict(params.to_dict())
    assert restored == params
    assert restored.chipload_mm_per_tooth == pytest.approx(300 / (12000 * 3))
    assert restored.radial_engagement_fraction == pytest.approx(0.5)
    assert "G4 P3.000" in FacingPlan.from_params(params).gcode()
