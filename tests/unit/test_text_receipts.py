import base64
import hashlib
import json

import pytest

from carveracontroller.headless.text_receipts import TextReceipts
from tests.unit.test_tool_measurement import review


def observe(receipts, text, now=11):
    event = {"event": "unsolicited_response", "text": text}
    raw = json.dumps(event).encode() + b"\n"
    receipts.observe(event, raw, now, 100)
    return raw


def test_original_ipc_loss_independent_cursors_and_connection_retirement():
    receipts = TextReceipts(2)
    receipts.observe({"event": "connection", "connected": True, "connection_id": "wire"}, b"", 10, 100)
    raw = observe(receipts, "late measurement")
    first = receipts.since(0)
    duplicate = receipts.since(0)
    assert first == duplicate and first["latest_sequence"] == 1
    row = first["receipts"][0]
    assert base64.b64decode(row["original_ipc_bytes_base64"]) == raw
    assert row["ipc_sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["controller_original_bytes_retained"] is False and row["normalized_by_backend"] is True
    assert row["command_attribution_verified"] is False
    row["text"] = "mutated projection"
    assert receipts.since(0) == duplicate
    observe(receipts, "second")
    observe(receipts, "third")
    assert receipts.since(0)["lost_receipts"] == 1
    assert receipts.since(1)["lost_receipts"] == 0
    receipts.observe({"event": "connection", "connected": False}, b"", 12, 100)
    observe(receipts, "after disconnect")
    assert receipts.since(3)["receipts"][0]["connection_id"] is None


def batch():
    receipts = TextReceipts()
    receipts.observe({"event": "connection", "connected": True, "connection_id": "wire"}, b"", 10, 100)
    observe(receipts, "late measurement")
    return {"session_id": "child", **receipts.since(0)}


def test_normalized_text_can_be_retained_but_cannot_claim_original_firmware_bytes():
    value = batch()
    rows = review().normalized_output(value, 0)
    assert rows[0]["controller_original_bytes_retained"] is False
    assert rows[0]["command_attribution_verified"] is False


@pytest.mark.parametrize(
    "change",
    [
        "owner",
        "connection",
        "loss",
        "sequence",
        "cursor",
        "text",
        "hash",
        "raw",
        "qualified",
        "attributed",
        "clock",
        "utc",
        "truncation",
        "boolean_sequence",
    ],
)
def test_output_owner_sequence_and_original_ipc_projection_are_checked(change):
    value = batch()
    row = value["receipts"][0]
    if change == "owner":
        value["session_id"] = "other"
    elif change == "connection":
        row["connection_id"] = "other"
    elif change == "loss":
        value["lost_receipts"] = 1
    elif change == "sequence":
        row["sequence"] = 3
    elif change == "cursor":
        value["latest_sequence"] = 3
    elif change == "text":
        row["text"] = "changed"
    elif change == "hash":
        row["ipc_sha256"] = "changed"
    elif change == "raw":
        row["original_ipc_bytes_base64"] = "?"
    elif change == "qualified":
        row["controller_original_bytes_retained"] = True
    elif change == "clock":
        row["received_at_s"] = float("nan")
    elif change == "utc":
        row["received_utc_s"] = -1
    elif change == "truncation":
        row["text_may_be_truncated"] = True
    elif change == "boolean_sequence":
        row["sequence"] = True
    else:
        row["command_attribution_verified"] = True
    with pytest.raises(ValueError):
        review().normalized_output(value, 0)


@pytest.mark.parametrize("change", ["raw", "clock", "missing_clock", "truncated", "event"])
def test_invalid_input_is_not_retained(change):
    receipts = TextReceipts()
    event = {"event": "unsolicited_response", "text": "line"}
    raw = json.dumps(event).encode() + b"\n"
    now = 11
    if change == "raw":
        raw = b"{}\n"
    elif change == "clock":
        now = float("nan")
    elif change == "missing_clock":
        now = None
    elif change == "truncated":
        event["text"] = "x" * 513
        raw = json.dumps(event).encode() + b"\n"
    else:
        raw = b"not json\n"
    with pytest.raises(ValueError):
        receipts.observe(event, raw, now, 100)
    assert receipts.since(0)["receipts"] == []
