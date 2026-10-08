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


def test_snapshot_bounds_are_exact_immutable_and_do_not_rescan(monkeypatch):
    from dataclasses import FrozenInstanceError

    from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot

    values = vertex(1, 2, 3) + vertex(-5, 7, 8) + vertex(100, 100, 100)
    indices = [0, 1, 0]
    snapshot = GeometrySnapshot(values, indices)
    assert snapshot.bounds == ((-5, 2, 3), (1, 7, 8))
    values[0], indices[0] = 999, 2
    assert snapshot.vertices[0] == 1 and snapshot.indices[0] == 0
    with pytest.raises(FrozenInstanceError):
        snapshot.vertices = ()
    with pytest.raises(FrozenInstanceError):
        snapshot.bounds = None
    with pytest.raises(TypeError):
        snapshot.vertices[0] = 999
    monkeypatch.setattr(
        "carveracontroller.machine.scene_inspection.indexed_bounds", lambda *args: pytest.fail("Rescan")
    )
    assert geometry_bounds(snapshot) is snapshot.bounds


@pytest.mark.parametrize("indices", [[-1], [1], [True], [0.0]])
def test_snapshot_rejects_invalid_indexed_geometry(indices):
    from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot

    with pytest.raises(ValueError, match="index"):
        GeometrySnapshot(vertex(1, 2, 3), indices)


def test_editable_geometry_bounds_are_revalidated_after_changes():
    geometry = SimpleNamespace(vertices=vertex(1, 2, 3), indices=[0])
    assert geometry_bounds(geometry) == ((1, 2, 3), (1, 2, 3))
    geometry.vertices[0] = -10
    assert geometry_bounds(geometry) == ((-10, 2, 3), (-10, 2, 3))
    geometry.vertices[0] = float("nan")
    with pytest.raises(ValueError, match="Nonfinite"):
        geometry_bounds(geometry)
