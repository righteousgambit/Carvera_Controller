"""Actual preview producers invalidate bank intent before backend submission."""

import copy
import threading
from types import SimpleNamespace

import pytest

from carveracontroller.desktop_bank_handoff import BankReviewHandoff
from carveracontroller.desktop_program_picker import ProgramBrowser
from carveracontroller.machine.probe_settings_workflow import append_journal
from carveracontroller.machine.program_places import ProgramPlaces
from tests.integration.bank_preview_support import completed_bank_preview  # noqa: F401
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401
from tests.integration.test_backend_tool_measurement import measurement_workbench  # noqa: F401
from tests.integration.test_bank_review_handoff import bank_workbench, prepare_exchange  # noqa: F401
from tests.integration.test_completed_program_source import until


@pytest.fixture
def actual_bank(completed_bank_preview, bank_workbench, monkeypatch, tmp_path):  # noqa: F811
    preview = completed_bank_preview
    bank, exchange, measurement, backend, ws, state, requests, profile = bank_workbench
    custody, library = ws.machine.tool_custody, ws.machine.gcode_viewer.library_tool_table_mm
    assembly_id = bank.choices[1]
    monkeypatch.setitem(preview.root.__dict__, "_tool_custody", custody)
    monkeypatch.setattr(preview.root.gcode_viewer, "library_tool_table_mm", library)
    monkeypatch.setattr(preview.workspace, "selected_machine_profile", ws.selected_machine_profile)
    monkeypatch.setattr(
        preview.workspace.profile_store, "_data", dict(preview.workspace.profile_store.data, tools=[profile])
    )
    monkeypatch.setattr(preview.workspace, "open_tool_exchange", exchange.use_bank)
    monkeypatch.setattr(preview.workspace, "open_tool_measurement", measurement.use_bank)
    ws.machine, ws.app = preview.root, preview.app
    bank.workspace = bank.operations.workspace = preview.workspace
    bank.operations.program = preview.program
    bank.load(preview.program)
    bank.selector.text = next(label for label, item in bank.options.items() if item.index == 2)
    bank.choose(1, assembly_id)
    bank.save()
    assert bank.choices == {1: assembly_id}, bank.result.text
    browser = ProgramBrowser(preview.workspace, ProgramPlaces(tmp_path / "places.json"))
    browser._build()
    browser.navigate(str(preview.path.parent))
    until(lambda: any(entry.path == str(preview.path) for entry in browser.visible_entries), "Bank program row missing")
    browser.select(next(entry for entry in browser.visible_entries if entry.path == str(preview.path)))
    until(lambda: browser.inspection is not None, "Bank program inspection did not finish")
    try:
        yield SimpleNamespace(preview=preview, parts=bank_workbench, browser=browser)
    finally:
        browser.dismiss()
        browser._stop_polling()
        until(lambda: not browser._places_worker_running, "Picker place writer did not settle")


def prepare(case, workflow):
    bank, exchange, measurement, *_ = case.parts
    if workflow == "exchange":
        return exchange, prepare_exchange(case.parts), exchange.exchange
    bank.review_exchange(1, measurement=True)
    measurement.read_identity()
    wait_for(lambda: not measurement.busy)
    measurement.kind.text = "Installed cutter"
    measurement.review_measurement()
    wait_for(lambda: not measurement.busy)
    assert measurement.review is not None, measurement.note.text
    return measurement, measurement.review, measurement.measurement


def hold_intent(monkeypatch, workflow):
    entered, release = threading.Event(), threading.Event()

    def delayed(path, record, **kwargs):
        append_journal(path, record, **kwargs)
        if record["phase"] == workflow + "_pending":
            entered.set()
            assert release.wait(10)

    monkeypatch.setattr(f"carveracontroller.desktop_tool_{workflow}.append_journal", delayed)
    return entered, release


@pytest.mark.parametrize("workflow", ["exchange", "measurement"])
@pytest.mark.parametrize("reload_result", ["complete", "failed"])
def test_actual_same_path_preview_rejects_pending_and_new_bank_intent(
    actual_bank, monkeypatch, workflow, reload_result
):
    case = actual_bank
    preview, browser = case.preview, case.browser
    root, app = preview.root, preview.app
    bank, _exchange, _measurement, _backend, _ws, state, *_ = case.parts
    panel, review, dispatch = prepare(case, workflow)
    handoff = panel.bank_handoff
    entered, release = hold_intent(monkeypatch, workflow)
    loader_entered, loader_release, loader_done = threading.Event(), threading.Event(), threading.Event()
    original = root.load_gcode_file

    def paused_loader(*args, **kwargs):
        loader_entered.set()
        try:
            assert loader_release.wait(10)
            original(*args, **kwargs)
        finally:
            loader_done.set()

    monkeypatch.setattr(root, "load_gcode_file", paused_loader)
    old_generation = root.program_preview_generation
    old_program, old_hash = bank.program, root.gcode_viewer.loaded_program_hash
    dispatch(review)
    try:
        wait_for(entered.is_set)
        browser.preview()  # Actual picker -> actual root method, same selected path.
        wait_for(loader_entered.is_set)
        assert root.program_preview_generation > old_generation
        assert app.selected_local_filename == str(preview.path)
        assert bank.operations.program is old_program and bank.program is old_program
        assert root.gcode_viewer.loaded_program_hash == old_hash and not root.loading_file
        release.set()
        wait_for(lambda: not panel.busy)
        assert panel.latest_record["phase"] == "not_submitted", panel.latest_record
        assert not panel.latest_record["submitted"] and state.exchanges == state.measurements == []
        with pytest.raises(ValueError, match="Preview this program locally"):
            BankReviewHandoff(bank, 1)
        if reload_result == "failed":
            preview.path.unlink()
    finally:
        release.set()
        loader_release.set()
        until(loader_done.is_set, "Held preview worker did not finish")
        pump_frames(10, sleep=0.02)
    with pytest.raises(ValueError):
        handoff.resolve()
    if reload_result == "complete":
        until(
            lambda: not root.loading_file and preview.workspace.retained_program_source(str(preview.path)) is not None,
            "Same-content reload did not complete",
        )
        assert BankReviewHandoff(bank, 1).resolve()["program_hash"] == old_hash
    else:
        with pytest.raises(ValueError, match="Preview this program locally"):
            BankReviewHandoff(bank, 1)


