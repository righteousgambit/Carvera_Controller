"""Analytic continuous-contact oracles and BVH equivalence, without sampling."""

from fractions import Fraction as F

import pytest

from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh, mesh_contacts, triangle_interval

A = ((0, 0, 0), (2, 0, 0), (0, 2, 0))


def test_thin_plane_crossing_between_noncontacting_endpoints():
    assert triangle_interval(A, A, (0, 0, 1)) is None
    assert triangle_interval(A, A, (0, 0, -1)) is None
    assert triangle_interval(A, A, (0, 0, 1), (0, 0, -2)) == (F(1, 2), F(1, 2))


def test_coplanar_entry_exit_direction_and_shared_tangent():
    assert triangle_interval(A, A, (-4, 0, 0), (8, 0, 0)) == (F(1, 4), F(3, 4))
    assert triangle_interval(A, A, (4, 0, 0), (-8, 0, 0)) == (F(1, 4), F(3, 4))
    assert triangle_interval(A, A, (2, 0, 0)) == (F(0), F(1))


def test_coplanar_empty_aabb_space_is_rejected_by_in_plane_axes():
    # Overlapping AABBs but x+y separates the triangular surfaces.
    b = ((2, 2, 0), (2, 0.5, 0), (0.5, 2, 0))
    assert triangle_interval(A, b) is None
    assert triangle_interval(A, b, position_error_mm=0.5) is not None


def test_degenerate_points_and_lines_are_conservative():
    point = ((1, 1, 0),) * 3
    line = ((0, 0, 0), (1, 1, 0), (1, 1, 0))
    assert triangle_interval(point, line) is not None
    assert triangle_interval(point, line, (0, 0, 1)) is None


def test_bvh_matches_every_brute_pair_and_retains_original_triangle_ids():
    rows = tuple(tuple((p[0] + i * 5, p[1], p[2]) for p in A) for i in range(20))
    first, second = SurfaceMesh.create(rows), SurfaceMesh.create(rows[::-1])
    shift, delta = (0, 0, 1), (0, 0, -2)
    expected = {
        (i, j, *hit)
        for i, a in enumerate(rows)
        for j, b in enumerate(rows[::-1])
        if (hit := triangle_interval(a, b, shift, delta)) is not None
    }
    actual = mesh_contacts(first, second, shift, delta)
    assert {(c.first_triangle, c.second_triangle, c.lower, c.upper) for c in actual} == expected
    assert len(actual) == 20 and all(c.first_triangle + c.second_triangle == 19 for c in actual)


@pytest.mark.parametrize(
    "options", [{"max_nodes": 1}, {"max_pairs": 1}, {"max_contacts": 1}, {"cancelled": lambda: True}]
)
def test_shared_limits_and_cancellation_never_return_partial_contact_reports(options):
    mesh = SurfaceMesh.create((A,) * 10)
    with pytest.raises((ValueError, InterruptedError), match="budget|cancelled"):
        mesh_contacts(mesh, mesh, (0, 0, 0), (0, 0, 0), budget=SurfaceBudget(**options))


@pytest.mark.parametrize("point", [(float("nan"), 0, 0), (float("inf"), 0, 0), (True, 0, 0), (10**1000, 0, 0)])
def test_invalid_coordinates_are_refused_even_before_culling(point):
    with pytest.raises(ValueError):
        SurfaceMesh.create(((point, *A[1:]),))
    mesh = SurfaceMesh.create((A,))
    with pytest.raises(ValueError):
        mesh_contacts(mesh, mesh, point, (0, 0, 0))


def test_factory_detaches_geometry_and_cannot_be_bypassed():
    source = [list(A)]
    mesh = SurfaceMesh.create(source)
    source[0][0] = (99, 99, 99)
    assert mesh.triangles == (A,)
    with pytest.raises(TypeError, match="create"):
        SurfaceMesh()
    with pytest.raises(InterruptedError):
        SurfaceMesh.create((A,), cancelled=lambda: True)
