"""Evidence validity and invalidation, independent of hardware/UI."""

import json

import pytest

from carveracontroller.machine.setup_readiness import SetupEvidenceStore, evaluate_setup, fingerprint


def items(store, snapshot=None, present=None, now=120, machine="one"):
    return evaluate_setup(
        machine,
        snapshot or {k: {"value": 1} for k in ("stock", "tools", "workholding", "offsets")},
        present or dict.fromkeys(("stock", "tools", "workholding", "offsets"), True),
        store,
        now,
    )


def test_receipt_survives_restart_and_changed_setup_remains_stale(tmp_path):
    path = tmp_path / "evidence.json"
    store = SetupEvidenceStore(path)
    store.record("one", "stock", {"value": 1}, "inspection-42", "micrometer", 100, 200)
    restored = SetupEvidenceStore(path)
    assert items(restored)[0].state == "measured"
    changed = {k: {"value": 2} for k in ("stock", "tools", "workholding", "offsets")}
    assert items(restored, changed)[0].state == "stale"
    assert restored.latest("one", "stock")["source"] == "inspection-42"
    assert items(restored, machine="two")[0].state == "entered"


@pytest.mark.parametrize("now", [99, 200, 300])
def test_expired_and_future_receipts_are_stale(tmp_path, now):
    store = SetupEvidenceStore(tmp_path / "evidence.json")
    store.record("one", "stock", {"value": 1}, "receipt", "probe", 100, 200)
    assert items(store, now=now)[0].state == "stale"


def test_absent_components_and_corrupt_store_never_become_measured(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text("{broken")
    store = SetupEvidenceStore(path)
    assert all(item.state == "unresolved" for item in items(store))
    with pytest.raises(ValueError, match="Repair"):
        store.record("one", "stock", {}, "receipt", "probe", 100, 200)
    assert path.read_text() == "{broken"


def test_parallel_store_instances_preserve_receipts(tmp_path):
    path = tmp_path / "evidence.json"
    a, b = SetupEvidenceStore(path), SetupEvidenceStore(path)
    a.record("one", "stock", {}, "one", "probe", 100, 200)
    b.record("two", "tools", {}, "two", "setter", 100, 200)
    assert len(SetupEvidenceStore(path).records) == 2


@pytest.mark.parametrize(
    "source,method,start,end",
    [("", "probe", 100, 200), ("ref", "", 100, 200), ("ref", "probe", 100, 99), ("ref", "probe", float("nan"), 200)],
)
def test_invalid_measurement_records_do_not_write(tmp_path, source, method, start, end):
    path = tmp_path / "evidence.json"
    with pytest.raises(ValueError):
        SetupEvidenceStore(path).record("one", "stock", {}, source, method, start, end)
    assert not path.exists()


def test_nonfinite_geometry_and_unsupported_schema_rejected(tmp_path):
    with pytest.raises(ValueError):
        fingerprint({"dimension": float("nan")})
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({"schema_version": True, "receipts": []}))
    assert SetupEvidenceStore(path).error


@pytest.mark.parametrize("bad", [True, None, "100", 10**1000, float("inf"), -1])
def test_invalid_imported_dates_reject_cleanly_without_store_mutation(tmp_path, bad):
    path = tmp_path / "evidence.json"
    store = SetupEvidenceStore(path)
    receipt = store.record("one", "stock", {"value": 1}, "original", "probe", 100, 200)
    original = path.read_bytes()
    for key in ("measured_at", "expires_at"):
        invalid = dict(receipt, **{key: bad})
        with pytest.raises(ValueError, match="UTC dates"):
            store.validate(invalid)
    with pytest.raises(ValueError, match="UTC dates"):
        items(store, now=bad)
    assert path.read_bytes() == original and len(store.records) == 1


