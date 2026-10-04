import copy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.tool_bank_review import BankReviewStore, capture_bank, inspect_bank
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport


def setup_bank(tmp_path):
    program = ProgramOperations.from_text("G21 G90\n" + "\n".join(f"T{t} M6" for t in range(1, 13)))
    bank = program.plan_tool_banks()[1]
    custody = ToolCustodyStore(tmp_path / "custody.json")
    profile = {"id": "design", "name": "Quarter-inch flat", "number": 1, "diameter": 6.35, "shank_diameter": 6.35}
    assembly = custody.create_assembly("Cutter #7", "Collet", 28, "design")
    record = capture_bank(program, bank, "machine", {1: assembly["id"]}, custody, [profile])
    return program, bank, custody, profile, assembly, record


def test_preparation_restores_exact_bank_and_rejects_stale_writer(tmp_path):
    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    store = BankReviewStore(tmp_path / "reviews.json")
    store.save(record)
    second = BankReviewStore(store.path)
    assert second.get(program.file_hash, "machine", 2) == record
    assert second.get(program.file_hash, "other-machine", 2) is None
    assert second.get(program.file_hash, "machine", 1) is None
    updated = capture_bank(program, bank, "machine", {1: assembly["id"]}, custody, [profile], "Reviewed")
    store.save(updated, record["revision"])
    with pytest.raises(ValueError, match="changed elsewhere"):
        second.save(record, record["revision"])
    assert second.get(program.file_hash, "machine", 2) == updated


def test_receipt_endpoint_tool_and_definition_stay_distinct(tmp_path):
    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    custody.assign("machine", 1, assembly["id"])
    wrong_tool = custody.capture(1, TloReport((28, 28.01), 0.01, 28, 100), "endpoint")
    custody.link(wrong_tool["id"], assembly["id"], "Selected assembly")
    row = inspect_bank(program, bank, record, custody, [profile], "endpoint")[0]
    assert row["tool"] == 7 and row["pocket"] == 1
    assert len(row["reports"]) == 1 and not row["applicable"]
    current = custody.capture(7, TloReport((28, 28.01), 0.01, 28, 101), "endpoint")
    custody.link(current["id"], assembly["id"], "Selected assembly at T7")
    assert len(inspect_bank(program, bank, record, custody, [profile], "endpoint")[0]["applicable"]) == 1
    changed = dict(profile, diameter=3.175)
    assert not inspect_bank(program, bank, record, custody, [changed], "endpoint")[0]["applicable"]
    assert not inspect_bank(program, bank, record, custody, [profile], "other-endpoint")[0]["applicable"]
    custody.revise(assembly["id"], assembly["id"], "Reseated", "Collet", 30, "design", "Reseated")
    row = inspect_bank(program, bank, record, custody, [profile], "endpoint")[0]
    assert not row["applicable"] and any("changed" in issue for issue in row["issues"])
    assert any("declaration" in issue for issue in row["issues"])


def test_catalog_change_and_program_change_invalidate_preparation(tmp_path):
    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    changed = dict(profile, diameter=3.175)
    row = inspect_bank(program, bank, record, custody, [changed])[0]
    assert any("changed" in issue for issue in row["issues"])
    different = ProgramOperations.from_text("G21 G90\nT7 M6")
    with pytest.raises(ValueError, match="different program"):
        inspect_bank(different, different.plan_tool_banks()[0], record, custody, [profile])
    with pytest.raises(ValueError, match="different program"):
        inspect_bank(program, bank, record, custody, [profile], machine_id="other-machine")
    with pytest.raises(ValueError, match="own physical assembly"):
        capture_bank(program, bank, "machine", {1: assembly["id"], 2: assembly["id"]}, custody, [profile])


@pytest.mark.parametrize("content", ["{bad", '{"schema":true,"reviews":[]}', '{"schema":99,"reviews":[]}'])
def test_invalid_original_is_preserved(tmp_path, content):
    *_, record = setup_bank(tmp_path)
    path = tmp_path / "reviews.json"
    path.write_text(content)
    store = BankReviewStore(path)
    assert store.error
    with pytest.raises(ValueError):
        store.save(record)
    assert path.read_text() == content
    assert not path.with_suffix(".lock").exists()


