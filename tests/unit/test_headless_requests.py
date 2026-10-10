import base64
import hashlib
import json
import math
import select
import socket
import subprocess
import sys
import threading
import time
from unittest.mock import Mock

import pytest

from carveracontroller.headless.arguments import command_line, deadline, read_only_flag
from carveracontroller.headless.link import CarveraLink
from carveracontroller.headless.requests import MAX_REQUEST, decode_request, validate_parameters


@pytest.mark.parametrize(
    "raw",
    [
        b'{"id":"one","id":"two","method":"snapshot"}\n',
        b'{"id":"one","method":"snapshot","method":"connect"}\n',
        b'{"id":"one","method":"command","params":{"command":"M105","command":"M3"}}\n',
        b'{"id":"one","method":"compile","params":{"operation":"spindle.set","parameters":{"rpm":1,"rpm":2}}}\n',
        b'{"id":"one","method":"compile","params":{"parameters":{"nested":[{"X":1,"X":2}]}}}\n',
        b'{"id":"one","method":"snapshot","params":{"value":NaN}}\n',
        b'{"id":"one","method":"snapshot","params":{"value":Infinity}}\n',
        b'{"id":"one","method":"snapshot","params":{"value":-Infinity}}\n',
        b'{"id":"one","method":"snapshot","params":{"value":1e999}}\n',
        b'{"id":"one","method":"snapshot","params":{"value":-1e999}}\n',
        b'{"id":"one","method":[],"params":{}}\n',
        b'{"id":"one","method":"snapshot","params":null}\n',
        b'{"id":"one","method":"snapshot","extra":true}\n',
        b'{"id":"one","method":"snapshot"}',
        b"\xff\n",
        b"[]\n",
    ],
)
def test_ambiguous_or_nonfinite_envelopes_are_refused(raw):
    with pytest.raises((ValueError, UnicodeError)):
        decode_request(raw)


