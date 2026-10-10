"""Analytic closed solids, cavities, components and continuous occupancy."""

from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation.stock_solid import (
    SolidBudget,
    SolidBudgetExceeded,
    TriangleSolid,
)
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceContact, SurfaceMesh
from carveracontroller.machine.surface_occupancy import review_solid_pair, separated_intervals
from tests.unit.test_stock_solid import box, l_stock, reverse, wedge


def pair(a, b, shift=(0, 0, 0), delta=(0, 0, 0), **kwargs):
    return review_solid_pair(SurfaceMesh.create(a), SurfaceMesh.create(b), shift, delta, **kwargs)


@pytest.mark.parametrize("inverted", [False, True])
@pytest.mark.parametrize(
    "rows,volume,shells",
    [
        (box(), 8, 1),
        (wedge(), 30, 1),
        (l_stock(), 10, 1),
        (box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4))), 98, 2),
        (box() + reverse(box((3, 0, 0), (5, 2, 2))), 16, 2),
    ],
)
def test_complete_geometry_admission_volume_shells_and_winding(rows, volume, shells, inverted):
    solid = TriangleSolid.validate(reverse(rows) if inverted else rows)
    assert solid.material_volume_mm3 == volume and solid.shell_count == shells
    assert len(solid.representatives) == shells
    assert not hasattr(solid.mesh, "source_sha256")


def test_exact_membership_boundary_cavity_and_concave_empty_space():
    solid = TriangleSolid.validate(box((0, 0, 0), (5, 5, 5)) + reverse(box((1, 1, 1), (4, 4, 4))))
    assert solid.classify((F(1, 2), 2, 2)) == "inside"
    assert solid.classify((2, 2, 2)) == "outside"
    assert solid.classify((1, 2, 2)) == "boundary"
    assert solid.classify((0, 0, 0)) == "boundary"
    assert solid.classify((6, 2, 2)) == "outside"
    concave = TriangleSolid.validate(l_stock())
    assert concave.classify((2, 2, 1)) == "outside"
    assert concave.classify((F(1, 2), 2, 1)) == "inside"


@pytest.mark.parametrize(
    "rows",
    [
        box()[:-1],
        box() + box()[:1],
        box() + box((1, 1, 1), (3, 3, 3)),
        box((0, 0, 0), (5, 5, 5)) + box((1, 1, 1), (4, 4, 4)),
        [((0, 0, 0), (1, 0, 0), (2, 0, 0))],
    ],
)
def test_open_duplicate_self_crossing_wrong_cavity_winding_and_degenerate_meshes_remain_unavailable(rows):
    report = pair(rows, box((10, 10, 10), (12, 12, 12)))
    assert report.gap and not report.intervals


def test_nested_noncontacting_solids_detect_containment_in_both_directions():
    a, b = box((1, 1, 1), (2, 2, 2)), box((0, 0, 0), (4, 4, 4))
    for first, second, side in ((a, b, "first"), (b, a, "second")):
        report = pair(first, second)
        assert not report.contacts and not report.gap
        assert len(report.intervals) == 1
        interval = report.intervals[0]
        assert interval.state == "contained" and interval.contained_side == side
        assert interval.lower == 0 and interval.upper == 1 and interval.lower_closed and interval.upper_closed
        assert interval.witness_point is not None


def test_every_disconnected_boundary_shell_is_checked_not_only_first_component():
    a = box((0, 0, 0), (1, 1, 1)) + box((7, 1, 1), (8, 2, 2))
    b = box((6, 0, 0), (9, 3, 3))
    result = pair(a, b)
    assert not result.contacts and result.intervals[0].state == "contained"
    assert result.intervals[0].witness_triangle >= 12


def test_object_inside_a_true_cavity_is_separated_despite_overlapping_boxes():
    hollow = box((0, 0, 0), (10, 10, 10)) + reverse(box((2, 2, 2), (8, 8, 8)))
    result = pair(box((3, 3, 3), (4, 4, 4)), hollow)
    assert not result.contacts and not result.gap
    assert result.intervals[0].state == "separated"
    assert pair(box((1, 1, 1), (1.5, 1.5, 1.5)), hollow).intervals[0].state == "contained"


