"""Independent full-axis rational contact oracle for continuous SAT shortcuts."""

import math
import random
from fractions import Fraction as F

import pytest

from carveracontroller.machine.surface_motion import triangle_interval


def sub(a, b):
    return tuple(x - y for x, y in zip(a, b))


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), F(0))


def full_axis_reference(first, second, shift, delta, error):
    a, b = tuple(tuple(F(v) for v in p) for p in first), tuple(tuple(F(v) for v in p) for p in second)
    shift, delta = tuple(F(v) for v in shift), tuple(F(v) for v in delta)
    ea, eb = [sub(a[(i + 1) % 3], a[i]) for i in range(3)], [sub(b[(i + 1) % 3], b[i]) for i in range(3)]
    na, nb = cross(ea[0], ea[1]), cross(eb[0], eb[1])
    axes = [
        na,
        nb,
        *[cross(x, y) for x in ea for y in eb],
        *[cross(n, e) for n in (na, nb) for e in ea + eb],
        (F(1), F(0), F(0)),
        (F(0), F(1), F(0)),
        (F(0), F(0), F(1)),
    ]
    lower, upper = F(0), F(1)
    for axis in axes:
        if axis == (0, 0, 0):
            continue
        aa, bb = [dot(p, axis) for p in a], [dot(p, axis) for p in b]
        allowance = F(error) * sum(abs(v) for v in axis)
        start, speed = dot(shift, axis), dot(delta, axis)
        lo, hi = min(bb) - max(aa) - allowance - start, max(bb) - min(aa) + allowance - start
        if speed:
            x, y = lo / speed, hi / speed
            lower, upper = max(lower, min(x, y)), min(upper, max(x, y))
            if lower > upper:
                return None
        elif not lo <= 0 <= hi:
            return None
    return lower, upper


@pytest.mark.parametrize("error", [0, 0.000001, 0.25])
def test_exact_contact_matches_full_original_axis_intersection_on_random_translations(error):
    rng = random.Random(2199)
    for _ in range(160):
        first = tuple(tuple(rng.uniform(-8, 8) for _ in range(3)) for _ in range(3))
        second = tuple(tuple(rng.uniform(-8, 8) for _ in range(3)) for _ in range(3))
        shift = tuple(rng.uniform(-12, 12) for _ in range(3))
        delta = tuple(rng.uniform(-24, 24) for _ in range(3))
        assert triangle_interval(first, second, shift, delta, position_error_mm=error) == full_axis_reference(
            first, second, shift, delta, error
        )


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("scale", [math.ulp(0.0), 1.0, 100000.0])
def test_axis_permutations_subnormal_scaling_and_exact_endpoint_contact(axis, scale):
    def point(x, y, z):
        values = (x * scale, y * scale, z * scale)
        return values[axis:] + values[:axis]

    first = (point(0, 0, 0), point(2, 0, 0), point(0, 2, 0))
    second = first[::-1]
    for shift, delta, error in (
        (point(-4, 0, 0), point(8, 0, 0), 0),
        (point(0, 0, 1), point(0, 0, -2), 0),
        (point(2, 0, 0), point(0, 0, 0), 0),
        (point(0, 0, 1), point(0, 0, 0), min(scale, 2000)),
    ):
        assert triangle_interval(first, second, shift, delta, position_error_mm=error) == full_axis_reference(
            first, second, shift, delta, error
        )


def test_validation_precedes_any_early_separation_certificate():
    first = ((0, 0, 0), (1, 0, 0), (0, 1, 0))
    second = ((10, 10, 0), (11, 10, 0), (10, 11, 0))
    for shift, delta, error in (
        ((True, 0, 0), (0, 0, 0), 0),
        ((0, 0, 0), (float("inf"), 0, 0), 0),
        ((0, 0, 0), (0, 0, 0), True),
        ((0, 0, 0), (0, 0, 0), float("nan")),
    ):
        with pytest.raises(ValueError):
            triangle_interval(first, second, shift, delta, position_error_mm=error)


