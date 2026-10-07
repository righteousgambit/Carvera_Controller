import hashlib
import io
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from carveracontroller.headless.link import CarveraLink, ControllerRejected, LinkUnavailable, OutcomeUnknown
from carveracontroller.headless.ownership import EndpointBusyError, EndpointLock
from carveracontroller.WIFIStream import MachineDetector
from carveracontroller.XMODEM import XMODEM

STATUS = b"<Idle|MPos:-232,-195,-3|WPos:0,0,20|C:1,4,0,1|S:0,12000,100>\n"


@pytest.fixture
def server(tmp_path):
    resources = []

    def start(handler, *, poll=False):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        errors = []

        def serve():
            try:
                sock, _ = listener.accept()
                with sock:
                    sock.settimeout(3)
                    handler(sock)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        link = CarveraLink("127.0.0.1", port, lock_directory=tmp_path / "locks", poll=poll)
        resources.append((link, listener, thread, errors))
        link.connect()
        return link

    yield start
    for link, listener, thread, errors in resources:
        link.close()
        listener.close()
        thread.join(4)
        assert not thread.is_alive(), "server did not stop"
        assert not errors, errors


def line(sock):
    data = bytearray()
    while not data.endswith(b"\n"):
        char = sock.recv(1)
        if not char:
            return bytes(data)
        data.extend(char)
    return bytes(data)


def test_one_command_at_a_time_with_interleaved_status_and_full_wire_receipts(server):
    wire = []

    def handle(sock):
        for _ in range(2):
            wire.append(line(sock))
            sock.sendall(STATUS + b"ok\n")

    link = server(handle)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(link.command, ("M821", "M7")))
    assert sorted(wire) == [b"M7\n", b"M821\n"]
    assert all(receipt["outcome"] == "controller_acknowledged" for receipt in results)
    assert all(receipt["motion_completed"] is False for receipt in results)
    assert link.snapshot()["status"]["machine_position"]["x"] == -232


def test_shell_query_uses_a_readonly_acknowledgement_barrier(server):
    def handle(sock):
        assert line(sock) == b"diagnose\n"
        assert line(sock) == b"M105\n"
        sock.sendall(b"{G:1|P:0,0|E:0,0,0,0,0,1|I:0}\nok T:0\n")

    link = server(handle)
    receipt = link.command("diagnose", read_only=True)
    assert receipt["wire_commands"] == ["diagnose", "M105"]
    assert link.snapshot()["diagnostics"]["light_on"] is True


def test_disconnect_after_delivery_latches_unknown_and_never_replays(server):
    wire = []

    def handle(sock):
        wire.append(line(sock))

    link = server(handle)
    with pytest.raises(OutcomeUnknown):
        link.command("G1 X1 F100")
    assert link.snapshot()["unknown_outcome"] is True
    with pytest.raises(LinkUnavailable):
        link.command("G1 X1 F100")
    assert wire == [b"G1 X1 F100\n"]


def test_reconciliation_only_clears_local_latch_on_exact_fresh_idle_connection(server):
    wire = []
    received_close = threading.Event()

    def handle(sock):
        sock.sendall(b"ok\n<Idle|MPos:0,0,-3|C:1,4,0,1|S:0,0,100|P:0,0,0,0>\n{S:0|G:1|P:0,0|I:0|E:0,0,0,0,0,1}\n")
        wire.append(sock.recv(100))
        received_close.set()

    link = server(handle)
    link.wait_for_observation("diagnostics")
    assert link.snapshot()["unknown_outcome"] is True
    with pytest.raises(LinkUnavailable):
        link.acknowledge_unknown_outcome("old-connection")
    result = link.acknowledge_unknown_outcome(link.connection_id)
    assert result["original_command_replayed"] is False
    assert link.snapshot()["unknown_outcome"] is False
    link.close()
    assert received_close.wait(2), "server did not observe connection closure"
    assert wire == [b""]


def test_hold_can_interrupt_a_pending_command_without_claiming_a_stop(server):
    accepted = threading.Event()

    def handle(sock):
        assert line(sock) == b"G1 X1 F100\n"
        accepted.set()
        assert sock.recv(1) == b"!"
        sock.sendall(b"ok\n")

    link = server(handle)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(link.command, "G1 X1 F100")
        assert accepted.wait(2)
        assert link.realtime("feed_hold")["outcome"] == "sent_unacknowledged"
        assert future.result(timeout=2)["outcome"] == "controller_acknowledged"


