"""Actual private child + socket Player workflow; no physical machine or GUI writes."""

import json
import threading
import time

import pytest
from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.machine.setup_readiness import GROUPS, ReadinessItem, fingerprint
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job, freeze_upload


@pytest.fixture
def backend_run(backend_job):  # noqa: F811 - imported pytest fixture
    panel, backend, ws, state, requests, setup = backend_job
    now = time.time()
    ws.selected_machine_profile["model"] = "C1"
    for key in GROUPS:
        setup.setdefault(key, {"group": key})
    ws.readiness.snapshot = lambda: ("job", setup, dict.fromkeys(GROUPS, True))
    ws.readiness.items = [
        ReadinessItem(
            key,
            key,
            "measured",
            "loopback operator receipt",
            "Setup",
            {
                "machine_id": "job",
                "group": key,
                "fingerprint": fingerprint(setup[key]),
                "source": "operator",
                "method": "native loopback fixture",
                "measured_at": now - 60,
                "expires_at": now + 3600,
            },
        )
        for key in GROUPS
    ]
    state.version = b"version = 2.1.0c\n"
    state.reject_start = False
    state.drop_start = False

    def report(mode="Idle", playing=False):
        state.status = (
            f"<{mode}|MPos:1,2,3|WPos:4,5,6|C:1,4,0,1|S:0,0,100|T:1,12|G:0|P:0,0,0,{int(playing)}>\n".encode()
        )

    def handler(sock, command):
        if command == b"model\n":
            sock.sendall(b"model = C1, 1, 4, 1\n")
        elif command == b"version\n":
            sock.sendall(state.version)
        elif command.startswith(b"play "):
            if state.drop_start:
                import socket

                # Intentional disconnect ends the fixture server before it can
                # process observation bytes queued behind the dropped start.
                state.stop.set()
                sock.shutdown(socket.SHUT_RDWR)
                return True
            if state.reject_start:
                sock.sendall(b"ERROR: loopback refused program\n")
            else:
                sock.sendall(b"Playing file\n")
                report("Run", True)
        elif command == b"suspend\n":
            report("Pause", True)
        elif command == b"resume\n":
            report("Run", True)
        elif command == b"abort\n":
            report()
        else:
            return False
        return True

    state.command_handler = handler
    report()
    wait_for(lambda: backend.client.snapshot()["last_machine_snapshot"]["status"]["active_wcs"] == 0)
    yield backend_job


def prepare_run(fixture):
    panel, _backend, _ws, _state, _requests, _setup = fixture
    freeze_upload(panel)
    panel.verify_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert panel.job.phase == "verified", panel.note.text
    panel.review_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert panel.job.phase == "reviewed", panel.note.text
    panel.run_panel.identity_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert panel.run_panel.identity is not None, panel.run_panel.note.text
    from carveracontroller.machine.desktop_control_owner import reported_state

    def current_review_context():
        try:
            client = panel._validate_job("compile")
        except ValueError:
            return False
        return (
            client is _backend.client
            and panel.can_review()
            # Leave test-only headroom for review_run's context construction;
            # production admission still uses its unchanged 0.8-second lease.
            and reported_state(client.snapshot(), max_age_s=0.4) == "Idle"
        )

    # Settle identity/control rendering before qualifying the single review.
    pump_frames(3)
    wait_for(current_review_context)
    panel.run_panel.review_action.dispatch("on_release")
    assert panel.run_panel.run is not None, panel.run_panel.note.text
    assert panel.run_panel.popup is not None
    run_panel = panel.run_panel
    popup = run_panel.popup
    # Finish opening/rendering the rich review before callers alter intentional
    # negative context or dispatch their single reviewed start. SD/file receipts
    # and an earlier Idle observation do not qualify the current combined lease.
    pump_frames(3)
    wait_for(
        lambda: (
            run_panel.popup is popup
            and popup.parent is not None
            and popup._anim_alpha == 1
            and reported_state(_backend.client.snapshot()) == "Idle"
            and run_panel.can_control("job.start")
        )
    )
    return panel.run_panel


def wait_phase(run_panel, phase):
    def observed():
        run_panel.refresh()
        return not run_panel.file_panel.busy and not run_panel.journaling and run_panel.run.phase == phase

    wait_for(observed)


def start_review(run_panel):
    from carveracontroller.desktop_components import Action

    button = next(
        widget
        for widget in run_panel.popup.content.walk()
        if isinstance(widget, Action) and widget.text == "Start reviewed program"
    )
    button.dispatch("on_release")