def test_index_keeps_every_face_once_and_encloses_thin_duplicate_and_degenerate_geometry():
    from collections import Counter

    from carveracontroller.machine.surface_motion import SurfaceMesh

    rows = (
        tuple(
            (
                (float(i % 5), float(i // 5), 0.0),
                (float(i % 5) + 20.0, float(i // 5), 0.0),
                (float(i % 5), float(i // 5) + 0.01, 0.0),
            )
            for i in range(35)
        )
        + (((2.0, 2.0, 2.0),) * 3,) * 17
    )
    mesh = SurfaceMesh.create(rows)
    ids = []

    def visit(node):
        if node.children:
            assert not node.ids
            for child in node.children:
                assert all(
                    node.bounds[0][a] <= child.bounds[0][a] <= child.bounds[1][a] <= node.bounds[1][a] for a in range(3)
                )
                visit(child)
        else:
            assert node.ids
            ids.extend(node.ids)
            assert all(
                node.bounds[0][a] <= p[a] <= node.bounds[1][a] for i in node.ids for p in rows[i] for a in range(3)
            )

    visit(mesh.root)
    assert Counter(ids) == Counter(range(len(rows)))
    assert mesh.triangles == rows


@pytest.mark.parametrize("error", [0.0, 0.01])
def test_spatial_index_matches_independent_all_pairs_on_thin_clustered_surfaces(error):
    from carveracontroller.machine.surface_motion import SurfaceMesh, mesh_contacts

    rows = tuple(
        ((i * 10.0, j * 30.0, 0.0), (i * 10.0 + 2.0, j * 30.0, 0.0), (i * 10.0, j * 30.0 + 0.001, 0.0))
        for i in range(6)
        for j in range(3)
    )
    other = rows[::-1] + (((1.0, 1.0, 0.0),) * 3,)
    shift, delta = (-3.0, 0.0, 1.0), (6.0, 0.0, -2.0)
    expected = {
        (i, j, *hit)
        for i, a in enumerate(rows)
        for j, b in enumerate(other)
        if (hit := full_axis_reference(a, b, shift, delta, error)) is not None
    }
    actual = mesh_contacts(SurfaceMesh.create(rows), SurfaceMesh.create(other), shift, delta, position_error_mm=error)
    assert {(c.first_triangle, c.second_triangle, c.lower, c.upper) for c in actual} == expected


def test_complete_thin_cluster_review_fits_existing_pair_limit_without_dropping_contacts():
    from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh, mesh_contacts

    rows = tuple(
        ((i * 10.0, j * 30.0, 0.0), (i * 10.0 + 2.0, j * 30.0, 0.0), (i * 10.0, j * 30.0 + 0.001, 0.0))
        for i in range(6)
        for j in range(3)
    )
    other = rows[::-1] + (((1.0, 1.0, 0.0),) * 3,)
    shift, delta = (-3.0, 0.0, 1.0), (6.0, 0.0, -2.0)
    old_first, old_second = (SurfaceMesh.create(x, index_method="median-v1") for x in (rows, other))
    old_complete = mesh_contacts(old_first, old_second, shift, delta)
    with pytest.raises(ValueError, match="pairs budget; no partial report"):
        mesh_contacts(old_first, old_second, shift, delta, budget=SurfaceBudget(max_pairs=100))
    new_budget = SurfaceBudget(max_pairs=100)
    result = mesh_contacts(SurfaceMesh.create(rows), SurfaceMesh.create(other), shift, delta, budget=new_budget)
    assert result == old_complete
    assert len(result) == 18 and new_budget.pairs <= 100


@pytest.mark.parametrize("method", ["unknown", True, None, []])
def test_unknown_index_methods_refuse_before_preparation(method):
    from carveracontroller.machine.surface_motion import SurfaceMesh

    with pytest.raises(ValueError, match="index method"):
        SurfaceMesh.create((((0, 0, 0), (1, 0, 0), (0, 1, 0)),), index_method=method)
