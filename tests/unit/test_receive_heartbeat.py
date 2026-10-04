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
