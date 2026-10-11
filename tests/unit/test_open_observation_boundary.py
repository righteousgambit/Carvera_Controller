"""Event-driven regression for real Controller.open, with no device/native I/O."""

import threading
import time as real_time
import weakref
from copy import deepcopy
from unittest.mock import Mock

import pytest

from carveracontroller import Controller as controller_module
from carveracontroller.CNC import CNC
from carveracontroller.Controller import CONN_USB, CONN_WIFI, NOT_CONNECTED, Controller
from carveracontroller.session_replay import replay_jsonl


@pytest.fixture(autouse=True)
def isolated_cnc_vars(monkeypatch):
    # Controller connection publication changes class-level machine state.
    # Restore the original mapping after every test, including failure paths.
    monkeypatch.setattr(CNC, "vars", deepcopy(CNC.vars))


class FakeTransport:
    uses_framed_transfer = False

    def __init__(self, attempt):
        self.attempt = attempt
        self.open_calls = 0
        self.close_calls = 0
        self.wire = []

    def open(self, _address):
        self.open_calls += 1
        self.attempt.block("open")
        return True

    def close(self):
        self.close_calls += 1
        self.attempt.block("cleanup")
        self.attempt.block("closing")

    def send(self, data):
        self.wire.append(data)


class Attempt:
    def __init__(self, monkeypatch, stage, succeeds=True):
        self.stage = stage
        self.succeeds = succeeds
        self.entered = threading.Event()
        self.release = threading.Event()
        self.receiver_started = threading.Event()
        self.receiver_errors = []
        self.finished = threading.Event()
        self.result = []
        self.controller = Controller(CNC(), None)
        self.transport = FakeTransport(self)
        self.controller.usb_stream = self.controller.wifi_stream = self.transport
        self.controller.reconnect_enabled = False
        monkeypatch.setattr(Controller, "_instances", weakref.WeakSet([self.controller]))
        monkeypatch.setattr(self.controller, "streamIO", self.receive)
        attempt = self

        class TimeProxy:
            def __getattr__(self, name):
                return getattr(real_time, name)

            def sleep(self, seconds):
                attempt.sleep(seconds)

        # Replace only this module binding; do not change shared time.sleep
        # used by pytest, Kivy, transports or surviving background threads.
        monkeypatch.setattr(controller_module, "time", TimeProxy())

        def detect(candidate, stream):
            assert candidate is not self.controller.comms
            assert stream is self.transport
            return self.detect(stream)

        monkeypatch.setattr(controller_module.ProtocolSession, "detect_and_select", detect)

    def block(self, stage):
        if self.stage == stage:
            self.entered.set()
            assert self.release.wait(3), "test did not release the blocked operation"

    def sleep(self, seconds):
        if seconds == 2.0:
            self.block("boot")

    def detect(self, stream):
        # Patched on the class without a receiver binding; use a closure below
        # when testing that the private candidate differs from shared comms.
        self.block("detect")
        if not self.succeeds:
            raise OSError("synthetic protocol failure")
        return "smoothie"

    def receive(self, generation):
        try:
            assert generation == self.controller._connection_generation
            assert self.controller.stream is self.transport
            assert self.controller.comms.ready
            assert not self.controller.stop.is_set()
            self.receiver_started.set()
            self.controller.stop.wait(3)
        except BaseException as error:
            self.receiver_errors.append(error)
            self.receiver_started.set()

    def start(self, conn_type=CONN_WIFI):
        def work():
            try:
                self.result.append(self.controller.open(conn_type, "test.invalid"))
            except Exception as error:
                self.result.append(error)
            finally:
                self.finished.set()

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        assert self.entered.wait(1)

    def cleanup(self):
        self.release.set()
        self.worker.join(4)
        assert not self.worker.is_alive()
        if self.result == [True]:
            assert self.receiver_started.wait(1), "successful receiver never started"
        self.controller.close_manual()
        assert all(not thread.is_alive() for thread in self.controller._receive_threads)
        assert not self.receiver_errors


