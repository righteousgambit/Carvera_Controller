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


def test_rendered_cutter_uses_shader_rotation_scale_and_offsets():
    from carveracontroller.machine.scene_interaction import render_tool_snapshot

    snapshot = {
        "vertices": tuple(
            v for point in ((0, 0, 0), (2, 0, 0), (0, 2, 0)) for v in (*point, 0, 0, 1, 1, 1, 1, 1, 0, 0)
        ),
        "indices": (0, 1, 2),
        "rotation": (0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1),
        "offset": (10, 20, 30),
        "center": (2, 4, 6),
        "scale": 2,
        "work_offset": (-180, -120, -100),
    }
    geometry = render_tool_snapshot(snapshot)
    assert geometry.vertices[:3] == (-174, -108, -82)
    assert geometry.vertices[10:13] == (-174, -107, -82)
    assert pick_geometry((-174.25, -107.75, -70), (0, 0, -1), [("cutter", geometry, (0, 0, 0))]) == ("cutter", 12)
    for change in ({"scale": 0}, {"indices": (-1, 1, 2)}, {"vertices": (1, 2)}, {"offset": (float("nan"), 0, 0)}):
        with pytest.raises(ValueError):
            render_tool_snapshot({**snapshot, **change})


def test_pick_segment_respects_near_and_far_clip_limits():
    triangle = mesh([(0, 0, 0), (2, 0, 0), (0, 2, 0)])
    components = [("surface", triangle, (0, 0, 0))]
    assert pick_geometry((0.5, 0.5, 10), (0, 0, -1), components, max_distance=9) is None
    assert pick_geometry((0.5, 0.5, 10), (0, 0, -1), components, max_distance=10) == ("surface", 10)
    with pytest.raises(ValueError):
        pick_geometry((0, 0, 0), (0, 0, 1), [], max_distance=-1)


def test_surface_reference_retains_source_triangle_point_normal_and_motion_frame():
    from carveracontroller.addons.machine_simulation.model import Geometry
    from carveracontroller.machine.scene_interaction import pick_surface

    mesh = Geometry()
    mesh.triangle(((0, 0, 0), (2, 0, 0), (0, 2, 0)), (0, 0, 1), (1, 1, 1, 1))
    hit = pick_surface((10.5, 20.5, 10), (0, 0, -20), [("fixture", mesh, (10, 20, 3), "plate")])
    assert hit.component == "fixture" and hit.group == "plate"
    assert hit.triangle_index == 0
    assert hit.distance_mm == pytest.approx(7)
    assert hit.display_point_mm == pytest.approx((10.5, 20.5, 3))
    assert hit.component_point_mm == pytest.approx((0.5, 0.5, 0))
    assert hit.normal == pytest.approx((0, 0, 1))
    assert hit.triangle == ((0, 0, 0), (2, 0, 0), (0, 2, 0))
    assert pick_surface((10.5, 20.5, 10), (0, 0, -20), [("fixture", mesh, (10, 20, 3))], max_distance=6) is None
