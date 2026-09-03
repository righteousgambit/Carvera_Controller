"""End-to-end check that the simulator speaks the wire protocol.

Drives the server through the controller's own ``MakeraProtocol`` encoder and
receive state machine, so a framing mistake in the simulator shows up here
rather than as a mysterious failure against real hardware.
"""

import socket

import pytest
from carvera_sim.machine import SimulatedMachine
from carvera_sim.server import CarveraSimServer

from carveracontroller.protocols.makera import MakeraProtocol
from carveracontroller.protocols.messages import MessageKind


@pytest.fixture
def server():
    machine = SimulatedMachine()
    srv = CarveraSimServer(machine, port=0)
    srv.start_background()
    yield srv
    srv.stop()


def _exchange(srv, payload, expect_kinds, timeout=3.0):
    """Send ``payload``, return parsed messages of the requested kinds."""
    proto = MakeraProtocol()
    collected = []
    with socket.create_connection(("127.0.0.1", srv.port), timeout=timeout) as sock:
        sock.sendall(payload)
        sock.settimeout(timeout)
        deadline = timeout
        while deadline > 0 and not collected:
            try:
                chunk = sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            for message in proto.feed(chunk):
                if message.kind in expect_kinds:
                    collected.append(message)
            deadline -= 0.1
    return collected


def test_status_request_returns_a_parseable_report(server):
    proto = MakeraProtocol()
    messages = _exchange(server, proto.encode_realtime(ord("?")), {MessageKind.LINE})

    assert messages, "simulator did not answer a status request"
    text = messages[0].text
    assert text.startswith("<") and text.endswith(">")
    assert "|PWM:" in text
    assert "|S:" in text


def test_mdi_command_mutates_machine_state(server):
    proto = MakeraProtocol()
    _exchange(server, proto.encode_command(b"M3 S9000\n"), {MessageKind.LINE}, timeout=1.0)

    server.machine.settle(4.0)

    assert server.machine.spindle_on
    assert server.machine.target_rpm == pytest.approx(9000.0)
    assert server.machine.current_rpm > 0


def test_version_query_answers(server):
    proto = MakeraProtocol()
    messages = _exchange(server, proto.encode_command(b"version\n"), {MessageKind.LINE})

    assert messages
    assert "Simulator" in messages[0].text