def test_readiness_distinguishes_future_expiration_and_dependency_changes(tmp_path):
    from types import MappingProxyType

    store = SetupEvidenceStore(tmp_path / "evidence.json")
    receipt = store.record("one", "stock", {"value": 1}, "original", "probe", 100, 200)
    snapshots = MappingProxyType({group: {"value": 1} for group in ("stock", "tools", "workholding", "offsets")})
    present = MappingProxyType(dict.fromkeys(snapshots, True))
    future = evaluate_setup("one", snapshots, present, store, 99)[0]
    expired = evaluate_setup("one", snapshots, present, store, 200)[0]
    assert "dated in the future" in future.detail
    assert "validity interval expired" in expired.detail
    assert future.receipt == expired.receipt == receipt
    assert evaluate_setup("one", snapshots, present, store, 100)[0].state == "measured"
    assert store.validate(receipt) is not receipt
    assert len(store.records) == 1


def test_mounting_details_roundtrip_remain_bound_and_preserve_legacy_receipts(tmp_path):
    path = tmp_path / "evidence.json"
    store = SetupEvidenceStore(path)
    legacy = store.record("one", "stock", {"value": 1}, "stock-log", "micrometer", 100, 200)
    details = {"hole_labels": [" A1 ", "B3"], "jaw_contact_notes": "Fixed jaw shoulder", "stock_protrusion_mm": 6.35}
    receipt = store.record("one", "workholding", {"value": 1}, "mount-log", "indicator", 100, 200, mounting=details)
    details["hole_labels"].append("C5")
    restored = SetupEvidenceStore(path)
    assert not restored.error and restored.records[0] == legacy and "mounting" not in legacy
    assert restored.latest("one", "workholding")["mounting"]["hole_labels"] == ["A1", "B3"]
    assert restored.latest("one", "workholding")["mounting"]["stock_protrusion_mm"] == 6.35
    assert items(restored)[1].state == "measured"
    changed = {k: {"value": 2} for k in ("stock", "tools", "workholding", "offsets")}
    assert items(restored, changed)[1].state == "stale"
    assert restored.latest("one", "workholding") == receipt


@pytest.mark.parametrize(
    "update",
    [
        {"hole_labels": ["A1", "a1"]},
        {"hole_labels": ["A1", ""]},
        {"hole_labels": ["A1"] * 17},
        {"hole_labels": ["a" * 81]},
        {"hole_labels": ["A1\nB3"]},
        {"stock_protrusion_mm": True},
        {"stock_protrusion_mm": float("nan")},
        {"stock_protrusion_mm": -1},
        {"stock_protrusion_mm": 1001},
        {"jaw_contact_notes": "x" * 1001},
        {"unknown": "field"},
    ],
)
def test_bad_mounting_details_preserve_store(tmp_path, update):
    store = SetupEvidenceStore(tmp_path / "evidence.json")
    store.record("one", "stock", {}, "stock-log", "micrometer", 100, 200)
    before = store.path.read_bytes()
    details = {"hole_labels": ["A1"], "jaw_contact_notes": "", "stock_protrusion_mm": None, **update}
    with pytest.raises(ValueError):
        store.record("one", "workholding", {}, "mount-log", "indicator", 100, 200, mounting=details)
    assert store.path.read_bytes() == before


def test_mounting_details_reject_other_groups_and_empty_detail(tmp_path):
    store = SetupEvidenceStore(tmp_path / "evidence.json")
    with pytest.raises(ValueError, match="workholding"):
        store.record("one", "stock", {}, "log", "micrometer", 100, 200, mounting={})
    with pytest.raises(ValueError, match="at least one"):
        store.record(
            "one",
            "workholding",
            {},
            "log",
            "indicator",
            100,
            200,
            mounting={"hole_labels": [], "jaw_contact_notes": "", "stock_protrusion_mm": None},
        )
    assert not store.path.exists()


