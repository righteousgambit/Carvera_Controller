"""Actual operation analysis consumes the committed immutable preview source."""

import hashlib
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller import desktop_operations as operations
from carveracontroller.desktop_job_transaction import LocalJobTransaction
from tests.integration.conftest import pump_frames
from tests.integration.test_job_setup_transaction import apply_changes
from tests.integration.test_job_setup_transaction import job as _job
from tests.integration.test_staged_program_preview import staged as _staged

job, staged = _job, _staged


def settle(panel):
    deadline = time.monotonic() + 8
    while panel.program is None and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert panel.program is not None, panel.note.text


def commit(s):
    with LocalJobTransaction(s.workspace, s.profile, program=s.prepared) as tx:
        apply_changes(s, tx)
        tx.commit()
    return tx


@pytest.mark.parametrize("mutation", ["replace", "delete"])
def test_committed_and_reanalysed_operations_use_retained_text(job, mutation):
    s = job
    # The source is changed/deleted after its renderer buffers were prepared.
    if mutation == "replace":
        s.path.write_text("(operation: Unreviewed replacement)\nG20\nT9 M6\nG0 X99\n")
    else:
        s.path.unlink()
    commit(s)
    panel = s.workspace.operation_panel
    settle(panel)
    assert panel.program.file_hash == s.prepared.program.source_hash
    assert panel.program.lines == tuple(line.rstrip("\r\n") for line in s.prepared.program.lines)
    assert panel.program.file_hash == s.viewer.loaded_program_hash
    settings = panel.analysis_settings
    settings.dialect.text = "LinuxCNC · spline study"
    settings.tolerance.text, settings.budget.text = "0.02", "1234"
    settings.apply_action.dispatch("on_release")
    settle(panel)
    assert panel.program.file_hash == s.prepared.program.source_hash
    assert panel.program.dialect == "linuxcnc"
    assert panel.program.parse_settings.spline_tolerance_mm == 0.02
    assert panel.program.parse_settings.max_spline_segments == 1234
    s.send.assert_not_called()


def test_unrelated_analysis_query_does_not_discard_active_source(job):
    s = job
    commit(s)
    original = s.workspace.retained_program_source(str(s.path))
    assert original is not None
    assert s.workspace.retained_program_source("another-file.nc") is None
    assert s.workspace.retained_program_source(str(s.path)) is original


def test_failed_import_rebinds_old_source_without_reloading_old_analysis(job):
    s = job
    commit(s)
    panel = s.workspace.operation_panel
    settle(panel)
    previous_source = s.workspace.retained_program_source(str(s.path))
    previous_program = panel.program
    generation = s.root.program_preview_generation
    s.analysis_reload.reset_mock()
    with pytest.raises(RuntimeError), LocalJobTransaction(s.workspace, s.profile, program=s.prepared) as tx:
        apply_changes(s, tx)
        raise RuntimeError("after second local program")
    assert not tx.recovery_errors
    current = s.workspace.retained_program_source(str(s.path))
    assert current is not None and current.lines is previous_source.lines
    assert current.generation > generation
    assert panel.program is previous_program
    s.analysis_reload.assert_not_called()
    s.path.unlink()
    panel.load(str(s.path))
    settle(panel)
    assert panel.program.file_hash == s.prepared.program.source_hash


@pytest.mark.parametrize("change", ["generation", "identity", "remote"])
def test_old_retained_worker_cannot_publish_for_a_changed_selection(job, monkeypatch, change):
    s = job
    commit(s)
    panel = s.workspace.operation_panel
    settle(panel)
    workers = []

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    monkeypatch.setattr(operations, "threading", SimpleNamespace(Thread=DeferredThread))
    panel.load(str(s.path))
    assert len(workers) == 1 and panel.program is None
    if change == "generation":
        s.root.program_preview_generation += 1
    elif change == "identity":
        s.viewer.set_loaded_program_identity("0" * 64)
    else:
        s.app.selected_remote_filename = "remote.nc"
        # The ordinary selection observer owns any newly requested analysis.
        panel.generation += 1
    workers[0]()
    pump_frames(3)
    assert panel.program is None
    if change != "remote":
        assert "Preview source changed" in panel.note.text
    s.send.assert_not_called()


def test_ordinary_reload_generation_drops_retained_source_and_reads_current_file(job):
    s = job
    commit(s)
    panel = s.workspace.operation_panel
    settle(panel)
    new = "G21 G90\nT9 M6\nG0 X99\n"
    s.path.write_text(new)
    s.root.program_preview_generation += 1
    assert s.workspace.retained_program_source(str(s.path)) is None
    panel.load(str(s.path))
    settle(panel)
    assert panel.program.file_hash == hashlib.sha256(new.encode()).hexdigest()
    assert panel.program.file_hash != s.prepared.program.source_hash


def defer_workers(monkeypatch):
    workers = []

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    monkeypatch.setattr(operations, "threading", SimpleNamespace(Thread=DeferredThread))
    return workers


def test_pending_analysis_survives_recovered_import_without_reading_disk(job, monkeypatch):
    s = job
    commit(s)
    panel = s.workspace.operation_panel
    settle(panel)
    workers = defer_workers(monkeypatch)
    panel.load(str(s.path))
    source = s.workspace.retained_program_source(str(s.path))
    with pytest.raises(RuntimeError), LocalJobTransaction(s.workspace, s.profile, program=s.prepared) as tx:
        apply_changes(s, tx)
        raise RuntimeError("recover before analysis finishes")
    assert not tx.recovery_errors
    recovered = s.workspace.retained_program_source(str(s.path))
    assert recovered.generation > source.generation and recovered.lines is source.lines
    assert len(workers) == 1
    s.path.unlink()
    workers[0]()
    settle(panel)
    assert panel.program.file_hash == source.source_hash
    s.send.assert_not_called()


def test_superseded_completion_preserves_new_analysis_and_source(job, monkeypatch):
    s = job
    commit(s)
    panel = s.workspace.operation_panel
    settle(panel)
    workers = defer_workers(monkeypatch)
    panel.load(str(s.path))
    commit(s)
    current = s.workspace.retained_program_source(str(s.path))
    assert len(workers) == 2
    s.path.unlink()
    workers[1]()
    settle(panel)
    newest = panel.program
    workers[0]()
    pump_frames(3)
    assert panel.program is newest
    assert s.workspace.retained_program_source(str(s.path)) is current
    s.send.assert_not_called()
