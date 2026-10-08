import copy
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.tool_bank_review import BankReviewStore, capture_bank, inspect_bank, mapped_offset_status
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


def test_mapped_receipts_require_controller_number_endpoint_and_latest_placement(tmp_path):
    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)

    def assignment(stamp):
        with patch("carveracontroller.machine.tool_custody.time.time", return_value=stamp):
            custody.assign("machine", 1, assembly["id"])

    def receipt(tool, stamp, *, measured_at=None, applied=28, endpoint="endpoint"):
        with patch("carveracontroller.machine.tool_custody.time.time", return_value=stamp):
            event = custody.capture(
                tool,
                TloReport((28, 28.01), 0.01, applied, stamp if measured_at is None else measured_at),
                endpoint,
            )
            custody.link(event["id"], assembly["id"], "Attributed receipt")
        return event

    def row(profiles=None):
        return inspect_bank(program, bank, record, custody, profiles or [profile], "endpoint")[0]

    assignment(100)
    logical = receipt(7, 110)
    assert row()["tool"] == 7 and row()["controller_tool"] == 1
    assert row()["applicable"] == [logical]
    assert not row()["controller_applicable"]
    receipt(1, 111, endpoint="other-endpoint")
    receipt(1, 112, applied=None)
    mapped = receipt(1, 113)
    assert row()["controller_applicable"] == [mapped]
    assert row()["placement_at"] == 100
    # Redeclaring the same assembly requires a new mapped calibration receipt;
    # unchanged cutter definitions do not preserve pre-reload acceptance.
    assignment(200)
    assert not row()["controller_applicable"]
    receipt(1, 201, measured_at=199)  # An old measurement captured later is still old.
    assert not row()["controller_applicable"]
    current = receipt(1, 202)
    assert row()["controller_applicable"] == [current]
    assert not row([dict(profile, diameter=3.175)])["controller_applicable"]
    custody.revise(assembly["id"], assembly["id"], "Reseated", "Collet", 30, "design", "Reseated")
    assert not row()["controller_applicable"] and row()["placement_at"] is None


def test_current_spindle_offset_comparison_uses_only_fresh_mapped_tool_report(tmp_path):
    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    pose = ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), 1, 28)
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=100):
        custody.assign("machine", 1, assembly["id"])
    row = inspect_bank(program, bank, record, custody, [profile], "endpoint")[0]
    assert mapped_offset_status(row, pose, 1000.1)["state"] == "unknown"
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=110):
        receipt = custody.capture(1, TloReport((28, 28.01), 0.01, 28, 110), "endpoint")
        custody.link(receipt["id"], assembly["id"], "Controller T1 receipt")
    row = inspect_bank(program, bank, record, custody, [profile], "endpoint")[0]
    matched = mapped_offset_status(row, pose, 1000.1)
    assert matched["state"] == "matched" and matched["difference_mm"] == 0
    assert "0.001 mm comparison" in matched["detail"]
    assert mapped_offset_status(row, pose, 1002)["state"] == "unknown"
    assert mapped_offset_status(row, pose, 999)["state"] == "unknown"
    for tool, length in ((7, 28), (None, 28), (1, None)):
        reported = ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), tool, length)
        assert mapped_offset_status(row, reported, 1000.1)["state"] == "unknown"
    mismatch = ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), 1, 28.003)
    result = mapped_offset_status(row, mismatch, 1000.1)
    assert result["state"] == "mismatch" and result["difference_mm"] == pytest.approx(0.003)
    for invalid in (0, -1, float("nan"), True):
        with pytest.raises(ValueError, match="tolerance"):
            mapped_offset_status(row, pose, 1000.1, invalid)


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
    ws.selected_machine_profile = {"id": "different"}
    panel.refresh_if_changed()
    assert not panel.record and not panel.choices
    assert panel.summary.text.startswith("different · Bank")
    ws.selected_machine_profile = {"id": "machine", "name": "Carvera"}
    panel.refresh_if_changed()
    assert panel.record == before
    assert panel.note.text == "Unsaved bank-two note"
    panel.load(ProgramOperations.from_text("G21 G90\nG0 X0 Y0"))
    assert not panel.banks and not panel.rows
    assert "No ATC tool changes" in panel.summary.text
    assert panel.save_action.disabled


