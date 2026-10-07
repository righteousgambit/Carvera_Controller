import copy

import pytest

from carveracontroller.machine.kinematic_frames import declared_frame_paths
from carveracontroller.machine.kinematic_review import example_profile


def indexed(record, state, length=5):
    return {path.review.name: path for path in declared_frame_paths(record, state, length)}


def test_parent_local_composition_is_not_commutative_and_tip_length_is_once():
    record = {
        "schema": 1,
        "name": "Declared pivot example",
        "tool_base": {"translation": [10, 20, 30]},
        "tool_chain": [
            {"name": "C", "kind": "rotary", "axis": [0, 0, 1], "pivot": [2, 0, 0], "minimum": -180, "maximum": 180},
            {"name": "X", "kind": "linear", "axis": [1, 0, 0], "minimum": -20, "maximum": 20},
        ],
    }
    rows = indexed(record, {"C": 90, "X": 3})
    assert rows["Tool joint 1 · C"].review.point_mm == pytest.approx((12, 18, 30))
    assert rows["Tool joint 2 · X"].review.point_mm == pytest.approx((12, 21, 30))
    assert rows["Tool joint 2 · X"].parent == "Tool joint 1 · C"
    assert rows["Tool tip in world"].review.point_mm == pytest.approx((12, 21, 25))
    assert rows["Tool tip in world"].parent == "Final tool world reference"
    assert rows["Tool tip in workpiece"].review.point_mm == pytest.approx((12, 21, 25))
    assert "pivot (2.0, 0.0, 0.0)" in rows["Tool joint 1 · C"].review.relation
    assert "row-major rotation" in rows["Tool joint 2 · X"].review.relation
    original = copy.deepcopy(record)
    indexed(record, {"C": 90, "X": 3}, 10)
    assert record == original


def test_workpiece_inverse_changes_tool_relation_and_direction_not_a_point():
    record = {
        "schema": 1,
        "tool_base": {"translation": [10, 0, 0]},
        "work_chain": [{"name": "C", "kind": "rotary", "axis": [0, 0, 1], "minimum": -180, "maximum": 180}],
    }
    rows = indexed(record, {"C": 90})
    assert rows["Tool relative to workpiece"].review.point_mm == pytest.approx((0, -10, 0))
    assert rows["Tool tip in workpiece"].review.point_mm == pytest.approx((0, -10, -5))
    assert rows["Tool tip in world"].review.point_mm == (10, 0, -5)
    assert rows["Tool axis in workpiece"].review.point_mm is None
    assert "direction only" in rows["Tool axis in workpiece"].review.relation
    assert all("not measured" in path.review.source for path in rows.values())


@pytest.mark.parametrize("topology", ["Head / head", "Head / table", "Table / table"])
def test_topologies_keep_separate_chains_with_declared_limit_diagnostics(topology):
    record = example_profile(topology)
    joints = record["tool_chain"] + record["work_chain"]
    state = {row["name"]: 0 for row in joints}
    state["B"] = 150
    rows = indexed(record, state)
    assert any("OUTSIDE declared limits" in path.review.relation for path in rows.values())
    assert "B" in rows["Tool axis in workpiece"].review.relation
    assert len(rows) == len(joints) + 7


@pytest.mark.parametrize(
    "state,length", [({"X": True}, 5), ({"X": float("nan")}, 5), ({}, 5), ({"X": 0, "Y": 1}, 5), ({"X": 0}, -1)]
)
def test_invalid_states_do_not_produce_a_partial_chain(state, length):
    record = {
        "schema": 1,
        "tool_chain": [{"name": "X", "kind": "linear", "axis": [1, 0, 0], "minimum": -10, "maximum": 10}],
    }
    with pytest.raises(ValueError):
        declared_frame_paths(record, state, length)