def assert_observations_complete_before_release(controller):
    finished = threading.Event()
    failures = []

    def read():
        try:
            controller.machine_response_age(1)
            controller.status_reacquisition_remaining(1)
            _ = controller.status_reacquisition_pending
            controller.sensor_context_snapshot()
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()

    observer = threading.Thread(target=read, daemon=True)
    observer.start()
    assert finished.wait(1), "opening owns a UI observation lock across blocking I/O"
    observer.join(1)
    assert not failures


@pytest.mark.parametrize("stage,conn_type", [("open", CONN_WIFI), ("boot", CONN_USB), ("detect", CONN_WIFI)])
def test_real_open_keeps_observations_responsive_and_excludes_other_io(monkeypatch, tmp_path, stage, conn_type):
    attempt = Attempt(monkeypatch, stage)
    controller = attempt.controller
    try:
        attempt.start(conn_type)
        assert controller._connecting and controller.stop.is_set()
        assert controller.stream is None
        assert not attempt.receiver_started.is_set()
        assert_observations_complete_before_release(controller)
        before = (
            controller._connection_generation,
            controller._recovery_pending_token,
            controller._recovery_external_requests,
            controller.stop.is_set(),
        )
        assert controller.open(conn_type, "duplicate.invalid") is False
        assert before == (
            controller._connection_generation,
            controller._recovery_pending_token,
            controller._recovery_external_requests,
            controller.stop.is_set(),
        )
        with pytest.raises(ValueError, match="disconnected"):
            replay_jsonl(tmp_path / "must-not-be-read.jsonl")
        assert controller.executeCommand("G0 X1") is False
        controller.executeRealtime(ord("~"))
        controller.executeFileCommand("upload /sd/test.nc")
        with pytest.raises(ConnectionError, match="opening"):
            controller._send_observed(b"G0 X1\n", "command")
        with pytest.raises(ConnectionError, match="opening"):
            controller.pauseStream()
        assert not controller.paused and not controller.pausing
        assert attempt.transport.wire == []
    finally:
        attempt.cleanup()
    assert attempt.result == [True]
    assert attempt.receiver_started.is_set()


@pytest.mark.parametrize("stage,conn_type", [("open", CONN_WIFI), ("boot", CONN_USB), ("detect", CONN_WIFI)])
@pytest.mark.parametrize("manual", [False, True])
def test_close_during_any_open_stage_prevents_late_publication(monkeypatch, stage, conn_type, manual):
    attempt = Attempt(monkeypatch, stage)
    controller = attempt.controller
    try:
        attempt.start(conn_type)
        prior_generation = controller._connection_generation
        close_finished = threading.Event()
        close = controller.close_manual if manual else controller.close
        closer = threading.Thread(target=lambda: (close(), close_finished.set()), daemon=True)
        closer.start()
        assert close_finished.wait(1), "close must cancel generation without waiting for opening I/O"
        closer.join(1)
        assert controller._connection_generation == prior_generation + 1
        assert controller._connecting
        assert controller.stop.is_set()
        assert controller.stream is None
        if manual:
            assert controller._manual_disconnect
        assert_observations_complete_before_release(controller)
    finally:
        attempt.cleanup()
    assert attempt.result == [False]
    assert not attempt.receiver_started.is_set()
    assert controller.stop.is_set() and controller.stream is None
    assert not controller._connecting and not controller.comms.ready
    assert CNC.vars["state"] == NOT_CONNECTED
    assert attempt.transport.close_calls >= 1


def test_failure_cleanup_keeps_observations_available_and_blocks_replay(monkeypatch, tmp_path):
    attempt = Attempt(monkeypatch, "cleanup", succeeds=False)
    try:
        attempt.start()
        assert attempt.controller._connecting and attempt.controller.stop.is_set()
        assert_observations_complete_before_release(attempt.controller)
        with pytest.raises(ValueError, match="disconnected"):
            replay_jsonl(tmp_path / "must-not-be-read.jsonl")
    finally:
        attempt.cleanup()
    assert len(attempt.result) == 1 and isinstance(attempt.result[0], OSError)
    assert not attempt.receiver_started.is_set()
    assert not attempt.controller._connecting and not attempt.controller.comms.ready


