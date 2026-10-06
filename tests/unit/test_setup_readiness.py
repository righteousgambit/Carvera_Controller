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
