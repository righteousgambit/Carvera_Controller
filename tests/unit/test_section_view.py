import threading

import pytest

from carveracontroller.addons.machine_simulation.model import Geometry
from carveracontroller.machine.section_view import SectionCancelled, SectionResult, section_geometry, section_svg


def box():
    geometry = Geometry()
    geometry.box((10, 20, 30), (14, 26, 38), (1, 1, 1, 1))
    return geometry


@pytest.mark.parametrize("axis", [0, 1, 2])
@pytest.mark.parametrize("above", [False, True])
def test_cutaway_shader_matches_nominal_plane_across_work_offset_and_scale(axis, above):
    from carveracontroller.machine.section_view import SectionClip

    clip = SectionClip(axis, 23, above)
    offset, scale = (100, -75, 9), 0.125
    equation = clip.shader_plane(offset, scale)
    for value in (22, 23, 24):
        point = [10, 20, 30]
        point[axis] = value
        rendered = [(point[i] - offset[i]) * scale for i in range(3)]
        distance = sum(a * b for a, b in zip(rendered, equation[:3])) + equation[3]
        assert (distance <= 0) == clip.contains(point)
        assert clip.contains(point) == (value >= 23 if above else value <= 23)


@pytest.mark.parametrize(
    "axis,coordinate,above",
    [(True, 0, False), (3, 0, False), (0, True, False), (0, float("nan"), False), (0, 1e308, False), (0, 0, 1)],
)
def test_invalid_cutaway_draft_is_rejected(axis, coordinate, above):
    from carveracontroller.machine.section_view import SectionClip

    with pytest.raises(ValueError):
        SectionClip(axis, coordinate, above)


@pytest.mark.parametrize("scale", [0, -1, True, float("inf"), 1e300])
def test_cutaway_rejects_invalid_or_overflowing_render_frame(scale):
    from carveracontroller.machine.section_view import SectionClip

    with pytest.raises(ValueError):
        SectionClip(0, 10).shader_plane((0, 0, 0), scale)


@pytest.mark.parametrize(
    "axis,coordinate,expected",
    [(0, 12, ((20, 26), (30, 38))), (1, 23, ((10, 14), (30, 38))), (2, 34, ((10, 14), (20, 26)))],
)
def test_actual_triangle_slices_preserve_off_origin_dimensions(axis, coordinate, expected):
    result = section_geometry((box(),), axis, coordinate)
    assert result.bounds == expected
    assert result.triangle_count == 12
    assert len(result.segments) == 8  # Each side contains two tessellation pieces.
    assert all(p[axis] == coordinate for segment in result.segments for p in segment)


def test_coplanar_face_has_boundary_without_triangulation_diagonal():
    result = section_geometry((box(),), 2, 38)
    assert len(result.segments) == 4
    assert result.bounds == ((10, 14), (20, 26))
    assert all(sum(a[i] != b[i] for i in range(3)) == 1 for a, b in result.segments)


def test_open_mesh_remains_open_and_disjoint_components_are_not_joined():
    triangle = Geometry()
    triangle.triangle(((0, 0, -1), (2, 0, 1), (0, 2, 1)), (0, 0, 1), (1, 1, 1, 1))
    result = section_geometry((triangle, box()), 2, 0)
    assert result.segments == (((1, 0, 0), (0, 1, 0)),)
    assert section_geometry((box(),), 2, 100).bounds is None


def test_worker_cancellation_and_segment_budget_never_return_partial_section():
    event = threading.Event()

    def progress(_count):
        event.set()

    with pytest.raises(SectionCancelled):
        section_geometry((box(),), 2, 34, cancelled=event.is_set, progress=progress)
    with pytest.raises(ValueError, match="budget"):
        section_geometry((box(),), 2, 34, max_segments=1)


@pytest.mark.parametrize("axis,coordinate", [(True, 0), (3, 0), (2, float("nan")), (1, float("inf"))])
def test_invalid_plane_rejected(axis, coordinate):
    with pytest.raises(ValueError):
        section_geometry((box(),), axis, coordinate)


def test_corrupt_geometry_rejected():
    geometry = box()
    geometry.indices[0] = -1
    with pytest.raises(ValueError, match="index"):
        section_geometry((geometry,), 2, 34)


def test_captured_section_detaches_mutable_points_and_keeps_computed_bounds():
    segments = [[[1, 2, 3], [4, 5, 3]]]
    result = SectionResult(2, 3, segments, 1, 1e-6)
    bounds = result.bounds
    segments[0][0][0] = 1000
    assert result.segments == (((1, 2, 3), (4, 5, 3)),)
    assert result.bounds is bounds
    assert bounds == ((1, 4), (2, 5))


@pytest.mark.parametrize("axis,coordinate", [(0, 12), (1, 23), (2, 34)])
def test_svg_keeps_all_open_segments_in_one_mm_per_drawing_unit(axis, coordinate):
    from xml.etree import ElementTree

    result = section_geometry((box(),), axis, coordinate)
    root = ElementTree.fromstring(section_svg(result, "Fixture & <slice>"))
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.find("s:title", ns).text.startswith("Fixture & <slice>")
    width, height = map(float, root.attrib["viewBox"].split()[2:])
    assert float(root.attrib["width"][:-2]) == width
    assert float(root.attrib["height"][:-2]) == height
    contour = root.find("s:path", ns).attrib["d"]
    assert contour.count("M ") == contour.count("L ") == len(result.segments)
    assert "Z" not in contour  # Open CAD contours are never silently closed.
    points = [tuple(map(float, pair.split(","))) for pair in contour.split() if "," in pair]
    assert max(p[0] for p in points) - min(p[0] for p in points) == result.bounds[0][1] - result.bounds[0][0]
    assert max(p[1] for p in points) - min(p[1] for p in points) == result.bounds[1][1] - result.bounds[1][0]
    assert "physical placement unverified" in root.find("s:desc", ns).text


def test_svg_rejects_empty_contours_instead_of_creating_a_false_drawing():
    with pytest.raises(ValueError, match="nonempty"):
        section_svg(section_geometry((box(),), 2, 100), "Empty")


@pytest.mark.parametrize("count", [-1, True, 1.5])
def test_captured_section_rejects_invalid_triangle_count(count):
    with pytest.raises(ValueError, match="triangle count"):
        SectionResult(2, 0, (), count, 1e-6)


@pytest.mark.parametrize("tolerance", [0, -1, True, float("nan"), float("inf")])
def test_captured_section_rejects_invalid_tolerance(tolerance):
    with pytest.raises(ValueError, match="tolerance"):
        SectionResult(2, 0, (), 0, tolerance)
