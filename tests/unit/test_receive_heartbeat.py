import threading
from unittest.mock import Mock

import pytest
from carvera_sim.machine import SimulatedMachine

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller


def test_heartbeat_tracks_valid_receive_time_not_ui_or_wall_clock(monkeypatch):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller._connection_started_at = 10
    assert controller.machine_response_age(13) == 3
    monkeypatch.setattr(module.time, "monotonic", lambda: 20)
    controller.parseLine(SimulatedMachine().status_line())
    assert controller.machine_response_age(20.25) == pytest.approx(0.25)
    # Neither unrelated output nor a malformed/partial pose refreshes evidence.
    monkeypatch.setattr(module.time, "monotonic", lambda: 30)
    controller.parseLine("ERROR: Failed to query STA Netmask, status: 16688")
    controller.parseLine("<Idle|MPos:1,2,3>")
    assert controller.machine_response_age(30) == 10
    assert controller.machine_response_age(19) == float("inf")
    controller.stream = None
    assert controller.machine_response_age(30) is None


@pytest.mark.parametrize("raises", [False, True])
def test_retired_receiver_cannot_publish_or_reset_replacement_parser(raises):
    controller = Controller(CNC(), lambda _: None)
    entered, release = threading.Event(), threading.Event()
    old_stream = Mock()
    old_stream.waiting_for_recv.return_value = True

    def receive():
        entered.set()
        assert release.wait(3)
        if raises:
            raise OSError("old socket closed")
        return b"<Idle|MPos:1,2,3|WPos:1,2,3>\n"

    old_stream.recv.side_effect = receive
    controller.stream = old_stream
    controller.comms = Mock(ready=False)
    controller._connection_generation = 1
    controller._last_status_received_at = 20
    worker = threading.Thread(target=controller.streamIO, args=(1,))
    worker.start()
    try:
        assert entered.wait(2)
        with controller._adaptive_lock:
            controller._connection_generation = 2
            controller.stream = Mock()
            controller._last_status_received_at = 50
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert controller._last_status_received_at == 50
    controller.comms.feed.assert_not_called()
    controller.comms.reset_parser.assert_not_called()


def test_open_invalidates_previous_receive_evidence_even_if_connection_fails(monkeypatch):
    controller = Controller(CNC(), lambda _: None)
    controller._last_status_received_at = 20
    controller._connection_started_at = 10
    generation = controller._connection_generation
    monkeypatch.setattr(controller, "_close_existing_connection", lambda: None)
    monkeypatch.setattr(controller.wifi_stream, "open", lambda _: False)
    from carveracontroller.Controller import CONN_WIFI

    assert not controller.open(CONN_WIFI, "192.0.2.10")
    assert controller._connection_generation == generation + 1
    assert controller._last_status_received_at is None
    assert controller._connection_started_at is None


def test_transfer_handoff_is_bounded_idempotent_and_requires_actual_status(monkeypatch):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller._last_status_received_at = 10
    controller.paused = True
    monkeypatch.setattr(module.time, "monotonic", lambda: 30)
    controller.resumeStream()
    assert controller.machine_response_age(30) == 20
    assert controller.status_reacquisition_remaining(30) == 5
    assert controller.status_reacquisition_pending
    assert controller._status_poll_requested
    monkeypatch.setattr(module.time, "monotonic", lambda: 31)
    controller.resumeStream()  # Exception cleanup may resume twice.
    assert controller.status_reacquisition_remaining(31) == 4
    controller.parseLine("ok")
    controller.parseLine("<Idle|MPos:1,2,3>")
    assert controller.status_reacquisition_remaining(31) == 4
    assert controller.status_reacquisition_remaining(35) == 0
    assert controller.status_reacquisition_pending  # Expiry is not readiness.
    assert controller.machine_response_age(35) == 25
    for now in (29, float("nan"), float("inf")):
        assert controller.status_reacquisition_remaining(now) == 0
    controller.parseLine(SimulatedMachine().status_line())
    assert not controller.status_reacquisition_pending
    assert controller.status_reacquisition_remaining(31) == 0
    assert controller.machine_response_age(31.2) == pytest.approx(0.2)


def test_resumed_receiver_polls_immediately_without_waiting_normal_interval(monkeypatch):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller.stream.waiting_for_recv.return_value = False
    controller.comms = Mock(ready=True)
    controller.paused = True
    monkeypatch.setattr(module.time, "time", lambda: 100)
    monkeypatch.setattr(module.time, "monotonic", lambda: 100)
    controller.resumeStream()
    poll = Mock(side_effect=lambda _: controller.stop.set())
    monkeypatch.setattr(controller, "viewStatusReport", poll)
    controller.streamIO()
    poll.assert_called_once_with(True)
    assert not controller._status_poll_requested
    controller.stream.send.assert_not_called()


def test_status_handoff_blocks_motion_but_keeps_queries_and_stop_available(monkeypatch):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller.paused = True
    monkeypatch.setattr(module.time, "monotonic", lambda: 100)
    controller.resumeStream()
    for command in ("G0 X10", "M6 T2", "resume", "play /sd/job.nc", b"$J X1", "diagnose\nG0 X1"):
        assert controller.executeCommand(command) is False
    controller.cyclestartCommand()
    controller.toggleFeedholdCommand(True)
    controller.jog("X1")
    controller.jog_mode = controller.JOG_MODE_CONTINUOUS
    controller.startContinuousJog("X")
    assert not controller.continuous_jog_active
    controller.stream.send.assert_not_called()
    controller.executeCommand("diagnose")
    controller.feedholdCommand()
    controller.estopCommand()
    assert controller.stream.send.call_count == 3
    controller.stream.send.reset_mock()
    controller.parseLine(SimulatedMachine().status_line())
    controller.executeCommand("G0 X1")
    controller.stream.send.assert_called_once()


def test_failed_reconnect_clears_transfer_transition(monkeypatch):
    from carveracontroller.Controller import CONN_WIFI

    controller = Controller(CNC(), lambda _: None)
    controller._status_reacquire_started_at = 10
    controller._status_reacquire_deadline = 15
    controller._status_poll_requested = True
    monkeypatch.setattr(controller, "_close_existing_connection", lambda: None)
    monkeypatch.setattr(controller.wifi_stream, "open", lambda _: False)
    assert not controller.open(CONN_WIFI, "192.0.2.10")
    assert controller._status_reacquire_started_at is None
    assert controller._status_reacquire_deadline is None
    assert not controller._status_poll_requested
