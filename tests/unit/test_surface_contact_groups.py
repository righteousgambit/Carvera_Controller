"""Complete exact groups versus independent exhaustive triangle contact evidence."""

from fractions import Fraction as F

import pytest

from carveracontroller.machine.surface_motion import (
    ContactGroupBudget,
    SurfaceBudget,
    SurfaceMesh,
    mesh_contact_groups,
    mesh_contacts,
)
from tests.unit.test_surface_motion_exact import full_axis_reference

A = ((0.0, 0.0, 0.0), (0.0, 2.0, 0.0), (0.0, 0.0, 2.0))


def expand(groups):
    return {(a, b, g.lower, g.upper) for g in groups for a, b in g.triangle_pairs}


def test_identical_exact_intervals_keep_more_than_ten_thousand_original_members():
    point = ((0.0, 0.0, 0.0),) * 3
    first, second = SurfaceMesh.create((point,) * 100), SurfaceMesh.create((point,) * 101)
    with pytest.raises(ValueError, match="contacts budget; no partial report"):
        mesh_contacts(first, second, (0, 0, 0), (0, 0, 0))
    work, representation = SurfaceBudget(), ContactGroupBudget()
    groups = mesh_contact_groups(first, second, (0, 0, 0), (0, 0, 0), budget=work, group_budget=representation)
    assert len(groups) == 1 and groups[0].lower == 0 and groups[0].upper == 1
    assert groups[0].triangle_pairs == tuple((a, b) for a in range(100) for b in range(101))
    assert representation.groups == 1 and representation.members == 10100
    assert work.pairs == 10100 and work.contacts == 0


def test_distinct_exact_times_and_touching_intervals_are_never_merged():
    first = SurfaceMesh.create((A,))
    second = SurfaceMesh.create(tuple(tuple((p[0] + shift, p[1], p[2]) for p in A) for shift in (0.25, 0.75)))
    groups = mesh_contact_groups(first, second, (0, 0, 0), (1, 0, 0))
    assert [(g.lower, g.upper) for g in groups] == [(F(1, 4), F(1, 4)), (F(3, 4), F(3, 4))]
    assert [g.triangle_pairs for g in groups] == [((0, 0),), ((0, 1),)]


@pytest.mark.parametrize("error", [0.0, 0.125])
def test_group_expansion_matches_every_independent_rational_pair(error):
    rows = tuple(tuple((p[0] + i / 4, p[1], p[2]) for p in A) for i in range(14))
    other = rows[::-1] + (((0.0, 0.0, 0.0),) * 3,)
    shift, delta = (-0.5, 0.0, 0.0), (4.0, 0.0, 0.0)
    expected = {
        (i, j, *hit)
        for i, a in enumerate(rows)
        for j, b in enumerate(other)
        if (hit := full_axis_reference(a, b, shift, delta, error)) is not None
    }
    groups = mesh_contact_groups(
        SurfaceMesh.create(rows), SurfaceMesh.create(other), shift, delta, position_error_mm=error
    )
    assert expand(groups) == expected
    assert sum(len(g.triangle_pairs) for g in groups) == len(expected)


@pytest.mark.parametrize("kind", ["groups", "members", "nodes", "pairs", "cancel"])
def test_shared_limits_refuse_complete_operation_instead_of_partial_groups(kind):
    first = SurfaceMesh.create((A, A, A))
    second = SurfaceMesh.create(tuple(tuple((p[0] + shift, p[1], p[2]) for p in A) for shift in (0.25, 0.75)))
    work = SurfaceBudget(**({"max_" + kind: 1} if kind in ("nodes", "pairs") else {}))
    representation = ContactGroupBudget(
        **({"max_" + kind: 1} if kind in ("groups", "members") else {"cancelled": lambda: kind == "cancel"})
    )
    with pytest.raises((ValueError, InterruptedError), match="budget|cancelled"):
        mesh_contact_groups(first, second, (0, 0, 0), (1, 0, 0), budget=work, group_budget=representation)


@pytest.mark.parametrize(
    "options", [{"max_groups": 10001}, {"max_members": 100001}, {"max_groups": True}, {"members": 100001}]
)
def test_representation_resource_contract_cannot_be_raised(options):
    with pytest.raises(ValueError):
        ContactGroupBudget(**options)
