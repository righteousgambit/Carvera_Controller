import hashlib
import io
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

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


def test_connected_headless_owner_refuses_desktop_before_socket_creation(server, monkeypatch):
    from carveracontroller.WIFIStream import WIFIStream

    closed = threading.Event()

    def handle(sock):
        assert sock.recv(1) == b""
        closed.set()

    link = server(handle)
    directory = link.endpoint_lock.directory
    monkeypatch.setattr(
        "carveracontroller.WIFIStream.EndpointLock", lambda host, port: EndpointLock(host, port, directory)
    )

    def forbidden_socket(*args, **kwargs):
        raise AssertionError("Desktop must not create a socket while headless owns the endpoint")

    # Patch the desktop consumer only. socket.accept() constructs its accepted
    # socket through the module-level factory too; patching the shared module
    # races the already-started loopback server on Linux.
    monkeypatch.setattr(
        "carveracontroller.WIFIStream.socket",
        SimpleNamespace(socket=forbidden_socket, AF_INET=socket.AF_INET, SOCK_STREAM=socket.SOCK_STREAM),
    )
    desktop = WIFIStream()
    with pytest.raises(EndpointBusyError):
        desktop.open(f"{link.host}:{link.port}")
    desktop.close()
    assert link.endpoint_lock.fd is not None
    assert link.snapshot()["connected"] is True
    link.close()
    assert closed.wait(2)
    next_owner = EndpointLock(link.host, link.port, directory)
    next_owner.acquire()
    next_owner.release()