def test_contact_complement_covers_enter_contained_exit_and_outer_intervals():
    result = pair(box((-2, 1, 1), (-1, 2, 2)), box((0, 0, 0), (4, 3, 3)), delta=(7, 0, 0))
    assert result.contacts and not result.gap
    intervals = result.intervals
    assert [(i.lower, i.upper, i.state) for i in intervals] == [
        (F(0), F(1, 7), "separated"),
        (F(2, 7), F(5, 7), "contained"),
        (F(6, 7), F(1), "separated"),
    ]
    assert [(i.lower_closed, i.upper_closed) for i in intervals] == [(True, False), (False, False), (False, True)]
    padded = pair(box((-2, 1, 1), (-1, 2, 2)), box((0, 0, 0), (4, 3, 3)), delta=(7, 0, 0), position_error_mm=0.1)
    contained = next(i for i in padded.intervals if i.state == "contained")
    assert contained.lower > F(2, 7) and contained.upper < F(5, 7)


def test_touching_boundaries_stay_possible_contact_without_false_separation():
    result = pair(box(), box((2, 0, 0), (4, 2, 2)))
    assert result.contacts and not result.intervals
    assert not separated_intervals(result.contacts)


def test_invalid_solid_is_cached_and_query_work_is_shared():
    a, b = SurfaceMesh.create(box()), SurfaceMesh.create(box((4, 0, 0), (6, 2, 2)))
    cache = {}
    budget = SolidBudget()
    review_solid_pair(a, b, (0, 0, 0), (0, 0, 0), cache=cache, budget=budget)
    pairs = budget.pairs
    queries = budget.queries
    assert len(cache) == 2
    review_solid_pair(a, b, (0, 0, 0), (0, 0, 0), cache=cache, budget=budget)
    assert budget.pairs == pairs and budget.queries > queries
    bad = SurfaceMesh.create(box()[:-1])
    cache = {}
    assert review_solid_pair(bad, b, (0, 0, 0), (0, 0, 0), cache=cache).gap
    assert isinstance(cache[id(bad)], str)


@pytest.mark.parametrize(
    "options", [{"max_nodes": 1}, {"max_pairs": 1}, {"max_rays": 1}, {"max_queries": 1}, {"cancelled": lambda: True}]
)
def test_shared_limits_and_cancellation_refuse_the_whole_operation(options):
    with pytest.raises((SolidBudgetExceeded, InterruptedError)):
        pair(
            box((3, 3, 3), (4, 4, 4)),
            box((0, 0, 0), (10, 10, 10)) + reverse(box((2, 2, 2), (8, 8, 8))),
            budget=SolidBudget(**options),
        )


def test_factory_invalid_inputs_and_nonfinite_queries_are_refused():
    with pytest.raises(TypeError):
        TriangleSolid()
    with pytest.raises(ValueError):
        TriangleSolid.validate([((10**1000, 0, 0), (1, 0, 0), (0, 1, 0))])
    solid = TriangleSolid.validate(box())
    for point in ((True, 0, 0), (float("nan"), 0, 0), (10**1000, 0, 0)):
        with pytest.raises(ValueError):
            solid.classify(point)


def test_contact_complement_merges_touching_ranges_and_retains_closed_domain_ends():
    hits = [SurfaceContact(0, 0, F(1, 2), F(3, 4)), SurfaceContact(1, 1, F(1, 4), F(1, 2))]
    assert separated_intervals(hits) == ((F(0), F(1, 4), True, False), (F(3, 4), F(1), False, True))
    for lo, hi in ((F(-1), F(0)), (F(1), F(2)), (F(3, 4), F(1, 2))):
        with pytest.raises(ValueError, match="Invalid closed"):
            separated_intervals([SurfaceContact(0, 0, lo, hi)])


def test_surface_cancellation_remains_active_during_default_solid_admission(monkeypatch):
    original = TriangleSolid.validate
    state = [False]

    def validate(*args, **kwargs):
        result = original(*args, **kwargs)
        state[0] = True
        return result

    monkeypatch.setattr(TriangleSolid, "validate", validate)
    with pytest.raises(InterruptedError):
        pair(box(), box((4, 0, 0), (6, 2, 2)), surface_budget=SurfaceBudget(cancelled=lambda: state[0]))
