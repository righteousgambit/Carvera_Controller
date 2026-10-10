"""Fast exact certificates against independent full rational intersection."""

import math
import random
from fractions import Fraction

import pytest

from carveracontroller.addons.manufacturing_simulation.solid_separation import boundary_separated, integer_triangles
from carveracontroller.addons.manufacturing_simulation.stock_solid import (
    SolidBudget,
    SolidBudgetExceeded,
    TriangleSolid,
    _box,
    _cross,
    _ExactTriangle,
    _improper_intersection,
    _index,
    _sub,
    _validate_intersections,
)
from tests.unit.test_stock_solid import box


def exact(row):
    points = tuple(tuple(Fraction(v) for v in p) for p in row)
    return _ExactTriangle(points, _cross(_sub(points[1], points[0]), _sub(points[2], points[0])))


def test_binary_integer_embedding_preserves_all_coordinates_and_cancellation():
    rows = [((0.1, 0, 0), (math.nextafter(0.1, 1), 1, 0), (0.2, 0, math.ulp(0.0)))]
    result = integer_triangles(rows, None)[0]
    ratios = {Fraction(v) / actual for p, q in zip(rows[0], result.points) for v, actual in zip(p, q) if actual}
    assert len(ratios) == 1
    assert all(
        Fraction(v) == actual * next(iter(ratios)) for p, q in zip(rows[0], result.points) for v, actual in zip(p, q)
    )
    with pytest.raises(InterruptedError):
        integer_triangles(rows, lambda: True)


@pytest.mark.parametrize("planar", [False, True])
def test_random_certificates_never_discard_full_rational_intersection(planar):
    rng = random.Random(391 + planar)
    proven = 0
    fallback = 0
    for _ in range(500):
        rows = [
            tuple((rng.randrange(-4, 5), rng.randrange(-4, 5), 0 if planar else rng.randrange(-4, 5)) for _ in range(3))
            for _ in range(2)
        ]
        a, b = (exact(row) for row in rows)
        fast = boundary_separated(*integer_triangles(rows, None))
        if fast:
            assert not _improper_intersection(a, b), rows
            proven += 1
        else:
            fallback += 1
    assert proven > 30 and fallback > 30


