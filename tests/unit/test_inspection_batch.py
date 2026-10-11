import json
from dataclasses import replace

import pytest

from carveracontroller.machine.inspection_batch import apply_batch, batch_feature, review_batch
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore, sample_results
from tests.unit.test_surface_inspection import feature, receipt


def prepare(store, identity, content, **options):
    return review_batch(
        store.get(identity), content, separator="CSV", default_kind="compensated_ball_center", **options
    )


def test_units_provenance_mixed_kinds_review_and_atomic_retention(tmp_path, monkeypatch):
    store = SurfaceInspectionStore(tmp_path / "records.json")
    identity = feature(store)
    original = store.path.read_bytes()
    content = (
        "x,y,z,source_ref,kind,registration_ref,calibration_ref,observed_at\n"
        '1 mm,2 mm,4.02 mm,"source, one",,reg,probe,observed\n'
        "1/25.4 in,2,4.2,second,raw_trigger,,,\n"
        "1,2,4.2,third,,reg,probe,\n"
    )
    reviewed = prepare(store, identity, content)
    proposed = batch_feature(store.get(identity), reviewed)
    assert store.path.read_bytes() == original
    assert reviewed.count == 3
    assert proposed["samples"][0]["position_mm"] == pytest.approx([1, 2, 4.02])
    assert proposed["samples"][0]["source_ref"] == "source, one"
    assert proposed["samples"][0]["observed_at"] == "observed"
    assert [item["state"] for item in sample_results(proposed)] == [
        "within_declared_limits",
        "unevaluated",
        "outside_declared_limits",
    ]
    assert all(item["recorded_at"] == 0 for item in proposed["samples"])
    monkeypatch.setattr("carveracontroller.machine.inspection_batch.time.time", lambda: 1234.5)
    ids = apply_batch(store, reviewed)
    loaded = SurfaceInspectionStore(store.path).get(identity)
    assert [sample["id"] for sample in loaded["samples"]] == ids
    assert all(sample["recorded_at"] == 1234.5 for sample in loaded["samples"])
    assert all(sample["source_class"] == "operator_entered" for sample in loaded["samples"])
    with pytest.raises(ValueError, match="changed after review"):
        apply_batch(store, reviewed)
    assert len(store.get(identity)["samples"]) == 3


@pytest.mark.parametrize(
    "content",
    [
        "x,y,z,source_ref\n1,2,4.02,good\n1,bad,4,bad\n",
        "x,y,z,source_ref\n1,2,4\n",
        "x,y,z,source_ref\n1,2,4,\n",
        "x,y,z,source_ref,kind\n1,2,4,row,unknown\n",
        "x,y,z,source_ref\n1,2,nan,row\n",
        "x,y,z,source_ref\n1,2,1e20,row\n",
        "x,y,z,source_ref,unknown\n1,2,4,row,abc\n",
        "x,x,z,source_ref\n1,2,4,row\n",
        'x,y,z,source_ref\n1,2,4,"unterminated\n',
        "x,y,z,source_ref\n",
    ],
)
def test_malformed_rows_never_retain_a_valid_prefix(tmp_path, content):
    store = SurfaceInspectionStore(tmp_path / "records.json")
    identity = feature(store)
    before = store.path.read_bytes()
    with pytest.raises(ValueError):
        prepare(store, identity, content)
    assert store.path.read_bytes() == before and not store.get(identity)["samples"]


def test_stale_feature_external_changes_and_tampered_review(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "records.json")
    identity = feature(store)
    reviewed = prepare(store, identity, "x,y,z,source_ref\n1,2,4,new\n")
    with pytest.raises(ValueError, match="Reviewed batch changed"):
        apply_batch(store, replace(reviewed, records_json="[]"))
    with pytest.raises(ValueError, match="batch count"):
        apply_batch(store, replace(reviewed, count=2))
    receipt(store, identity, 4.02)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="changed after review"):
        apply_batch(store, reviewed)
    assert store.path.read_bytes() == before
    reviewed = prepare(store, identity, "x,y,z,source_ref\n1,2,4,new\n")
    external = json.loads(store.path.read_text())
    external["features"][0]["name"] = "External edit"
    store.path.write_text(json.dumps(external))
    changed = store.path.read_bytes()
    with pytest.raises(ValueError, match="changed externally"):
        apply_batch(store, reviewed)
    assert store.path.read_bytes() == changed and len(store.get(identity)["samples"]) == 1


def test_tsv_blank_rows_default_kind_and_limits(tmp_path, monkeypatch):
    store = SurfaceInspectionStore(tmp_path / "records.json")
    identity = feature(store)
    reviewed = review_batch(
        store.get(identity), "x\ty\tz\tsource_ref\n\n1\t2\t4\traw\n", separator="TSV", default_kind="raw_trigger"
    )
    assert batch_feature(store.get(identity), reviewed)["samples"][0]["kind"] == "raw_trigger"
    monkeypatch.setattr(SurfaceInspectionStore, "MAX_SAMPLES", 1)
    with pytest.raises(ValueError, match="1000 rows"):
        prepare(store, identity, "x,y,z,source_ref\n1,2,4,a\n1,2,4,b\n")
    receipt(store, identity, 4)
    with pytest.raises(ValueError, match="retained receipts"):
        prepare(store, identity, "x,y,z,source_ref\n1,2,4,a\n")


def test_failed_save_does_not_publish_batch(tmp_path, monkeypatch):
    store = SurfaceInspectionStore(tmp_path / "records.json")
    identity = feature(store)
    reviewed = prepare(store, identity, "x,y,z,source_ref\n1,2,4,new\n")
    before = store.path.read_bytes()

    def fail(*args):
        raise OSError("write failed")

    monkeypatch.setattr("carveracontroller.machine.surface_inspection.os.replace", fail)
    with pytest.raises(OSError, match="write failed"):
        apply_batch(store, reviewed)
    assert store.path.read_bytes() == before and not store.get(identity)["samples"]
