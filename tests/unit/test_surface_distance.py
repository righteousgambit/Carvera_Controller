"""Analytic triangle minima and complete hierarchy, cancellation and work caps."""

from fractions import Fraction as F

import pytest

from carveracontroller.machine.surface_distance import DistanceBudget, closest_triangle, nearest_surface
from carveracontroller.machine.surface_motion import SurfaceMesh, qpoint

TRIANGLE = ((0.0, 0.0, 0.0), (2.0, 0.0, 0.0), (0.0, 2.0, 0.0))


@pytest.mark.parametrize(
    "point,expected,squared,feature",
    [
        ((0.5, 0.5, 3), (0.5, 0.5, 0), 9, "face"),
        ((1, -2, 0), (1, 0, 0), 4, "edge"),
        ((-2, -3, 1), (0, 0, 0), 14, "vertex"),
        ((2, 2, 1), (1, 1, 0), 3, "edge"),
        ((0, 0, 0), (0, 0, 0), 0, "vertex"),
    ],
)
def test_independent_analytic_closest_features(point, expected, squared, feature):
    hit = nearest_surface(SurfaceMesh.create((TRIANGLE,)), point)
    assert hit.point == qpoint(expected) and hit.distance_squared == squared and hit.feature == feature
    assert sum(hit.barycentric) == 1 and all(w >= 0 for w in hit.barycentric)


@pytest.mark.parametrize("scale", [1e-12, 1, 1e5])
def test_scale_extremes_and_rational_squared_distance(scale):
    tri = tuple(tuple(v * scale for v in p) for p in TRIANGLE)
    distance, point, _ = closest_triangle(qpoint((0, 0, scale)), tri)
    assert point == (0, 0, 0) and distance == F(scale) ** 2


def test_degenerate_edges_and_single_vertex():
    assert closest_triangle(qpoint((1, 2, 0)), ((0, 0, 0), (2, 0, 0), (2, 0, 0)))[:2] == (4, (1, 0, 0))
    assert closest_triangle(qpoint((1, 2, 0)), ((0, 0, 0),) * 3)[:2] == (5, (0, 0, 0))


def test_all_primitives_and_stable_face_tie():
    faces = tuple(tuple((x + i * 4, y, z) for x, y, z in TRIANGLE) for i in range(90)) + (TRIANGLE,)
    mesh = SurfaceMesh.create(faces, index_method="surface-area-v2")
    hit = nearest_surface(mesh, (0.5, 0.5, 1))
    assert hit.triangle == 0 and hit.distance_squared == 1
    for point in ((100, 3, 2), (300, -1, 1), (0, 0, 10)):
        hit = nearest_surface(mesh, point)
        oracle = min((closest_triangle(qpoint(point), tri)[0], i) for i, tri in enumerate(faces))
        assert (hit.distance_squared, hit.triangle) == oracle


def test_cancel_shared_limits_and_invalid_admission():
    mesh = SurfaceMesh.create((TRIANGLE,) * 40)
    with pytest.raises(InterruptedError):
        nearest_surface(mesh, (1, 1, 1), budget=DistanceBudget(cancelled=lambda: True))
    with pytest.raises(ValueError, match="no partial"):
        nearest_surface(mesh, (1, 1, 1), budget=DistanceBudget(max_triangles=1))
    with pytest.raises(ValueError, match="no partial"):
        nearest_surface(mesh, (1, 1, 1), budget=DistanceBudget(max_nodes=1))
    for kwargs in ({"max_nodes": True}, {"max_triangles": 250001}, {"nodes": -1}, {"triangles": True}):
        with pytest.raises(ValueError):
            DistanceBudget(**kwargs)
