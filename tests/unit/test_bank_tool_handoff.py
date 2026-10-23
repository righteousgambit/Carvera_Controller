import copy
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from carveracontroller.desktop_bank_handoff import BankReviewHandoff
from carveracontroller.machine.bank_tool_handoff import capture_handoff
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.tool_bank_review import BankReviewStore, capture_bank
from carveracontroller.machine.tool_custody import ToolCustodyStore


@pytest.fixture
def bank_context(tmp_path):
    program = ProgramOperations.from_text("G21 G90\n" + "\n".join(f"T{t} M6" for t in range(1, 13)))
    bank = program.plan_tool_banks()[1]
    custody = ToolCustodyStore(tmp_path / "custody.json")
    profile = {"id": "design-7", "name": "Fine cutter", "number": 7, "diameter": 3.175, "shank_diameter": 6.35}
    assembly = custody.create_assembly("Cutter #7", "Collet", 28, "design-7")
    machine = {"id": "machine", "name": "Test Carvera", "model": "C1"}
    choices = {1: assembly["id"]}
    record = capture_bank(program, bank, machine["id"], choices, custody, [profile])
    store = BankReviewStore(tmp_path / "banks.json")
    store.save(record)
    panel = SimpleNamespace(
        program=program,
        bank=bank,
        banks=program.plan_tool_banks(),
        operations=SimpleNamespace(program=program),
        store=store,
        record=record,
        choices=choices,
        context=lambda: (machine, [profile], custody),
    )
    return panel, machine, custody, profile, assembly


def test_handoff_retains_logical_t7_and_resolves_controller_t1_without_mutation(bank_context):
    panel, machine, custody, profile, assembly = bank_context
    before = copy.deepcopy((panel.record, profile, custody.events))
    handoff = BankReviewHandoff(panel, 1)
    context = handoff.resolve()
    assert (context["logical_tool"], context["controller_tool"]) == (7, 1)
    assert context["declared_tool_mm"]["number"] == 1
    assert context["declared_tool_mm"]["diameter"] == 3.175
    assert context["declared_tool_mm"]["stickout"] == 28
    assert context["assembly_id"] == assembly["id"]
    assert context["preparation_revision"] == panel.record["revision"]
    assert context["program_hash"] == panel.program.file_hash
    assert context["source_range"] == [panel.bank.start_line, panel.bank.end_line]
    assert context["machine_profile"] == machine
    assert "Program T7 · Controller T1" in handoff.label
    context["assembly"]["name"] = "Changed returned copy"
    assert handoff.resolve()["assembly"]["name"] == "Cutter #7"
    assert (panel.record, profile, custody.events) == before
    handoff.verify_saved()


@pytest.mark.parametrize(
    "change",
    [
        "program",
        "active_program",
        "bank",
        "range",
        "machine",
        "revision",
        "choice",
        "assembly",
        "design",
        "replaced",
        "store",
    ],
)
def test_changed_handoff_is_refused(bank_context, change, tmp_path):
    panel, machine, custody, profile, assembly = bank_context
    handoff = BankReviewHandoff(panel, 1)
    if change == "program":
        panel.program = ProgramOperations.from_text("G21\nT7 M6")
    elif change == "active_program":
        panel.operations.program = None
    elif change == "bank":
        panel.bank = panel.program.plan_tool_banks()[0]
    elif change == "range":
        panel.bank = replace(panel.bank, end_line=panel.bank.end_line + 1)
    elif change == "machine":
        machine["name"] = "Different profile contents"
    elif change == "revision":
        updated = capture_bank(panel.program, panel.bank, machine["id"], panel.choices, custody, [profile])
        panel.store.save(updated, panel.record["revision"])
        panel.record = updated
    elif change == "choice":
        panel.choices[1] = "different-assembly"
    elif change == "assembly":
        custody.revise(assembly["id"], assembly["id"], "Reseated", "Collet", 29, "design-7", "Reseated")
    elif change == "design":
        profile["diameter"] = 6.35
    elif change == "replaced":
        replacement = custody.create_assembly("Replacement", "Collet", 28, "design-7")
        custody.record_replacement(
            assembly["id"],
            assembly["id"],
            replacement["id"],
            replacement["id"],
            source="Operator",
            note="Replaced",
            occurred_at=time.time(),
        )
    else:
        panel.store = BankReviewStore(tmp_path / "other-bank-store.json")
    with pytest.raises(ValueError):
        handoff.resolve()


def test_unsaved_preparation_or_mismatched_choice_cannot_borrow_saved_revision(bank_context):
    panel, machine, custody, profile, _assembly = bank_context
    for record, saved, choices in (
        (None, panel.record, panel.choices),
        (panel.record, None, panel.choices),
        (dict(panel.record, revision="unsaved"), panel.record, panel.choices),
        (panel.record, panel.record, {1: "other-assembly"}),
    ):
        with pytest.raises(ValueError):
            capture_handoff(panel.program, panel.bank, machine, record, saved, choices, custody, [profile], 1)


def test_worker_readback_refuses_external_saved_revision_change(bank_context):
    panel, machine, custody, profile, _assembly = bank_context
    handoff = BankReviewHandoff(panel, 1)
    external = BankReviewStore(panel.store.path)
    changed = capture_bank(
        panel.program, panel.bank, machine["id"], panel.choices, custody, [profile], "Changed elsewhere"
    )
    external.save(changed, panel.record["revision"])
    # This editor's cache is deliberately still the earlier revision.
    assert handoff.resolve()["preparation_revision"] == panel.record["revision"]
    with pytest.raises(ValueError, match="Saved bank preparation changed"):
        handoff.verify_saved()


def test_revalidation_does_not_rescan_program_lines(bank_context, monkeypatch):
    panel, *_ = bank_context
    calls = []
    original = panel.program.plan_tool_banks

    def counted():
        calls.append(1)
        return original()

    monkeypatch.setattr(panel.program, "plan_tool_banks", counted)
    handoff = BankReviewHandoff(panel, 1)
    assert calls == []
    for _ in range(50):
        handoff.resolve()
    assert calls == []
