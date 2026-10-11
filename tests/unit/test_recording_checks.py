import json
from hashlib import sha256

import pytest

from carveracontroller.machine.recording_checks import inspect_receipt
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording


def archive():
    record = RunRecording(gap_seconds=2)
    record.capture_status("Run", {"MPos": [1, 2, 3], "C": [0, 0, 0], "T": [1, 40]}, 10, 1000, 1)
    record.capture_status("Alarm:1", {"T": [2]}, 11, 1001, 1)
    record.capture_status("Disconnected", {}, 14, 1004, 1)
    record.capture_status("Run", {"T": [3]}, 15, 1005, 2)
    return RecordingReplay(record.export_bytes())


def codes(result):
    return {item.code for item in result.checks}


def test_age_budget_tool_comparison_and_packet_local_unknowns_are_read_only():
    replay = archive()
    before = replay.export_bytes()
    assert not inspect_receipt(replay, 0, expected_tool=1).checks
    at_budget = inspect_receipt(replay, 0, 10.8, expected_tool=1)
    assert "stale" not in codes(at_budget)
    stale = inspect_receipt(replay, 0, 10.9, expected_tool=2)
    assert codes(stale) == {"stale", "tool_mismatch"}
    assert stale.sample_age_seconds == pytest.approx(0.9)
    alarm = inspect_receipt(replay, 1, expected_tool=1)
    assert codes(alarm) == {"alarm", "tool_mismatch", "position_unknown"}
    disconnected = inspect_receipt(replay, 3, expected_tool=1)
    assert codes(disconnected) == {"disconnected", "tool_unknown", "position_unknown"}
    assert disconnected.reported_tool is None  # Never borrows T2 from the prior receipt.
    assert replay.export_bytes() == before


def test_gap_intervals_and_duplicate_timestamp_boundaries_are_not_status_receipts():
    replay = archive()
    assert "missing_interval" in codes(inspect_receipt(replay, 1, 11.1))
    gap = inspect_receipt(replay, 2)
    assert codes(gap) == {"gap"} and gap.sample_age_seconds is None
    boundary = inspect_receipt(replay, 4)
    assert codes(boundary) == {"connection_boundary"} and boundary.reported_tool is None
    status = inspect_receipt(replay, 5)
    assert status.reported_tool == 3  # Same timestamp as boundary, distinct selected sequence.
    with pytest.raises(ValueError, match="interval"):
        inspect_receipt(replay, 0, 11.1)


@pytest.mark.parametrize("expected", [True, -1, 10000, 1.5, "T1"])
def test_invalid_logical_tool_expectations_are_rejected(expected):
    with pytest.raises(ValueError, match="logical tool"):
        inspect_receipt(archive(), 0, expected_tool=expected)


@pytest.mark.parametrize(
    "budget",
    [True, 0, -1, 3601, float("nan"), float("inf"), 10**10000],
    ids=["bool", "zero", "negative", "too_long", "nan", "infinite", "huge"],
)
def test_invalid_age_budgets_are_rejected_without_overflow(budget):
    with pytest.raises(ValueError, match="freshness budget"):
        inspect_receipt(archive(), 0, max_age_seconds=budget)


@pytest.mark.parametrize(
    "stamp",
    [True, 9, 16, float("nan"), float("inf"), 10**10000],
    ids=["bool", "before", "after", "nan", "infinite", "huge"],
)
def test_invalid_review_times_are_rejected(stamp):
    with pytest.raises(ValueError, match="interval"):
        inspect_receipt(archive(), 0, stamp)


def test_integer_wire_tool_fields_and_fractional_tool_reports():
    replay = archive()
    envelope = json.loads(replay.export_bytes())
    for value, expected in ((1, 1), (1.5, None), (-1, None)):
        envelope["payload"]["events"][0]["data"]["fields"]["T"] = [value]
        raw = json.dumps(envelope["payload"], sort_keys=True, separators=(",", ":")).encode()
        envelope["sha256"] = sha256(raw).hexdigest()
        changed = RecordingReplay(json.dumps(envelope).encode())
        result = inspect_receipt(changed, 0, expected_tool=1)
        assert result.reported_tool == expected
        assert ("tool_unknown" in codes(result)) == (expected is None)
