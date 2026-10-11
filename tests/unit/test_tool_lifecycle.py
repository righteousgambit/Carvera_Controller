import json
import math

import pytest

from carveracontroller.machine.tool_custody import CustodyError, ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport
from carveracontroller.machine.tool_lifecycle import describe, page, summary
from carveracontroller.machine.tool_passport import passport_sections


def use(store, assembly, **changes):
    fields = {
        "seconds": 90,
        "material": "6061",
        "reference": "job-A/interval-1",
        "source": "run receipt A",
        "note": "Finished pocket; visual finish acceptable",
        "occurred_at": 100,
    }
    fields.update(changes)
    return store.record_use(assembly["id"], assembly["revision_id"], **fields)


def assembly(store, name="A"):
    return store.assembly(store.create_assembly(name)["id"])


def replace(store, old, new, **changes):
    fields = {"source": "inventory log", "note": "Edge chipped; replacement tag checked", "occurred_at": 200}
    fields.update(changes)
    return store.record_replacement(old["id"], old["revision_id"], new["id"], new["revision_id"], **fields)


def test_replacement_preserves_old_evidence_and_current_placement(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a, b = assembly(store), assembly(store, "B")
    use(store, a)
    raw = store.capture(2, TloReport((50, 50.01), 0.01, 50, 123))
    store.link(raw["id"], a["id"], "Tag confirmed")
    place = store.assign("machine", 2, a["id"])
    before = store.events
    replace(store, a, b)
    restored = ToolCustodyStore(store.path)
    assert restored.events[: len(before)] == before
    assert restored.assignment("machine", 2) == place
    assert restored.assembly_reports(a["id"]) == [raw]
    assert restored.assembly_reports(b["id"]) == []
    assert "1.5 minutes" in "\n".join(summary(restored, a["id"]))
    assert "0 minutes" in "\n".join(summary(restored, b["id"]))
    assert "reconciliation" in "\n".join(summary(restored, a["id"]))
    with pytest.raises(CustodyError, match="declared replaced"):
        restored.assign("machine", 3, a["id"])
    restored.release("machine", 2, a["id"], place["id"], "Removed old cutter")
    restored.assign("machine", 2, b["id"])
    assert restored.assignment("machine", 2)["assembly_id"] == b["id"]
    # A later-entered receipt for earlier use retains the old identity.
    use(restored, a, reference="job-A/interval-2", occurred_at=150)
    with pytest.raises(CustodyError, match="Use occurred after"):
        use(restored, a, reference="job-after", occurred_at=201)


@pytest.mark.parametrize(
    "changes",
    [
        {"seconds": -1},
        {"seconds": True},
        {"seconds": math.nan},
        {"seconds": 31557601},
        {"source": ""},
        {"note": ""},
        {"reference": ""},
        {"occurred_at": math.inf},
        {"occurred_at": 4102444801},
    ],
)
def test_bad_use_preserves_history_and_releases_lock(tmp_path, changes):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = assembly(store)
    before = store.path.read_bytes()
    with pytest.raises(CustodyError):
        use(store, a, **changes)
    assert store.path.read_bytes() == before
    assert not store.path.with_suffix(".lock").exists()


def test_duplicate_reference_and_stale_revision_are_atomic(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = assembly(store)
    use(store, a)
    other = ToolCustodyStore(store.path)
    before = store.path.read_bytes()
    with pytest.raises(CustodyError, match="already recorded"):
        use(other, a, reference=" job-A/interval-1 ")
    assert store.path.read_bytes() == before
    other.revise(a["id"], a["revision_id"], "Reseated", note="Changed seating")
    before = store.path.read_bytes()
    with pytest.raises(CustodyError, match="changed since lifecycle"):
        use(store, a, reference="new")
    assert store.path.read_bytes() == before
    assert store.assembly(a["id"])["revision_count"] == 2


def test_replacement_cycles_duplicate_targets_and_chronology_rejected(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a, b, c = assembly(store), assembly(store, "B"), assembly(store, "C")
    use(store, a)
    with pytest.raises(CustodyError, match="predates recorded use"):
        replace(store, a, b, occurred_at=99)
    with pytest.raises(CustodyError, match="distinct active"):
        replace(store, a, a)
    replace(store, a, b)
    with pytest.raises(CustodyError, match="distinct active"):
        replace(store, c, b)
    with pytest.raises(CustodyError, match="distinct active"):
        replace(store, b, a)
    with pytest.raises(CustodyError, match="incoming replacement"):
        replace(store, b, c, occurred_at=199)
    replace(store, b, c, occurred_at=250)
    assert len(store.lifecycle_events(b["id"])) == 2


def test_inspection_observation_order_units_and_all_history_pages(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = assembly(store)
    for i in range(43):
        use(store, a, reference=f"interval-{i}", occurred_at=100 + i)
    for observed, condition in ((190, "monitor"), (180, "serviceable")):
        store.record_inspection(
            a["id"],
            a["revision_id"],
            condition=condition,
            measured_diameter_mm=6.30,
            method="micrometer",
            source="inspection log",
            note="Two-axis measurement",
            occurred_at=observed,
        )
    assert "Latest operator inspection: monitor" in "\n".join(summary(store, a["id"]))
    rows, pages = page(store, a["id"])
    assert pages == 3 and len(rows) == 20
    all_rows = [row for i in range(pages) for row in page(store, a["id"], i)[0]]
    assert len({row["id"] for row in all_rows}) == 45
    assert "6.3 mm" in describe(rows[0]) and "inspection log" in describe(rows[0])
    assert page(store, a["id"], 999)[0] == page(store, a["id"], 2)[0]
    assert "Lifecycle" in passport_sections(store, a["id"], {})
    assert ToolCustodyStore(store.path).error is None
    data = json.loads(store.path.read_text())
    data["events"][-1]["condition"] = "perfect"
    store.path.write_text(json.dumps(data))
    assert ToolCustodyStore(store.path).error


def test_future_observation_and_stale_replacement_cannot_publish(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a, b = assembly(store), assembly(store, "B")
    with pytest.raises(CustodyError, match="after the saved receipt"):
        use(store, a, occurred_at=4102444800)
    other = ToolCustodyStore(store.path)
    other.revise(b["id"], b["revision_id"], "B reseated", note="New seating")
    before = store.path.read_bytes()
    with pytest.raises(CustodyError, match="Replacement changed"):
        replace(store, a, b)
    assert store.path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("condition", {}), ("occurred_at", 10**400), ("kind", [])])
def test_corrupt_lifecycle_fields_preserved_without_startup_crash(tmp_path, field, value):
    store = ToolCustodyStore(tmp_path / "custody.json")
    a = assembly(store)
    store.record_inspection(
        a["id"],
        a["revision_id"],
        condition="monitor",
        measured_diameter_mm=None,
        method="visual",
        source="photo",
        note="Inspect edge",
        occurred_at=100,
    )
    data = json.loads(store.path.read_text())
    data["events"][-1][field] = value
    store.path.write_text(json.dumps(data))
    before = store.path.read_bytes()
    restored = ToolCustodyStore(store.path)
    assert restored.error and store.path.read_bytes() == before
