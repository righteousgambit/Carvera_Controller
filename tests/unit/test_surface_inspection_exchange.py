import copy
import csv
import io
import json

import pytest

from carveracontroller.machine.surface_inspection import SurfaceInspectionStore
from carveracontroller.machine.surface_inspection_exchange import (
    bundle,
    csv_report,
    export_file,
    html_report,
    import_file,
    merge_features,
    preview_import,
    read_bundle,
)
from tests.unit.test_surface_inspection import feature, receipt


@pytest.fixture
def source(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "source.json")
    identity = feature(store)
    receipt(store, identity, 4.02)
    receipt(store, identity, 4.1, kind="raw_trigger", source_ref="raw-2")
    return store, identity


def test_bundle_exact_roundtrip_and_export_readback(source, tmp_path):
    store, identity = source
    target = tmp_path / "report.cvinspect"
    saved = export_file(store.features, target, "Portable JSON")
    assert saved["features"] == 1 and saved["receipts"] == 2
    restored = read_bundle(target.read_bytes())
    assert restored == store.features
    assert restored[0]["id"] == identity
    assert saved["bytes"] == len(target.read_bytes())
    assert restored[0]["samples"][1]["kind"] == "raw_trigger"


def test_review_import_merge_idempotence_and_independent_receipts(source, tmp_path):
    store, identity = source
    target = tmp_path / "portable.cvinspect"
    export_file(store.features, target, "Portable JSON")
    dest = SurfaceInspectionStore(tmp_path / "destination.json")
    review = preview_import(dest, target)
    assert review["features_added"] == 1 and review["receipts_added"] == 2
    assert not dest.path.exists()
    imported = import_file(dest, target, review["source_sha256"])
    assert imported["features_added"] == 1
    original = dest.path.read_bytes()
    again = import_file(dest, target)
    assert again["features_added"] == again["receipts_added"] == 0
    assert dest.path.read_bytes() == original
    receipt(store, identity, 4.03, source_ref="independent-3")
    export_file(store.features, target, "Portable JSON")
    result = import_file(dest, target)
    assert result["features_added"] == 0 and result["receipts_added"] == 1
    assert len(dest.get(identity)["samples"]) == 3


@pytest.mark.parametrize("conflict", ["definition", "receipt"])
def test_conflicting_identity_rejected_without_mutating_original(source, conflict):
    store, _ = source
    incoming = copy.deepcopy(store.features)
    if conflict == "definition":
        incoming[0]["limits_mm"] = [-0.1, 0.1]
    else:
        incoming[0]["samples"][0]["position_mm"][2] = 4.5
    before = copy.deepcopy(store.features)
    with pytest.raises(ValueError, match="Conflicting"):
        merge_features(store.features, incoming)
    assert before == store.features


def test_changed_bundle_after_review_is_rejected(source, tmp_path):
    store, _ = source
    target = tmp_path / "portable.cvinspect"
    export_file(store.features, target, "Portable JSON")
    dest = SurfaceInspectionStore(tmp_path / "destination.json")
    review = preview_import(dest, target)
    target.write_text(bundle(store.features))
    with pytest.raises(ValueError, match="changed after review"):
        import_file(dest, target, review["source_sha256"])
    assert not dest.path.exists()


@pytest.mark.parametrize("edit", ["checksum", "version", "format", "boolean_version", "nominal"])
def test_bundle_corruption_rejected(source, edit):
    store, _ = source
    data = json.loads(bundle(store.features))
    if edit == "checksum":
        data["sha256"] = "0" * 64
    elif edit == "version":
        data["version"] = 2
    elif edit == "format":
        data["format"] = "other"
    elif edit == "boolean_version":
        data["version"] = True
    else:
        data["features"][0]["plan"]["tip_diameter_mm"] = 3
    with pytest.raises(ValueError):
        read_bundle(json.dumps(data))


def test_duplicate_keys_and_recursive_bundle_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        read_bundle('{"version":1,"version":1}')
    with pytest.raises(ValueError):
        read_bundle("[" * 2000 + "]" * 2000)