def test_desktop_owner_refuses_headless_and_failed_contender_cannot_release_owner(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from carveracontroller.WIFIStream import WIFIStream

    directory = tmp_path / "locks"
    monkeypatch.setattr(
        "carveracontroller.WIFIStream.EndpointLock", lambda host, port: EndpointLock(host, port, directory)
    )
    desktop_socket = Mock()
    monkeypatch.setattr(socket, "socket", Mock(return_value=desktop_socket))
    network = Mock(side_effect=AssertionError("Contender must not touch the network"))
    monkeypatch.setattr(socket, "create_connection", network)
    desktop = WIFIStream()
    contender = CarveraLink("127.0.0.1", 2222, lock_directory=directory, poll=False)
    try:
        assert desktop.open("127.0.0.1:2222")
        desktop_socket.connect.assert_called_once_with(("127.0.0.1", 2222))
        with pytest.raises(EndpointBusyError):
            contender.connect()
        contender.close()
        with pytest.raises(EndpointBusyError):
            EndpointLock("127.0.0.1", 2222, directory).acquire()
        network.assert_not_called()
    finally:
        desktop.close()
        contender.close()
    desktop_socket.close.assert_called_once_with()
    next_owner = EndpointLock("127.0.0.1", 2222, directory)
    next_owner.acquire()
    next_owner.release()


def test_failed_desktop_connection_releases_socket_and_endpoint_for_retry(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from carveracontroller.WIFIStream import WIFIStream

    directory = tmp_path / "locks"
    monkeypatch.setattr(
        "carveracontroller.WIFIStream.EndpointLock", lambda host, port: EndpointLock(host, port, directory)
    )
    failed_socket, retry_socket = Mock(), Mock()
    failed_socket.connect.side_effect = ConnectionRefusedError("synthetic refusal")
    factory = Mock(side_effect=[failed_socket, retry_socket])
    monkeypatch.setattr(socket, "socket", factory)
    desktop = WIFIStream()
    with pytest.raises(ConnectionRefusedError, match="synthetic refusal"):
        desktop.open("127.0.0.1:2222")
    assert desktop.socket is None and desktop.endpoint_lock is None
    failed_socket.close.assert_called_once_with()
    try:
        assert desktop.open("127.0.0.1:2222")
        assert desktop.socket is retry_socket and desktop.endpoint_lock.fd is not None
    finally:
        desktop.close()
    retry_socket.close.assert_called_once_with()


def test_command_phase_evidence_uses_parsed_ack_and_serial_queue_with_no_motion_claim(server):
    first_arrived, release_ack, second_queued = threading.Event(), threading.Event(), threading.Event()
    wire = []

    def handle(sock):
        wire.append(line(sock))
        first_arrived.set()
        assert release_ack.wait(2)
        sock.sendall(STATUS + b"ok\n")
        wire.append(line(sock))
        sock.sendall(b"ERROR: synthetic refusal\nok\n")
        assert sock.recv(1) == b""

    link = server(handle)
    original_lock = link._command_lock

    class ObservedLock:
        def __enter__(self):
            if first_arrived.is_set():
                second_queued.set()
            original_lock.acquire()

        def __exit__(self, *args):
            original_lock.release()

    link._command_lock = ObservedLock()
    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(link.command, "M821")
        assert first_arrived.wait(2)
        second = pool.submit(link.command, "M105")
        assert second_queued.wait(2)
        release_ack.set()
        accepted = first.result(timeout=2)
        with pytest.raises(ControllerRejected) as error:
            second.result(timeout=2)
    rejected = error.value.receipt
    assert wire == [b"M821\n", b"M105\n"]
    for receipt in (accepted, rejected):
        timing = receipt["host_timing"]
        assert timing["clock_state"] == "valid"
        assert timing["connection_id"] == receipt["connection_id"] == link.connection_id
        assert timing["outcome"] == receipt["outcome"]
        assert timing["queued_at_s"] <= timing["admitted_at_s"] <= timing["send_started_at_s"]
        assert timing["send_started_at_s"] <= timing["acknowledged_at_s"] <= timing["finished_at_s"]
        assert timing["send_call_ms"] >= 0 and timing["send_start_to_ack_ms"] >= 0
        assert timing["physical_response_ms"] is None and timing["motion_completed"] is False
    assert rejected["host_timing"]["command_queue_ms"] > 0
    health = link.snapshot()["transport_health"]
    assert health["total_commands"] == 2
    assert health["outcomes"] == {"controller_acknowledged": 1, "controller_rejected": 1, "unknown_outcome": 0}
    assert health["status_arrivals"]["window_packets"] == 1
    assert health["recent_commands"][0]["acknowledged_at_s"] == accepted["host_timing"]["acknowledged_at_s"]
    link.close()


def test_timeout_preserves_phase_evidence_and_unknown_count_without_inventing_ack(server):
    def handle(sock):
        assert line(sock) == b"M821\n"
        sock.sendall(STATUS)
        assert sock.recv(1) == b""

    link = server(handle)
    with pytest.raises(OutcomeUnknown) as error:
        link.command("M821", timeout=0.1)
    row = error.value.receipt["host_timing"]
    assert row["send_completed_at_s"] is not None
    assert row["acknowledged_at_s"] is None and row["send_start_to_ack_ms"] is None
    assert row["clock_state"] == "valid" and row["outcome"] == "unknown_outcome"
    health = link.snapshot()["transport_health"]
    assert health["outcomes"]["unknown_outcome"] == 1
    assert health["mean_send_start_to_ack_ms"] is None
    assert health["status_arrivals"]["window_packets"] == 1
    assert link.snapshot()["unknown_outcome"] is True


def test_send_failure_retains_receipt_and_unbound_diagnostics_cannot_change_transport_outcome():
    class BrokenSocket:
        def sendall(self, payload):
            raise OSError("synthetic partial transmission")

        def shutdown(self, how):
            pass

        def close(self):
            pass

    link = CarveraLink("127.0.0.1", poll=False)
    link.socket = BrokenSocket()
    link.connection_id = "unbound-fixture"
    with pytest.raises(OutcomeUnknown) as error:
        link.command("M821")
    row = error.value.receipt["host_timing"]
    assert row["send_started_at_s"] is not None
    assert row["send_completed_at_s"] is None and row["acknowledged_at_s"] is None
    assert row["outcome"] == "unknown_outcome"
    assert link.snapshot()["transport_health"]["total_commands"] == 0
    assert link.snapshot()["transport_health"]["rejected_connection_timings"] == 1
