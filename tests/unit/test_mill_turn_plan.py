"""Dependency/resource admission and declared transfer state, without hardware."""

import json
from dataclasses import replace

import pytest

from carveracontroller.machine.mill_turn_plan import (
    PlanCancelled,
    example_record,
    load_plan,
    plan_from_record,
    plan_record,
    review_plan,
)


def demo():
    return example_record()


def step(record, identifier):
    return next(row for row in record["steps"] if row["id"] == identifier)


def inspect(record):
    return review_plan(plan_from_record(record))


def test_parallel_barriers_transfer_datum_and_new_side_milling():
    review = inspect(demo())
    assert review.duration_s == 24.5 and not review.issues
    rows = {row.step.id: row for row in review.steps}
    assert rows["spin-main"].start_s == rows["prepare-sub"].start_s == 0
    assert rows["wait-main"].start_s == rows["wait-sub"].start_s == 13
    assert rows["grip"].resources == ("main", "piece:part", "sub")
    assert rows["grip"].after.pieces[0].holders == ("main", "sub")
    assert rows["cutoff"].after.pieces[0].datum == ""
    final = review.final_state.pieces[0]
    assert (final.holders, final.datum, final.attached, final.remnant_holder) == (("sub",), "sub-back", False, "main")
    assert not review.final_state.synchronized
    assert dict(review.final_state.spindle_rpm) == {"main": 0, "sub": 0}
    assert rows["cutoff"].before.pieces[0].attached  # Earlier immutable snapshot retained.


def test_canonical_roundtrip_and_identity_changes():
    plan = plan_from_record(demo())
    assert plan_from_record(plan_record(plan)) == load_plan(json.dumps(plan_record(plan))) == plan
    changed = replace(plan, steps=(replace(plan.steps[0], duration_s=3), *plan.steps[1:]))
    assert review_plan(changed).digest != review_plan(plan).digest


@pytest.mark.parametrize("resource", ["Z-shared", "turret-main", "main", "live-sub"])
def test_shared_resource_conflicts_are_blocked_and_stop_barriers(resource):
    record = demo()
    step(record, "spin-main")["resources"] = [resource]
    step(record, "prepare-sub")["resources"] = [resource]
    review = inspect(record)
    assert any(issue.code == "resource_conflict" and resource in issue.resources for issue in review.issues)
    rows = {row.step.id: row for row in review.steps}
    assert rows["wait-main"].status == rows["wait-sub"].status == "blocked"
    assert rows["sync"].status == rows["grip"].status == rows["back-mill"].status == "blocked"
    assert review.final_state.pieces[0].holders == ("main",)


def test_shared_axis_endpoint_is_not_overlap():
    review = inspect(demo())
    rows = {row.step.id: row for row in review.steps}
    assert rows["approach"].start_s == rows["rough"].end_s
    assert not review.issues


@pytest.mark.parametrize(
    "identifier,updates,message",
    [
        ("grip", {"grip_mm": 3}, "minimum"),
        ("grip", {"overlap_mm": 5}, "overlap"),
        ("grip", {"peer": "sub"}, "different"),
        ("sync", {"action": "reserve", "spindle": "", "peer": ""}, "synchronized"),
        ("cutoff", {"resources": []}, "turret"),
        ("datum", {"action": "reserve", "piece": "", "spindle": "", "datum": ""}, "datum"),
        ("stop-pair", {"peer": ""}, "together"),
        ("back-mill", {"resources": ["Z-shared", "turret-sub"]}, "live-tool"),
        ("rough", {"mode": "mill", "resources": ["live-sub"]}, "stopped"),
    ],
)
def test_invalid_transfer_never_applies(identifier, updates, message):
    record = demo()
    step(record, identifier).update(updates)
    if identifier == "rough" and updates.get("mode") == "mill":
        step(record, "prepare-sub")["resources"] = ["turret-sub"]
    if identifier == "grip" and updates.get("peer") == "sub":
        with pytest.raises(ValueError, match=message):
            inspect(record)
    else:
        review = inspect(record)
        assert any(message in issue.message for issue in review.issues)
        assert any(row.status == "blocked" for row in review.steps)


@pytest.mark.parametrize(
    "updates",
    [
        {"duration_s": True},
        {"duration_s": float("inf")},
        {"duration_s": -1},
        {"peer": False},
        {"spindle": None},
        {"bogus": 1},
        {"after": ["missing"]},
        {"after": ["rough"]},
        {"resources": ["Z-shared", "Z-shared"]},
    ],
)
def test_strict_step_admission(updates):
    record = demo()
    step(record, "rough").update(updates)
    with pytest.raises(ValueError):
        inspect(record)


@pytest.mark.parametrize("changes", ["missing", "duplicate", "cycle", "own-arrival", "reservation"])
def test_barrier_cohort_and_dependency_graph_admission(changes):
    record = demo()
    if changes == "missing":
        record["steps"].remove(step(record, "wait-sub"))
        step(record, "sync")["after"] = []
    elif changes == "duplicate":
        record["steps"].append(dict(step(record, "wait-sub"), id="extra"))
    elif changes == "cycle":
        step(record, "rough")["after"] = ["approach"]
    elif changes == "own-arrival":
        step(record, "wait-main")["after"] = ["wait-sub"]
    else:
        step(record, "wait-main")["spindle"] = "main"
    with pytest.raises(ValueError):
        inspect(record)


