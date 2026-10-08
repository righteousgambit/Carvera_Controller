import copy
import json
import threading

import pytest

from carveracontroller.machine.cutter_table import TableSelection, export_tsv, review_tsv
from carveracontroller.machine.desktop_profiles import ProfileError, ProfileStore


def test_spreadsheet_roundtrip_and_unit_changes(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    tools = store.data["tools"]
    original = copy.deepcopy(tools)
    assert review_tsv(export_tsv(tools), tools) == ()
    text = f"ID\tStickout\tVendor\n{tools[0]['id']}\t1.5 in\tHelical Solutions\n"
    changes = review_tsv(text, tools)
    assert changes[0].after["stickout"] == pytest.approx(38.1)
    assert changes[0].fields == ("stickout", "vendor")
    assert tools == original
    generation = store.generation
    result = store.update_tools([changes[0].after], generation)
    assert store.generation == generation + 1
    assert result[0]["stickout"] == pytest.approx(38.1)
    assert ProfileStore(store.path).data["tools"][0]["vendor"] == "Helical Solutions"


@pytest.mark.parametrize(
    "paste",
    [
        "Name\tDiameter\nA\t1/4 in",
        "ID\tUnknown\na\t1",
        "ID\tName\tName\na\tA\tB",
        "ID\tName\nmissing\tName",
        "ID\tDiameter\na\t",
        "ID\tDiameter\na\t-1",
        "ID\tOverall\na\t1/8 in",
        "ID\tStickout\na\t4 in",
        "ID\tTool\na\t1.2",
        "ID\tShape\na\tnot-a-tool-shape",
        "ID\tName\na\tOne\na\tTwo",
        "ID\tName\na\tOne\textra",
    ],
)
def test_invalid_paste_is_all_or_nothing(paste, tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    record = dict(store.data["tools"][0], id="a")
    with pytest.raises(ProfileError):
        review_tsv(paste, [record])
    assert not store.path.exists()


def test_whole_batch_validation_and_stale_review(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    tools = store.data["tools"]
    store.save_tool(tools[0])
    before = store.path.read_bytes()
    updates = [dict(tools[0], vendor="New"), dict(tools[1], length=1)]
    with pytest.raises(ProfileError):
        store.update_tools(updates, store.generation)
    assert store.path.read_bytes() == before
    old_generation = store.generation
    store.save_tool(dict(tools[2], vendor="Other change"))
    after = store.path.read_bytes()
    with pytest.raises(ProfileError, match="changed after review"):
        store.update_tools([dict(tools[0], vendor="New")], old_generation)
    assert store.path.read_bytes() == after


def test_selection_ranges_toggles_and_identity_after_filter():
    selection = TableSelection()
    order = ["a", "b", "c", "d"]
    selection.select("b", order)
    selection.select("d", order, extend=True)
    assert selection.ids == {"b", "c", "d"}
    selection.select("c", order, toggle=True)
    assert selection.ids == {"b", "d"}
    selection.select("a", list(reversed(order)), extend=True)
    assert selection.ids == {"a", "b", "c"}
    selection.reconcile({"a", "c", "d"})
    assert selection.ids == {"a", "c"}


def test_detects_external_library_change_before_bulk_save(tmp_path):
    store = ProfileStore(tmp_path / "profiles.json")
    store.save_tool(store.data["tools"][0])
    generation, data = store.snapshot()
    external = copy.deepcopy(data)
    external["tools"][0]["vendor"] = "External edit"
    store.path.write_text(json.dumps(external))
    before = store.path.read_bytes()
    with pytest.raises(ProfileError, match="outside this editor"):
        store.update_tools([dict(data["tools"][0], vendor="Bulk edit")], generation)
    assert store.path.read_bytes() == before
    updated_generation, current = store.reload()
    assert updated_generation == generation + 1
    assert current["tools"][0]["vendor"] == "External edit"


def test_profile_readback_does_not_wait_for_disk_commit(tmp_path, monkeypatch):
    import carveracontroller.machine.desktop_profiles as module

    store = ProfileStore(tmp_path / "profiles.json")
    generation, data = store.snapshot()
    entered, gate, readback = threading.Event(), threading.Event(), threading.Event()
    original = module._write
    observed = []

    def delayed_write(*args):
        entered.set()
        assert gate.wait(2)
        return original(*args)

    monkeypatch.setattr(module, "_write", delayed_write)
    worker = threading.Thread(target=lambda: store.update_tools([dict(data["tools"][0], vendor="Updated")], generation))
    reader = threading.Thread(target=lambda: (observed.append(store.snapshot()), readback.set()))
    try:
        worker.start()
        assert entered.wait(1)
        reader.start()
        assert readback.wait(0.25), "Live profile readers must not wait for disk I/O"
        assert observed[0] == (generation, data)
    finally:
        gate.set()
        worker.join(2)
        reader.join(2)
    assert not worker.is_alive() and not reader.is_alive()
    assert store.generation == generation + 1
    assert store.data["tools"][0]["vendor"] == "Updated"


def test_reconcile_one_shot_ids_retains_visible_current_and_anchor():
    selection = TableSelection()
    selection.select("a", ["a", "b", "c"])
    selection.select("b", ["a", "b", "c"], toggle=True)
    selection.reconcile(identity for identity in ("b", "c"))
    assert selection.ids == {"b"}
    assert selection.current == selection.anchor == "b"
    selection.select("c", ["b", "c"], extend=True)
    assert selection.ids == {"b", "c"}


def test_preparation_detaches_saved_cells_and_cancels_without_results(tmp_path):
    from carveracontroller.machine.cutter_table import COLUMNS, prepare_cutters
    from carveracontroller.machine.library_browser import CutterFilter

    records = ProfileStore(tmp_path / "profiles.json").data["tools"]
    original = copy.deepcopy(records)
    result = prepare_cutters(records, "", CutterFilter(), "number", True, lambda: False)
    assert result is not None
    assert [item["number"] for item in result.records] == sorted([r["number"] for r in records], reverse=True)
    assert len(result.cells[0]) == len(COLUMNS)
    result.records[0]["name"] = "Detached name"
    assert records == original
    assert prepare_cutters(records, "", CutterFilter(), "name", False, lambda: True) is None
