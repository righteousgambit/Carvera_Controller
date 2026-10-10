import socket
import threading
import time
from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.desktop_backend import BackendPanel
from carveracontroller.headless.client import ClientUnavailable, Response, SupervisorClient
from carveracontroller.headless.ownership import EndpointLock
from tests.integration.conftest import pump_frames


def wait_for(predicate):
    until = time.monotonic() + 6
    while not predicate() and time.monotonic() < until:
        pump_frames(1, sleep=0.005)
    assert predicate()


@pytest.fixture
def backend_connection():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(0.05)
    machine = SimpleNamespace(
        status=b"<Idle|MPos:1,2,3,45|WPos:4,5,6,45|C:0,4,0,1|S:11950,12000,100|F:600,0,80|T:2>\n",
        diagnostics=b"{S:1|P:0,1|E:0,0,0,0,0,1|I:0}\n",
        wire=[],
        errors=[],
        accepted=threading.Event(),
        stop=threading.Event(),
        block_barrier=threading.Event(),
        barrier_waiting=threading.Event(),
        held=threading.Event(),
        aborted=threading.Event(),
    )

    def serve():
        try:
            while not machine.stop.is_set():
                try:
                    sock, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            machine.accepted.set()
            with sock:
                sock.settimeout(0.05)
                buffer = bytearray()
                pending_barrier = False
                while not machine.stop.is_set():
                    if pending_barrier and not machine.block_barrier.is_set():
                        sock.sendall(b"ok\n")
                        pending_barrier = False
                    try:
                        char = sock.recv(1)
                    except socket.timeout:
                        continue
                    if not char:
                        return
                    if char == b"?":
                        machine.wire.append(char)
                        sock.sendall(machine.status)
                    elif char in (b"!", b"\x18"):
                        machine.wire.append(char)
                        (machine.held if char == b"!" else machine.aborted).set()
                    else:
                        buffer.extend(char)
                        if char == b"\n":
                            machine.wire.append(bytes(buffer))
                            if buffer == b"diagnose\n":
                                sock.sendall(machine.diagnostics)
                            elif buffer == b"M105\n":
                                if machine.block_barrier.is_set():
                                    machine.barrier_waiting.set()
                                    pending_barrier = True
                                else:
                                    sock.sendall(b"ok\n")
                            else:
                                raise AssertionError("Unexpected non-observation command")
                            buffer.clear()
        except BaseException as error:
            machine.errors.append(error)

    worker = threading.Thread(target=serve, name="backend-loopback-machine", daemon=True)
    worker.start()
    methods, clients = [], []

    class RecordingClient(SupervisorClient):
        def __init__(self, *args):
            super().__init__(*args)
            clients.append(self)

        def submit(self, method, params=None):
            methods.append(method)
            return super().submit(method, params)

    controller = SimpleNamespace(stream=None, executeCommand=Mock(), close=Mock())
    workspace = SimpleNamespace(
        selected_machine_profile={"id": "loopback", "host": "127.0.0.1", "port": listener.getsockname()[1]},
        machine=SimpleNamespace(controller=controller),
        active_section="Settings",
        machine_tasks=SimpleNamespace(active="Backend"),
    )
    panel = BackendPanel(workspace, client_factory=RecordingClient, size_hint=(None, None), width=dp(300))
    Window.add_widget(panel)
    timer = Clock.schedule_interval(lambda _dt: panel.refresh_if_visible(), 0.1)
    try:
        panel.start_action.dispatch("on_release")
        wait_for(lambda: panel.client is not None and not panel.busy)
        assert methods == ["snapshot"] and not machine.accepted.is_set()
        yield panel, workspace, machine, methods
    finally:
        timer.cancel()
        panel.dispose()
        for client in clients:
            client.close()
            assert client._process.poll() is not None and not any(thread.is_alive() for thread in client._threads)
        machine.stop.set()
        worker.join(5)
        listener.close()
        Window.remove_widget(panel)
        assert not worker.is_alive() and not machine.errors, machine.errors
        controller.executeCommand.assert_not_called()
        controller.close.assert_not_called()


