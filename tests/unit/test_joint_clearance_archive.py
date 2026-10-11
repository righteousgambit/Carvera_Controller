"""Saved clearance evidence must match recomputed articulated geometry."""

import hashlib
import json
from dataclasses import replace

import pytest

from carveracontroller.machine.joint_clearance import body_record, review_joint_clearance
from carveracontroller.machine.joint_clearance_archive import encoded, load_joint_review, save_joint_review
from tests.unit.test_joint_clearance import rotary_case


def sample(tmp_path):
    machine, bodies = rotary_case()
    record = {
        "schema": 1,
        "tool_chain": [{"name": "C", "kind": "rotary", "axis": [0, 0, 1], "minimum": -720, "maximum": 720}],
        "collision_bodies": [body_record(b) for b in bodies],
    }
    waypoints = [{"C": 0}, {"C": 360}]
    report = review_joint_clearance(machine, waypoints, bodies, tolerance_mm=0.01)
    path = tmp_path / "route.cvclearance"
    save_joint_review(path, record, waypoints, report)
    return path, record, waypoints, report


def resign(payload):
    payload.pop("sha256", None)
    payload["sha256"] = hashlib.sha256(encoded(payload)).hexdigest()
    return encoded(payload)


def test_roundtrip_recomputes_route_bodies_and_contact_intervals(tmp_path):
    path, record, waypoints, report = sample(tmp_path)
    restored = load_joint_review(path)
    assert restored.report == report and restored.waypoints == waypoints
    assert encoded(restored.record) == encoded(record)
    assert restored.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("field", ["contacts", "status", "intervals", "route", "frame", "tolerance"])
def test_resigned_forged_report_or_inputs_cannot_reuse_saved_geometry_evidence(tmp_path, field):
    path, _record, _waypoints, _report = sample(tmp_path)
    payload = json.loads(path.read_bytes())
    if field == "contacts":
        payload["report"]["contacts"] = []
    elif field == "status":
        payload["report"]["status"] = "clear_declared_envelopes"
    elif field == "intervals":
        payload["report"]["intervals"] += 1
    elif field == "route":
        payload["waypoints"][1]["C"] = 0
    elif field == "frame":
        payload["machine"]["collision_bodies"][0]["frame"] = "world"
        payload["machine"]["collision_bodies"][0]["joint_count"] = 0
    else:
        payload["tolerance_mm"] = 0.1
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError, match="recomputed"):
        load_joint_review(path)


def test_integrity_duplicates_size_schema_and_cancellation_refused(tmp_path):
    path, record, waypoints, report = sample(tmp_path)
    raw = path.read_bytes()
    with pytest.raises(InterruptedError):
        load_joint_review(path, cancelled=lambda: True)
    with pytest.raises(InterruptedError):
        save_joint_review(path, record, waypoints, report, cancelled=lambda: True)
    assert path.read_bytes() == raw
    payload = json.loads(raw)
    payload["report"]["contacts"] = []
    path.write_bytes(encoded(payload))
    with pytest.raises(ValueError, match="integrity"):
        load_joint_review(path)
    path.write_bytes(raw.replace(b'"schema":1', b'"schema":1,"schema":1', 1))
    with pytest.raises(ValueError, match="Duplicate"):
        load_joint_review(path)
    payload = json.loads(raw)
    payload["schema"] = True
    path.write_bytes(resign(payload))
    with pytest.raises(ValueError, match="schema"):
        load_joint_review(path)
    path.write_bytes(b" " * (2 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="2 MiB"):
        load_joint_review(path)


def test_forged_clear_report_with_valid_transport_hash_still_fails(tmp_path):
    path, record, waypoints, report = sample(tmp_path)
    save_joint_review(path, record, waypoints, replace(report, contacts=(), status="clear_declared_envelopes"))
    with pytest.raises(ValueError, match="recomputed"):
        load_joint_review(path)