def test_error_does_not_steal_the_next_commands_acknowledgement(server):
    def handle(sock):
        assert line(sock) == b"M6 T9\n"
        sock.sendall(b"ERROR: tool absent\nok\n")
        assert line(sock) == b"M821\n"
        sock.sendall(b"ok\n")

    link = server(handle)
    with pytest.raises(ControllerRejected) as error:
        link.command("M6 T9")
    assert error.value.receipt["lines"] == ["ERROR: tool absent", "ok"]
    assert link.command("M821")["lines"] == ["ok"]


def test_oversized_response_and_forged_readonly_commands_fail_closed(server):
    def handle(sock):
        assert line(sock) == b"M821\n"
        sock.sendall(b"x" * 9000)

    link = server(handle)
    with pytest.raises(ValueError):
        link.command("M3 S12000", read_only=True)
    with pytest.raises(ValueError):
        link.command("M821\nM3 S12000")
    with pytest.raises(OutcomeUnknown):
        link.command("M821")


def test_transfer_excludes_observation_bytes_and_requires_firmware_completion(server):
    data = b"G21\nG90\nM5\n" * 900
    received = io.BytesIO()

    def handle(sock):
        assert line(sock) == b"upload /sd/gcodes/acceptance.nc\n"

        def getc(size, timeout=0.5):
            sock.settimeout(timeout)
            output = bytearray()
            try:
                while len(output) < size:
                    output.extend(sock.recv(size - len(output)))
            except socket.timeout:
                return None
            return bytes(output)

        def putc(payload, timeout=0.5):
            sock.sendall(payload)
            return len(payload)

        modem = XMODEM(getc, putc, "xmodem8k")
        assert modem.recv_legacy(received, timeout=1) >= len(data)
        assert received.getvalue() == data
        sock.sendall(b"Info: upload success: /sd/gcodes/acceptance.nc.\r\n")

    link = server(handle, poll=True)
    result = link.transfer("upload", "/sd/gcodes/acceptance.nc", data)
    assert received.getvalue() == data
    assert result["sha256"] == hashlib.sha256(data).hexdigest()
    assert result["readback_verified"] is False


def test_endpoint_ownership_releases_only_when_the_owner_closes(tmp_path):
    first = EndpointLock("192.168.0.79", 2222, tmp_path / "locks")
    second = EndpointLock("192.168.0.79", 2222, tmp_path / "locks")
    first.acquire()
    try:
        with pytest.raises(EndpointBusyError):
            second.acquire()
    finally:
        first.release()
    second.acquire()
    second.release()


def test_gui_discovery_does_not_open_a_competing_socket(tmp_path, monkeypatch):
    directory = tmp_path / "locks"
    first = EndpointLock("192.168.0.79", 2222, directory)
    first.acquire()
    monkeypatch.setattr(
        "carveracontroller.WIFIStream.EndpointLock", lambda host, port: EndpointLock(host, port, directory)
    )

    def forbidden_connect(*args, **kwargs):
        raise AssertionError("Discovery must not connect while headless owns the endpoint")

    monkeypatch.setattr(socket, "create_connection", forbidden_connect)
    try:
        assert MachineDetector().is_machine_busy("192.168.0.79") is True
    finally:
        first.release()


def test_original_receive_bytes_precede_line_normalization_and_include_status(server):
    import base64

    original = STATUS + b"  X Diameter is: 12.000\r\n\r\n ok \r\n"

    def handle(sock):
        assert line(sock) == b"M461 D3\n"
        sock.sendall(original)
        assert sock.recv(1) == b""

    link = server(handle)
    receipt = link.command("M461 D3")
    evidence = receipt["controller_receive_evidence"]
    assert base64.b64decode(evidence["original_bytes_base64"]) == original
    assert evidence["sha256"] == hashlib.sha256(original).hexdigest()
    assert evidence["byte_count"] == len(original)
    assert receipt["lines"] == ["X Diameter is: 12.000", "ok"]
    assert evidence["connection_id"] == receipt["connection_id"]
    assert evidence["sendall_completed"] is True
    assert evidence["planned_command_bytes_base64"] == base64.b64encode(b"M461 D3\n").decode()
    assert evidence["may_include_interleaved_or_unattributed_bytes"] is True
    assert evidence["firmware_identity_verified"] is False
    link.close()


