import csv
import io

import pytest

from carveracontroller.machine.inspection_table import ORDERS, ordered_receipts, receipts_tsv
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore, sample_results
from tests.unit.test_surface_inspection import feature, receipt


@pytest.fixture
def data(tmp_path):
    store = SurfaceInspectionStore(tmp_path / "receipts.json")
    identity = feature(store)
    for source, z, kind in (
        ("b", 4.02, "compensated_ball_center"),
        ("a", 3.8, "compensated_ball_center"),
        ("a", 4.02, "compensated_ball_center"),
        ("unknown", 9, "raw_trigger"),
    ):
        receipt(store, identity, z, source_ref=source, kind=kind)
    f = store.get(identity)
    for i, sample in enumerate(f["samples"]):
        sample["recorded_at"] = float(i + 1)
    return f, list(zip(f["samples"], sample_results(f)))


@pytest.mark.parametrize(
    "order,indices", zip(ORDERS, ((0, 1, 2, 3), (3, 2, 1, 0), (1, 2, 0, 3), (1, 0, 2, 3), (0, 2, 1, 3), (1, 0, 2, 3)))
)
def test_order_keeps_identity_ties_unknowns_and_original_data(data, order, indices):
    f, rows = data
    before = repr(f)
    result = ordered_receipts(rows, order)
    assert [row[0]["id"] for row in result] == [rows[i][0]["id"] for i in indices]
    assert repr(f) == before and rows[0][0] is f["samples"][0]


def test_unknown_sort_rejected(data):
    with pytest.raises(ValueError, match="Unknown receipt order"):
        ordered_receipts(data[1], "unknown")


@pytest.mark.parametrize("draft", (False, True))
def test_tsv_full_precision_unknowns_provenance_and_quoted_cells(data, draft):
    f, rows = data
    rows[0][0]["source_ref"] = 'source\twith\n"quotes"'
    rows[0][0]["position_mm"] = (1.123456789012345, 2, 4.02)
    exported = list(csv.DictReader(io.StringIO(receipts_tsv(f, rows, draft=draft)), delimiter="\t"))
    assert len(exported) == 4
    assert float(exported[0]["x_mm"]) == rows[0][0]["position_mm"][0]
    assert exported[0]["source_ref"] == rows[0][0]["source_ref"]
    assert exported[0]["nominal_sha256"] == f["nominal_sha256"]
    assert exported[0]["receipt_id"] == rows[0][0]["id"]
    assert exported[0]["registration_ref"] == "registration-A"
    assert exported[0]["retention"] == ("proposed" if draft else "retained")
    assert exported[0]["recorded_at_unix"] == ("" if draft else "1.0")
    assert exported[-1]["deviation_mm"] == "" and exported[-1]["comparison"] == "unevaluated"
    assert exported[-1]["kind"] == "raw_trigger"
