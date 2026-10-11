import base64
import hashlib
import json
import socket
import sys
import threading
import time

import pytest

from carveracontroller.headless.client import ClientBusy, ClientUnavailable, SupervisorClient, child_arguments


@pytest.mark.parametrize("completion", ["acknowledged", "disconnected"])
def test_actual_client_pending_command_hold_snapshot_and_original_backend_receipt(completion):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(5)
    started, held, release, stop = (threading.Event() for _ in range(4))
    wire, errors = [], []

    def serve():
        try:
            sock, _ = listener.accept()
            with sock:
                sock.settimeout(0.05)
                buffer, pending = bytearray(), False
                while not stop.is_set():
                    if pending and release.is_set():
                        if completion == "disconnected":
                            return
                        sock.sendall(b"ok\n")
                        pending = False
                    try:
                        char = sock.recv(1)
                    except socket.timeout:
                        continue
                    if not char:
                        return
                    if char == b"?":
                        sock.sendall(b"<Idle|MPos:0,0,0|WPos:0,0,0|S:0,0,100>\n")
                    elif char == b"!":
                        wire.append(char)
                        held.set()
                    else:
                        buffer.extend(char)
                        if char == b"\n":
                            wire.append(bytes(buffer))
                            if buffer == b"M821\n":
                                pending = True
                                started.set()
                            elif buffer == b"M105\n":
                                sock.sendall(b"ok\n")
                            buffer.clear()
        except BaseException as error:
            errors.append(error)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()
    client = SupervisorClient("127.0.0.1", listener.getsockname()[1])
    try:
        client.start()
        state = client.submit("connect").result(timeout=5).envelope["result"]
        assert state["connected"] is True and state["connection_id"]
        command = client.submit("command", {"command": "M821", "timeout": 10})
        assert started.wait(5) and not command.done()
        held_response = client.submit("realtime", {"action": "feed_hold"}).result(timeout=5)
        assert held_response.envelope["result"]["outcome"] == "sent_unacknowledged"
        assert held.wait(5) and not command.done()
        assert client.submit("snapshot").result(timeout=5).envelope["result"]["connected"] is True
        assert not command.done()
        release.set()
        response = command.result(timeout=5)
        envelope = response.envelope
        if completion == "acknowledged":
            assert envelope["ok"] is True
            receipt = envelope["result"]
            assert receipt["outcome"] == "controller_acknowledged"
        else:
            assert envelope["ok"] is False and envelope["error"] == "unknown_outcome"
            receipt = envelope["receipt"]
            assert receipt["outcome"] == "unknown_outcome"
            assert client.submit("snapshot").result(timeout=5).envelope["result"]["unknown_outcome"] is True
        assert receipt["motion_completed"] is False
        evidence = receipt["controller_receive_evidence"]
        raw = base64.b64decode(evidence["original_bytes_base64"], validate=True)
        assert evidence["original_bytes_retained"] is True
        assert evidence["byte_count"] == len(raw) and evidence["sha256"] == hashlib.sha256(raw).hexdigest()
        assert (b"ok\n" in raw) == (completion == "acknowledged")
        assert wire.count(b"M821\n") == wire.count(b"!") == 1
        assert response.request_sha256 and response.response_sha256 and response.elapsed_ms >= 0
    finally:
        stop.set()
        client.close()
        listener.close()
        worker.join(5)
        assert not worker.is_alive() and not errors, errors
        assert not any(thread.is_alive() for thread in client._threads)


@pytest.fixture
def real_client():
    client = SupervisorClient("127.0.0.1")
    client.start()
    try:
        yield client
    finally:
        client.close()
        assert client._process.poll() is not None
        assert not any(worker.is_alive() for worker in client._threads)