def test_real_backend_connection_telemetry_hidden_poll_and_disconnect_preserve_job_controller(
    backend_connection, tmp_path
):
    panel, workspace, machine, methods = backend_connection
    panel.connect_action.dispatch("on_release")
    wait_for(
        lambda: (
            not panel.busy
            and "actual 11950 RPM" in panel.telemetry.text
            and "Cover input: reported 1" in panel.telemetry.text
        )
    )
    client = panel.client
    identity = client.snapshot()["last_machine_snapshot"]["connection_id"]
    assert identity and machine.accepted.is_set() and methods.count("connect") == 1
    assert "Reported connection: connected" in panel.status.text
    assert "X 1 mm / Y 2 mm / Z 3 mm" in panel.telemetry.text and "A 45°" in panel.telemetry.text
    assert "current job controller" in panel.telemetry.text and panel.connect_action.disabled
    assert not panel.disconnect_action.disabled
    assert all(char in (b"?", b"diagnose\n", b"M105\n") for char in machine.wire)
    for width, columns in ((300, 1), (650, 2)):
        panel.width = dp(width)
        pump_frames(4)
        assert panel.actions.cols == columns
        assert all(item.height >= item.texture_size[1] for item in (panel.status, panel.telemetry, panel.note))
        panel.export_to_png(str(tmp_path / f"connected-backend-{width}.png"))
    workspace.active_section = "Job"
    wait_for(lambda: not panel.busy)
    count = len(methods)
    machine.status = b"<Hold|MPos:7,8,9|C:0,4,0,1>\n"
    machine.diagnostics = b"{P:1}\n"
    pump_frames(16, sleep=0.05)
    assert len(methods) == count
    workspace.active_section = "Settings"
    panel.refresh_if_visible()
    wait_for(
        lambda: (
            not panel.busy
            and "actual unknown / target unknown" in panel.telemetry.text
            and "Cover input: unknown" in panel.telemetry.text
        )
    )
    assert "11950" not in panel.telemetry.text and "X 7 mm / Y 8 mm / Z 9 mm" in panel.telemetry.text
    assert client.snapshot()["last_machine_snapshot"]["connection_id"] == identity
    panel.disconnect_action.dispatch("on_release")
    wait_for(lambda: not panel.busy and "Reported connection: disconnected" in panel.status.text)
    assert not panel.monitoring and methods.count("disconnect") == 1
    assert "retained report" in panel.telemetry.text and not panel.connect_action.disabled
    assert "physical machine stop" in panel.note.text


@pytest.mark.parametrize("change", ["profile", "job_owner"])
def test_backend_connect_refuses_changed_profile_and_preserves_existing_job_owner(backend_connection, change):
    panel, workspace, machine, methods = backend_connection
    if change == "profile":
        workspace.selected_machine_profile = {**workspace.selected_machine_profile, "id": "new-profile"}
    else:
        workspace.machine.controller.stream = object()
    panel.connect_action.dispatch("on_release")
    pump_frames(4)
    assert methods == ["snapshot"] and not machine.accepted.is_set() and not machine.wire
    assert ("profile changed" if change == "profile" else "job controller owns") in panel.note.text
    assert not panel.busy


def test_actual_endpoint_lock_refuses_backend_connect_without_releasing_the_original_owner(backend_connection):
    panel, workspace, machine, methods = backend_connection
    profile = workspace.selected_machine_profile
    owner = EndpointLock(profile["host"], profile["port"])
    owner.acquire()
    descriptor = owner.fd
    try:
        panel.connect_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        assert "already owned" in panel.note.text and owner.fd == descriptor
        assert methods == ["snapshot", "connect"] and not machine.accepted.is_set()
        assert panel.client.snapshot()["last_machine_snapshot"]["connected"] is False
        pump_frames(12, sleep=0.03)
        assert methods == ["snapshot", "connect"]
    finally:
        owner.release()
    panel.connect_action.dispatch("on_release")
    wait_for(lambda: not panel.busy and "actual 11950 RPM" in panel.telemetry.text)
    assert methods.count("connect") == 2 and machine.accepted.is_set()


def test_retired_or_unknown_backend_cannot_reopen_or_inherit_connected_display(backend_connection):
    panel, workspace, machine, methods = backend_connection
    panel.connect_action.dispatch("on_release")
    wait_for(lambda: not panel.busy and "actual 11950 RPM" in panel.telemetry.text)
    client = panel.client
    client.close()
    wait_for(lambda: not panel.busy)
    panel.refresh()
    assert "Backend unavailable" in panel.telemetry.text and "current receipt unavailable" in panel.telemetry.text
    assert panel.connect_action.disabled and panel.disconnect_action.disabled
    before = len(methods)
    panel.refresh_if_visible()
    assert len(methods) == before