def test_csv_evidence_columns_unknowns_and_spreadsheet_text(source, tmp_path):
    store, _ = source
    f = copy.deepcopy(store.features[0])
    f["name"] = "=SUM(1,2)"
    f["samples"][0]["source_ref"] = 'line one\n"line two"'
    rows = list(csv.DictReader(io.StringIO(csv_report([f]))))
    assert rows[0]["feature"] == "'=SUM(1,2)"
    assert rows[0]["source_ref"] == 'line one\n"line two"'
    assert float(rows[0]["normal_deviation_mm"]) == pytest.approx(0.02)
    assert rows[1]["normal_deviation_mm"] == ""
    assert rows[1]["comparison_state"] == "unevaluated"
    assert rows[0]["frame"] == "nominal_component_machine_mm"
    assert rows[0]["source_class"] == "operator_entered"
    assert float(rows[0]["nominal_z_mm"]) == 3
    assert float(rows[0]["outward_normal_z"]) == 1
    assert float(rows[0]["tip_diameter_mm"]) == 2
    empty = copy.deepcopy(f)
    empty["samples"] = []
    row = next(csv.DictReader(io.StringIO(csv_report([empty]))))
    assert row["comparison_state"] == "no_measurements"
    assert None not in row


def test_html_escapes_content_preserves_unknowns_and_is_self_contained(source):
    store, _ = source
    f = copy.deepcopy(store.features[0])
    f["name"] = '<script>alert("x")</script>'
    result = html_report([f])
    assert "<script>" not in result
    assert "&lt;script&gt;" in result
    assert "Unevaluated" in result
    assert "Operator-entered" in result
    assert "<details>" in result
    assert f["samples"][0]["id"] in result
    assert "https://" not in result
    assert "Conformance is unknown" in html_report([])


def test_failed_export_preserves_existing_artifact(source, tmp_path, monkeypatch):
    store, _ = source
    target = tmp_path / "report.csv"
    target.write_bytes(b"previous report")
    monkeypatch.setattr(
        "carveracontroller.machine.surface_inspection_exchange.os.replace",
        lambda *_: (_ for _ in ()).throw(OSError("disk full")),
    )
    with pytest.raises(OSError):
        export_file(store.features, target, "CSV")
    assert target.read_bytes() == b"previous report"


def test_broken_local_records_cannot_accept_even_empty_bundle(tmp_path):
    store_path = tmp_path / "broken.json"
    store_path.write_text("corrupt")
    store = SurfaceInspectionStore(store_path)
    target = tmp_path / "empty.cvinspect"
    target.write_text(bundle([]))
    with pytest.raises(ValueError, match="repair"):
        import_file(store, target)
    assert store_path.read_text() == "corrupt"


@pytest.mark.parametrize(
    "path,value",
    [
        (("part",), []),
        (("created_at",), 10**400),
        (("plan", "reference", "triangle"), None),
        (("plan", "reference", "normal"), [False, 0, 1]),
        (("plan", "reference", "triangle_index"), True),
        (("plan", "direction"), None),
        (("plan", "tip_diameter_mm"), "2"),
        (("samples", 0, "position_mm"), [1, 2, True]),
        (("samples", 0, "source_ref"), 7),
        (("samples", 0, "recorded_at"), 10**400),
        (("samples", 0, "registration_ref"), []),
        (("samples", 0, "kind"), {"kind": "raw_trigger"}),
    ],
)
def test_valid_digest_cannot_bypass_inspection_field_contracts(tmp_path, path, value):
    from carveracontroller.machine.surface_inspection import canonical, digest
    from tests.unit.test_surface_inspection import feature, receipt

    store = SurfaceInspectionStore(tmp_path / "retained.json")
    identity = feature(store)
    receipt(store, identity, 4)
    original = store.path.read_bytes()
    data = json.loads(bundle(store.features))
    row = data["features"][0]
    target = row
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    row["nominal_sha256"] = digest({"plan": row["plan"], "context": row["context"]})
    data["sha256"] = digest(data["features"])
    payload = canonical(data)
    with pytest.raises(ValueError):
        read_bundle(payload)
    source = tmp_path / "malformed.cvinspect"
    source.write_text(payload)
    with pytest.raises(ValueError):
        import_file(store, source)
    assert store.path.read_bytes() == original
    assert SurfaceInspectionStore(store.path).features == store.features