def test_request_size_and_nesting_are_bounded_and_missing_params_normalize_only_to_empty_object():
    with pytest.raises(ValueError):
        decode_request(b" " * MAX_REQUEST + b"\n")
    with pytest.raises(ValueError):
        decode_request(b'{"id":"one","method":"snapshot","params":{"v":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}}\n")
    assert decode_request(b'{"id":"one","method":"snapshot"}\n') == {"id": "one", "method": "snapshot", "params": {}}
    request = decode_request(
        b'{"id":"one","method":"command","params":{"command":"M105","timeout":0.25,"read_only":true}}\n'
    )
    validate_parameters(request["method"], request["params"])
    assert request["params"] == {"command": "M105", "timeout": 0.25, "read_only": True}


@pytest.mark.parametrize("value", [True, False, "10", None, -1, 0, 301, math.nan, math.inf, -math.inf, 10**1000])
def test_wire_deadlines_refuse_coercion_and_nonfinite_values_before_command_or_transfer_ownership(value):
    link = CarveraLink("127.0.0.1", poll=False)
    link.socket = Mock()
    before = link.snapshot()
    with pytest.raises(ValueError):
        link.command("M105", timeout=value)
    with pytest.raises(ValueError):
        link.transfer("upload", "/sd/gcodes/test.nc", b"G0 X1\n", timeout=value)
    link.socket.sendall.assert_not_called()
    assert link.snapshot()["transport_health"] == before["transport_health"]
    assert link._pending is None and link._transfer is False and link._unknown is False


@pytest.mark.parametrize("value", [0, 1, "false", "true", None, {}, []])
def test_read_only_classification_cannot_be_coerced_before_wire_dispatch(value):
    link = CarveraLink("127.0.0.1", poll=False)
    link.socket = Mock()
    with pytest.raises(ValueError):
        link.command("M105", read_only=value)
    link.socket.sendall.assert_not_called()
    assert link._pending is None and link._unknown is False


@pytest.mark.parametrize(
    "method,params",
    [
        ("command", {}),
        ("command", {"command": "M105", "timeout": True}),
        ("command", {"command": "M105", "read_only": "false"}),
        ("command", {"command": "M105", "extra": 0}),
        ("command", {"command": "M105\nM3"}),
        ("command", {"command": "M105\u00e9"}),
        ("snapshot", {"connect": True}),
        ("cancel_transfer", {"path": "/sd/gcodes/test.nc"}),
        ("realtime", {"action": ["feed_hold"]}),
        ("realtime", {"action": "shell"}),
        ("upload", {"path": "/sd/gcodes/test.nc", "timeout": False}),
        ("upload", {"path": "/etc/passwd"}),
        ("download", {"path": "/sd/gcodes/test.nc", "data_base64": "QQ=="}),
        ("compile", {"operation": [], "parameters": {}}),
        ("operation", {"operation": "machine.home", "parameters": [], "extra": 0}),
        ("reconcile", {"connection_id": True}),
        ("reconcile", {"connection_id": ""}),
        ("probe_profile_apply", {"schema_version": "anything"}),
    ],
)
def test_closed_method_contracts_refuse_invalid_parameters(method, params):
    with pytest.raises(ValueError):
        validate_parameters(method, params)


def test_shared_validation_preserves_legitimate_wire_arguments_without_coercion():
    for value in (0.001, 10, 300):
        deadline(value)
    for value in (True, False):
        read_only_flag(value)
    command_line("M105")
    for method, params in (
        ("snapshot", {}),
        ("command", {"command": "M105", "timeout": 0.2, "read_only": True}),
        ("realtime", {"action": "feed_hold"}),
        ("upload", {"path": "/sd/gcodes/test.nc", "data_base64": "QQ=="}),
        ("download", {"path": "/sd/gcodes/test.nc", "data_base64": ""}),
        ("compile", {"operation": "machine.home", "parameters": {}}),
        ("reconcile", {"connection_id": "current-connection_1"}),
    ):
        before = json.dumps(params, sort_keys=True)
        validate_parameters(method, params)
        assert json.dumps(params, sort_keys=True) == before


@pytest.fixture
def private_child():
    process = subprocess.Popen(
        [sys.executable, "-m", "carveracontroller.headless", "--host", "127.0.0.1"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def receive():
        assert select.select([process.stdout], [], [], 5)[0], "Private child did not return a record"
        return json.loads(process.stdout.readline())

    assert receive()["event"] == "ready"
    try:
        yield process, receive
    finally:
        process.stdin.close()
        process.stdin = None
        process.communicate(timeout=5)
        assert process.returncode == 0


@pytest.mark.parametrize(
    "method,params",
    [
        ("command", {"command": "M105", "timeout": True}),
        ("command", {"command": "M105", "read_only": "false"}),
        ("download", {"path": "/sd/gcodes/test.nc", "data_base64": "QQ=="}),
        ("realtime", {"action": "unsupported"}),
        ("operation", {"operation": [], "parameters": {}}),
    ],
)
def test_actual_private_child_refuses_bad_arguments_then_still_services_observers(private_child, method, params):
    process, receive = private_child
    process.stdin.write(json.dumps({"id": "bad", "method": method, "params": params}) + "\n")
    process.stdin.flush()
    assert receive() == {"id": "bad", "ok": False, "error": "ValueError"}
    process.stdin.write('{"id":"observer","method":"snapshot"}\n')
    process.stdin.flush()
    response = receive()
    assert response["id"] == "observer" and response["ok"] is True
    result = response["result"]
    assert result["connected"] is False and result["connection_id"] is None
    assert result["unknown_outcome"] is False and result["transport_health"]["total_commands"] == 0


@pytest.mark.parametrize(
    "raw",
    [
        '{"id":"ambiguous","method":"compile","params":{"operation":"spindle.set","parameters":{"rpm":1,"rpm":2}}}\n',
        '{"id":"ambiguous","method":"snapshot","method":"connect"}\n',
        '{"id":"ambiguous","method":"compile","params":{"operation":"accessory.light","parameters":{"enabled":false,"enabled":true}}}\n',
        '{"id":"ambiguous","method":"snapshot","params":{"value":1e999}}\n',
    ],
)
def test_actual_private_child_terminates_on_ambiguous_envelope_without_compiling_or_dispatching(private_child, raw):
    process, receive = private_child
    process.stdin.write(raw)
    process.stdin.flush()
    assert receive() == {"event": "protocol_error", "error": "invalid_request"}
    process.wait(timeout=5)
    assert process.stdout.read() == ""


@pytest.mark.parametrize("completion", ["acknowledged", "protocol_refusal"])
def test_actual_rpc_rejects_bad_parameters_services_urgent_requests_and_preserves_pending_receipt(completion):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    started, held, release_ack, stop = (threading.Event() for _ in range(4))
    errors, wire = [], []

    def serve():
        try:
            sock, _ = listener.accept()
            with sock:
                sock.settimeout(0.1)
                buffer, awaiting_ack = bytearray(), False
                while not stop.is_set():
                    if awaiting_ack and release_ack.is_set():
                        sock.sendall(b"ok\n")
                        awaiting_ack = False
                    try:
                        char = sock.recv(1)
                    except socket.timeout:
                        continue
                    if not char:
                        break
                    if char == b"?":
                        sock.sendall(b"<Idle|MPos:0,0,0|WPos:0,0,0|S:0,0,100>\n")
                    elif char == b"!":
                        held.set()
                        wire.append(b"!")
                    else:
                        buffer.extend(char)
                        if char == b"\n":
                            wire.append(bytes(buffer))
                            if bytes(buffer) == b"M821\n":
                                awaiting_ack = True
                                started.set()
                            elif bytes(buffer) == b"M105\n":
                                sock.sendall(b"ok\n")
                            buffer.clear()
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "carveracontroller.headless",
            "--host",
            "127.0.0.1",
            "--port",
            str(listener.getsockname()[1]),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    responses, events = {}, []

    def send(request_id, method, params=None):
        process.stdin.write((json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n").encode())

    def response(request_id):
        end = time.monotonic() + 5
        while request_id not in responses:
            remaining = end - time.monotonic()
            assert remaining > 0 and select.select([process.stdout], [], [], remaining)[0], "RPC response timed out"
            value = json.loads(process.stdout.readline())
            if "id" in value:
                responses[value["id"]] = value
            else:
                events.append(value)
        return responses[request_id]

    try:
        send("connect", "connect")
        assert response("connect")["result"]["connected"] is True
        send("pending", "command", {"command": "M821", "timeout": 10})
        assert started.wait(5)
        send("bad", "command", {"command": "M7", "timeout": True})
        assert response("bad") == {"id": "bad", "ok": False, "error": "ValueError"}
        assert "pending" not in responses and not release_ack.is_set()
        send("hold", "realtime", {"action": "feed_hold"})
        assert response("hold")["result"]["outcome"] == "sent_unacknowledged"
        assert held.wait(5)
        send("observer", "snapshot")
        assert response("observer")["result"]["connected"] is True
        assert "pending" not in responses and not release_ack.is_set()
        assert b"M7\n" not in wire
        if completion == "acknowledged":
            release_ack.set()
            result = response("pending")["result"]
            assert result["outcome"] == "controller_acknowledged"
        else:
            process.stdin.write(b'{"id":"ambiguous","method":"snapshot","method":"connect"}\n')
            returned = response("pending")
            assert returned["ok"] is False and returned["error"] == "unknown_outcome"
            assert {"event": "protocol_error", "error": "invalid_request"} in events
            result = returned["receipt"]
            assert result["outcome"] == "unknown_outcome" and not release_ack.is_set()
            assert result["host_timing"]["acknowledged_at_s"] is None
        assert result["motion_completed"] is False
        evidence = result["controller_receive_evidence"]
        assert evidence["original_bytes_retained"] is True and evidence["delivery_verified"] is False
        received = base64.b64decode(evidence["original_bytes_base64"], validate=True)
        assert evidence["byte_count"] == len(received)
        if completion == "acknowledged":
            assert b"ok\n" in received
        else:
            assert b"ok\n" not in received
        assert evidence["sha256"] == hashlib.sha256(received).hexdigest()
        assert wire.count(b"M821\n") == 1 and wire.count(b"!") == 1 and b"M7\n" not in wire
    finally:
        stop.set()
        process.stdin.close()
        process.stdin = None
        process.communicate(timeout=5)
        listener.close()
        worker.join(5)
        assert not worker.is_alive() and not errors, errors
        assert process.returncode == 0