def test_failed_atomic_save_does_not_replace_existing_preparation(tmp_path):
    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    store = BankReviewStore(tmp_path / "reviews.json")
    store.save(record)
    original = store.path.read_bytes()
    updated = capture_bank(program, bank, "machine", {1: assembly["id"]}, custody, [profile])
    with (
        patch("carveracontroller.machine.tool_bank_review.os.replace", side_effect=OSError("disk full")),
        pytest.raises(OSError, match="disk full"),
    ):
        store.save(updated, record["revision"])
    assert store.path.read_bytes() == original
    assert not list(tmp_path.glob(".bank-review-*"))
    assert not store.path.with_suffix(".lock").exists()


def test_bank_board_select_save_and_preview_do_not_dispatch_controller_commands(tmp_path):
    from carveracontroller.desktop_tool_banks import ToolBankPanel

    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    controller = Mock(connection_address="endpoint")
    preview = Mock()
    ws = SimpleNamespace(
        machine=SimpleNamespace(tool_custody=custody, controller=controller),
        selected_machine_profile={"id": "machine", "name": "Carvera"},
        profile_store=SimpleNamespace(data={"tools": [profile]}, generation=0),
        preview_assembly=preview,
    )
    panel = ToolBankPanel(SimpleNamespace(workspace=ws), BankReviewStore(tmp_path / "reviews.json"))
    panel.load(program)
    panel.selector.text = tuple(panel.options)[1]
    panel.choose(1, assembly["id"])
    panel.choose(2, assembly["id"])
    assert panel.choices == {1: assembly["id"]}
    assert "own physical assembly" in panel.result.text
    panel.save()
    assert panel.record["bindings"][0]["tool"] == 7
    assert "Controller mapping" in panel.stage_summary.text
    panel.preview(1, 7)
    preview.assert_called_once_with(assembly["id"], 7)
    controller.executeCommand.assert_not_called()
    before = copy.deepcopy(panel.record)
    panel.note.text = "Unsaved bank-two note"
    panel.selector.text = tuple(panel.options)[0]
    assert not panel.choices
    panel.selector.text = tuple(panel.options)[1]
    assert panel.note.text == "Unsaved bank-two note" and panel.record == before
    ws.selected_machine_profile = {"id": "different", "name": "Other"}
    panel.refresh_if_changed()
    assert not panel.record and not panel.choices
    ws.selected_machine_profile = {"id": "machine", "name": "Carvera"}
    panel.refresh_if_changed()
    assert panel.record == before
    assert panel.note.text == "Unsaved bank-two note"
    panel.load(ProgramOperations.from_text("G21 G90\nG0 X0 Y0"))
    assert not panel.banks and not panel.rows
    assert "No ATC tool changes" in panel.summary.text
    assert panel.save_action.disabled


@pytest.mark.parametrize("width, columns", [(360, 1), (760, 2)])
def test_bank_cards_reflow_and_keep_controls_inside_their_pockets(tmp_path, width, columns):
    from kivy.clock import Clock
    from kivy.metrics import dp

    from carveracontroller.desktop_tool_banks import ToolBankPanel

    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    ws = SimpleNamespace(
        machine=SimpleNamespace(tool_custody=custody, controller=SimpleNamespace(connection_address="endpoint")),
        selected_machine_profile={"id": "machine", "name": "Carvera"},
        profile_store=SimpleNamespace(data={"tools": [profile]}, generation=0),
    )
    panel = ToolBankPanel(SimpleNamespace(workspace=ws), BankReviewStore(tmp_path / "reviews.json"))
    panel.size_hint_x = None
    panel.width = dp(width)
    panel.load(program)
    for _ in range(8):
        Clock.tick()
    assert panel.grid.cols == columns
    assert len(panel.grid.children) == 6
    for card in panel.grid.children:
        for widget in card.children:
            assert widget.x >= card.x and widget.right <= card.right
            assert widget.y >= card.y and widget.top <= card.top