@pytest.mark.parametrize("busy", ["paused", "pausing", "sendNUM", "loadNUM", "_baud_switch_in_progress"])
def test_existing_transfer_rejects_open_without_invalidating_its_state(monkeypatch, busy):
    controller = Controller(CNC(), None)
    monkeypatch.setattr(controller, busy, True)
    opening = Mock()
    monkeypatch.setattr(controller, "_open_owned", opening)
    before = (
        controller._connection_generation,
        controller._recovery_pending_token,
        controller._recovery_external_requests,
        controller.stop.is_set(),
        deepcopy(controller.run_evidence.program),
    )
    assert controller.open(CONN_WIFI, "test.invalid") is False
    after = (
        controller._connection_generation,
        controller._recovery_pending_token,
        controller._recovery_external_requests,
        controller.stop.is_set(),
        deepcopy(controller.run_evidence.program),
    )
    assert before == after
    opening.assert_not_called()


def test_backend_owner_rejection_has_no_connection_side_effects(monkeypatch):
    controller = Controller(CNC(), None)
    controller.command_owner_guard = lambda: False
    before = (
        controller._connection_generation,
        controller._recovery_pending_token,
        controller._recovery_external_requests,
        controller.stop.is_set(),
    )
    assert controller.open(CONN_WIFI, "test.invalid") is False
    assert before == (
        controller._connection_generation,
        controller._recovery_pending_token,
        controller._recovery_external_requests,
        controller.stop.is_set(),
    )
    with pytest.raises(ConnectionError, match="another command owner"):
        controller.pauseStream()
    assert not controller.paused


def test_replay_lock_admission_is_nonblocking_and_preserves_connection_evidence(monkeypatch):
    controller = Controller(CNC(), None)
    opening = Mock(return_value=False)
    monkeypatch.setattr(controller, "_open_owned", opening)
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    result = []

    def replay_owner():
        with Controller._evidence_global_lock:
            entered.set()
            assert release.wait(3)

    def open_worker():
        result.append(controller.open(CONN_WIFI, "test.invalid"))
        returned.set()

    holder = threading.Thread(target=replay_owner, daemon=True)
    holder.start()
    worker = threading.Thread(target=open_worker, daemon=True)
    before = (controller._connection_generation, controller._recovery_pending_token, controller.stop.is_set())
    try:
        assert entered.wait(1)
        worker.start()
        assert returned.wait(1), "open waited for replay while owning observation state"
        assert_observations_complete_before_release(controller)
        assert result == [False]
        assert before == (
            controller._connection_generation,
            controller._recovery_pending_token,
            controller.stop.is_set(),
        )
        opening.assert_not_called()
    finally:
        release.set()
        holder.join(4)
        if worker.ident is not None:
            worker.join(4)
    assert not holder.is_alive() and not worker.is_alive()


@pytest.mark.parametrize("manual", [False, True])
def test_close_after_live_publication_before_open_finalizer_detaches_exact_resources(monkeypatch, manual):
    attempt = Attempt(monkeypatch, "publication")
    controller = attempt.controller
    original = controller._open_owned
    published = threading.Event()

    def pause_before_finalizer(*args):
        result = original(*args)
        assert result is True
        published.set()
        attempt.block("publication")
        return result

    monkeypatch.setattr(controller, "_open_owned", pause_before_finalizer)
    try:
        attempt.start()
        assert published.is_set()
        assert attempt.receiver_started.wait(1)
        assert not attempt.receiver_errors
        assert controller.stream is attempt.transport
        assert controller._connecting and not controller.stop.is_set()
        generation = controller._connection_generation
        (controller.close_manual if manual else controller.close)()
        assert controller._connection_generation == generation + 1
        assert controller.stream is None and controller.thread is None
        assert controller.stop.is_set() and not controller.comms.ready
        assert controller._connecting
        assert attempt.transport.close_calls == 1
        assert_observations_complete_before_release(controller)
        # The older open finalizer may only release its gate/owner. It must not
        # reinstall its closed transport, clear stop, or make comms ready again.
    finally:
        attempt.cleanup()
    assert attempt.result == [True]
    assert controller.stream is None and controller.thread is None
    assert controller.stop.is_set() and not controller.comms.ready
    assert not controller._connecting