def test_mounting_attachment_keeps_base_document_legacy_compatible(tmp_path):
    path = tmp_path / "evidence.json"
    store = SetupEvidenceStore(path)
    details = {"hole_labels": ["A1"], "jaw_contact_notes": "Fixed jaw", "stock_protrusion_mm": 10}
    receipt = store.record("one", "workholding", {}, "mount-log", "indicator", 100, 200, mounting=details)
    base = json.loads(path.read_text())
    assert base["schema_version"] == 1 and "mounting" not in base["receipts"][0]
    assert set(base["receipts"][0]) == {
        "machine_id",
        "group",
        "fingerprint",
        "source",
        "method",
        "measured_at",
        "expires_at",
    }
    attachments = json.loads(store.mounting_path.read_text())["attachments"]
    assert attachments[fingerprint(base["receipts"][0])] == details
    assert SetupEvidenceStore(path).latest("one", "workholding") == receipt
    # An older writer can append a normal receipt without touching attachments.
    base["receipts"].append({**base["receipts"][0], "group": "stock", "source": "old-writer"})
    path.write_text(json.dumps(base))
    restored = SetupEvidenceStore(path)
    assert len(restored.records) == 2 and restored.records[0] == receipt
    assert "mounting" not in restored.records[1]


def test_interrupted_base_commit_preserves_inert_attachment_and_old_receipts(tmp_path, monkeypatch):
    store = SetupEvidenceStore(tmp_path / "evidence.json")
    prior = store.record("one", "stock", {}, "stock-log", "micrometer", 100, 200)
    before = store.path.read_bytes()
    write = store._write

    def fail_base(path, raw):
        if path == store.path:
            raise OSError("Simulated base commit failure")
        write(path, raw)

    monkeypatch.setattr(store, "_write", fail_base)
    with pytest.raises(OSError, match="base commit"):
        store.record(
            "one",
            "workholding",
            {},
            "mount-log",
            "indicator",
            100,
            200,
            mounting={"hole_labels": ["A1"], "jaw_contact_notes": "", "stock_protrusion_mm": None},
        )
    assert store.path.read_bytes() == before
    restored = SetupEvidenceStore(store.path)
    assert not restored.error and restored.records == [prior]
    orphan = restored.mounting_path.read_bytes()
    restored.record("two", "stock", {}, "later", "caliper", 100, 200)
    assert restored.mounting_path.read_bytes() == orphan


def test_duplicate_receipt_cannot_change_retained_mounting_details(tmp_path):
    store = SetupEvidenceStore(tmp_path / "evidence.json")
    args = ("one", "workholding", {}, "mount-log", "indicator", 100, 200)
    store.record(*args, mounting={"hole_labels": ["A1"], "jaw_contact_notes": "", "stock_protrusion_mm": None})
    before = (store.path.read_bytes(), store.mounting_path.read_bytes())
    with pytest.raises(ValueError, match="different mounting"):
        store.record(*args, mounting={"hole_labels": ["B3"], "jaw_contact_notes": "", "stock_protrusion_mm": None})
    assert (store.path.read_bytes(), store.mounting_path.read_bytes()) == before


def test_invalid_attachment_preserves_base_and_reports_error(tmp_path):
    store = SetupEvidenceStore(tmp_path / "evidence.json")
    store.record("one", "stock", {}, "stock-log", "micrometer", 100, 200)
    before = store.path.read_bytes()
    store.mounting_path.write_text(json.dumps({"schema_version": True, "attachments": {}}))
    assert SetupEvidenceStore(store.path).error
    assert store.path.read_bytes() == before


def test_experimental_inline_attachment_migration_preserves_exact_bytes(tmp_path):
    path = tmp_path / "evidence.json"
    receipt = SetupEvidenceStore.validate(
        {
            "machine_id": "one",
            "group": "workholding",
            "fingerprint": fingerprint({}),
            "source": "mount-log",
            "method": "indicator",
            "measured_at": 100,
            "expires_at": 200,
            "mounting": {"hole_labels": ["A1"], "jaw_contact_notes": "", "stock_protrusion_mm": None},
        }
    )
    original = json.dumps({"schema_version": 1, "receipts": [receipt]}, indent=4) + "\n"
    path.write_text(original)
    store = SetupEvidenceStore(path)
    assert not store.error and store.records == [receipt]
    store.record("two", "stock", {}, "later", "caliper", 100, 200)
    recoveries = list(tmp_path.glob("evidence.inline-*.json"))
    assert len(recoveries) == 1 and recoveries[0].read_text() == original
    assert "mounting" not in json.loads(path.read_text())["receipts"][0]
    assert SetupEvidenceStore(path).records[0] == receipt
