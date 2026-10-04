from types import SimpleNamespace

import pytest

from carveracontroller.machine.scene_inspection import geometry_bounds, related_components


def vertex(x, y, z):
    return [x, y, z, 0, 0, 1, 1, 1, 1, 1]


def test_bounds_ignore_unreferenced_vertices():
    geometry = SimpleNamespace(vertices=vertex(1, 2, 3) + vertex(-5, 7, 8) + vertex(100, 100, 100), indices=[0, 1, 0])
    assert geometry_bounds(geometry) == ((-5, 2, 3), (1, 7, 8))
    geometry.indices = []
    assert geometry_bounds(geometry) is None


@pytest.mark.parametrize("indices", [[-1], [1], [True], [0.0]])
def test_bounds_reject_invalid_indices(indices):
    with pytest.raises(ValueError, match="index"):
        geometry_bounds(SimpleNamespace(vertices=vertex(1, 2, 3), indices=indices))


def test_bounds_reject_nonfinite_and_malformed_geometry():
    with pytest.raises(ValueError, match="Nonfinite"):
        geometry_bounds(SimpleNamespace(vertices=vertex(float("nan"), 2, 3), indices=[0]))
    with pytest.raises(ValueError, match="stride"):
        geometry_bounds(SimpleNamespace(vertices=[1, 2], indices=[0]))


def test_relationships_can_be_followed_in_both_directions():
    assert ("workholding", "Vise holds (declared) Stock") in related_components("stock")
    assert ("stock", "Vise holds (declared) Stock") in related_components("workholding")
    assert any("unreconciled" in reason for _, reason in related_components("atc"))
    with pytest.raises(ValueError):
        related_components("invalid")