def test_actual_child_reviewed_start_pause_resume_cancel_and_retained_observations(backend_run, tmp_path):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    ticks = []
    heartbeat = Clock.schedule_interval(lambda _dt: ticks.append(1), 0.01)
    try:
        start_review(rp)
        wait_phase(rp, "playing_reported")
        assert not rp.pause_action.disabled and not rp.cancel_action.disabled
        assert panel.freeze_action.disabled or rp.active
        rp.pause_action.dispatch("on_release")
        wait_phase(rp, "paused_reported")
        assert not rp.resume_action.disabled
        rp.resume_action.dispatch("on_release")
        wait_phase(rp, "playing_reported")
        rp.cancel_action.dispatch("on_release")
        wait_phase(rp, "settled_reported")
        assert len(ticks) >= 3
        wire = [
            command
            for command in state.wire
            if command.startswith(b"play ") or command in (b"suspend\n", b"resume\n", b"abort\n")
        ]
        assert wire == [f"play {panel.job.remote_path}\n".encode(), b"suspend\n", b"resume\n", b"abort\n"]
        records = [json.loads(line) for line in panel.journal_path.read_text().splitlines()]
        runs = [record["job_run"] for record in records if record["job_run"] is not None]
        assert [run["phase"] for run in runs] == [
            "start_pending",
            "start_acknowledged",
            "playing_reported",
            "pause_pending",
            "pause_acknowledged",
            "paused_reported",
            "resume_pending",
            "resume_acknowledged",
            "playing_reported",
            "cancel_pending",
            "cancel_acknowledged",
            "settled_reported",
        ]
        assert all(run["motion_completed"] is False and run["physical_setup_verified"] is False for run in runs)
        assert runs[-1]["last_observation"]["status"]["state"] == "Idle"
        assert len(runs[-1]["receipts"]) == 4
        assert records[-1]["reported_identity"]["model"]["reported_model"] == "C1"
        for width in (300, 650):
            panel.width = dp(width)
            pump_frames(5)
            assert all(widget.height >= widget.texture_size[1] for widget in (rp.note, rp.status))
            panel.export_to_png(str(tmp_path / f"backend-job-run-{width}.png"))
        ws.machine.controller.executeCommand.assert_not_called()
    finally:
        heartbeat.cancel()


@pytest.mark.parametrize("change", ["setup", "expired_review", "expired_measurement", "tool", "wcs", "version"])
def test_review_changes_refuse_actual_child_play_without_gui_fallback(backend_run, change):
    panel, backend, ws, state, requests, setup = backend_run
    if change == "version":
        state.version = b"version = future\n"
    rp = prepare_run(backend_run) if change != "version" else None
    if change == "version":
        freeze_upload(panel)
        panel.verify_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        panel.review_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        panel.run_panel.read_identity()
        wait_for(lambda: not panel.busy)
        panel.run_panel.review_run()
        assert panel.run_panel.run is None
    else:
        if change == "setup":
            setup["stock"] = [99]
        elif change == "expired_review":
            rp.run.reviewed_at -= 31
        elif change == "expired_measurement":
            for item in ws.readiness.items:
                item.receipt["expires_at"] = time.time() - 1
        else:
            state.status = (
                state.status.replace(b"T:1,12", b"T:2,12") if change == "tool" else state.status.replace(b"G:0", b"G:1")
            )
            wait_for(
                lambda: (
                    backend.client.snapshot()["last_machine_snapshot"]["status"][
                        "tool" if change == "tool" else "active_wcs"
                    ]
                    == (2 if change == "tool" else 1)
                )
            )
        start_review(rp)
        assert rp.run.phase == "review"
    assert not any(command.startswith(b"play ") for command in state.wire)
    ws.machine.controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("change", ["setup", "retired", "journal_failed"])
def test_context_recheck_after_durable_intent_prevents_actual_play(backend_run, monkeypatch, change):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    entered, release = threading.Event(), threading.Event()
    original = panel._journal
    ui_thread = threading.get_ident()

    def delayed(job, path):
        assert threading.get_ident() != ui_thread
        if job.run_record["phase"] == "start_pending":
            entered.set()
            assert release.wait(4)
            if change == "journal_failed":
                raise OSError("loopback receipt store unavailable")
        return original(job, path)

    monkeypatch.setattr(panel, "_journal", delayed)
    start_review(rp)
    wait_for(entered.is_set)
    if change == "setup":
        setup["stock"] = [101]
    elif change == "retired":
        panel.dispose()
    release.set()
    wait_for(lambda: rp.run.phase == "unresolved")
    if change != "retired":
        wait_for(lambda: not panel.busy)
    assert not any(command.startswith(b"play ") for command in state.wire)
    assert rp.run.receipts[-1]["outcome"] == "not_submitted"


def test_actual_child_rejection_retained_without_retry_or_gui_fallback(backend_run):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    state.reject_start = True
    start_review(rp)
    wait_phase(rp, "unresolved")
    count = sum(command.startswith(b"play ") for command in state.wire)
    rp.dispatch_run("job.start")
    rp.dispatch_run("job.resume")
    pump_frames(5)
    assert count == 1 and sum(command.startswith(b"play ") for command in state.wire) == count
    assert rp.pause_action.disabled and rp.resume_action.disabled and rp.cancel_action.disabled
    assert json.loads(panel.journal_path.read_text().splitlines()[-1])["job_run"]["phase"] == "unresolved"
    ws.machine.controller.executeCommand.assert_not_called()


