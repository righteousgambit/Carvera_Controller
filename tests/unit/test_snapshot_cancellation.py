"""Cancellation of real CAD copies and validation without partial publication."""

import copy
import pickle

import pytest

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot, indexed_bounds


def mesh(count=600):
    return [value for i in range(count) for value in (i, -i, i / 2, 0, 0, 1, 1, 1, 1, 1)], list(range(count))


@pytest.mark.parametrize("stop", [1, 3, 5, 8, 10, 12, 15, 17])
def test_snapshot_cancel_during_copy_and_bounds_retains_inputs(stop):
    vertices, indices = mesh()
    before = (vertices[:], indices[:])
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == stop

    with pytest.raises(InterruptedError, match="Geometry snapshot preparation cancelled"):
        GeometrySnapshot(vertices, indices, cancelled=cancelled)
    assert calls == stop
    assert (vertices, indices) == before
    complete = GeometrySnapshot(vertices, indices, cancelled=lambda: False)
    assert complete.bounds == ((0, -599, 0), (599, 0, 299.5))
    assert copy.deepcopy(complete) is complete
    assert pickle.loads(pickle.dumps(complete)) == complete


def test_repeated_indices_observe_cancel_without_unbounded_set_preparation():
    vertices, _ = mesh(1)
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == 4

    with pytest.raises(InterruptedError):
        indexed_bounds(vertices, [0] * 100000, cancelled=cancelled)
    assert calls == 4


@pytest.mark.parametrize("indices", [[True], [-1], [600], [0.0]])
def test_cancellable_bounds_reject_invalid_indices(indices):
    vertices, _ = mesh()
    with pytest.raises(ValueError, match="Invalid scene vertex index"):
        GeometrySnapshot(vertices, indices, cancelled=lambda: False)


def test_complete_vertex_coverage_observes_cancel_after_bounds_validation(monkeypatch):
    from carveracontroller.addons.machine_simulation import geometry_snapshot as module

    vertices, indices = mesh()
    before = (vertices[:], indices[:])
    validated = False
    checks = 0
    original = module.indexed_bounds

    def bounds(*args, **kwargs):
        nonlocal validated
        result = original(*args, **kwargs)
        validated = True
        return result

    def cancelled():
        nonlocal checks
        if validated:
            checks += 1
        return checks == 3

    monkeypatch.setattr(module, "indexed_bounds", bounds)
    with pytest.raises(InterruptedError, match="Geometry snapshot preparation cancelled"):
        GeometrySnapshot(vertices, indices, cancelled=cancelled)
    assert checks == 3
    assert (vertices, indices) == before
    assert GeometrySnapshot(vertices, indices).covers_all_vertices