def test_stop_requests_use_real_urgent_lane_while_ordinary_acknowledgment_waits(backend_connection):
    panel, workspace, machine, methods = backend_connection
    panel.connect_action.dispatch("on_release")
    wait_for(lambda: not panel.busy and "actual 11950 RPM" in panel.telemetry.text)
    workspace.active_section = "Job"
    wait_for(lambda: not panel.busy)
    client = panel.client
    identity = client.snapshot()["last_machine_snapshot"]["connection_id"]
    machine.block_barrier.set()
    ordinary = client.submit("command", {"command": "M105", "read_only": True, "timeout": 5})
    try:
        wait_for(machine.barrier_waiting.is_set)
        panel.busy = True
        panel._controls()
        assert panel.snapshot_action.disabled and not panel.hold_action.disabled and not panel.abort_action.disabled
        panel.request_stop("feed_hold")
        panel.request_stop("feed_hold")
        assert panel.hold_action.disabled and not panel.abort_action.disabled
        panel.request_stop("software_abort")
        wait_for(lambda: machine.held.is_set() and machine.aborted.is_set() and len(panel.control_receipts) == 2)
        assert not ordinary.done() and methods.count("realtime") == 2
        assert machine.wire.count(b"!") == 1 and machine.wire.count(b"\x18") == 1
        assert "Physical stop is unconfirmed" in panel.control_note.text
        assert all(char in (b"?", b"diagnose\n", b"M105\n", b"!", b"\x18") for char in machine.wire)
        for receipt in panel.control_receipts:
            assert receipt["outcome"] == "sent_unacknowledged"
            assert receipt["connection_id"] == identity and receipt["backend_session_id"] == client.session_id
            assert receipt["request_id"] and len(receipt["request_sha256"]) == len(receipt["response_sha256"]) == 64
        machine.block_barrier.clear()
        wait_for(ordinary.done)
        assert ordinary.result().envelope["ok"] is True
    finally:
        machine.block_barrier.clear()
        panel.busy = False


@pytest.mark.parametrize("failure", ["wrong_connection", "lost_response", "late_session"])
def test_stop_receipts_preserve_uncertainty_and_ignore_late_session_ui(failure):
    future = Future()
    client = SimpleNamespace(
        session_id="original-session",
        snapshot=lambda: {
            "ready": True,
            "running": True,
            "last_machine_snapshot": {
                "connected": True,
                "connection_id": "original-connection",
                "unknown_outcome": True,
                "transfer_active": False,
            },
        },
        submit=Mock(return_value=future),
        close=Mock(),
    )
    panel = BackendPanel(SimpleNamespace(selected_machine_profile=None))
    panel.client = client
    panel.busy = True
    panel._controls()
    assert not panel.hold_action.disabled and not panel.abort_action.disabled and panel.connect_action.disabled
    panel.request_stop("feed_hold")
    panel.request_stop("feed_hold")
    client.submit.assert_called_once_with("realtime", {"action": "feed_hold"})
    if failure == "late_session":
        panel.generation += 1
        panel.control_note.text = "replacement session display"
    if failure == "lost_response":
        future.set_exception(ClientUnavailable("lost", request_id="retained-request", submission="written"))
    else:
        future.set_result(
            Response(
                {
                    "id": "retained-request",
                    "ok": True,
                    "result": {
                        "action": "feed_hold",
                        "connection_id": "wrong" if failure == "wrong_connection" else "original-connection",
                        "outcome": "sent_unacknowledged",
                        "motion_completed": False,
                    },
                },
                "a" * 64,
                "b" * 64,
                None,
                None,
            )
        )
    pump_frames(4)
    receipt = panel.control_receipts[-1]
    assert receipt["request_id"] == "retained-request" and receipt["backend_session_id"] == "original-session"
    assert receipt["connection_id"] == "original-connection" and client.submit.call_count == 1
    if failure == "late_session":
        assert panel.control_note.text == "replacement session display" and receipt["outcome"] == "sent_unacknowledged"
    else:
        assert receipt["outcome"] == "backend_response_unknown"
        assert "physical stop is unconfirmed" in panel.control_note.text and not panel.hold_action.disabled
    if failure == "lost_response":
        assert receipt["submission"] == "written"
    panel.dispose()
