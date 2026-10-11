"""Directional rejection preserves exact whole-chord hits and tangencies."""

from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.machine.rotating_directions import _radial_norm_upper, section_projections
from carveracontroller.machine.rotating_surface import box_candidate, triangle_contact
from carveracontroller.machine.surface_directions import overlap_interval, project
from carveracontroller.machine.surface_motion import SurfaceMesh, qpoint

SECTION = AxialEnvelope("cutter", 0, 2, 1)


def candidate(triangle, shift, delta, error=0):
    node = SurfaceMesh.create((triangle,)).root
    return overlap_interval(
        section_projections(SECTION, error),
        node.projections,
        project(qpoint(shift)),
        project(qpoint(delta)),
        F(0),
        (F(0), F(1)),
    )


def test_diagonal_original_triangle_rejects_when_its_box_cannot():
    triangle = ((-1.0, 2.6, -1.0), (2.6, -1.0, -1.0), (0.8, 0.8, 3.0))
    mesh = SurfaceMesh.create((triangle,))
    assert box_candidate(SECTION, mesh.root.bounds, qpoint((0, 0, 0)), qpoint((0, 0, 0)), 0)
    assert candidate(triangle, (0, 0, 0), (0, 0, 0)) is None
    assert triangle_contact(SECTION, triangle) is None
    assert triangle_contact(SECTION, triangle, delta=(0.1, 0.1, 0)) is not None
    assert candidate(triangle, (0, 0, 0), (0.1, 0.1, 0)) is not None


@pytest.mark.parametrize("normal", [(1, 1), (2, 1), (1, 2), (3, 4), (0, 0)])
def test_radial_support_is_exact_or_outward(normal):
    norm = _radial_norm_upper(*normal)
    square = sum(v * v for v in normal)
    assert norm * norm >= square
    assert norm == 0 or (norm - F(1, 1 << 32)) ** 2 < square


@pytest.mark.parametrize("error", [0, 0.01])
def test_all_exact_hits_survive_directional_bounds_across_forward_reverse_and_axial_moves(error):
    triangles = (
        ((1.0, -1.0, 0.0), (1.0, 1.0, 0.0), (1.0, 0.0, 2.0)),
        ((0.0, 0.0, 2.0), (2.0, 0.0, 2.0), (0.0, 2.0, 2.0)),
        ((-1.0, 2.6, -1.0), (2.6, -1.0, -1.0), (0.8, 0.8, 3.0)),
    )
    motions = (((0, 0, 0), (0, 0, 0)), ((-4, 0, 0), (8, 0, 0)), ((4, 0, 0), (-8, 0, 0)), ((0, 0, -4), (0, 0, 8)))
    hits = 0
    for triangle in triangles:
        for shift, delta in motions:
            hit = triangle_contact(SECTION, triangle, shift, delta, position_error_mm=error)
            if hit is not None:
                hits += 1
                bounds = candidate(triangle, shift, delta, error)
                assert bounds is not None and bounds[0] <= hit.sample <= bounds[1]
    assert hits >= 8
