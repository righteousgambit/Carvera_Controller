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