def test_actual_application_entry_point_starts_private_child_and_returns_detached_offline_state(real_client):
    client = real_client
    assert client.snapshot()["ready"] is True and client.snapshot()["pending_requests"] == 0
    response = client.submit("snapshot").result(timeout=3)
    assert response.envelope["ok"] is True
    result = response.envelope["result"]
    assert result["connected"] is False and result["connection_id"] is None and result["unknown_outcome"] is False
    assert result["transport_health"]["total_commands"] == 0
    assert len(response.request_sha256) == len(response.response_sha256) == 64
    assert response.elapsed_ms >= 0 and response.received_at_s >= 0
    result["connected"] = True
    view = client.snapshot()
    assert view["last_machine_snapshot"]["connected"] is False
    view["recent_requests"].clear()
    assert len(client.snapshot()["recent_requests"]) == 1
    assert "not CNC acknowledgment" in view["timing_source"]
    catalog = client.submit("catalog").result(timeout=3).envelope["result"]
    assert catalog["schema_version"] == "carvera.operations.v2"
    assert any(row["id"] == "machine.hold" for row in catalog["operations"])
    assert client.submit("compile", {"operation": "accessory.light", "parameters": {"enabled": True}}).result(
        timeout=3
    ).envelope["result"]["commands"] == ["M821"]
    assert client.submit("snapshot").result(timeout=3).envelope["result"]["transport_health"]["total_commands"] == 0


@pytest.mark.parametrize("host,port", [("8.8.8.8", 2222), ("::1", 2222), ("192.168.0.79", 1234), ("127.0.0.1", True)])
def test_invalid_endpoint_is_refused_before_starting_a_child(host, port):
    with pytest.raises(ValueError):
        child_arguments(host, port)


def test_frozen_launcher_uses_the_early_application_entry_point_and_sessions_cannot_restart(real_client):
    assert child_arguments("192.168.0.79", 2222, frozen=True) == [
        sys.executable,
        "--headless-supervisor",
        "--host",
        "192.168.0.79",
        "--port",
        "2222",
    ]
    with pytest.raises(ClientUnavailable):
        real_client.start()
    stopped = SupervisorClient("127.0.0.1")
    stopped.close()
    with pytest.raises(ClientUnavailable):
        stopped.start()


def test_invalid_client_arguments_do_not_create_requests_or_backend_commands(real_client):
    before = real_client.snapshot()["responses_received"]
    for params in (
        {"command": "M105", "timeout": True},
        {"command": "M105", "read_only": "false"},
        {"command": "M105", "timeout": float("nan")},
    ):
        with pytest.raises(ValueError):
            real_client.submit("command", params)
    assert real_client.snapshot()["responses_received"] == before
    assert real_client.snapshot()["pending_requests"] == 0
    assert (
        real_client.submit("snapshot").result(timeout=3).envelope["result"]["transport_health"]["total_commands"] == 0
    )


def stub_client(tmp_path, body):
    journal = tmp_path / "requests.jsonl"
    ready = {
        "event": "ready",
        "runtime_version": "carvera.headless.v1",
        "connection_owned": False,
        "protocol": "smoothie",
    }
    script = (
        "import json,sys\nprint("
        + repr(json.dumps(ready))
        + ",flush=True)\nfor raw in sys.stdin.buffer:\n request=json.loads(raw)\n with open("
        + repr(str(journal))
        + ",'ab') as f:f.write(raw)\n"
        + body
    )
    client = SupervisorClient("127.0.0.1", argv=[sys.executable, "-u", "-c", script])
    client.start()
    return client, journal


def wait_for(predicate):
    end = time.monotonic() + 3
    while not predicate() and time.monotonic() < end:
        time.sleep(0.005)
    assert predicate()


def test_private_process_eof_preserves_submission_ambiguity_and_never_replays(tmp_path):
    client, journal = stub_client(tmp_path, " break\n")
    try:
        with pytest.raises(ClientUnavailable) as error:
            client.submit("command", {"command": "M105"}).result(timeout=3)
        assert error.value.submission == "backend_response_unknown" and error.value.request_id is not None
        with pytest.raises(ClientUnavailable):
            client.submit("command", {"command": "M105"})
        assert len(journal.read_bytes().splitlines()) == 1
        assert client.snapshot()["recent_requests"][-1]["outcome"] == "backend_response_unknown"
    finally:
        client.close()