@pytest.mark.parametrize("workflow", ["exchange", "measurement"])
@pytest.mark.parametrize("change", ["identity_aba", "display_aba", "loading"])
def test_display_replacement_during_intent_never_revives_bank_review(actual_bank, monkeypatch, workflow, change):
    case = actual_bank
    viewer, root = case.preview.root.gcode_viewer, case.preview.root
    panel, review, dispatch = prepare(case, workflow)
    entered, release = hold_intent(monkeypatch, workflow)
    dispatch(review)
    try:
        wait_for(entered.is_set)
        if change in {"identity_aba", "display_aba"}:
            digest = viewer.loaded_program_hash
            if change == "display_aba":
                previous = viewer.capture_program_display()
                viewer.meshmanager = copy.deepcopy(viewer.meshmanager)
                viewer.restore_program_display(previous)
            else:
                viewer.set_loaded_program_identity(None)
                viewer.set_loaded_program_identity(digest)
            assert viewer.loaded_program_hash == digest
        else:
            root.loading_file = True
    finally:
        release.set()
    wait_for(lambda: not panel.busy)
    assert panel.latest_record["phase"] == "not_submitted", panel.latest_record
    assert case.parts[5].exchanges == case.parts[5].measurements == []
    root.loading_file = False


def test_candidate_inspection_preserves_completed_bank_review(actual_bank, tmp_path):
    case = actual_bank
    bank = case.parts[0]
    handoff = BankReviewHandoff(bank, 1)
    captured = handoff.resolve()
    other = tmp_path / "candidate.nc"
    other.write_text("G21 G90\nT2 M6\nG0 X44 Y22 Z10\n")
    case.browser.navigate(str(other.parent))
    until(lambda: any(entry.path == str(other) for entry in case.browser.visible_entries), "Candidate row missing")
    case.browser.select(next(entry for entry in case.browser.visible_entries if entry.path == str(other)))
    until(lambda: case.browser.inspection is not None, "Candidate inspection did not finish")
    assert case.browser.inspection.digest != bank.program.file_hash
    assert handoff.resolve() == captured
    assert case.parts[5].exchanges == case.parts[5].measurements == []


def test_actual_portable_import_completion_supports_fresh_bank_review(actual_bank, monkeypatch, tmp_path):
    from carveracontroller import desktop_job_packages as jobs
    from carveracontroller.machine.job_packages import JobPackage, save_package
    from carveracontroller.machine.retained_program_source import RetainedProgramSource

    case = actual_bank
    ws, root = case.preview.workspace, case.preview.root
    bank, exchange, measurement, *_ = case.parts
    assembly_id = bank.choices[1]
    previous = BankReviewHandoff(bank, 1)
    archive = save_package(
        JobPackage("Bank preview", case.preview.path.read_bytes(), program_name="bank.nc"), tmp_path / "bank.cvjob"
    )
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ws, "choose_asset_file", lambda selected, **_kwargs: selected(archive))
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    jobs.import_job(ws)
    until(lambda: getattr(ws, "_job_import_review", None) is not None, ws.package_note.text)
    ws._job_import_review.apply_button.dispatch("on_release")
    until(lambda: ws.package_note.text.startswith("Restored local preview"), ws.package_note.text)
    until(lambda: ws.operation_panel.program is not None, "Imported program analysis unavailable")
    assert isinstance(ws._retained_program_source, RetainedProgramSource)
    assert ws._retained_program_source.generation == root.program_preview_generation
    with pytest.raises(ValueError):
        previous.resolve()
    bank.operations.program = ws.operation_panel.program
    bank.load(ws.operation_panel.program)
    bank.selector.text = next(label for label, item in bank.options.items() if item.index == 2)
    bank.choose(1, assembly_id)
    bank.save()
    bank.review_exchange(1)
    bank.review_exchange(1, measurement=True)
    assert exchange.bank_handoff.resolve()["program_preview"]["request_generation"] == root.program_preview_generation
    assert measurement.bank_handoff.resolve()["program_hash"] == ws._retained_program_source.source_hash
    assert case.parts[5].exchanges == case.parts[5].measurements == []
