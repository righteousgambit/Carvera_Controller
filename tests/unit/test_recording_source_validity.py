"""Raw extended records survive, while validity survives old schema-4 writers."""

import hashlib
import json

import pytest

from carveracontroller.headless.telemetry import parse_status
from carveracontroller.headless.tool_exchange import idle_report
from carveracontroller.machine.backend_telemetry import BackendTelemetry
from carveracontroller.machine.recording_checks import inspect_receipt
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording, recording_source_validity
from tests.unit.test_backend_telemetry import add, consume, packet, queue
from tests.unit.test_tool_exchange import state


def sealed(archive):
    payload = archive["payload"]
    archive["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    return json.dumps(archive, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def backend_archive():
    q, source = queue(), BackendTelemetry("session", "connection")
    add(q, 2, packet(extra="|SE:1,1,1,1,100,0,0,1,1"))
    consume(source, q, 2)
    return source.recording.export_bytes()


@pytest.mark.parametrize("old_writer", [False, True])
def test_invalid_raw_fields_are_retained_and_old_writer_cannot_erase_original_validity(old_writer):
    archive = json.loads(backend_archive())
    if old_writer:
        archive["payload"]["events"][0]["data"]["fields"].pop("SE")
    data = sealed(archive)
    replay = RecordingReplay(data)
    body = replay.payload["events"][0]["data"]
    assert recording_source_validity(body)["tool_status"] is False
    assert recording_source_validity(body)["spindle_status"] is False
    assert body["fields"]["T"] == [2, 47.5]
    assert body["fields"]["S"] == [12000, 12000, 100]
    checks = inspect_receipt(replay, 0, expected_tool=2)
    assert checks.reported_tool is None
    assert {item.code for item in checks.checks} >= {"tool_unknown", "spindle_invalid"}
    assert replay.export_bytes() == data


@pytest.mark.parametrize(
    "change", ["mask_conflict", "missing_source_mask", "malformed_original", "unsupported_original"]
)
def test_rehashed_archive_cannot_substitute_source_validity(change):
    archive = json.loads(backend_archive())
    body = archive["payload"]["events"][0]["data"]
    if change == "mask_conflict":
        body["fields"]["SE"][6] = 9
    else:
        receipt = body["source_receipt"]
        if change == "missing_source_mask":
            receipt["status_text"] = receipt["status_text"].split("|SE:")[0] + ">"
        else:
            receipt["status_text"] = receipt["status_text"].replace(
                "SE:1,1,1", "SE:1,1" if change == "malformed_original" else "SE:2,1,1"
            )
            body["fields"].pop("SE")  # Old-writer representation must still validate original text.
        receipt["status_sha256"] = hashlib.sha256(receipt["status_text"].encode()).hexdigest()
    with pytest.raises(ValueError):
        RecordingReplay(sealed(archive))


def test_malformed_direct_source_is_rejected_before_gap_or_status_mutation():
    record = RunRecording()
    record.capture_status("Idle", {}, 1, 1001, 0)
    before = record.export_bytes()
    status = packet(extra="|SE:1,1,1,1,100,0,0,1,1")
    status["raw_fields"]["SE"][0] = 2
    with pytest.raises(ValueError):
        record.capture_status("Idle", status["raw_fields"], 10, 1010, 0)
    assert record.export_bytes() == before


def test_invalid_tool_source_blocks_tool_exchange_and_measurement_admission():
    current = state()
    text = "<Idle|MPos:1,2,3|WPos:0,0,0|C:1,4,0,1|S:0,0,100|F:0,0,100|T:1,30,1,0|P:0,0,0,0|SE:1,1,1,1,100,0,33,1,1>"
    current["last_machine_snapshot"]["status"] = parse_status(text)
    with pytest.raises(ValueError, match="known tool"):
        idle_report(current, "wire")