def test_forward_dependency_equal_time_is_topologically_ordered():
    record = demo()
    record["channels"].append("third")
    # An independent channel's forward dependency observes the barrier after
    # its failed predecessor even when the schema places its row first.
    record["steps"].insert(
        0,
        {
            "id": "dependent",
            "name": "Depends on zero-duration arrival",
            "channel": "third",
            "action": "reserve",
            "duration_s": 1,
            "after": ["wait-main"],
        },
    )
    step(record, "prepare-sub")["resources"] = ["main"]
    review = inspect(record)
    assert next(row for row in review.steps if row.step.id == "dependent").status == "blocked"


def test_json_duplicates_numeric_tokens_bounds_and_direct_dataclass():
    with pytest.raises(ValueError, match="Duplicate"):
        load_plan('{"schema":1,"schema":1}')
    for value in ("NaN", "Infinity", "12345678901234567890"):
        with pytest.raises(ValueError):
            load_plan('{"schema":' + value + "}")
    with pytest.raises(ValueError, match="256 KiB"):
        load_plan(" " * (256 * 1024 + 1))
    plan = plan_from_record(demo())
    with pytest.raises(ValueError):
        review_plan(replace(plan, steps=(replace(plan.steps[0], duration_s=float("nan")), *plan.steps[1:])))


def test_cancellation_is_checked_before_review_and_inside_graph():
    plan = plan_from_record(demo())
    with pytest.raises(PlanCancelled):
        review_plan(plan, lambda: True)
    count = 0

    def cancelled():
        nonlocal count
        count += 1
        return count > 5

    with pytest.raises(PlanCancelled):
        review_plan(plan, cancelled)
    assert count == 6


def test_independent_channel_end_events_preserve_both_updates():
    record = demo()
    record["barriers"] = {}
    record["pieces"].append(
        {"id": "second", "holder": "sub", "datum": "sub-front", "attached": False, "minimum_grip_mm": 4}
    )
    record["steps"] = [
        {
            "id": "left",
            "name": "Main datum",
            "channel": "main-channel",
            "action": "datum",
            "piece": "part",
            "spindle": "main",
            "datum": "main-new",
            "duration_s": 2,
        },
        {
            "id": "right",
            "name": "Sub datum",
            "channel": "sub-channel",
            "action": "datum",
            "piece": "second",
            "spindle": "sub",
            "datum": "sub-new",
            "duration_s": 2,
        },
    ]
    review = inspect(record)
    assert not review.issues
    assert {p.id: p.datum for p in review.final_state.pieces} == {"part": "main-new", "second": "sub-new"}


def test_attached_source_cannot_release_and_receiver_release_invalidates_datum():
    record = demo()
    row = step(record, "cutoff")
    row.update(action="release")
    review = inspect(record)
    assert any("still attached" in issue.message for issue in review.issues)
    assert review.final_state.pieces[0].attached
    record["pieces"][0]["attached"] = False
    review = inspect(record)
    assert not review.issues
    release = next(item for item in review.steps if item.step.id == "cutoff")
    assert release.after.pieces[0].holders == ("sub",)
    assert release.after.pieces[0].datum == ""


def test_stop_cannot_silently_break_a_different_peers_pair():
    record = demo()
    record["resources"].append({"id": "third", "kind": "spindle"})
    record["barriers"] = {}
    record["steps"] = [
        {
            "id": "sync",
            "name": "Pair main sub",
            "channel": "main-channel",
            "action": "sync",
            "spindle": "main",
            "peer": "sub",
            "rpm": 100,
            "duration_s": 1,
        },
        {
            "id": "stop",
            "name": "Foreign peer",
            "channel": "main-channel",
            "action": "stop",
            "spindle": "third",
            "peer": "sub",
            "duration_s": 1,
        },
    ]
    review = inspect(record)
    assert review.steps[-1].status == "blocked"
    assert review.final_state.synchronized == (("main", "sub"),)


def test_maximum_plan_export_roundtrips_within_same_admission_budget():
    from carveracontroller.machine.mill_turn_plan import MAX_BYTES, dump_plan

    record = demo()
    record["channels"] = [f"channel-{i}" for i in range(8)]
    record["barriers"] = {}
    record["resources"] += [{"id": f"axis-{i}", "kind": "axis"} for i in range(58)]
    record["steps"] = [
        {
            "id": f"step-{i}",
            "name": f"Reservation {i}",
            "channel": record["channels"][i % 8],
            "action": "reserve",
            "resources": [r["id"] for r in record["resources"]],
            "duration_s": 1,
        }
        for i in range(256)
    ]
    admitted = load_plan(json.dumps(record))
    exported = dump_plan(admitted)
    assert len(exported.encode()) <= MAX_BYTES
    assert load_plan(exported) == admitted
    assert review_plan(load_plan(exported)).digest == review_plan(admitted).digest
