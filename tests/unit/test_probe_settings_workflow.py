import copy
import hashlib
import json
from dataclasses import FrozenInstanceError, replace

import pytest

from carveracontroller.headless.client import Response
from carveracontroller.headless.probe_settings import read_settings
from carveracontroller.headless.probe_settings_application import apply_settings
from carveracontroller.headless.probe_settings_receipts import ipc_record, validate_apply, validate_read
from carveracontroller.machine import probe_settings_workflow as workflow
from tests.unit.test_headless_probe_settings_application import FakeLink, request


def declared(**changes):
    return {
        "name": "Measured probe",
        "kind": "mechanical",
        "tip_diameter_token": "2.01",
        "tlo_correction_token": "0.0000",
        "note": "Coupon measurement",
        **changes,
    }


def test_named_store_readback_exact_tokens_and_corrupt_existing_store_preserved(tmp_path):
    store = workflow.PresetStore(tmp_path / "presets.json")
    assert store.load() == [] and not store.path.exists()
    assert store.save(declared()) == [declared()]
    assert store.save(declared(tlo_correction_token="-0.0000"))[0]["tlo_correction_token"] == "-0.0000"
    store.path.write_bytes(b'{"schema":1,"presets":[')
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        store.replace({"schema": 1, "presets": []})
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("token", ["0", "-1", "501", "nan", "2\nM3", "2" * 20, True, None, "1e999"])
def test_preset_tip_rejects_invalid_exact_token(token):
    with pytest.raises(ValueError):
        workflow.preset(declared(tip_diameter_token=token))


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema":1,"schema":1,"presets":[]}',
        b'{"schema":1,"presets":NaN}',
        b'{"number":1e999}',
        b'{"integer":' + b"9" * 129 + b"}",
        b"x" * (workflow.MAX_BYTES + 1),
    ],
)
def test_duplicate_nonfinite_and_unbounded_json_refused(raw):
    with pytest.raises(ValueError):
        workflow.strict_json(raw)


def test_immutable_review_distinguishes_missing_and_zero_and_matches_exact_context():
    before = request()["expected_settings"]
    before[workflow.KEYS[1]] = {"state": "missing", "value_mm": None, "original_numeric_token": None}
    review = workflow.ProbeReview.create("child", "one", {"machine": 1}, before, declared(), 10)
    original = review.params
    original["settings"][workflow.KEYS[0]] = "300"
    assert review.params["settings"][workflow.KEYS[0]] == "2.01"
    assert review.params["expected_settings"][workflow.KEYS[1]]["state"] == "missing"
    with pytest.raises(FrozenInstanceError):
        review.connection_id = "other"
    for session, connection, context, now in [
        ("other", "one", {"machine": 1}, 11),
        ("child", "other", {"machine": 1}, 11),
        ("child", "one", {"machine": 2}, 11),
        ("child", "one", {"machine": 1}, 41),
        ("child", "one", {"machine": 1}, 9),
        ("child", "one", {"machine": 1}, float("nan")),
    ]:
        with pytest.raises(ValueError):
            review.authorize(session, connection, context, now)
    assert review.authorize("child", "one", {"machine": 1}, 40) == review.params
    before[workflow.KEYS[1]]["value_mm"] = 0
    with pytest.raises(ValueError):
        workflow.expected_settings(before)


def test_journal_independent_readback_truncation_hash_and_exclusive_creation(tmp_path):
    path = tmp_path / "attempt.jsonl"
    workflow.append_journal(path, {"phase": "apply_pending"}, new=True)
    workflow.append_journal(path, {"phase": "reported_sd_values_match"})
    assert [r["record"]["phase"] for r in workflow.load_journal(path)] == ["apply_pending", "reported_sd_values_match"]
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        workflow.append_journal(path, {"phase": "replacement"}, new=True)
    assert path.read_bytes() == original
    for bad in (original[:-1], original.replace(b"reported_sd_values_match", b"fabricated_result")):
        path.write_bytes(bad)
        with pytest.raises(ValueError):
            workflow.load_journal(path)
        with pytest.raises(ValueError):
            workflow.append_journal(path, {"phase": "retry"})
        assert path.read_bytes() == bad


def test_fsync_failure_retains_partial_intent_for_inspection(tmp_path, monkeypatch):
    path = tmp_path / "attempt.jsonl"

    def failed(_descriptor):
        raise OSError("synthetic fsync failure")

    monkeypatch.setattr(workflow.os, "fsync", failed)
    with pytest.raises(OSError):
        workflow.append_journal(path, {"phase": "apply_pending"}, new=True)
    assert workflow.load_journal(path)[0]["record"]["phase"] == "apply_pending"


def response(envelope):
    raw = json.dumps(envelope).encode() + b"\n"
    return Response(envelope, "0" * 64, hashlib.sha256(raw).hexdigest(), 10, 5, raw)


def test_original_ipc_and_window_validation_keeps_proof_flags_false():
    link = FakeLink()
    result = apply_settings(link, request(), [])
    value = response({"ok": True, "result": result})
    assert ipc_record(value)["envelope"] == value.envelope
    validate_apply(result, request())
    assert validate_read(result["after"], "one")[workflow.KEYS[1]]["original_numeric_token"] == "0.0000"
    for changed in (
        replace(value, original_line=None),
        replace(value, response_sha256="f" * 64),
        replace(value, envelope={"ok": False}),
    ):
        with pytest.raises(ValueError):
            ipc_record(changed)


@pytest.mark.parametrize("change", ["active", "tokens", "window", "order", "connection", "plan", "rollback"])
def test_apply_result_cannot_upgrade_claims_or_replace_original_evidence(change):
    result = apply_settings(FakeLink(), request(), [])
    if change == "active":
        result["active_settings_verified"] = True
    elif change == "tokens":
        result["after"]["settings"][workflow.KEYS[1]]["original_numeric_token"] = "0"
    elif change == "window":
        result["after"]["command_receipts"][0]["controller_receive_evidence"]["original_bytes_base64"] = ""
    elif change == "order":
        result["command_receipts"].reverse()
    elif change == "connection":
        result["connection_id"] = "other"
    elif change == "plan":
        result["plan"]["settings"][workflow.KEYS[0]] = "2.02"
    else:
        result["automatic_rollback_performed"] = True
    with pytest.raises(ValueError):
        validate_apply(result, request())


def test_read_result_settings_must_match_original_windows():
    value = read_settings(FakeLink(), [])
    original = copy.deepcopy(value)
    assert validate_read(value, "one") == value["settings"]
    value["settings"][workflow.KEYS[0]] = {"state": "reported", "value_mm": 3, "original_numeric_token": "3"}
    with pytest.raises(ValueError):
        validate_read(value, "one")
    assert original["settings"][workflow.KEYS[0]]["value_mm"] == 2
