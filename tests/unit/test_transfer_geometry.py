"""Analytic contact, engagement, admission and schedule propagation evidence."""

from dataclasses import replace

import pytest

from carveracontroller.machine.mill_turn_plan import dump_plan, example_record, load_plan, plan_from_record, review_plan
from carveracontroller.machine.transfer_geometry import (
    Chuck,
    example_geometry,
    geometry_from_record,
    geometry_record,
    receiver_face,
    study_transfer,
)


def plan(geometry):
    record = example_record()
    record["transfer_geometry"] = [geometry_record(geometry)]
    return plan_from_record(record)


def test_clear_declared_demo_has_measured_intervals_not_claimed_overlap():
    study = study_transfer(example_geometry(), 6, source_required_mm=4)
    assert study.accepted and not study.contacts
    assert study.source_engagement_mm == 15
    assert study.receiver_engagement_mm == 6
    assert study.minimum_clearance_mm == 2
    review = review_plan(plan(example_geometry()))
    assert not review.issues and review.duration_s == 24.5
    grip = next(row for row in review.steps if row.step.id == "grip")
    assert grip.geometry == study and grip.status == "planned"
    assert load_plan(dump_plan(review.plan)) == review.plan


def test_source_minimum_is_independent_of_receiver_requested_engagement():
    geometry = replace(example_geometry(), stock_start_z_mm=-5)
    assert study_transfer(geometry, 6, source_required_mm=4).accepted
    assert review_plan(plan(geometry)).steps[-1].status == "planned"


@pytest.mark.parametrize("clearance,expected_z", [(0, 50), (0.5, 50.5), (2, 52)])
def test_oversize_stock_first_contacts_receiver_entrance(clearance, expected_z):
    geometry = replace(
        example_geometry(), source=Chuck(50, 80, 32, 20), receiver=Chuck(50, 80, 18, 12), clearance_mm=clearance
    )
    study = study_transfer(geometry, 6)
    contact = study.contacts[0]
    assert not study.accepted and contact.code == "receiver_bore"
    assert contact.receiver_face_z_mm == pytest.approx(expected_z)
    assert contact.fraction == pytest.approx((80 - expected_z) / 36)


def test_collision_between_clear_endpoint_poses_is_found_without_sampling():
    geometry = replace(example_geometry(), receiver_end_z_mm=-200)
    study = study_transfer(geometry, 6)
    # Receiver is completely to the right at start and to the left at end.
    assert geometry.receiver_start_z_mm > geometry.stock_end_z_mm
    assert geometry.receiver_end_z_mm + geometry.receiver.body_length_mm < geometry.stock_start_z_mm
    contact = study.contacts[0]
    assert contact.code == "receiver_bottom"
    assert contact.receiver_face_z_mm == pytest.approx(38.5)
    assert contact.fraction == pytest.approx(41.5 / 280)


def test_nested_chuck_annuli_avoid_false_face_contact_but_blind_end_still_contacts():
    geometry = replace(
        example_geometry(),
        stock_start_z_mm=-5,
        stock_end_z_mm=5,
        stock_diameter_mm=4,
        source=Chuck(30, 20, 6, 10),
        receiver=Chuck(60, 80, 30, 40),
        receiver_end_z_mm=-25,
        clearance_mm=0,
    )
    study = study_transfer(geometry, 1)
    assert not any(c.code == "chuck_bodies" for c in study.contacts)
    # The source body can fit inside the receiver bore. Its full blind end
    # eventually reaches the source annulus even though face rings do not meet.
    deeper = study_transfer(replace(geometry, receiver_end_z_mm=-50), 1)
    first = next(c for c in deeper.contacts if c.code == "chuck_bodies")
    assert first.receiver_face_z_mm == pytest.approx(-40)


@pytest.mark.parametrize(
    "change,code", [({"stock_start_z_mm": -20}, "source_bottom"), ({"stock_diameter_mm": 24}, "source_bore")]
)
def test_initial_stock_contacts_report_fraction_zero(change, code):
    study = study_transfer(replace(example_geometry(), **change), 6)
    assert next(c for c in study.contacts if c.code == code).fraction == 0


def test_contact_blocks_grip_and_dependents_without_changing_ownership():
    review = review_plan(plan(replace(example_geometry(), receiver_end_z_mm=35)))
    rows = {row.step.id: row for row in review.steps}
    assert rows["grip"].status == rows["cutoff"].status == rows["back-mill"].status == "blocked"
    assert rows["grip"].before == rows["grip"].after
    assert review.final_state.pieces[0].holders == ("main",)
    issue = next(issue for issue in review.issues if issue.code == "transfer_geometry")
    first = rows["grip"].geometry.contacts[0]
    assert issue.at_s == pytest.approx(rows["grip"].start_s + first.fraction * rows["grip"].step.duration_s)
    assert "blind bore bottom" in issue.message