@pytest.mark.parametrize("disconnect", [False, True])
def test_unknown_outcome_preserves_partial_original_bytes_without_resend(server, disconnect):
    import base64

    original = b"  Final Positon Z: 1.00"
    wire = []

    def handle(sock):
        wire.append(line(sock))
        sock.sendall(original)
        if not disconnect:
            assert sock.recv(1) == b""

    link = server(handle)
    with pytest.raises(OutcomeUnknown) as error:
        link.command("M466 Z-5", timeout=0.2)
    receipt = error.value.receipt
    assert receipt["outcome"] == "unknown_outcome"
    assert receipt["lines"] == []
    evidence = receipt["controller_receive_evidence"]
    assert base64.b64decode(evidence["original_bytes_base64"]) == original
    assert evidence["sha256"] == hashlib.sha256(original).hexdigest()
    assert evidence["complete_controller_response_verified"] is False
    with pytest.raises(LinkUnavailable):
        link.command("M466 Z-5")
    assert wire == [b"M466 Z-5\n"]


def test_receive_window_is_retained_even_when_parser_refuses_oversized_line(server):
    import base64

    original = b"x" * 8193

    def handle(sock):
        assert line(sock) == b"M821\n"
        sock.sendall(original)
        assert sock.recv(1) == b""

    link = server(handle)
    with pytest.raises(OutcomeUnknown) as error:
        link.command("M821")
    evidence = error.value.receipt["controller_receive_evidence"]
    assert base64.b64decode(evidence["original_bytes_base64"]) == original
    assert evidence["sha256"] == hashlib.sha256(original).hexdigest()


def test_receive_budget_never_returns_a_truncated_original():
    import base64

    from carveracontroller.headless.wire_evidence import MAX_RECEIVE_WINDOW, ReceiveWindow

    window = ReceiveWindow()
    exact = b"x" * MAX_RECEIVE_WINDOW
    window.append(exact)
    assert base64.b64decode(window.evidence("c", b"M821\n", False)["original_bytes_base64"]) == exact
    window.append(b"tail")
    evidence = window.evidence("c", b"M821\n", False)
    assert evidence["original_bytes_base64"] is None
    assert evidence["original_bytes_retained"] is False
    assert evidence["byte_count"] == len(exact) + 4
    assert evidence["sha256"] == hashlib.sha256(exact + b"tail").hexdigest()
    assert evidence["delivery_verified"] is False


def test_sendall_failure_retains_plan_but_never_claims_delivery(monkeypatch):
    import base64

    class BrokenSocket:
        def sendall(self, payload):
            raise OSError("synthetic ambiguous partial write")

        def shutdown(self, how):
            pass

        def close(self):
            pass

    link = CarveraLink("127.0.0.1", poll=False)
    link.socket = BrokenSocket()
    link.connection_id = "synthetic-connection"
    with pytest.raises(OutcomeUnknown) as error:
        link.command("M821")
    evidence = error.value.receipt["controller_receive_evidence"]
    assert evidence["sendall_completed"] is False
    assert evidence["delivery_verified"] is False
    assert base64.b64decode(evidence["planned_command_bytes_base64"]) == b"M821\n"
    assert evidence["byte_count"] == 0


def test_rejected_command_and_next_command_keep_distinct_original_windows(server):
    import base64

    rejected = b" ERROR: tool absent\r\nok\r\n"
    accepted = b"ok\n"

    def handle(sock):
        assert line(sock) == b"M6 T9\n"
        sock.sendall(rejected)
        assert line(sock) == b"M821\n"
        sock.sendall(accepted)
        assert sock.recv(1) == b""

    link = server(handle)
    with pytest.raises(ControllerRejected) as error:
        link.command("M6 T9")
    assert base64.b64decode(error.value.receipt["controller_receive_evidence"]["original_bytes_base64"]) == rejected
    receipt = link.command("M821")
    assert base64.b64decode(receipt["controller_receive_evidence"]["original_bytes_base64"]) == accepted
    link.close()