@pytest.mark.parametrize("fault", ["unknown_identity", "duplicate_key", "nonfinite", "wrong_result", "missing_flags"])
def test_malformed_private_responses_retire_the_session_without_replacing_them_with_success(tmp_path, fault):
    bodies = {
        "unknown_identity": " print(json.dumps({'id':'other','ok':True,'result':{}}),flush=True)\n",
        "duplicate_key": ' print(\'{"id":"\'+request[\'id\']+\'","ok":false,"ok":true,"result":{}}\',flush=True)\n',
        "nonfinite": " print(json.dumps({'id':request['id'],'ok':True,'result':{'value':float('nan')}}),flush=True)\n",
        "wrong_result": " print(json.dumps({'id':request['id'],'ok':True,'result':[]}),flush=True)\n",
        "missing_flags": " print(json.dumps({'id':request['id'],'ok':True,'result':{'connected':False}}),flush=True)\n",
    }
    client, journal = stub_client(tmp_path, bodies[fault])
    try:
        with pytest.raises(ClientUnavailable) as error:
            client.submit("snapshot").result(timeout=3)
        assert error.value.submission == "backend_response_unknown"
        assert client.snapshot()["ready"] is False and client.snapshot()["responses_received"] == 0
        assert len(journal.read_bytes().splitlines()) == 1
    finally:
        client.close()


def test_urgent_capacity_remains_available_when_all_ordinary_requests_are_pending(tmp_path):
    body = " if request['method']=='snapshot':print(json.dumps({'id':request['id'],'ok':True,'result':{'connected':False,'connection_id':None,'unknown_outcome':False,'transfer_active':False}}),flush=True)\n"
    client, journal = stub_client(tmp_path, body)
    try:
        ordinary = [client.submit("command", {"command": "M105"}) for _ in range(16)]
        with pytest.raises(ClientBusy):
            client.submit("command", {"command": "M7"})
        assert client.submit("snapshot").result(timeout=3).envelope["result"]["connected"] is False
        assert all(not future.done() for future in ordinary)
        assert client.snapshot()["pending_requests"] == 16
    finally:
        client.close()
    assert all(future.done() for future in ordinary)


@pytest.mark.parametrize("withdrawal", ["cancel", "close"])
def test_unsent_requests_can_be_withdrawn_and_close_does_not_dispatch_a_queued_command(
    tmp_path, monkeypatch, withdrawal
):
    body = " print(json.dumps({'id':request['id'],'ok':True,'result':{'connected':False,'connection_id':None,'unknown_outcome':False,'transfer_active':False}}),flush=True)\n"
    client, journal = stub_client(tmp_path, body)
    started, release = threading.Event(), threading.Event()
    write = client._process.stdin.write

    def blocked(data):
        started.set()
        assert release.wait(3)
        return write(data)

    monkeypatch.setattr(client._process.stdin, "write", blocked)
    closer = None
    try:
        first = client.submit("snapshot")
        assert started.wait(3)
        queued = client.submit("command", {"command": "M7"})
        if withdrawal == "cancel":
            assert queued.cancel() is True
        else:
            closer = threading.Thread(target=client.close)
            closer.start()
            with pytest.raises(ClientUnavailable) as error:
                queued.result(timeout=3)
            assert error.value.submission == "not_submitted"
        release.set()
        first.result(timeout=3)
        if closer:
            closer.join(5)
            assert not closer.is_alive()
        else:
            wait_for(lambda: client.snapshot()["pending_requests"] == 0)
        sent = [json.loads(line) for line in journal.read_bytes().splitlines()]
        assert [row["method"] for row in sent] == ["snapshot"]
    finally:
        release.set()
        client.close()


def test_future_owns_a_frozen_request_and_snapshot_history_excludes_raw_command_text(tmp_path, monkeypatch):
    client, journal = stub_client(
        tmp_path, " print(json.dumps({'id':request['id'],'ok':True,'result':{'echo':request['params']}}),flush=True)\n"
    )
    try:
        params = {"command": "M105"}
        result = client.submit("command", params)
        params["command"] = "M3"
        assert result.result(timeout=3).envelope["result"]["echo"]["command"] == "M105"
        assert json.loads(journal.read_bytes().splitlines()[0])["params"]["command"] == "M105"
        assert "M105" not in json.dumps(client.snapshot())
    finally:
        client.close()
