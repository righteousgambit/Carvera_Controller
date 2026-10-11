import hashlib
import json

import pytest

from carveracontroller.headless.status_receipts import StatusReceipts
from carveracontroller.headless.telemetry import parse_status
from carveracontroller.machine.backend_live_report import BackendLiveReport
from carveracontroller.machine.backend_telemetry import BackendTelemetry
from carveracontroller.machine.receipt_playback import ReceiptPlayback
from carveracontroller.machine.recording_checks import inspect_receipt
from carveracontroller.machine.run_recording import RecordingReplay, load_recording


def packet(rpm=12000, extra="", inches=False):
    return parse_status(
        f"<Idle|MPos:1,2,3,0|WPos:0,0,0,0|C:1,4,{int(inches)},1|R:0|G:0|S:{rpm},12000,100|F:0,0,100|T:2,47.5{extra}>"
    )


def queue(capacity=256):
    result = StatusReceipts(capacity)
    result.observe({"event": "connection", "connected": True, "connection_id": "connection"}, b"connected\n", 1, 1000)
    return result


def add(q, stamp, status=None):
    event = {"event": "observation", "kind": "status", "observation": packet() if status is None else status}
    raw = (json.dumps(event) + "\n").encode()
    q.observe(event, raw, stamp, 1000 + stamp)
    return raw


def consume(source, q, now, current=True):
    report = BackendLiveReport(packet() if current else None, session_id="session", connection_id="connection")
    source.consume({"session_id": "session", **q.since(source.cursor)}, report, now)


def test_each_original_event_receipt_is_counted_once_without_repeated_snapshot_samples():
    q, source = queue(), BackendTelemetry("session", "connection")
    original = add(q, 2)
    consume(source, q, 2.1)
    before = source.recording.export_bytes()
    for now in (2.2, 2.3, 2.4):
        consume(source, q, now)
    assert source.recording.export_bytes() == before and len(source.monitor.history) == 1
    event = load_recording(before)["events"][0]
    assert event["data"]["source_receipt"] == {
        "sequence": 1,
        "ipc_sha256": hashlib.sha256(original).hexdigest(),
        "status_text": packet()["raw"],
        "status_sha256": hashlib.sha256(packet()["raw"].encode()).hexdigest(),
    }
    assert event["monotonic_at"] == 2 and event["utc_at"] == 1002
    detached = q.since(0)
    detached["receipts"][0]["status"]["raw_fields"].clear()
    assert q.since(0)["receipts"][0]["status"]["raw_fields"]


@pytest.mark.parametrize("raw", [None, 3, {}, b"<Idle>"])
def test_malformed_original_text_rejects_receipt_without_crashing_monitor(raw):
    q, source = queue(), BackendTelemetry("session", "connection")
    add(q, 1)
    batch = {"session_id": "session", **q.since(0)}
    batch["receipts"][0]["status"]["raw"] = raw
    source.consume(batch, BackendLiveReport(packet(), session_id="session", connection_id="connection"), 1)
    assert source.rejected_receipts == 1 and source.monitor.fault
    assert source.recording.summary()["retained_events"] == 0


def test_connection_event_ownership_prevents_preconnect_or_replaced_connection_packets_from_entering_buffer():
    q, source = StatusReceipts(), BackendTelemetry("session", "connection")
    add(q, 1)
    q.observe({"event": "connection", "connected": True, "connection_id": "replacement"}, b"other\n", 2, 1002)
    add(q, 3)
    consume(source, q, 3)
    assert source.recording.summary()["retained_events"] == 0
    assert source.rejected_receipts == 2 and not source.monitor.history


def test_real_receipt_sequence_captures_baseline_and_replaced_owner_never_inherits_it():
    q, source = queue(), BackendTelemetry("session", "connection")
    source.command("adaptive baseline")
    for i in range(28):
        now = 1 + i * 0.2
        add(q, now)
        consume(source, q, now)
    assert source.monitor.baseline and source.monitor.baseline["rpm"] == 12000
    replacement = BackendTelemetry("session", "replacement")
    assert replacement.monitor.baseline is None and replacement.recording.source != source.recording.source
    assert source.monitor.snapshot(6.4)["active_control_available"] is False


def test_invalid_firmware_spindle_source_retires_baseline_until_explicit_recapture():
    q, source = queue(), BackendTelemetry("session", "connection")
    source.command("adaptive baseline")
    for i in range(28):
        now = 1 + i * 0.2
        add(q, now)
        consume(source, q, now)
    assert source.monitor.baseline
    add(q, 7, packet(extra="|SE:1,1,1,1,100,0,8,1,1"))
    consume(source, q, 7)
    assert source.monitor.baseline is None and source.monitor.fault and not source.latest_complete
    add(q, 7.2, packet(extra="|SE:1,1,1,2,200,0,9,1,1"))
    consume(source, q, 7.2)
    assert source.monitor.baseline is None and source.monitor.fault
    source.command("adaptive baseline")
    for i in range(28):
        now = 7.4 + i * 0.2
        add(q, now, packet(extra=f"|SE:1,1,1,{i + 3},{300 + i},0,9,1,1"))
        consume(source, q, now)
    assert source.monitor.baseline and source.monitor.fault is None


