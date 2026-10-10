from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.machine.receive_health import ReceiveHealth


@pytest.mark.parametrize(
    "route,kind,payload",
    [
        ("command", "command", b"M821\n"),
        ("realtime", "realtime", b"!"),
        ("file", "file_initiation", b"upload /sd/gcodes/test.nc\n"),
    ],
)
def test_real_control_write_routes_preserve_wire_and_callbacks_while_observing_host_calls(
    monkeypatch, route, kind, payload
):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    stream = Mock()
    controller.stream = stream
    controller.execCallback = Mock()
    controller.comms.encode_command = lambda data: data
    controller.comms.encode_file_command = lambda data: data
    controller.comms.encode_realtime = lambda char: bytes([char])
    now = [10.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0]))

    def send(data):
        now[0] += 0.025
        return 1  # A normal call return does not establish complete-byte delivery.

    stream.send.side_effect = send
    if route == "command":
        assert controller.executeCommand("M821") is True
        controller.execCallback.assert_called_once_with("M821\n")
    elif route == "realtime":
        controller.executeRealtime(ord("!"))
        controller.execCallback.assert_not_called()
    else:
        controller.executeFileCommand("upload /sd/gcodes/test.nc")
        controller.execCallback.assert_called_once_with("upload /sd/gcodes/test.nc\n")
    stream.send.assert_called_once_with(payload)
    result = controller.receive_diagnostics(11)["current"]["control_writes"]
    assert result["total_calls"] == 1 and result["failed_calls"] == 0
    assert result["last_call_ms"] == pytest.approx(25)
    assert result["recent_calls"][0]["kind"] == kind
    assert result["recent_calls"][0]["requested_bytes"] == len(payload)
    assert result["recent_calls"][0]["call_returned"] is True
    assert result["delivery_verified"] is False and result["acknowledgment_latency_ms"] is None


def test_failed_send_preserves_existing_command_result_and_only_retains_error_class(monkeypatch):
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    controller.stream.send.side_effect = OSError("private diagnostic fixture payload")
    controller.execCallback = Mock()
    assert controller.executeCommand("M821") is False
    controller.execCallback.assert_not_called()
    writes = controller.receive_diagnostics()["current"]["control_writes"]
    assert writes["total_calls"] == writes["failed_calls"] == 1
    assert writes["recent_calls"][0]["error_class"] == "OSError"
    assert "private diagnostic fixture payload" not in str(writes)
    assert writes["delivery_verified"] is False


def test_retired_writer_cannot_contaminate_replacement_connection_health():
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    before = controller._receive_health
    replacement = ReceiveHealth(9, 1)

    def replace(data):
        controller._receive_health = replacement

    controller.stream.send.side_effect = replace
    assert controller.executeCommand("M821") is True
    assert before.snapshot(2)["control_writes"]["total_calls"] == 1
    assert controller.receive_diagnostics(2)["current"]["control_writes"]["total_calls"] == 0
    assert controller.receive_diagnostics(2)["current"]["connection_generation"] == 9


@pytest.mark.parametrize("transport_failure", [False, True])
def test_diagnostic_failure_never_replaces_the_original_transport_outcome(monkeypatch, transport_failure):
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock(return_value=None)
    error = OSError("original synthetic transport failure")
    if transport_failure:
        controller.stream.send.side_effect = error
    monkeypatch.setattr(controller._receive_health, "write", Mock(side_effect=RuntimeError("diagnostic fault")))
    if transport_failure:
        with pytest.raises(OSError) as raised:
            controller._send_observed(b"M821\n", "command")
        assert raised.value is error
    else:
        controller._send_observed(b"M821\n", "command")
    controller.stream.send.assert_called_once_with(b"M821\n")
    assert controller.receive_diagnostics()["current"]["control_writes"]["unavailable_observations"] == 1


def test_unavailable_measurement_clock_cannot_prevent_or_replay_a_control_write(monkeypatch):
    from carveracontroller import Controller as module

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    monotonic = Mock(side_effect=RuntimeError("synthetic measurement clock fault"))
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=monotonic))
    assert controller.executeCommand("M821") is True
    controller.stream.send.assert_called_once()
    writes = controller.receive_diagnostics(11)["current"]["control_writes"]
    assert writes["total_calls"] == 1 and writes["failed_calls"] == 0
    assert writes["last_call_ms"] is None and writes["last_call_age_s"] is None
