"""CAD export preserves facets that display-coordinate rounding would collapse."""

import json
import math

import pytest

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from scripts.convert_carvera_profile import triangle_vertices
from tests.unit.test_scene_joint_clearance import scene_viewer


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0, 0), (0.000001, 0, 0), (0, 1, 0)),
        ((0, 0, 0), (math.ulp(0.0), 0, 0), (0, math.ulp(0.0), 0)),
        ((0, 0, 0), (1e200, 0, 0), (0, 1e200, 0)),
        ((0.1, 0, 0), (math.nextafter(0.1, 1), 1, 0), (0.2, 0, 0)),
    ],
)
def test_complete_small_and_subnormal_facets_preserve_original_positions_after_json_roundtrip(points):
    vertices = triangle_vertices(points, (0.5, 0.5, 0.5, 1))
    restored = json.loads(json.dumps(vertices, allow_nan=False))
    assert len(restored) == 30
    assert [tuple(restored[i : i + 3]) for i in range(0, 30, 10)] == list(points)
    assert all(math.isfinite(v) for v in restored)
    assert sum(v * v for v in restored[3:6]) == pytest.approx(1, abs=2e-5)


def test_zero_area_source_facet_is_retained_for_explicit_admission_failure():
    points = ((0, 0, 0), (0, 0, 0), (1, 2, 3))
    result = triangle_vertices(points, (1, 1, 1, 1))
    assert len(result) == 30 and result[3:6] == [0, 0, 0]
    assert [tuple(result[i : i + 3]) for i in range(0, 30, 10)] == list(points)


@pytest.mark.parametrize(
    "points,color",
    [
        (((0, 0, 0), (1, 0, 0)), (1, 1, 1, 1)),
        (((0, 0), (1, 0, 0), (0, 1, 0)), (1, 1, 1, 1)),
        (((0, 0, 0), (1, 0, 0), (0, 1, 0)), (1, 1, 1)),
        (((0, 0, 0), (float("nan"), 0, 0), (0, 1, 0)), (1, 1, 1, 1)),
        (((0, 0, 0), (1, 0, 0), (0, 1, 0)), (1, 1, float("inf"), 1)),
    ],
)
def test_invalid_or_incomplete_input_is_not_serialized_as_geometry(points, color):
    with pytest.raises(ValueError):
        triangle_vertices(points, color)


def test_full_precision_triangles_and_conversion_metadata_are_accepted_by_profile_loader():
    profile = scene_viewer().machine_profile
    source = {
        "schema": 1,
        "units": "mm",
        "model": profile.model,
        "source_url": profile.source_url,
        "source_revision": profile.source_revision,
        "source_sha256": profile.source_sha256,
        "components": [dict(c) for c in profile.components],
    }
    points = ((0, 0, 0), (0.000001, 0, 0), (0, 1, 0))
    source["components"][0]["vertices"] = triangle_vertices(points, (1, 1, 1, 1))
    source["components"][0]["triangulation"] = {"position_storage": "full binary64", "zero_area_faces_retained": 0}
    loaded = MachineProfile(json.loads(json.dumps(source)))
    assert loaded.components[0]["vertices"][10] == points[1][0]
    assert loaded.components[0]["triangulation"]["position_storage"] == "full binary64"
