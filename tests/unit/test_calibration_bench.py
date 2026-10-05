import math
from unittest.mock import patch

import pytest

from carveracontroller.machine.calibration_bench import (
    assembly_calibrations,
    post_placement_receipts,
    sample_statistics,
)
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport


def test_raw_sample_statistics_keep_reported_spread_and_applied_offset_separate():
    report = {"measurements": [10, 10.1, 10.2], "max_delta": 0.3, "applied": 10.2}
    result = sample_statistics(report)
    assert result["count"] == 3
    assert result["mean_mm"] == pytest.approx(10.1)
    assert result["range_mm"] == pytest.approx(0.2)
    assert result["stdev_mm"] == pytest.approx(0.1)
    assert result["reported_spread_mm"] == 0.3 and result["applied_mm"] == 10.2
    assert result["spread_agrees"] is False
    assert report["max_delta"] == 0.3  # Never rewrite raw evidence to match the computation.


@pytest.mark.parametrize("samples", [[], [True], [1, math.nan], [1, math.inf], [1e308, -1e308]])
def test_incomplete_or_invalid_samples_do_not_create_partial_statistics(samples):
    result = sample_statistics({"measurements": samples, "max_delta": 0, "applied": None})
    assert result["count"] == len(samples)
    assert result["mean_mm"] is None and result["range_mm"] is None and result["stdev_mm"] is None
    assert result["spread_agrees"] is None


def test_one_sample_has_no_sample_standard_deviation():
    result = sample_statistics({"measurements": [10], "max_delta": 0, "applied": None})
    assert result["mean_mm"] == 10 and result["range_mm"] == 0
    assert result["stdev_mm"] is None and result["spread_agrees"] is True


def test_offset_changes_never_cross_revision_endpoint_tool_or_unknown_baselines(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Physical cutter", "Collet", 28)

    def capture(value, timestamp, endpoint="machine", tool=1):
        event = store.capture(tool, TloReport((28, 28.01), 0.01, value, timestamp), endpoint)
        store.link(event["id"], assembly["id"], "Operator attribution")
        return event

    first = capture(28, 100)
    capture(28.01, 101)
    capture(29, 102, endpoint="other")
    capture(29, 103, tool=2)
    capture(None, 104)
    capture(28.02, 105)
    capture(28.03, 99)  # Out-of-order measurement must break the baseline.
    capture(28.04, 106)
    store.revise(assembly["id"], assembly["id"], "New definition", "Collet", 29, "", "Reseated")
    capture(29, 107)
    rows = assembly_calibrations(store.events, assembly["id"])
    assert rows[0]["applied_change_mm"] is None
    assert rows[1]["applied_change_mm"] == pytest.approx(0.01)
    assert rows[1]["previous_receipt_id"] == first["id"]
    assert all(row["applied_change_mm"] is None for row in rows[2:])
    assert rows[-1]["revision_id"] != rows[0]["revision_id"]
    assert store.events[0]["name"] == "Physical cutter"


def test_unversioned_links_do_not_gain_comparable_revision_evidence(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Physical cutter", "", None)
    for index in range(2):
        report = store.capture(1, TloReport((28,), 0, 28 + index, 100 + index), "machine")
        store.link(report["id"], assembly["id"], "Legacy attribution")
    events = store.events
    for event in events:
        if event["kind"] == "link":
            event.pop("revision_id")
    assert all(row["applied_change_mm"] is None for row in assembly_calibrations(events, assembly["id"]))
    assert store.assembly(assembly["id"])["revision_id"] == assembly["id"]


def test_current_offset_receipt_requires_latest_matching_placement_and_source():
    assembly = {"id": "physical", "revision_id": "revision"}
    placement = {"assembly_id": "physical", "revision_id": "revision", "slot": 1, "at": 100}
    receipt = {"endpoint": "machine", "tool_number": 1, "at": 101, "report": {"timestamp": 101, "applied": 28}}
    rows = [{"revision_id": "revision", "receipt": receipt}]
    assert post_placement_receipts(rows, assembly, placement, "machine") == [receipt]
    assert not post_placement_receipts(rows, assembly, placement, "other")
    assert not post_placement_receipts(rows, assembly, None, "machine")
    assert not post_placement_receipts(rows, assembly, dict(placement, at=102), "machine")
    assert not post_placement_receipts(rows, assembly, dict(placement, slot=2), "machine")
    assert not post_placement_receipts(rows, dict(assembly, revision_id="new"), placement, "machine")
    receipt["report"]["timestamp"] = 99
    assert not post_placement_receipts(rows, assembly, placement, "machine")
    receipt["report"].update(timestamp=101, applied=None)
    assert not post_placement_receipts(rows, assembly, placement, "machine")