def test_open_signals_recovery_cancellation_before_waiting_for_observation_lock(monkeypatch):
    controller = Controller(CNC(), None)
    opening = Mock(return_value=False)
    monkeypatch.setattr(controller, "_open_owned", opening)
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    result = []

    def current_write():
        with controller._adaptive_lock:
            entered.set()
            assert release.wait(3)

    def request_open():
        result.append(controller.open(CONN_WIFI, "test.invalid"))
        finished.set()

    holder = threading.Thread(target=current_write, daemon=True)
    worker = threading.Thread(target=request_open, daemon=True)
    holder.start()
    try:
        assert entered.wait(1)
        worker.start()
        assert controller._recovery_cancel_event.wait(1)
        assert not finished.is_set()
        # Immediate recovery cancellation is distinct from admitted connection
        # stop/generation invalidation, which awaits the existing write.
        assert not controller.stop.is_set()
        assert controller._connection_generation == 0
    finally:
        release.set()
        holder.join(4)
        if worker.ident is not None:
            worker.join(4)
    assert not holder.is_alive() and not worker.is_alive()
    assert result == [False] and controller._recovery_external_requests == 0


def test_detached_close_cannot_reopen_reusable_transport_before_cleanup(monkeypatch, tmp_path):
    attempt = Attempt(monkeypatch, "none")
    controller = attempt.controller
    assert controller.open(CONN_WIFI, "test.invalid") is True
    assert attempt.receiver_started.wait(1)
    assert not attempt.receiver_errors
    attempt.stage = "closing"
    close_finished = threading.Event()
    closer = threading.Thread(target=lambda: (controller.close_manual(), close_finished.set()), daemon=True)
    closer.start()
    try:
        assert attempt.entered.wait(1)
        assert controller._closing and controller.stream is None
        assert_observations_complete_before_release(controller)
        opens = attempt.transport.open_calls
        assert controller.open(CONN_WIFI, "replacement.invalid") is False
        assert attempt.transport.open_calls == opens
        with pytest.raises(ValueError, match="disconnected"):
            replay_jsonl(tmp_path / "must-not-be-read.jsonl")
        assert not close_finished.is_set()
    finally:
        attempt.release.set()
        closer.join(4)
    assert not closer.is_alive() and close_finished.is_set()
    assert not controller._closing and controller.stream is None
    assert controller.stop.is_set() and not controller.comms.ready
    assert all(not thread.is_alive() for thread in controller._receive_threads)
    assert not attempt.receiver_errors


def test_prior_receiver_must_exit_before_same_transport_object_can_reopen(monkeypatch, tmp_path):
    attempt = Attempt(monkeypatch, "none")
    controller = attempt.controller
    old_entered, release_old = threading.Event(), threading.Event()
    old_closed, open_finished = threading.Event(), threading.Event()
    old_errors, result = [], []
    close_transport = attempt.transport.close

    def old_receiver():
        old_entered.set()
        try:
            assert release_old.wait(4)
        except BaseException as error:
            old_errors.append(error)

    def close_old_transport():
        close_transport()
        old_closed.set()

    def reopen():
        try:
            result.append(controller.open(CONN_WIFI, "replacement.invalid"))
        except BaseException as error:
            result.append(error)
        finally:
            open_finished.set()

    old_thread = threading.Thread(target=old_receiver, daemon=True)
    controller.stream = attempt.transport
    controller.thread = old_thread
    controller._receive_threads.add(old_thread)
    monkeypatch.setattr(attempt.transport, "close", close_old_transport)
    old_thread.start()
    worker = threading.Thread(target=reopen, daemon=True)
    try:
        assert old_entered.wait(1)
        worker.start()
        assert old_closed.wait(1), "teardown must close old transport before joining receiver"
        assert_observations_complete_before_release(controller)
        assert attempt.transport.open_calls == 0
        assert open_finished.wait(2), "old receiver join exceeded its existing bounded budget"
        worker.join(1)
        assert result == [False]
        assert old_thread.is_alive() and controller.stop.is_set()
        assert controller.stream is None and controller.thread is None
        assert controller.open(CONN_WIFI, "still-retired.invalid") is False
        assert attempt.transport.open_calls == 0
        with pytest.raises(ValueError, match="disconnected"):
            replay_jsonl(tmp_path / "must-not-be-read.jsonl")
        release_old.set()
        old_thread.join(1)
        assert not old_thread.is_alive() and not old_errors
        assert controller.open(CONN_WIFI, "replacement.invalid") is True
        assert attempt.transport.open_calls == 1
        assert attempt.receiver_started.wait(1)
        assert not attempt.receiver_errors
    finally:
        release_old.set()
        old_thread.join(2)
        if worker.ident is not None:
            worker.join(3)
        controller.close_manual()
    assert not old_thread.is_alive() and not worker.is_alive()
    assert all(not thread.is_alive() for thread in controller._receive_threads)
    assert not old_errors and not attempt.receiver_errors


