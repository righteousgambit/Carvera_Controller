"""Arbitrary frames, incremental prefixes and backwards reconstruction."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.machine.contact_pose_material import MaterialCursor, prepare_contact_material
from carveracontroller.machine.contact_pose_view import prepare_path_pose_view
from carveracontroller.machine.stock_generated_clearance import review_generated_finish
from tests.unit.test_contact_pose_material import volume
from tests.unit.test_stock_generated_clearance import prepared


@pytest.fixture
def source(tmp_path):
    parent, plan = prepared(tmp_path)
    return review_generated_finish(plan, parent)


def frame(source, index, time, state, cursor=None, **kwargs):
    scene = prepare_path_pose_view(source.scene, source.plan.tool, index, time)
    assert scene.pair == ("", "") and all(not b.highlighted_faces for b in scene.bodies)
    return prepare_contact_material(source, scene, state, cursor=cursor, **kwargs)


@pytest.mark.parametrize("state_index", range(4))
def test_forward_partial_repeated_and_backwards_frames_match_independent_full_replay(source, state_index):
    assert len(source.plan.states) == 4
    state = tuple(source.plan.states)[state_index]
    cursor = MaterialCursor(source, state)
    last = len(source.plan.moves) - 1
    requests = [(i, F(1)) for i in range(last + 1)] + [
        (last, F(1)),
        (1, F(1, 2)),
        (1, F(1, 4)),
        (last, F(1)),
        (0, F(0)),
    ]
    for index, time in requests:
        cached = frame(source, index, time, state, cursor)
        independent = frame(source, index, time, state)
        assert cached.view == independent.view
        assert cached.remaining_mm3 == independent.remaining_mm3
        assert volume(cached.view.bodies[-2].triangles) == pytest.approx(cached.remaining_mm3)
    assert cursor.next_move == 0


def test_forward_complete_prefix_replays_only_new_moves_and_partial_sweep_never_pollutes_it(source):
    state = next(iter(source.plan.states))
    cursor = MaterialCursor(source, state)
    first = frame(source, 0, F(1), state, cursor)
    second = frame(source, 1, F(1), state, cursor)
    repeat = frame(source, 1, F(1), state, cursor)
    assert (first.replayed_moves, second.replayed_moves, repeat.replayed_moves) == (1, 1, 0)
    index = next(i for i, m in enumerate(source.plan.moves) if m.cutting)
    frame(source, index, F(3, 4), state, cursor)
    checkpoint = cursor.checkpoint
    earlier = frame(source, index, F(1, 4), state, cursor)
    independent = frame(source, index, F(1, 4), state)
    assert earlier.view == independent.view and cursor.next_move == index
    assert cursor.checkpoint == checkpoint


@pytest.mark.parametrize("failure", ["cancel", "boundary", "work", "state", "source", "stale"])
def test_failed_frame_preserves_previous_valid_prefix(source, failure, monkeypatch):
    import carveracontroller.machine.contact_pose_material as module

    state = next(iter(source.plan.states))
    cursor = MaterialCursor(source, state)
    frame(source, 0, F(1), state, cursor)
    previous = cursor.checkpoint, cursor.next_move, cursor.before_mm3
    options = {}
    selected = state
    if failure == "cancel":
        options["cancelled"] = lambda: True
    elif failure == "boundary":
        options["max_boundary_faces"] = 1
    elif failure == "work":
        options["max_cell_work"] = 1
    elif failure == "state":
        selected = next(s for s in source.plan.states if s != state)
    elif failure == "source":
        source = replace(source)
    else:
        original = module.stock_geometry

        def mutate(*args, **kwargs):
            result = original(*args, **kwargs)
            source.parent.body_review.records[source.plan.tool]["scene_source"]["scene_digest"] = "changed"
            return result

        monkeypatch.setattr(module, "stock_geometry", mutate)
    with pytest.raises((ValueError, InterruptedError)):
        frame(source, len(source.plan.moves) - 1, F(1), selected, cursor, **options)
    assert previous == (cursor.checkpoint, cursor.next_move, cursor.before_mm3)


@pytest.mark.parametrize("index,time", [(-1, F(0)), (10**6, F(0)), (True, F(0)), (0, F(-1)), (0, F(2)), (0, 0.5)])
def test_invalid_arbitrary_pose_refuses_without_contact_substitution(source, index, time):
    with pytest.raises(ValueError):
        prepare_path_pose_view(source.scene, source.plan.tool, index, time)