def test_bank_board_refreshes_offset_changes_without_rebuilding_on_each_packet(tmp_path):
    from carveracontroller.desktop_tool_banks import ToolBankPanel

    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=100):
        custody.assign("machine", 1, assembly["id"])
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=110):
        receipt = custody.capture(1, TloReport((28, 28.01), 0.01, 28, 110), "endpoint")
        custody.link(receipt["id"], assembly["id"], "Mapped tool receipt")
    send = Mock()
    controller = SimpleNamespace(connection_address="endpoint", observed_pose=None, executeCommand=send)
    ws = SimpleNamespace(
        machine=SimpleNamespace(tool_custody=custody, controller=controller),
        selected_machine_profile={"id": "machine", "name": "Carvera"},
        profile_store=SimpleNamespace(data={"tools": [profile]}, generation=0),
    )
    panel = ToolBankPanel(SimpleNamespace(workspace=ws), BankReviewStore(tmp_path / "reviews.json"))
    panel.load(program)
    panel.selector.text = tuple(panel.options)[1]
    panel.choose(1, assembly["id"])
    controller.observed_pose = ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), 1, 28)
    with patch("carveracontroller.desktop_tool_banks.time.monotonic", return_value=1000.1):
        panel.refresh_if_changed()
    assert panel.rows[0]["offset_status"]["state"] == "matched"
    assert "Current-spindle TLO comparisons 1/6" in panel.stage_summary.text
    cards = tuple(panel.grid.children)
    controller.observed_pose = ObservedPose(1001, "Idle", (0, 0, 0), (0, 0, 0), 1, 28)
    with patch("carveracontroller.desktop_tool_banks.time.monotonic", return_value=1001.1):
        panel.refresh_if_changed()
    assert tuple(panel.grid.children) == cards
    with patch("carveracontroller.desktop_tool_banks.time.monotonic", return_value=1003):
        panel.refresh_if_changed()
    assert panel.rows[0]["offset_status"]["state"] == "unknown"
    assert "Current-spindle TLO comparisons 0/6" in panel.stage_summary.text
    send.assert_not_called()


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


@pytest.mark.parametrize(
    "field,value",
    [
        ("updated_at", True),
        ("updated_at", "1"),
        ("updated_at", 10**1000),
        ("updated_at", float("nan")),
        ("bank_index", True),
        ("start_line", 0),
        ("end_line", "2"),
        ("program_hash", "x" * 64),
        ("revision", None),
        ("machine_id", ""),
        ("note", 5),
        ("bindings", {}),
    ],
)
def test_record_boundary_rejects_malformed_fields_without_overwriting_store(tmp_path, field, value):
    from carveracontroller.machine.tool_bank_review import validate_record

    *_, record = setup_bank(tmp_path)
    store = BankReviewStore(tmp_path / "reviews.json")
    store.save(record)
    original = store.path.read_bytes()
    bad = copy.deepcopy(record)
    bad[field] = value
    with pytest.raises(ValueError):
        validate_record(bad)
    with pytest.raises(ValueError):
        store.save(bad, record["revision"])
    assert store.path.read_bytes() == original
    assert not store.path.with_suffix(".lock").exists()


def test_duplicate_logical_tool_binding_is_rejected_and_record_is_detached(tmp_path):
    from carveracontroller.machine.tool_bank_review import validate_record

    *_, record = setup_bank(tmp_path)
    bad = copy.deepcopy(record)
    bad["bindings"].append(dict(bad["bindings"][0], pocket=2, assembly_id="different"))
    with pytest.raises(ValueError, match="one pocket"):
        validate_record(bad)
    detached = validate_record(record)
    detached["bindings"][0]["assembly_id"] = "other"
    assert record["bindings"][0]["assembly_id"] != "other"


@pytest.mark.parametrize("clock", [True, "1000", float("nan"), 10**1000])
def test_invalid_tlo_comparison_clock_does_not_claim_a_match(clock):
    row = {"controller_tool": 1, "controller_applicable": [{"report": {"applied": 28}}]}
    pose = ObservedPose(1000, "Idle", (0, 0, 0), (0, 0, 0), 1, 28)
    result = mapped_offset_status(row, pose, clock)
    assert result["state"] == "unknown" and result["difference_mm"] is None