def test_overflow_is_exported_as_missing_evidence_and_playback_stops_at_the_boundary():
    q, source = queue(2), BackendTelemetry("session", "connection")
    add(q, 1)
    consume(source, q, 1)
    source.command("adaptive baseline")
    for now in (1.2, 1.4, 1.6, 1.8):
        add(q, now)
    consume(source, q, 1.8)
    assert source.lost_receipts == 2 and source.monitor.baseline is None and source.monitor.fault
    replay = RecordingReplay(source.recording.export_bytes())
    assert replay.payload["source"] == source.source and replay.payload["schema"] == 4
    assert [event["kind"] for event in replay.payload["events"]] == ["status", "source_gap", "status", "status"]
    assert replay.payload["events"][1]["data"]["lost_receipts"] == 2
    assert replay.at(1.3)["sample"] is None
    assert inspect_receipt(replay, 1).checks[0].code == "source_gap"
    playback = ReceiptPlayback(replay)
    playback.play(0, 10)
    result = playback.advance(11)
    assert result.missing and not result.running and result.reason == "source_gap"


@pytest.mark.parametrize(
    "status", [parse_status("<Idle|C:1,4,0,1|S:12000,12000,100>"), packet(extra="|PWM:2"), packet(extra="|PWM:0.4,0.5")]
)
def test_partial_or_invalid_load_packet_is_retained_but_cannot_extend_a_baseline(status):
    q, source = queue(), BackendTelemetry("session", "connection")
    add(q, 1)
    consume(source, q, 1)
    source.command("adaptive baseline")
    add(q, 1.2, status)
    consume(source, q, 1.2)
    assert source.monitor.baseline is None and source.monitor.fault and not source.latest_complete
    assert source.recording.summary()["retained_events"] == 2


def test_wire_units_pwm_and_raw_tool_reference_survive_archive_while_monitor_uses_normalized_xyz():
    q, source = queue(), BackendTelemetry("session", "connection")
    add(q, 1, packet(extra="|PWM:0.4", inches=True))
    consume(source, q, 1)
    assert source.monitor.last.position == pytest.approx((25.4, 50.8, 76.2))
    assert source.monitor.last.pwm == 0.4
    replay = RecordingReplay(source.recording.export_bytes())
    assert replay.machine_point(0) == pytest.approx((25.4, 50.8, 76.2))
    assert replay.payload["events"][0]["data"]["fields"]["T"] == [2, 47.5]
    assert replay.payload["events"][0]["data"]["fields"]["PWM"] == [0.4]


@pytest.mark.parametrize(
    "change", ["owner", "sequence", "digest", "missing_receipt", "generation", "gap_count", "raw_text", "fields"]
)
def test_rehashed_backend_archive_still_rejects_malformed_source_semantics(change):
    q, source = queue(2), BackendTelemetry("session", "connection")
    add(q, 1)
    consume(source, q, 1)
    for now in (2, 3, 4):
        add(q, now)
    consume(source, q, 4)
    archive = json.loads(source.recording.export_bytes())
    payload = archive["payload"]
    if change == "owner":
        payload["source"]["connection_id"] = "bad\nidentity"
    elif change == "sequence":
        payload["events"][-1]["data"]["source_receipt"]["sequence"] = 1
    elif change == "digest":
        payload["events"][-1]["data"]["source_receipt"]["ipc_sha256"] = "bad"
    elif change == "missing_receipt":
        payload["events"][-1]["data"].pop("source_receipt")
    elif change == "generation":
        payload["events"][-1]["generation"] = 1
    elif change == "raw_text":
        payload["events"][-1]["data"]["source_receipt"]["status_text"] = "<Run|S:2>"
    elif change == "fields":
        payload["events"][-1]["data"]["fields"]["S"][0] = 999
    else:
        payload["events"][1]["data"]["lost_receipts"] = -1
    archive["sha256"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    with pytest.raises(ValueError):
        load_recording(json.dumps(archive).encode())


def test_changed_event_body_or_unknown_clock_never_enters_original_receipt_queue():
    q = queue()
    status = packet()
    status["spindle_rpm"] = 999
    with pytest.raises(ValueError):
        add(q, 1, status)
    with pytest.raises(ValueError):
        add(q, float("nan"))
    assert q.since(0)["latest_sequence"] == 0