def test_actual_child_ack_loss_latches_unresolved_without_replay(backend_run):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    state.drop_start = True
    start_review(rp)
    wait_phase(rp, "unresolved")
    wait_for(lambda: backend.client.snapshot()["last_machine_snapshot"]["unknown_outcome"] is True)
    rp.dispatch_run("job.start")
    pump_frames(5)
    assert sum(command.startswith(b"play ") for command in state.wire) == 1
    assert rp.run.receipts[0]["outcome"] == "unverified_response"
    assert rp.run.receipts[0]["response"]["error"] == "unknown_outcome"
    assert "controller_receive_evidence" in rp.run.receipts[0]["response"]["receipt"]
    assert rp.active and panel.freeze_action.disabled
    ws.machine.controller.executeCommand.assert_not_called()


def test_changed_setup_refuses_resume_but_allows_retained_job_cancel(backend_run):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    start_review(rp)
    wait_phase(rp, "playing_reported")
    rp.pause_action.dispatch("on_release")
    wait_phase(rp, "paused_reported")
    setup["stock"] = [102]
    rp.refresh()
    assert rp.resume_action.disabled and not rp.cancel_action.disabled
    assert not rp.allows_hold_resume()
    rp.dispatch_run("job.resume")
    assert b"resume\n" not in state.wire
    rp.cancel_action.dispatch("on_release")
    wait_phase(rp, "settled_reported")
    assert state.wire.count(b"abort\n") == 1


def test_main_program_pause_abort_route_actual_retained_backend_job(backend_run, kivy_app, monkeypatch):
    panel, backend, old_ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    start_review(rp)
    wait_phase(rp, "playing_reported")
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "backend_panel", backend)
    monkeypatch.setattr(ws, "control_owner", old_ws.control_owner)
    monkeypatch.setattr(ws, "selected_machine_profile", old_ws.selected_machine_profile)
    monkeypatch.setattr(ws, "job_file_panel", panel)
    monkeypatch.setattr(ws.machine.controller, "stream", None)
    from unittest.mock import Mock

    execute = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", execute)
    backend.workspace = ws
    try:
        ws.select("Job")
        ws.refresh(0)
        pause, cancel = ws.program_action_buttons["Pause program"], ws.program_action_buttons["Abort program"]
        assert pause.parent is ws.program_actions and cancel.parent is ws.program_actions
        assert not pause.disabled and not cancel.disabled
        pause.dispatch("on_release")
        wait_phase(rp, "paused_reported")
        ws.refresh(0)
        cancel.dispatch("on_release")
        wait_phase(rp, "settled_reported")
        assert state.wire.count(b"suspend\n") == 1 and state.wire.count(b"abort\n") == 1
        execute.assert_not_called()
    finally:
        backend.workspace = old_ws


def test_actual_run_review_shows_all_setup_groups_and_fits_compact_and_wide(backend_run, tmp_path):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    from kivy.uix.label import Label

    from carveracontroller.desktop_planning import PlanningCard

    popup = rp.popup
    cards = [widget for widget in popup.content.walk() if isinstance(widget, PlanningCard)]
    assert {card.title for card in cards} == {key.title() + " · measured setup" for key in GROUPS}
    labels = [widget for widget in popup.content.walk() if isinstance(widget, Label)]
    assert any("WCS: G54" in widget.text for widget in labels)
    for width in (300, 650):
        popup.size_hint_x = None
        popup.width = dp(width)
        for card in cards:
            card.set_expanded(True, reveal=False)
        pump_frames(8)
        labels = [widget for widget in popup.content.walk() if isinstance(widget, Label)]
        assert all(widget.height >= widget.texture_size[1] for widget in labels if widget.size_hint_y is None)
        assert any("native loopback fixture" in widget.text for widget in labels)
        assert popup.height <= 0.9 * __import__("kivy.core.window", fromlist=["Window"]).Window.height
        popup.export_to_png(str(tmp_path / f"backend-job-run-review-{width}.png"))
    assert not any(command.startswith(b"play ") for command in state.wire)


def test_expired_ui_admission_callback_cannot_submit_late(backend_run, monkeypatch):
    panel, backend, ws, state, requests, setup = backend_run
    rp = prepare_run(backend_run)
    saved = []
    schedule = Clock.schedule_once

    def delay_preflight(callback, *args, **kwargs):
        if callback.__name__ == "preflight":
            saved.append(callback)
            return None
        return schedule(callback, *args, **kwargs)

    monkeypatch.setattr(Clock, "schedule_once", delay_preflight)
    start_review(rp)
    wait_phase(rp, "unresolved")
    assert len(saved) == 1 and rp.run.receipts[-1]["outcome"] == "not_submitted"
    saved[0](0)
    pump_frames(5)
    assert not any(command.startswith(b"play ") for command in state.wire)
    ws.machine.controller.executeCommand.assert_not_called()
