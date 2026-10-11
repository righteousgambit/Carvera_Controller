"""Retained refusal context from the final UI gate, with no machine dispatch."""

import json
from types import SimpleNamespace

import pytest

from tests.integration import test_backend_job_file as file_support
from tests.integration import test_backend_job_run as run_support
from tests.integration.test_backend_connection import wait_for

backend_job = file_support.backend_job
backend_run = run_support.backend_run


@pytest.mark.parametrize("change", ["probe_transaction", "setup"])
def test_final_gate_retains_owned_reason_and_clock_context_without_submitting(backend_run, monkeypatch, change):
    panel, backend, ws, state, requests, setup = backend_run
    rp = run_support.prepare_run(backend_run)
    journal = panel._journal
    injected = False

    def retain_then_change(job, path):
        nonlocal injected
        result = journal(job, path)
        if job.run_record["phase"] == "start_pending" and not injected:
            injected = True
            if change == "probe_transaction":
                monkeypatch.setattr(ws, "probe_settings_panel", SimpleNamespace(busy=True), raising=False)
            else:
                setup["stock"] = [99]
        return result

    monkeypatch.setattr(panel, "_journal", retain_then_change)
    run_support.start_review(rp)
    wait_for(lambda: rp.run.phase == "unresolved" and not panel.busy)
    assert injected
    receipt = rp.run.receipts[-1]
    assert receipt["outcome"] == "not_submitted"
    assert receipt["dispatch_checkpoint"] == "final_ui_admission"
    expected = (
        "The probe-settings workflow owns an unfinished transaction"
        if change == "probe_transaction"
        else "Program, profile or setup changed after run review"
    )
    assert receipt["admission"]["reason"] == expected
    assert expected in rp.note.text
    assert receipt["admission"]["cached_snapshot_age_s"] >= 0
    assert receipt["admission"]["child_status_age_s"] >= 0
    assert receipt["admission"]["combined_report_age_s"] >= 0
    retained = json.loads(panel.journal_path.read_text().splitlines()[-1])["job_run"]
    assert retained["phase"] == "unresolved"
    assert retained["receipts"][-1] == receipt
    assert not any(command.startswith(b"play ") for command in state.wire)
    assert not any(method == "operation" and params.get("operation") == "job.start" for method, params in requests)
    ws.machine.controller.executeCommand.assert_not_called()
