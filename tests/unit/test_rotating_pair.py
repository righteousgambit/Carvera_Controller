"""Whole-section existence, material occupancy and shared work refusal."""

from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget
from carveracontroller.machine.rotating_pair import cylinder_pair, review_rotating_pair
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceBudgetExceeded, SurfaceMesh, qpoint
from tests.unit.test_stock_solid import box, reverse

SECTION = AxialEnvelope("cutter", 0, 2, 1)


def review(triangles, shift=(0, 0, 0), delta=(0, 0, 0), **kwargs):
    return review_rotating_pair(
        (SECTION,),
        shift,
        delta,
        mesh=SurfaceMesh.create(triangles),
        surface_budget=kwargs.pop("surface_budget", SurfaceBudget()),
        solid_budget=SolidBudget(),
        cache={},
        **kwargs,
    )[0]


def test_filled_rotational_volume_checks_surfaces_inside_and_outside_body():
    contact = review(box((-0.2, -0.2, 0.5), (0.2, 0.2, 1.5)))
    assert contact.state == "possible_contact" and contact.witness_triangle is not None
    inside = review(box((-2, -2, -2), (2, 2, 3)))
    assert inside.state == "contained" and inside.witness_point == (0, 0, 1)
    outside = review(box((3, 3, 0), (4, 4, 2)))
    assert outside.state == "separated" and outside.witness_point is None
    # A true material cavity is outside even when outer-shell bounds contain it.
    cavity = review(box((-3, -3, -3), (3, 3, 4)) + reverse(box((-2, -2, -2), (2, 2, 3))))
    assert cavity.state == "separated"


def test_open_mesh_preserves_unknown_material_not_a_clearance_result():
    result = review(box((3, 3, 0), (4, 4, 2))[:-1])
    assert result.state == "unavailable" and "solid unavailable" in result.reason


def test_cylinder_pair_whole_move_tangency_caps_and_exact_overlap_witness():
    other = AxialEnvelope("shank", 0, 2, 2)
    for shift, delta, expected in [
        ((4, 0, 0), (0, 0, 0), False),
        ((3, 0, 0), (0, 0, 0), True),
        ((-4, 0, 0), (8, 0, 0), True),
        ((0, 0, 3), (0, 0, 0), False),
        ((0, 0, 2), (0, 0, 0), True),
        ((-4, 0, -2), (8, 0, 40), False),
    ]:
        hit = cylinder_pair(SECTION, other, qpoint(shift), qpoint(delta), 0)
        assert (hit is not None) == expected
        if hit:
            t, p, distance = hit
            center = tuple(F(shift[j]) + t * F(delta[j]) for j in range(3))
            assert 0 <= t <= 1 and 0 <= p[2] <= 2 and 0 <= p[2] - center[2] <= 2
            assert (p[0] - center[0]) ** 2 + (p[1] - center[1]) ** 2 <= 1
            assert p[0] ** 2 + p[1] ** 2 <= 4 and distance <= 9


def test_all_sections_are_reviewed_and_original_budgets_are_shared():
    section2 = AxialEnvelope("shank", 4, 6, 1)
    budget = SurfaceBudget()
    result = review_rotating_pair(
        (SECTION, section2),
        (0, 0, 0),
        (0, 0, 0),
        other_sections=(SECTION,),
        surface_budget=budget,
        solid_budget=SolidBudget(),
        cache={},
    )
    assert [r.state for r in result] == ["possible_contact", "separated"]
    assert budget.pairs == 2 and budget.contacts == 1
    with pytest.raises(SurfaceBudgetExceeded, match="pairs"):
        review_rotating_pair(
            (SECTION, section2),
            (0, 0, 0),
            (0, 0, 0),
            other_sections=(SECTION,),
            surface_budget=SurfaceBudget(max_pairs=1),
            solid_budget=SolidBudget(),
            cache={},
        )
    for budget in (
        SurfaceBudget(max_nodes=1, nodes=1),
        SurfaceBudget(max_pairs=1, pairs=1),
        SurfaceBudget(max_contacts=1, contacts=1),
        SurfaceBudget(cancelled=lambda: True),
    ):
        with pytest.raises((SurfaceBudgetExceeded, InterruptedError)):
            review(box((-0.2, -0.2, 0.5), (0.2, 0.2, 1.5)), surface_budget=budget)


def test_complete_obstacle_admission_is_cached_across_rotating_sections():
    mesh = SurfaceMesh.create(box((3, 3, 0), (4, 4, 2)))
    cache = {}
    solid = SolidBudget()
    result = review_rotating_pair(
        (SECTION, SECTION),
        (0, 0, 0),
        (0, 0, 0),
        mesh=mesh,
        surface_budget=SurfaceBudget(),
        solid_budget=solid,
        cache=cache,
    )
    assert [r.state for r in result] == ["separated", "separated"]
    assert len(cache) == 1 and solid.queries == 2
