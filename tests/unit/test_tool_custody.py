import json
from unittest.mock import patch

import pytest

from carveracontroller.machine.tool_custody import CustodyError, ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport


def test_identity_survives_slot_reassignment_and_restart(tmp_path):
    path = tmp_path / "custody.json"
    store = ToolCustodyStore(path)
    a = store.create_assembly("Ball #1", "Collet A", 31)
    b = store.create_assembly("Ball #2", "Collet B", 28)
    raw = store.capture(2, TloReport((50, 50.01), 0.01, 50.01, 123), "machine-one:2222")
    assert not store.assembly_reports(a["id"])
    store.assign("machine-one", 2, a["id"])
    store.link(raw["id"], a["id"], "Inventory tag checked against setup photograph")
    original = store.events
    store.assign("machine-one", 2, b["id"])
    restored = ToolCustodyStore(path)
    assert restored.assignment("machine-one", 2)["assembly_id"] == b["id"]
    assert restored.assignment("machine-two", 2) is None
    assert restored.assembly_reports(a["id"]) == [raw]
    assert restored.assembly_reports(b["id"]) == []
    assert restored.events[: len(original)] == original
    detached = restored.events
    detached[0]["name"] = "Changed"
    assert restored.events[0]["name"] == "Ball #1"
    with pytest.raises(CustodyError, match="already linked"):
        restored.link(raw["id"], b["id"], "Reassign")


@pytest.mark.parametrize("bad", ["{bad", '{"schema": 999, "events": []}'])
def test_corrupt_file_preserved_and_error_visible(tmp_path, bad):
    path = tmp_path / "custody.json"
    path.write_text(bad)
    store = ToolCustodyStore(path)
    assert store.error
    with pytest.raises(ValueError):
        store.create_assembly("New")
    assert path.read_text() == bad
    assert not path.with_suffix(".lock").exists()


def test_concurrent_instances_merge_and_atomic_failure_preserves_receipt(tmp_path):
    path = tmp_path / "custody.json"
    first, second = ToolCustodyStore(path), ToolCustodyStore(path)
    a = first.create_assembly("One")
    second.create_assembly("Two")
    assert len(ToolCustodyStore(path).events) == 2
    before = path.read_bytes()
    with (
        patch("carveracontroller.machine.tool_custody.os.replace", side_effect=OSError("disk failure")),
        pytest.raises(OSError),
    ):
        first.assign("machine", 1, a["id"])
    assert path.read_bytes() == before
    assert not path.with_suffix(".lock").exists()
    path.with_suffix(".lock").write_text("another writer")
    with pytest.raises(CustodyError, match="writer lock exists"):
        first.create_assembly("Three")
    assert path.read_bytes() == before


def test_validation_cannot_persist_nonfinite_or_unattributed_links(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = store.create_assembly("One")
    before = store.path.read_bytes()
    for report in [TloReport((float("nan"),), 0), TloReport((1,), -1)]:
        with pytest.raises(CustodyError):
            store.capture(1, report)
    with pytest.raises(CustodyError):
        store.link("missing", a["id"], "checked")
    assert store.path.read_bytes() == before
    assert json.loads(before)["events"][0]["id"] == a["id"]


def test_unknown_tool_receipts_and_declared_moves_are_not_measurement_transfers(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = store.create_assembly("One")
    raw = store.capture(None, TloReport((1, 1.01), 0.01, None, 123))
    assert raw["tool_number"] is None
    store.assign("machine-A", 2, a["id"])
    store.assign("machine-B", 4, a["id"])
    assert store.assignment("machine-A", 2) is None
    assert store.assignment("machine-B", 4)["assembly_id"] == a["id"]
    assert not store.assembly_reports(a["id"])
    assert len([e for e in store.events if e["kind"] == "assignment"]) == 2


def test_revision_preserves_identity_and_measurement_attribution(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    initial = store.create_assembly("Ball", "A", 31, "design-A")
    raw = store.capture(2, TloReport((50, 50.01), 0.01, 50.01, 123))
    store.link(raw["id"], initial["id"], "Original setup")
    assignment = store.assign("machine", 2, initial["id"])
    before = store.events
    revised = store.revise(initial["id"], initial["id"], "Ball revised", "B", 28, "design-B", "Reseated cutter")
    restored = ToolCustodyStore(store.path)
    current = restored.assembly(initial["id"])
    assert current["id"] == initial["id"]
    assert current["revision_id"] == revised["id"]
    assert current["revision_count"] == 2
    assert current["stickout_mm"] == 28
    assert restored.events[: len(before)] == before
    assert restored.assembly_reports(initial["id"]) == [raw]
    assert restored.assignment("machine", 2) == assignment
    assert next(e for e in restored.events if e["kind"] == "link")["revision_id"] == initial["id"]
    with pytest.raises(CustodyError, match="changed since review"):
        store.revise(initial["id"], initial["id"], "Stale", note="Old editor")
    with pytest.raises(CustodyError, match="changed since review"):
        store.assign("machine", 2, initial["id"], initial["id"])
    assert len(restored.revisions(initial["id"])) == 2


def test_stale_removal_cannot_clear_replacement_and_history_survives(tmp_path):
    path = tmp_path / "custody.json"
    store = ToolCustodyStore(path)
    a = store.create_assembly("A")
    b = store.create_assembly("B")
    old = store.assign("machine", 2, a["id"])
    other = ToolCustodyStore(path)
    replacement = other.assign("machine", 2, b["id"])
    before = path.read_bytes()
    with pytest.raises(CustodyError, match="changed since review"):
        store.release("machine", 2, a["id"], old["id"], "Removed A")
    assert path.read_bytes() == before
    with pytest.raises(CustodyError, match="removal note"):
        other.release("machine", 2, b["id"], replacement["id"], "")
    other.release("machine", 2, b["id"], replacement["id"], "Moved B into storage")
    restored = ToolCustodyStore(path)
    assert restored.assignment("machine", 2) is None
    assert restored.assembly(b["id"])["name"] == "B"
    assert len(restored.events) == 5


def test_legacy_events_remain_explicitly_unversioned(tmp_path):
    path = tmp_path / "custody.json"
    store = ToolCustodyStore(path)
    a = store.create_assembly("A")
    raw = store.capture(1, TloReport((1,), 0))
    store.append("link", report_id=raw["id"], assembly_id=a["id"], note="Legacy attribution")
    store.append("assignment", machine_id="machine", slot=1, assembly_id=a["id"])
    restored = ToolCustodyStore(path)
    assert "revision_id" not in restored.assignment("machine", 1)
    assert "revision_id" not in next(e for e in restored.events if e["kind"] == "link")
    assert restored.assembly_reports(a["id"]) == [raw]


def test_reviewed_assignment_cannot_overwrite_unseen_slot_change(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = store.create_assembly("A")
    b = store.create_assembly("B")
    other = ToolCustodyStore(store.path)
    previous = other.assign("machine", 2, b["id"])
    with pytest.raises(CustodyError, match="changed since review"):
        store.assign("machine", 2, a["id"], expected_assignment_id=None)
    store.assign("machine", 2, a["id"], expected_assignment_id=previous["id"])
    assert store.assignment("machine", 2)["assembly_id"] == a["id"]
