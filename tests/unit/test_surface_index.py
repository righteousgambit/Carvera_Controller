import copy
import pickle
import random
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
from carveracontroller.machine import scene_interaction as picking
from carveracontroller.machine.section_view import SectionClip


def mesh(triangles):
    vertices = [v for triangle in triangles for point in triangle for v in (*point, 0, 0, 1, 1, 1, 1, 1)]
    return SimpleNamespace(vertices=vertices, indices=list(range(len(vertices) // 10)))


def grid(count=2048):
    return mesh([((2 * i, 0, 0), (2 * i + 1, 0, 0), (2 * i, 1, 0)) for i in range(count)])


def test_dense_pick_tests_only_reachable_leaves_and_keeps_exact_identity(monkeypatch):
    raw = grid()
    snapshot = GeometrySnapshot(raw.vertices, raw.indices)
    expected = picking.pick_surfaces((40.25, 0.25, 5), (0, 0, -1), [("fixture", raw, (0, 0, 0))])
    calls = []
    exact = picking.triangle_distance

    def tracked(*args):
        calls.append(args)
        return exact(*args)

    monkeypatch.setattr(picking, "triangle_distance", tracked)
    actual = picking.pick_surfaces((40.25, 0.25, 5), (0, 0, -1), [("fixture", snapshot, (0, 0, 0))])
    assert actual == expected and actual[0].triangle_index == 20
    assert len(calls) <= 32  # Full naive scan would visit 2048 triangles.
    assert snapshot.prepare_surface_index() is snapshot.prepare_surface_index()
    raw.vertices[0] = 1e6
    assert snapshot.vertices[0] == 0


@pytest.mark.parametrize("clip", [None, SectionClip(2, 5), SectionClip(2, 5, keep_above=True)])
def test_depth_ranked_overlaps_limits_motion_cutaways_and_equal_depth_ties(clip):
    triangles = [((0, 0, z), (1, 0, z), (0, 1, z)) for z in range(128)]
    triangles.extend(triangles)
    raw = mesh(triangles)
    snapshot = GeometrySnapshot(raw.vertices, raw.indices)
    motion = (100, -50, 30)
    clips = {} if clip is None else {"fixture": clip}
    for limit in (None, 2, 130, 300):
        for direction, origin in [((0, 0, -1), (100.25, -49.75, 200)), ((0, 0, 1), (100.25, -49.75, 0))]:
            expected = picking.pick_surfaces(
                origin, direction, [("fixture", raw, motion), ("stock", raw, (100, -50, 20))], limit, cutaways=clips
            )
            actual = picking.pick_surfaces(
                origin,
                direction,
                [("fixture", snapshot, motion), ("stock", snapshot, (100, -50, 20))],
                limit,
                cutaways=clips,
            )
            assert actual == expected


def test_index_matches_naive_oblique_and_boundary_rays():
    rng = random.Random(241)
    triangles = [tuple(tuple(rng.uniform(-20, 20) for _ in range(3)) for _ in range(3)) for _ in range(150)]
    raw = mesh(triangles)
    snapshot = GeometrySnapshot(raw.vertices, raw.indices)
    for _ in range(80):
        origin = tuple(rng.uniform(-30, 30) for _ in range(3))
        direction = tuple(rng.uniform(-1, 1) for _ in range(3))
        assert picking.pick_surfaces(origin, direction, [("mesh", snapshot, (3, 4, 5))]) == picking.pick_surfaces(
            origin, direction, [("mesh", raw, (3, 4, 5))]
        )
    raw = grid(256)
    snapshot = GeometrySnapshot(raw.vertices, raw.indices)
    for x in (0, 1 + 5e-10, 2 - 5e-10, 511, 513):
        for z in (0, 5, -5):
            origin = (x, 0, z)
            assert picking.pick_surfaces(origin, (0, 0, -1), [("mesh", snapshot, (0, 0, 0))]) == picking.pick_surfaces(
                origin, (0, 0, -1), [("mesh", raw, (0, 0, 0))]
            )


def test_index_publication_is_thread_safe_and_does_not_change_serialized_geometry():
    raw = grid(512)
    snapshot = GeometrySnapshot(raw.vertices, raw.indices)
    before = pickle.dumps(snapshot)
    with ThreadPoolExecutor(max_workers=2) as pool:
        indexes = list(pool.map(lambda _: snapshot.prepare_surface_index(), range(2)))
    assert indexes[0] is indexes[1]
    assert copy.deepcopy(snapshot) is snapshot
    assert pickle.dumps(snapshot) == before
    restored = pickle.loads(before)
    assert restored == snapshot and restored._surface_index is None
    assert restored.surface_candidates((20.25, 0.25, 5), (0, 0, -1), 100) == snapshot.surface_candidates(
        (20.25, 0.25, 5), (0, 0, -1), 100
    )