@pytest.mark.parametrize(
    "rows,allowed",
    [
        ([((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((0, 0, 0), (2, 0, 0), (0, -2, 0))], True),
        ([((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((0, 0, 0), (2, 0, 0), (1, 1, 0))], False),
        ([((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((0, 0, 0), (-2, 0, 0), (0, -2, 0))], True),
        ([((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((0, 0, 0), (2, 0, 0), (0, 2, 0))], False),
        ([((0, 0, 0), (2, 0, 0), (0, 2, 0)), ((1, 0, 0), (1, -2, 0), (3, -2, 0))], False),
    ],
)
def test_original_shared_boundary_and_unshared_t_junction_are_distinct(rows, allowed):
    assert boundary_separated(*integer_triangles(rows, None)) is allowed
    assert _improper_intersection(*(exact(row) for row in rows)) is not allowed


def test_cheap_proofs_use_validation_steps_and_reduce_full_pair_work():
    budget = SolidBudget(max_pairs=8)
    solid = TriangleSolid.validate(box(), budget=budget)
    assert solid.material_volume_mm3 == 8
    assert budget.nodes > budget.pairs and budget.pairs <= 8
    with pytest.raises(SolidBudgetExceeded, match="nodes"):
        TriangleSolid.validate(box(), budget=SolidBudget(max_nodes=1))


def test_full_intersection_budget_still_refuses_inconclusive_pairs():
    rng = random.Random(105)
    # Find reproducible disjoint pairs requiring the full intersection method.
    rows = []
    for _ in range(10000):
        pair = [tuple(tuple(rng.randrange(-3, 4) for _ in range(3)) for _ in range(3)) for _ in range(2)]
        from carveracontroller.addons.manufacturing_simulation.stock_solid import _overlap

        if (
            _overlap(*[_box(r) for r in pair])
            and not boundary_separated(*integer_triangles(pair, None))
            and not _improper_intersection(*(exact(r) for r in pair))
            and all(any(exact(r).normal) for r in pair)
        ):
            shift = len(rows) * 50
            rows += [tuple(tuple(v + shift for v in p) for p in r) for r in pair]
        if len(rows) == 6:
            break
    assert len(rows) == 6
    boxes = [_box(row) for row in rows]
    with pytest.raises(SolidBudgetExceeded, match="pairs"):
        _validate_intersections(
            _index(boxes, None),
            boxes,
            [exact(r) for r in rows],
            SolidBudget(max_pairs=1),
            integer_triangles(rows, None),
        )


def test_subnormal_plane_gap_and_thin_crossing_have_no_epsilon_shortcut():
    eps = math.ulp(0.0)
    a = ((-1, -1, 0), (1, -1, 0), (0, 1, 0))
    separated = ((0, 0, eps), (0, 0.5, eps), (0.5, 0, eps))
    crossing = ((0, 0, eps), (0, 0.5, -eps), (0.5, 0, -eps))
    assert boundary_separated(*integer_triangles((a, separated), None))
    assert not _improper_intersection(exact(a), exact(separated))
    assert not boundary_separated(*integer_triangles((a, crossing), None))
    assert _improper_intersection(exact(a), exact(crossing))


def test_cancellation_during_integer_certificates_refuses_the_whole_solid(monkeypatch):
    import carveracontroller.addons.manufacturing_simulation.stock_solid as module

    calls = [0]
    original = module.boundary_separated

    def counted(*args):
        calls[0] += 1
        return original(*args)

    monkeypatch.setattr(module, "boundary_separated", counted)
    with pytest.raises(InterruptedError):
        TriangleSolid.validate(box(), budget=SolidBudget(cancelled=lambda: calls[0] >= 2))
    assert calls[0] == 2


def test_many_disconnected_closed_components_fit_bounded_full_test_work():
    rows = []
    for i in range(64):
        rows += box((i * 5, i * 5, i * 5), (i * 5 + 2, i * 5 + 2, i * 5 + 2))
    budget = SolidBudget(max_pairs=512)
    result = TriangleSolid.validate(rows, budget=budget)
    assert result.shell_count == 64 and result.material_volume_mm3 == 512
    assert result.classify((1, 1, 1), budget=budget) == "inside"
    assert result.classify((3, 3, 3), budget=budget) == "outside"


def test_surface_area_tree_retains_every_face_exactly_once_with_complete_bounds():
    rng = random.Random(912)
    boxes = []
    for _ in range(180):
        low = tuple(rng.randrange(-100, 101) for _ in range(3))
        high = tuple(v + rng.choice((0, 1, 2, 300)) for v in low)
        boxes.append((low, high))
    tree = _index(boxes, None, surface_area=True)
    observed = []
    maximum_depth = [0]

    def visit(node, depth):
        maximum_depth[0] = max(maximum_depth[0], depth)
        ids = list(node.ids)
        assert not (node.ids and node.children)
        if node.ids:
            assert len(node.ids) <= 8
            observed.extend(node.ids)
        for child in node.children:
            ids += visit(child, depth + 1)
        assert len(ids) == node.count
        for i in ids:
            assert all(node.bounds[0][a] <= boxes[i][0][a] <= boxes[i][1][a] <= node.bounds[1][a] for a in range(3))
        return ids

    visit(tree, 0)
    assert sorted(observed) == list(range(len(boxes)))
    assert maximum_depth[0] <= 50


def test_coincident_centroids_use_bounded_balanced_fallback():
    rows = [((-1, -1, -1), (1, 1, 1))] * 129
    tree = _index(rows, None, surface_area=True)
    pending = [(tree, 0)]
    ids = []
    while pending:
        node, depth = pending.pop()
        assert depth < 8
        ids.extend(node.ids)
        pending.extend((child, depth + 1) for child in node.children)
    assert sorted(ids) == list(range(129))


def test_surface_area_build_cancellation_returns_no_partial_tree():
    calls = [0]

    def cancelled():
        calls[0] += 1
        return calls[0] >= 8

    boxes = [((i, 0, 0), (i + 1, 1, 1)) for i in range(300)]
    with pytest.raises(InterruptedError):
        _index(boxes, cancelled, surface_area=True)
