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
    with pytest.raises(CustodyError, match="being written"):
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
