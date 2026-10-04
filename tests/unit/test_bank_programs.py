import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from carveracontroller.machine.bank_programs import compile_bank, save_draft
from carveracontroller.machine.program_operations import ProgramOperations


def twelve_tools(extra="", header="G21 G90 G17 G94 G54 G49 M5 M9\nG0 X0 Y0 Z10\nF100"):
    return ProgramOperations.from_text(
        header + "\n" + "\n".join(f"T{t}\nM6\nG1 X{t} Y0 Z5\n{extra.format(t=t)}" for t in range(1, 13))
    )


def test_split_preselection_is_deferred_and_second_bank_is_explicit():
    program = twelve_tools()
    first, second = program.plan_tool_banks()
    # T7 lives in bank one's source range; M6 starts bank two.
    assert program.lines[first.end_line - 1] == "T7"
    a, b = compile_bank(program, first), compile_bank(program, second)
    assert not a.errors and not b.errors
    assert a.lines[-1].draft == "" and a.lines[-1].reason
    assert b.lines[0].draft == "T1 M6"
    assert b.mapping == tuple((t, t - 6) for t in range(7, 13))
    assert "T7" not in b.body and "T6 M6" in b.body
    assert program.lines[first.end_line - 1] == "T7"  # source is unchanged
    assert b.to_dict()["execution_available"] is False


def test_mapping_preserves_comments_collet_and_source_line_locators():
    program = ProgramOperations.from_text("G21 G90\n" + "\n".join(f"t{t} m06 s2 (T99 M6) ; H99" for t in range(1, 8)))
    draft = compile_bank(program, program.plan_tool_banks()[1])
    assert not draft.errors
    assert draft.lines[0].draft == " T1 m06 s2 (T99 M6) ; H99"
    assert draft.lines[0].source_line == 8
    assert draft.program_hash == program.file_hash


def test_preselected_tool_during_old_tool_motion_does_not_move_boundary():
    text = "G21 G90 G17 G94 G54 G49 M5 M9\nG0 X0 Y0 Z10\nF100\n"
    text += "\n".join(f"T{t} M6\nG1 X{t}" for t in range(1, 7))
    text += "\nT7 G1 X99 ; still T6 cutting\nM6\nG1 X100"
    program = ProgramOperations.from_text(text)
    first, second = program.plan_tool_banks()
    draft = compile_bank(program, first)
    assert not draft.errors
    assert draft.lines[-1].draft == " G1 X99 ; still T6 cutting"
    assert compile_bank(program, second).lines[0].draft == "T1 M6"


def test_offset_mapping_requires_explicit_convention_and_matching_active_tool():
    program = twelve_tools("G43 H{t}")
    second = program.plan_tool_banks()[1]
    assert any("explicit logical-H" in error for error in compile_bank(program, second).errors)
    mapped = compile_bank(program, second, offset_mode="logical_h")
    assert not mapped.errors and "G43 H1" in mapped.body and "G43 H6" in mapped.body
    mismatch = ProgramOperations.from_text("G21 G90\nT7 M6\nG43 H8")
    assert (
        "active logical tool"
        in compile_bank(mismatch, mismatch.plan_tool_banks()[0], offset_mode="logical_h").errors[0]
    )


@pytest.mark.parametrize(
    "line",
    [
        "T[#1] M6",
        "/ T1 M6",
        "T1 M6*3",
        "O100 CALL",
        "G1 X#4",
        "T1 T2 M6",
        "T1 M6 G0 Z1",
        "T1 M6 M3",
        "T1.5 M6",
        "T1 M6 (bad",
        "T1 M6 )",
        "G41 D1",
        "G0 A45",
    ],
)
def test_ambiguous_or_unsupported_source_has_no_compiled_body(line):
    program = ProgramOperations.from_text("G21 G90\nT1 M6\n" + line)
    draft = compile_bank(program, program.plan_tool_banks()[0])
    assert draft.errors and draft.body == ""
    assert any(item.original == line and item.reason.startswith("Cannot compile") for item in draft.lines)


@pytest.mark.parametrize("tool", [0, 999990])
def test_probe_and_empty_spindle_are_not_treated_as_normal_pockets(tool):
    program = ProgramOperations.from_text(f"G21 G90\nT{tool} M6")
    assert compile_bank(program, program.plan_tool_banks()[0]).errors


def test_inherited_modes_are_visible_without_generating_restart_or_approach():
    program = twelve_tools(header="G20 G90 G17 G94 G54 G49 M3 S12000 M7\nG0 X0 Y0 Z1\nF10")
    draft = compile_bank(program, program.plan_tool_banks()[1])
    assert draft.modal_restoration == ("G20", "G17", "G94", "G54", "F10", "G90")
    assert draft.inherited_state["tool"] == 6
    assert draft.inherited_state["position_mm"][0] == pytest.approx(152.4)
    assert any("G1 motion" in caution for caution in draft.cautions)
    assert any("M3 S12000" in caution for caution in draft.cautions)
    assert not any(command.split()[0] in ("M3", "M6", "G0", "G1", "G43") for command in draft.modal_restoration)