def test_baud_admission_rechecks_closing_after_outer_stream_check(monkeypatch):
    attempt = Attempt(monkeypatch, "closing")
    controller = attempt.controller
    controller.connection_type = CONN_USB
    controller.stream = attempt.transport
    reopen = Mock(return_value=True)
    monkeypatch.setattr(attempt.transport, "reopen_at_baud", reopen, raising=False)
    pause = Mock(wraps=controller.pauseStream)
    monkeypatch.setattr(controller, "pauseStream", pause)
    admission_entered, continue_admission = threading.Event(), threading.Event()
    baud_finished, close_finished = threading.Event(), threading.Event()
    result, errors = [], []
    original_lock = controller._adaptive_lock

    class AdmissionLock:
        gated = False

        def __getattr__(self, name):
            return getattr(original_lock, name)

        def __enter__(self):
            if threading.current_thread().name == "test-baud-admission" and not self.gated:
                self.gated = True
                admission_entered.set()
                assert continue_admission.wait(3)
            original_lock.acquire()
            return self

        def __exit__(self, *_args):
            original_lock.release()

    monkeypatch.setattr(controller, "_adaptive_lock", AdmissionLock())

    def baud_change():
        try:
            result.append(controller.request_baud_upgrade(230400))
        except BaseException as error:
            errors.append(error)
        finally:
            baud_finished.set()

    baud_worker = threading.Thread(target=baud_change, name="test-baud-admission", daemon=True)
    close_worker = threading.Thread(target=lambda: (controller.close_manual(), close_finished.set()), daemon=True)
    baud_worker.start()
    try:
        assert admission_entered.wait(1), "baud worker did not pass its outer live-USB check"
        close_worker.start()
        assert attempt.entered.wait(1)
        assert controller._closing and controller.stream is None
        continue_admission.set()
        assert baud_finished.wait(1)
        assert result == [False] and not errors
        pause.assert_not_called()
        reopen.assert_not_called()
        assert not controller._baud_switch_in_progress
        assert attempt.transport.wire == []
        assert_observations_complete_before_release(controller)
    finally:
        continue_admission.set()
        attempt.release.set()
        baud_worker.join(4)
        if close_worker.ident is not None:
            close_worker.join(4)
    assert not baud_worker.is_alive() and not close_worker.is_alive()
    assert close_finished.is_set() and not controller._closing


def test_transfer_pause_and_resume_do_not_mutate_closing_connection(monkeypatch):
    controller = Controller(CNC(), None)
    controller._closing = True
    with pytest.raises(ConnectionError, match="closing"):
        controller.pauseStream()
    assert not controller.paused and not controller.pausing
    controller.paused = True
    controller.pausing = True
    controller._stream_io_parked = True
    controller.resumeStream()
    assert controller.paused and controller.pausing and controller._stream_io_parked
    assert controller._status_reacquire_started_at is None
