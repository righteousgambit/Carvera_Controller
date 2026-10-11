import json

import pytest

from carveracontroller.machine.probe_evidence import ProbeEvidenceStore, setter_trends


def context(session="fit"):
    return {
        "probe_identity": "TP06-unit",
        "seat_revision": "seat-2",
        "configuration_id": "cfg-1",
        "orientation_deg": 0.0,
        "approach_feed_mm_min": 60.0,
        "reference_id": "ring-1",
        "source_session_id": session,
        "configured_tip_diameter_mm": 1.6,
        "approach_direction": 0.0,
        "phase": "before_cut",
        "assembly_id": "tool-a",
        "assembly_revision_id": "revision-a",
        "assignment_id": "assignment-a",
    }


def descriptor():
    return {
        "known_diameter": 25.0,
        "reference_uncertainty_mm": 0.0005,
        "feature": "bore",
        "context": context(),
        "samples": [
            {"angle_degrees": 0, "measured_diameter": 23.38},
            {"angle_degrees": 120, "measured_diameter": 23.4},
            {"angle_degrees": 240, "measured_diameter": 23.42},
        ],
    }


def qualification():
    d = descriptor()
    d.update(context=context("heldout"), max_residual_mm=0.001)
    return d


def test_raw_session_preserves_received_lines_unknowns_and_commands(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.command("M461 X10 F60", context())
    store.feed("#151 = 1.23")
    store.feed("[PRB:1,2,3:1]")
    event = store.capture("probe", {"kind": "bore", "x_diameter": 25.0}, {})
    loaded = ProbeEvidenceStore(store.path).events()[0]
    assert event == loaded
    assert loaded["command"] == "M461 X10 F60"
    assert loaded["context"]["spindle_temperature"] is None
    assert loaded["raw_hits_available"]
    assert len(loaded["reported_hits"]) == 1
    assert len(loaded["reported_variables"]) == 1
    assert all(hit["acquisition_at"] is None for hit in loaded["reported_hits"])
    assert loaded["context"]["source_session_id"] == "fit"
    assert loaded["end_context"]["source_session_id"] is None


def test_corrupt_evidence_is_preserved_and_append_refused(tmp_path):
    path = tmp_path / "evidence.jsonl"
    path.write_text("unfinished")
    store = ProbeEvidenceStore(path)
    with pytest.raises(ValueError):
        store.append("anything")
    assert path.read_text() == "unfinished"
    assert not path.with_suffix(".lock").exists()


def test_cmm_variable_only_and_single_contact_sessions_complete(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.command("M461 X10", context())
    store.feed("#151 = 1.23")
    store.feed("CMMProbe END")
    event = store.complete_raw("CMMProbe END", {})
    assert event["result"]["reported_variables"] == {"151": 1.23}
    store.command("G38.2 Z-1 F60", context())
    store.feed("[PRB:1,2,3:1]")
    assert store.complete_raw("[PRB:1,2,3:1]")["result_kind"] == "probe_contact"


def test_unqualified_map_refused_and_qualified_correction_preserves_raw(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    mapping = store.save_map(descriptor())
    store.begin(context())
    raw = store.capture("probe", {"kind": "bore", "x_diameter": 25.0, "y_diameter": 26.0})
    c = dict(context(), inspected_dimension="x_diameter")
    with pytest.raises(ValueError, match="qualification"):
        store.apply_correction(raw["id"], mapping["id"], 0, c)
    receipt = store.qualify_map(mapping["id"], qualification())
    assert receipt["passed"]
    corrected = store.apply_correction(raw["id"], mapping["id"], 0, c)
    assert corrected["corrected"] == pytest.approx({"x_diameter": 25.02})
    assert store.events()[1]["result"]["x_diameter"] == 25
    assert corrected["qualification_id"] == receipt["id"]


@pytest.mark.parametrize(
    "field", ["probe_identity", "seat_revision", "configuration_id", "orientation_deg", "approach_feed_mm_min"]
)
def test_changed_setup_refuses_correction(tmp_path, field):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    mapping = store.save_map(descriptor())
    store.qualify_map(mapping["id"], qualification())
    store.begin(context())
    raw = store.capture("probe", {"kind": "bore", "x_diameter": 25.0})
    c = dict(context(), inspected_dimension="x_diameter")
    c[field] = "changed"
    with pytest.raises(ValueError, match="context mismatch"):
        store.apply_correction(raw["id"], mapping["id"], 0, c)


def test_training_reuse_failed_latest_and_unknown_orientation_refused(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    mapping = store.save_map(descriptor())
    validation = qualification()
    validation["context"]["source_session_id"] = "fit"
    with pytest.raises(ValueError, match="held out"):
        store.qualify_map(mapping["id"], validation)
    validation = qualification()
    validation["samples"][0]["measured_diameter"] += 0.1
    assert not store.qualify_map(mapping["id"], validation)["passed"]
    bad = descriptor()
    bad["context"]["orientation_deg"] = None
    with pytest.raises(ValueError, match="orientation"):
        store.save_map(bad)


def test_setter_trends_partition_seating_and_retain_unknown_causes(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    for values, phase in (([1, 1.002], "before_cut"), ([1.01, 1.012], "after_cut")):
        c = dict(context(), phase=phase, spindle_temperature=30.0)
        store.begin(c)
        store.capture("setter", {"measurements": values, "max_delta": 0.002})
    store.begin(dict(context(), seat_revision="new-seat"))
    store.capture("setter", {"measurements": [1.3], "max_delta": 0})
    trends = setter_trends(store.events())
    assert len(trends) == 2
    assert trends[0]["count"] == 2
    assert trends[0]["mean_change_mm"] == pytest.approx(0.01)
    assert trends[0]["phases"] == ["before_cut", "after_cut"]
    assert "not distinguished" in trends[0]["interpretation"]
    assert trends[1]["mean_change_mm"] is None


def test_raw_buffer_bounds_are_reported(tmp_path, monkeypatch):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.begin({})
    for i in range(4098):
        store.feed(str(i))
    event = store.capture("probe", {})
    assert event["dropped_lines"] == 2
    assert len(event["raw_console"]) == 4096
    assert json.loads(store.path.read_text())["raw_console"][0]["text"] == "2"


def test_reported_variables_are_not_raw_contacts_and_uncertainty_is_guardbanded(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.begin(context())
    store.feed("#151 = 1.23")
    event = store.capture("probe_variables", {})
    assert not event["raw_hits_available"]
    assert event["reported_variables"]
    mapping = store.save_map(descriptor())
    validation = qualification()
    validation["samples"][0]["measured_diameter"] += 0.0006
    assert not store.qualify_map(mapping["id"], validation)["passed"]


def test_firmware_latched_contacts_preserve_source_clock_and_approach(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.begin(context())
    store.feed("{PRH:1,17,1,4,1234,2,1,10.1,20.2,30.3,1,3,60,3,0}")
    event = store.capture("probe", {"kind": "bore", "x_diameter": 25})
    hit = event["reported_hits"][0]["source"]
    assert hit["boot_id"] == 17
    assert hit["hit_sequence"] == 4
    assert hit["tick_us"] == 1234
    assert hit["tick_wraps"] == 2
    assert hit["machine_position"] == [10.1, 20.2, 30.3]
    assert hit["planner_nominal_feed_mm_min"] == 60
    assert hit["negative_direction_mask"] == 1
    assert event["raw_hits_available"]
    store.begin(context())
    store.feed("{PRH:1,17,0,5,1235,2,2,0,0,0,0,0,0,0,3}")
    source = store.capture("setter_single", {})["reported_hits"][0]["source"]
    assert source["boot_id"] is None
    assert source["machine_position"] is None
    assert source["planner_nominal_feed_mm_min"] is None
    assert source["dropped_hits_total"] == 3


def test_bad_latched_contacts_remain_raw_without_becoming_valid_hits(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.feed("{PRH:1,17,1,4,nan,2,1,10,20,30,0,1,60,3,0}")
    event = store.capture("probe", {})
    assert not event["raw_hits_available"]
    assert event["rejected_contacts"]
    assert "nan" in event["raw_console"][0]["text"]


def test_contact_without_cycle_terminator_is_durably_preserved(tmp_path):
    store = ProbeEvidenceStore(tmp_path / "evidence.jsonl")
    store.feed("{PRH:1,17,1,4,1234,2,1,10,20,30,0,1,60,3,0}")
    events = ProbeEvidenceStore(store.path).events()
    assert events[0]["kind"] == "latched_contact"
    assert events[0]["session_id"] is None
    assert events[0]["session_linkage"] == "unassigned"
    assert events[0]["source"]["machine_position"] == [10, 20, 30]
