"""Complete exact rows preserve cavity/boundary semantics and shared limits."""

from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation.stock_solid import (
    SolidBudget,
    SolidBudgetExceeded,
    SolidRowReuse,
    TriangleSolid,
)
from tests.unit.test_stock_solid import box, reverse


def cavity():
    return TriangleSolid.validate(box((-3, -3, -3), (3, 3, 3)) + reverse(box((-1, -1, -1), (1, 1, 1))))


@pytest.mark.parametrize("yz", [(F(1, 4), F(1, 4)), (F(1), F(0)), (F(3), F(0))])
def test_every_x_matches_independent_closed_solid_including_cavity_and_boundary(yz):
    solid = cavity()
    independent, shared, cache = SolidBudget(), SolidBudget(), SolidRowReuse()
    points = [(F(x, 2), *yz) for x in range(-6, 7)]
    expected = [solid.classify(p, budget=independent) for p in points]
    actual = [solid.classify(p, budget=shared, row_cache=cache) for p in points]
    assert actual == expected
    assert "boundary" in actual
    assert shared.queries == independent.queries == len(points)
    assert shared.rays < independent.rays and shared.nodes < independent.nodes
    assert len(cache.rows) == 1 and cache.hits == len(points) - 1
    assert next(iter(cache.rows.values()))[0] is solid


def test_exact_coordinates_and_admitted_solid_identity_bind_the_row():
    first, second = cavity(), TriangleSolid.validate(box((-2, -2, -2), (2, 2, 2)))
    cache, budget = SolidRowReuse(), SolidBudget()
    assert first.classify((0, 0, 0), budget=budget, row_cache=cache) == "outside"
    assert second.classify((0, 0, 0), budget=budget, row_cache=cache) == "inside"
    for p in ((0, F(1, 10**9), 0), (0, 0, F(1, 10**9))):
        assert first.classify(p, budget=budget, row_cache=cache) == first.classify(p)
    assert len(cache.rows) == 4 and cache.hits == 0


def test_cancelled_hits_query_limits_and_incomplete_rows_are_not_admitted():
    solid, cache, budget = cavity(), SolidRowReuse(), SolidBudget(max_queries=2)
    solid.classify((0, 0, 0), budget=budget, row_cache=cache)
    budget.cancelled = lambda: True
    with pytest.raises(InterruptedError):
        solid.classify((F(1, 2), 0, 0), budget=budget, row_cache=cache)
    assert cache.hits == 0 and budget.queries == 1
    budget.cancelled = lambda: False
    solid.classify((F(1, 2), 0, 0), budget=budget, row_cache=cache)
    with pytest.raises(SolidBudgetExceeded, match="queries"):
        solid.classify((F(3, 4), 0, 0), budget=budget, row_cache=cache)
    empty = SolidRowReuse()
    with pytest.raises(SolidBudgetExceeded, match="nodes"):
        solid.classify((0, 0, 0), budget=SolidBudget(max_nodes=1), row_cache=empty)
    assert not empty.rows and empty.members == 0


def test_complete_storage_refuses_without_eviction_or_partial_membership():
    solid, cache = cavity(), SolidRowReuse(max_rows=1)
    solid.classify((0, 0, 0), row_cache=cache)
    retained = dict(cache.rows)
    solid.classify((F(1, 2), 0, 0), row_cache=cache)
    with pytest.raises(SolidBudgetExceeded, match="storage"):
        solid.classify((0, F(1, 2), 0), row_cache=cache)
    assert cache.rows == retained
    small = SolidRowReuse(max_members=cache.members - 1)
    with pytest.raises(SolidBudgetExceeded, match="storage"):
        solid.classify((0, 0, 0), row_cache=small)
    assert not small.rows and small.members == 0


@pytest.mark.parametrize("value", [True, 0, -1, 100_001, 1.5])
def test_row_storage_admits_only_bounded_integer_limits(value):
    with pytest.raises(ValueError, match="limits"):
        SolidRowReuse(max_rows=value)
    with pytest.raises(ValueError, match="limits"):
        SolidRowReuse(max_members=value)
