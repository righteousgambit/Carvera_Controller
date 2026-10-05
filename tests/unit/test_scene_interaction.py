from types import SimpleNamespace

import pytest

from carveracontroller.machine.scene_interaction import pick_geometry, placement_delta, plane_point


def mesh(points):
    return SimpleNamespace(vertices=[v for point in points for v in (*point, 0, 0, 1, 1, 1, 1, 1)], indices=[0, 1, 2])


def test_nearest_surface_translation_and_two_sided_pick():
    triangle = mesh([(0, 0, 0), (2, 0, 0), (0, 2, 0)])
    components = [("far", triangle, (10, 20, 0)), ("near", triangle, (10, 20, 3))]
    assert pick_geometry((10.5, 20.5, 10), (0, 0, -4), components) == ("near", 7)
    assert pick_geometry((10.5, 20.5, -2), (0, 0, 1), components) == ("far", 2)
    # Inside the rectangular bounds, outside the actual triangular surface.
    assert pick_geometry((11.8, 21.8, 10), (0, 0, -1), components) is None
    assert pick_geometry((10.5, 20.5, 10), (0, 0, 1), components) is None


def test_degenerate_triangles_and_empty_mesh_miss():
    assert pick_geometry((0, 0, 5), (0, 0, -1), [("flat", mesh([(0, 0, 0)] * 3), (0, 0, 0))]) is None
    assert pick_geometry((0, 0, 5), (0, 0, -1), []) is None


def test_plane_intersection_and_axis_locks():
    point = plane_point((2, 3, 10), (0, 0, -2), (0, 0, 4), (0, 0, 1))
    assert point == pytest.approx((2, 3, 4))
    assert placement_delta((0, 0, 0), (1.3, -2.8, 9), "XY", 0.5) == (1.5, -3, 0)
    assert placement_delta((0, 0, 0), (1, 2, 3.1), "Z", 0) == (0, 0, 3.1)
    with pytest.raises(ValueError, match="angled"):
        plane_point((0, 0, 10), (1, 0, 0), (0, 0, 0), (0, 0, 1))
    with pytest.raises(ValueError, match="behind"):
        plane_point((0, 0, 10), (0, 0, 1), (0, 0, 0), (0, 0, 1))


@pytest.mark.parametrize("direction", [(0, 0, 0), (float("nan"), 0, 1), (True, 0, 1)])
def test_invalid_rays_rejected(direction):
    with pytest.raises(ValueError):
        pick_geometry((0, 0, 0), direction, [])


@pytest.mark.parametrize("snap", [-1, float("nan"), True])
def test_invalid_snap_rejected(snap):
    with pytest.raises(ValueError):
        placement_delta((0, 0, 0), (1, 2, 3), "XY", snap)


def test_full_homogeneous_inverse_preserves_perspective_row():
    from carveracontroller.machine.scene_interaction import homogeneous_point, inverse_projection

    identity = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)
    projection = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, -2, -1, 0, 0, -3, 0)
    inverse = inverse_projection(identity, projection)
    # Point (2, 1, -4) projects to (.5, .25, 1.25).
    assert homogeneous_point(inverse, 0.5, 0.25, 1.25) == pytest.approx((2, 1, -4))
    with pytest.raises(ValueError, match="invertible"):
        inverse_projection(identity, (0,) * 16)


def test_rotation_steps_accumulate_through_wrap_and_snap():
    import math

    from carveracontroller.machine.scene_interaction import canonical_angle, rotation_step, snap_angle

    pivot = (10, 20, 30)

    def point(angle):
        radians = math.radians(angle)
        return (10 + 5 * math.cos(radians), 20 + 5 * math.sin(radians), 30)

    assert rotation_step(point(170), point(-170), pivot) == pytest.approx(20)
    assert rotation_step(point(-170), point(170), pivot) == pytest.approx(-20)
    path = [170, 190, 280, 370, 460, 550]
    total = sum(rotation_step(point(a), point(b), pivot) for a, b in zip(path, path[1:]))
    assert total == pytest.approx(380)
    assert snap_angle(total, 15) == 375
    assert canonical_angle(170 + 30) == -160
    assert snap_angle(1.25, 0) == 1.25
    assert rotation_step((1e300, 0, 0), (0, 1e300, 0), (0, 0, 0)) == 90
    assert rotation_step((1e300, 1e300, 0), (-1e300, 1e300, 0), (0, 0, 0)) == pytest.approx(90)
    with pytest.raises(ValueError, match="pivot"):
        rotation_step(pivot, point(20), pivot)
    for invalid in (-1, 181, float("nan"), True):
        with pytest.raises(ValueError):
            snap_angle(10, invalid)


def test_rotation_ring_hit_follows_segments_not_bounding_box():
    from carveracontroller.machine.scene_interaction import near_polyline

    ring = [0, 0, 20, 0, 20, 20, 0, 20, 0, 0]
    assert near_polyline((10, 1), ring, 2)
    assert not near_polyline((10, 10), ring, 2)
    assert not near_polyline((30, 30), ring, 2)
    assert near_polyline((0, 1), [0, 0, 0, 0], 2)