def test_bank_identity_and_exclusive_export(tmp_path):
    program = twelve_tools()
    bank = program.plan_tool_banks()[1]
    with pytest.raises(ValueError, match="does not belong"):
        compile_bank(program, replace(bank, start_line=1))
    draft = compile_bank(program, bank)
    target = tmp_path / "review.json"
    save_draft(target, draft)
    assert json.loads(target.read_text()) == json.loads(json.dumps(draft.to_dict()))
    original = target.read_bytes()
    with pytest.raises(FileExistsError):
        save_draft(target, draft)
    assert target.read_bytes() == original


def test_review_load_export_and_stale_callback_are_command_free(tmp_path):
    from carveracontroller.desktop_bank_programs import BankProgramReview

    program = twelve_tools()
    bank = program.plan_tool_banks()[1]
    panel = SimpleNamespace(
        _context_key=Mock(return_value=(program.file_hash, "machine", 2)), program=program, bank=bank
    )
    with patch("carveracontroller.desktop_bank_programs.threading.Thread"):
        review = BankProgramReview(panel)
    draft = compile_bank(program, bank)
    review.loaded(review.generation, draft, None)
    assert "Logical T7 -> controller T1" in review.view.text
    assert review.draft == draft and not review.export_action.disabled
    with patch("carveracontroller.desktop_bank_programs.Path.home", return_value=tmp_path):
        review.export()
    assert len(list((tmp_path / ".carvera/bank-drafts").glob("*.json"))) == 1
    assert "saved and read back" in review.status.text
    panel._context_key.return_value = (program.file_hash, "different", 2)
    review.export()
    assert "context changed" in review.status.text
    with patch("carveracontroller.desktop_bank_programs.threading.Thread"):
        review.compile()
    review.loaded(review.generation - 1, draft, None)
    assert review.draft is None and review.export_action.disabled


def test_review_is_inline_and_dismissal_invalidates_pending_result():
    from carveracontroller.desktop_bank_programs import BankProgramReview
    from carveracontroller.desktop_components import Action, Surface

    program = twelve_tools()
    panel = Surface(orientation="vertical")
    panel._context_key = lambda: (program.file_hash, "machine", 2)
    panel.program, panel.bank = program, program.plan_tool_banks()[1]
    panel.program_review_action = Action("Review", lambda: None)
    panel.add_widget(panel.program_review_action)
    with patch("carveracontroller.desktop_bank_programs.threading.Thread"):
        review = BankProgramReview(panel)
    review.open()
    assert review.parent is panel
    assert panel.children.index(review) < panel.children.index(panel.program_review_action)
    generation = review.generation
    review.dismiss()
    assert review.parent is None
    review.loaded(generation, compile_bank(program, panel.bank), None)
    assert review.draft is None


def test_review_pages_every_source_line_and_locates_requested_line():
    from carveracontroller.desktop_bank_programs import BankProgramReview

    program = ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\n" + "\n".join(f"G1 X{i}" for i in range(420)))
    bank = program.plan_tool_banks()[0]
    panel = SimpleNamespace(_context_key=lambda: (program.file_hash, "machine", 1), program=program, bank=bank)
    with patch("carveracontroller.desktop_bank_programs.threading.Thread"):
        review = BankProgramReview(panel)
    review.loaded(review.generation, compile_bank(program, bank), None)
    review.select_section("Full source")
    seen = set()
    while True:
        seen.update(int(line.split(":", 1)[0][1:]) for line in review.view.text.splitlines() if line.startswith("L"))
        if review.next_action.disabled:
            break
        review.turn_page(1)
    assert seen == set(range(bank.start_line, bank.end_line + 1))
    review.line_input.text = "401"
    review.go_to_line()
    assert "L401:" in review.view.text and review.view.selection_text == "L401:"
    review.line_input.text = "99999"
    review.go_to_line()
    assert "must be in this bank" in review.page_status.text
    review.select_section("Source changes")
    assert "T1 M6" in review.view.text and "Draft:" in review.view.text and "G1 X419" not in review.view.text
    review.select_section("Modes & checks")
    assert "REQUIRED REVIEW" in review.view.text and review.line_action.disabled


def test_review_clears_previous_text_during_recompile_and_rejects_stale_navigation():
    from carveracontroller.desktop_bank_programs import BankProgramReview

    program = twelve_tools()
    key = Mock(return_value=(program.file_hash, "machine", 2))
    panel = SimpleNamespace(_context_key=key, program=program, bank=program.plan_tool_banks()[1])
    with patch("carveracontroller.desktop_bank_programs.threading.Thread"):
        review = BankProgramReview(panel)
        review.loaded(review.generation, compile_bank(program, panel.bank), None)
        review.compile()
    assert review.view.text == "" and review.export_action.disabled
    review.loaded(review.generation, compile_bank(program, panel.bank), None)
    key.return_value = (program.file_hash, "other machine", 2)
    review.line_input.text = str(panel.bank.start_line)
    review.go_to_line()
    assert "context changed" in review.page_status.text