def test_bank_filter_and_full_evidence_pages_preserve_context_and_never_send_commands(tmp_path):
    from carveracontroller.desktop_tool_banks import ToolBankPanel

    program, bank, custody, profile, assembly, record = setup_bank(tmp_path)
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=100):
        custody.assign("machine", 1, assembly["id"])
    with patch("carveracontroller.machine.tool_custody.time.time", return_value=110):
        for tool in (1, 7):
            receipt = custody.capture(
                tool, TloReport((28.0000012, 28.0000013, *range(2, 165)), 164, 28, 110), "endpoint"
            )
            custody.link(receipt["id"], assembly["id"], "Attributed test receipt")
    send = Mock()
    controller = SimpleNamespace(connection_address="endpoint", observed_pose=None, executeCommand=send)
    ws = SimpleNamespace(
        machine=SimpleNamespace(tool_custody=custody, controller=controller),
        selected_machine_profile={"id": "machine", "name": "Carvera"},
        profile_store=SimpleNamespace(data={"tools": [profile]}, generation=0),
    )
    panel = ToolBankPanel(SimpleNamespace(workspace=ws), BankReviewStore(tmp_path / "reviews.json"))
    panel.load(program)
    panel.selector.text = tuple(panel.options)[1]
    panel.choose(1, assembly["id"])
    panel.filter_choice.text = "Selected assemblies"
    assert len(panel.grid.children) == 1 and panel.visible_count.text == "1 / 6 pockets shown"
    panel.filter_choice.text = "Missing evidence"
    assert len(panel.grid.children) == 5
    panel.review_evidence(1)
    review = panel.evidence_review
    assert "Program T7" in review.heading.text and "Controller T1" in review.heading.text
    assert "No definition/declaration" in review.view.text
    review.section.text = "Raw receipts"
    assert "Receipt 1/2" in review.view.text
    assert "Captured (epoch s): 110 · report time: 110" in review.view.text
    assert "measured:" not in review.view.text
    assert "mapped controller tool" in review.view.text
    assert "samples 1–80/165" in review.view.text
    assert "28.0000012, 28.0000013" in review.view.text
    review.turn_samples(1)
    assert "samples 81–160/165" in review.view.text
    review.turn_samples(1)
    assert "samples 161–165/165" in review.view.text and review.samples_next.disabled
    review.turn_receipt(1)
    assert "Receipt 2/2" in review.view.text and "logical tool" in review.view.text
    assert "samples 1–80/165" in review.view.text and review.receipt_next.disabled
    panel.selector.text = tuple(panel.options)[0]
    assert panel.evidence_review is None and review.parent is None
    send.assert_not_called()


@pytest.mark.parametrize("width", [360, 760])
def test_pocket_evidence_controls_fit_and_new_pages_start_at_the_top(tmp_path, width):
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
    panel.selector.text = tuple(panel.options)[1]
    panel.choose(1, assembly["id"])
    panel.filter_choice.text = "Selected assemblies"
    panel.review_evidence(1)
    review = panel.evidence_review
    for _ in range(10):
        Clock.tick()
    assert review.view.cursor == (0, 0) and review.view.scroll_y == 0
    assert review.view.text.startswith("Assembly: Cutter #7")
    for widget in review.children:
        assert widget.x >= review.x and widget.right <= review.right
        assert widget.y >= review.y and widget.top <= review.top
    for widget in panel.grid.children[0].children:
        assert widget.x >= panel.grid.children[0].x
        assert widget.right <= panel.grid.children[0].right
    review.section.text = "Raw receipts"
    for _ in range(10):
        Clock.tick()
    assert review.view.cursor == (0, 0) and review.view.scroll_y == 0
    assert all(action.disabled for action in review.navigation.children)
    panel.record["program_hash"] = "0" * 64
    panel.refresh()
    assert not panel.rows
    assert panel.visible_count.text == "Evidence unavailable"
    assert "No current bank row" in review.view.text
    assert all(action.disabled for action in review.navigation.children)


def test_replaced_physical_identity_invalidates_bank_without_erasing_receipts(tmp_path):
    program, bank, custody, profile, old, record = setup_bank(tmp_path)
    custody.assign("machine", 1, old["id"])
    receipt = custody.capture(7, TloReport((28, 28.01), 0.01, 28, 100), "endpoint")
    custody.link(receipt["id"], old["id"], "Matched tag")
    new = custody.create_assembly("Replacement cutter", "Collet", 28, "design")
    custody.record_replacement(
        old["id"],
        old["id"],
        new["id"],
        new["id"],
        source="inventory receipt",
        note="Changed physical cutter",
        occurred_at=200,
    )
    row = inspect_bank(program, bank, record, custody, [profile], "endpoint")[0]
    assert row["reports"] == [receipt] and not row["applicable"]
    assert any("declared replaced" in issue for issue in row["issues"])
    with pytest.raises(ValueError, match="declared replaced"):
        capture_bank(program, bank, "machine", {1: old["id"]}, custody, [profile])
    fresh = capture_bank(program, bank, "machine", {1: new["id"]}, custody, [profile])
    assert fresh["bindings"][0]["assembly_id"] == new["id"]
    assert not inspect_bank(program, bank, fresh, custody, [profile], "endpoint")[0]["reports"]
