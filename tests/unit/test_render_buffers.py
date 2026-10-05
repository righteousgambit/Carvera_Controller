"""Exact geometry preparation without graphics or controller dependencies."""

import copy
import threading

import pytest

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.addons.machine_simulation.model import Geometry
from carveracontroller.addons.machine_simulation.profile import triangle_batches


def snapshot():
    vertices = [
        float(v)
        for v in (
            10,
            20,
            30,
            0,
            0,
            1,
            0.2,
            0.3,
            0.4,
            1,
            11,
            21,
            31,
            1,
            0,
            0,
            0.5,
            0.6,
            0.7,
            1,
            12,
            22,
            32,
            0,
            1,
            0,
            0.8,
            0.9,
            1,
            1,
        )
    ]
    return GeometrySnapshot(vertices, (2, 0, 1, 1, 0, 2))


@pytest.mark.parametrize("limit", [3, 4, 65535])
def test_buffers_match_previous_indexed_conversion_and_preserve_source(limit):
    source = snapshot()
    geometry = Geometry()
    geometry.vertices, geometry.indices = list(source.vertices), list(source.indices)
    expected = []
    for vertices, indices in triangle_batches(geometry, limit):
        for i in range(0, len(vertices), 10):
            vertices[i] = (vertices[i] - 2) * 3
            vertices[i + 1] = (vertices[i + 1] - 4) * 3
            vertices[i + 2] = (vertices[i + 2] - 6) * 3
        expected.append((tuple(vertices), tuple(indices)))
    result = source.render_batches((2, 4, 6), 3, limit)
    assert result == tuple(expected)
    assert source.vertices == tuple(geometry.vertices)
    assert source.render_batches((2, 4, 6), 3, limit) is result
    assert copy.deepcopy(source) is source
    with pytest.raises(TypeError):
        result[0][0][0] = 99


def test_cache_bound_and_frame_isolation():
    source = snapshot()
    a = source.render_batches((0, 0, 0), 1)
    b = source.render_batches((1, 2, 3), 2)
    assert a != b and len(source._render_frames) == 2
    assert source.render_batches((0, 0, 0), 1) is a
    for offset in range(4):
        source.render_batches((offset, 0, 0), 1)
        assert len(source._render_frames) <= 2
    assert source.render_batches((1, 2, 3), 2) == b
    assert a[0][0][:3] == (12, 22, 32)


def test_cache_hit_does_not_wait_for_another_frame_conversion(monkeypatch):
    source = snapshot()
    cached = source.render_batches((0, 0, 0))
    entered, release = threading.Event(), threading.Event()
    original = GeometrySnapshot._prepare_render_batches
    errors = []

    def blocked(self, *args):
        entered.set()
        if not release.wait(2):
            errors.append("worker timeout")
        return original(self, *args)

    monkeypatch.setattr(GeometrySnapshot, "_prepare_render_batches", blocked)
    worker = threading.Thread(target=lambda: source.render_batches((10, 0, 0)))
    worker.start()
    try:
        assert entered.wait(1)
        assert source.render_batches((0, 0, 0)) is cached
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive() and not errors


@pytest.mark.parametrize(
    "offset,scale,limit",
    [
        ((0, 0), 1, 3),
        ((0, 0, float("nan")), 1, 3),
        ((0, 0, 0), 0, 3),
        ((0, 0, 0), float("inf"), 3),
        ((0, 0, 0), 1, 65536),
        ((0, 0, 0), 1, True),
    ],
)
def test_invalid_frames_are_rejected(offset, scale, limit):
    with pytest.raises(ValueError):
        snapshot().render_batches(offset, scale, limit)


def test_nontriangle_snapshot_cannot_be_used_as_triangle_buffers():
    source = snapshot()
    lines = GeometrySnapshot(source.vertices, (0, 1))
    with pytest.raises(ValueError, match="triangles"):
        lines.render_batches((0, 0, 0))


def test_large_mesh_splits_before_unsigned_short_index_overflow():
    count = 65538
    vertices = tuple(value for i in range(count) for value in (float(i), 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0))
    source = GeometrySnapshot(vertices, tuple(range(count)))
    batches = source.render_batches((0, 0, 0))
    assert tuple(len(indices) for _, indices in batches) == (65535, 3)
    assert all(max(indices) < 65535 and len(indices) % 3 == 0 for _, indices in batches)
    assert tuple(v for batch, _ in batches for v in batch) == vertices


def test_overflow_rejected_without_cached_bad_buffer_and_pickle_ignores_cache():
    import pickle

    source = snapshot()
    with pytest.raises(ValueError, match="overflows"):
        source.render_batches((-1e308, 0, 0), 1e308)
    assert not source._render_frames
    source.render_batches((0, 0, 0))
    restored = pickle.loads(pickle.dumps(source))
    assert restored.vertices == source.vertices and restored.bounds == source.bounds
    assert not restored._render_frames