def test_declared_approach_axis_is_reserved_for_the_geometric_grip():
    record = example_record()
    record["transfer_geometry"] = [geometry_record(example_geometry())]
    record["channels"].append("axis-channel")
    record["steps"].append(
        {
            "id": "other-axis",
            "name": "Competing motion",
            "channel": "axis-channel",
            "action": "reserve",
            "resources": ["Z-shared"],
            "after": ["sync"],
            "duration_s": 3,
        }
    )
    review = review_plan(plan_from_record(record))
    grip = next(row for row in review.steps if row.step.id == "grip")
    assert "Z-shared" in grip.resources and grip.status == "blocked"
    assert any(
        issue.code == "resource_conflict" and set(issue.steps) == {"grip", "other-axis"} for issue in review.issues
    )
    record["transfer_geometry"][0]["axis"] = "main"
    with pytest.raises(ValueError, match="axis resource"):
        plan_from_record(record)


@pytest.mark.parametrize("change", [{"receiver_end_z_mm": 47}, {"stock_start_z_mm": -2}])
def test_clear_but_insufficient_engagement_blocks_the_transfer(change):
    review = review_plan(plan(replace(example_geometry(), **change)))
    grip = next(row for row in review.steps if row.step.id == "grip")
    assert not grip.geometry.contacts and grip.status == "blocked"
    assert any("actual/required" in issue.message for issue in review.issues)


@pytest.mark.parametrize(
    "key,value",
    [
        ("stock_diameter_mm", True),
        ("receiver_end_z_mm", float("nan")),
        ("stock_start_z_mm", -10001),
        ("clearance_mm", -1),
        ("stock_end_z_mm", -20),
        ("receiver_start_z_mm", 10),
        ("step", ""),
        ("unknown", 1),
    ],
)
def test_invalid_geometry_is_not_admitted(key, value):
    row = geometry_record(example_geometry())
    row[key] = value
    with pytest.raises(ValueError):
        geometry_from_record(row)


@pytest.mark.parametrize("key,value", [("bore_depth_mm", 50), ("bore_diameter_mm", 80), ("body_length_mm", 0)])
def test_invalid_blind_chuck_dimensions_are_rejected(key, value):
    row = geometry_record(example_geometry())
    row["source"][key] = value
    with pytest.raises(ValueError):
        geometry_from_record(row)


def test_geometry_ownership_duplicate_step_and_cancellation():
    record = example_record()
    row = geometry_record(example_geometry("rough"))
    record["transfer_geometry"] = [row]
    with pytest.raises(ValueError, match="grip step"):
        plan_from_record(record)
    row["step"] = "grip"
    record["transfer_geometry"] = [row, row]
    with pytest.raises(ValueError, match="Duplicate"):
        plan_from_record(record)
    with pytest.raises(ValueError, match="cancelled"):
        study_transfer(example_geometry(), 6, lambda: True)
    with pytest.raises(ValueError, match="fraction"):
        receiver_face(example_geometry(), 1.1)


def test_continuous_result_is_invariant_under_coordinate_origin_translation():
    geometry = replace(example_geometry(), receiver_end_z_mm=35)
    study = study_transfer(geometry, 6)
    translated = replace(
        geometry,
        **{
            key: getattr(geometry, key) + 1000
            for key in (
                "stock_start_z_mm",
                "stock_end_z_mm",
                "source_face_z_mm",
                "receiver_start_z_mm",
                "receiver_end_z_mm",
            )
        },
    )
    moved = study_transfer(translated, 6)
    assert moved.receiver_engagement_mm == study.receiver_engagement_mm
    assert moved.source_engagement_mm == study.source_engagement_mm
    assert [(c.code, c.fraction) for c in moved.contacts] == [(c.code, c.fraction) for c in study.contacts]
    for a, b in zip(study.contacts, moved.contacts):
        assert b.receiver_face_z_mm == pytest.approx(a.receiver_face_z_mm + 1000)


@pytest.mark.parametrize("target", [44, 35, -200])
def test_stationary_pose_contact_and_endpoint_semantics(target):
    geometry = replace(example_geometry(), receiver_start_z_mm=target, receiver_end_z_mm=target)
    study = study_transfer(geometry, 6)
    assert all(contact.fraction == 0 for contact in study.contacts)
    assert bool(study.contacts) == (target == 35)
