import hashlib
import io
import json
import socket
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.desktop_backend import BackendPanel
from carveracontroller.desktop_job_file import JobFilePanel
from carveracontroller.headless.client import SupervisorClient
from carveracontroller.machine.desktop_control_owner import DesktopControlOwner
from carveracontroller.XMODEM import XMODEM
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for


@pytest.fixture
def backend_job(tmp_path):
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    listener.settimeout(0.05)
    state = SimpleNamespace(
        stop=threading.Event(),
        errors=[],
        wire=[],
        files={},
        corrupt=False,
        status=b"<Idle|MPos:1,2,3|WPos:4,5,6|C:0,4,0,1|S:0,0,100|P:0,0,0,0>\n",
    )

    def serve():
        try:
            while not state.stop.is_set():
                try:
                    sock, _ = listener.accept()
                    break
                except socket.timeout:
                    continue
            else:
                return
            with sock:
                buffer = bytearray()
                while not state.stop.is_set():
                    sock.settimeout(0.05)
                    try:
                        char = sock.recv(1)
                    except socket.timeout:
                        continue
                    if not char:
                        return
                    if char == b"?":
                        state.wire.append(char)
                        sock.sendall(state.status)
                        continue
                    buffer.extend(char)
                    if char != b"\n":
                        continue
                    command = bytes(buffer)
                    buffer.clear()
                    state.wire.append(command)
                    if command == b"diagnose\n":
                        sock.sendall(b"{S:0|P:0,0|E:0,0,0,0,0,1|I:0}\n")
                    elif command == b"M105\n":
                        sock.sendall(b"ok\n")
                    elif command.startswith((b"upload ", b"download ")):
                        direction, path = command.decode().strip().split(" ", 1)

                        def getc(size, timeout=0.5):
                            sock.settimeout(timeout)
                            data = bytearray()
                            try:
                                while len(data) < size:
                                    chunk = sock.recv(size - len(data))
                                    if not chunk:
                                        return None
                                    data.extend(chunk)
                            except socket.timeout:
                                return None
                            return bytes(data)

                        def putc(data, timeout=0.5):
                            sock.sendall(data)
                            return len(data)

                        modem = XMODEM(getc, putc, "xmodem8k")
                        if direction == "upload":
                            stream = io.BytesIO()
                            assert modem.recv_legacy(stream, timeout=1) >= 0
                            state.files[path] = stream.getvalue()
                        else:
                            data = state.files[path]
                            if state.corrupt:
                                data = b"changed" + data[7:]
                            assert modem.send_legacy(io.BytesIO(data), hashlib.md5(data).hexdigest(), timeout=1)
                        sock.sendall(f"Info: {direction} success: {path}.\r\n".encode())
                    else:
                        raise AssertionError(f"Unexpected execution command: {command!r}")
        except BaseException as error:
            state.errors.append(error)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    clients, requests = [], []

    class Client(SupervisorClient):
        def __init__(self, *args):
            super().__init__(*args)
            clients.append(self)

        def submit(self, method, params=None):
            requests.append((method, params))
            return super().submit(method, params)

    source = tmp_path / "selected.nc"
    source.write_bytes(b"(Exact CRLF source)\r\nG21\nG90\nM5\n" * 500)
    setup = {"stock": [10, 20, 30], "tools": [1]}
    controller = SimpleNamespace(stream=None, executeCommand=Mock())
    ws = SimpleNamespace(
        selected_machine_profile={"id": "job", "host": "127.0.0.1", "port": listener.getsockname()[1]},
        control_owner=DesktopControlOwner(),
        machine=SimpleNamespace(controller=controller),
        app=SimpleNamespace(selected_local_filename=str(source)),
        readiness=SimpleNamespace(snapshot=lambda: ("job", setup, {"stock": True}), items=[]),
        active_section="Settings",
        machine_tasks=SimpleNamespace(active="Backend"),
    )
    backend = BackendPanel(ws, client_factory=Client)
    ws.backend_panel = backend
    panel = JobFilePanel(ws, journal_root=tmp_path / "receipts", size_hint=(None, None), width=dp(650))
    Window.add_widget(panel)
    timer = Clock.schedule_interval(lambda _dt: backend.refresh_if_visible(), 0.1)
    try:
        backend.start()
        wait_for(lambda: backend.client is not None and not backend.busy)
        backend.request("connect")
        wait_for(lambda: not backend.busy and "actual 0 RPM" in backend.telemetry.text)
        ws.control_owner.claim(backend.client.session_id, backend.client.snapshot(), gui_busy=False)
        ws.active_section = "Job"
        yield panel, backend, ws, state, requests, setup
    finally:
        timer.cancel()
        panel.dispose()
        backend.dispose()
        for client in clients:
            client.close()
            assert client._process.poll() is not None
            assert not any(worker.is_alive() for worker in client._threads)
        state.stop.set()
        thread.join(5)
        listener.close()
        Window.remove_widget(panel)
        assert not thread.is_alive() and not state.errors, state.errors
        controller.executeCommand.assert_not_called()


def freeze_upload(panel):
    panel.freeze_action.dispatch("on_release")
    wait_for(lambda: not panel.busy and panel.job is not None)
    assert panel.job.phase == "staged"
    panel.upload_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert panel.job.phase == "uploaded", panel.note.text


def test_actual_child_xmodem_upload_download_exact_readback_compiled_review_and_responsive_panes(backend_job, tmp_path):
    panel, backend, ws, state, requests, setup = backend_job
    ticks = []
    heartbeat = Clock.schedule_interval(lambda _dt: ticks.append(1), 0.01)
    try:
        freeze_upload(panel)
        job = panel.job
        assert state.files[job.remote_path] == job.data
        assert not panel.verify_action.disabled and panel.review_action.disabled
        panel.verify_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        assert job.phase == "verified", panel.note.text
        panel.review_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        assert job.phase == "reviewed" and "No job was started" in panel.note.text
        assert job.launch_plan["commands"] == [f"play {job.remote_path}"]
        assert len(ticks) >= 5
        records = [json.loads(line) for line in panel.journal_path.read_text().splitlines()]
        assert [record["phase"] for record in records] == [
            "staged",
            "upload_pending",
            "uploaded",
            "download_pending",
            "verified",
            "compile_pending",
            "reviewed",
        ]
        assert all(record["execution_admitted"] is False and record["motion_completed"] is False for record in records)
        assert records[-1]["receipts"][-2]["outcome"] == "exact_bytes_readback_verified"
        assert [method for method, _params in requests if method != "snapshot"] == [
            "connect",
            "upload",
            "download",
            "compile",
        ]
        assert all(
            command in (b"?", b"diagnose\n", b"M105\n") or command.startswith((b"upload ", b"download "))
            for command in state.wire
        )
        for width in (300, 650):
            panel.width = dp(width)
            pump_frames(5)
            assert all(item.height >= item.texture_size[1] for item in (panel.note, panel.details, panel.review))
            panel.export_to_png(str(tmp_path / f"backend-job-file-{width}.png"))
        setup["stock"] = [11, 20, 30]
        panel.refresh()
        assert "Retained attempt" in panel.details.text
        assert panel.upload_action.disabled and panel.verify_action.disabled and panel.review_action.disabled
    finally:
        heartbeat.cancel()


def test_actual_remote_file_corruption_is_retained_unresolved_without_retry(backend_job):
    panel, backend, ws, state, requests, setup = backend_job
    freeze_upload(panel)
    state.corrupt = True
    panel.verify_action.dispatch("on_release")
    wait_for(lambda: not panel.busy)
    assert panel.job.phase == "unresolved"
    assert panel.review_action.disabled and panel.verify_action.disabled
    assert json.loads(panel.journal_path.read_text().splitlines()[-1])["phase"] == "unresolved"
    count = len(requests)
    panel.request("download")
    assert len(requests) == count


@pytest.mark.parametrize("change", ["setup", "profile", "source", "edited_source", "lost_owner"])
def test_job_file_context_change_refuses_write_before_any_submission(backend_job, change):
    panel, backend, ws, state, requests, setup = backend_job
    panel.freeze()
    wait_for(lambda: not panel.busy and panel.job is not None)
    if change == "setup":
        setup["stock"] = [1, 2, 3]
    elif change == "profile":
        ws.selected_machine_profile = {**ws.selected_machine_profile, "id": "replacement"}
    elif change == "source":
        ws.app.selected_local_filename = "different.nc"
    elif change == "edited_source":
        from pathlib import Path

        Path(ws.app.selected_local_filename).write_bytes(b"edited contents")
    else:
        ws.control_owner = DesktopControlOwner()
    count = len(requests)
    panel.request("upload")
    assert len(requests) == count and not state.files


def test_main_review_routes_to_machine_file_task_with_actual_selected_backend(backend_job, kivy_app, monkeypatch):
    panel, backend, old_ws, state, requests, setup = backend_job
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws, "backend_panel", backend)
    monkeypatch.setattr(ws, "control_owner", old_ws.control_owner)
    monkeypatch.setattr(ws, "selected_machine_profile", old_ws.selected_machine_profile)
    monkeypatch.setattr(ws.machine.controller, "stream", None)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", Mock())
    backend.workspace = ws
    try:
        ws.select("Camera")
        ws.refresh(0)
        review = next(button for button, _guard in ws.guards if button.text == "Review & start")
        assert not review.disabled
        review.dispatch("on_release")
        pump_frames(5)
        assert ws.active_section == "Job" and ws.program_tasks.active == "Machine file"
        assert ws.job_file_panel.parent is ws.program_tasks.sections["Machine file"]
        assert not any(method == "operation" for method, _params in requests)
        ws.machine.controller.executeCommand.assert_not_called()
    finally:
        backend.workspace = old_ws


def test_journal_failure_prevents_the_first_machine_file_write(backend_job, monkeypatch):
    panel, backend, ws, state, requests, setup = backend_job
    panel.freeze()
    wait_for(lambda: not panel.busy and panel.job is not None)

    def no_journal(*_args, **_kwargs):
        raise OSError("test receipt store unavailable")

    monkeypatch.setattr(panel, "_journal", no_journal)
    count = len(requests)
    panel.request("upload")
    wait_for(lambda: not panel.busy)
    assert len(requests) == count and not state.files
    assert panel.job.phase == "unresolved" and panel.upload_action.disabled
    assert panel.job.receipts[-1]["outcome"] == "not_submitted"


@pytest.mark.parametrize("retire", [False, True])
def test_durable_pending_journal_runs_off_ui_and_precedes_machine_write(backend_job, monkeypatch, retire):
    panel, backend, ws, state, requests, setup = backend_job
    panel.freeze()
    wait_for(lambda: not panel.busy and panel.job is not None)
    original = panel._journal
    entered, release = threading.Event(), threading.Event()
    ui_thread = threading.get_ident()

    def slow_journal(*args, **kwargs):
        assert threading.get_ident() != ui_thread
        if panel.job.phase == "upload_pending":
            entered.set()
            assert release.wait(4)
        return original(*args, **kwargs)

    monkeypatch.setattr(panel, "_journal", slow_journal)
    count = len(requests)
    panel.request("upload")
    try:
        wait_for(entered.is_set)
        pump_frames(4)
        assert panel.busy and len(requests) == count and not state.files
        if retire:
            panel.dispose()
    finally:
        release.set()
    if retire:
        wait_for(lambda: panel.job.phase == "unresolved")
        wait_for(lambda: json.loads(panel.journal_path.read_text().splitlines()[-1])["phase"] == "unresolved")
        assert len(requests) == count and not state.files
        assert panel.job.receipts[-1]["outcome"] == "not_submitted"
    else:
        wait_for(lambda: not panel.busy)
        assert panel.job.phase == "uploaded" and state.files[panel.job.remote_path] == panel.job.data


@pytest.mark.parametrize("status", [b"<Run|S:0,0|P:0,0,0,1>\n", b"<Idle|S:1000,1000|P:0,0,0,0>\n", b"<Idle>\n"])
def test_nonidle_running_spindle_and_missing_reports_refuse_upload(backend_job, status):
    panel, backend, ws, state, requests, setup = backend_job
    panel.freeze()
    wait_for(lambda: not panel.busy and panel.job is not None)
    state.status = status
    wait_for(lambda: backend.client.snapshot()["last_machine_snapshot"]["status"].get("raw") == status.decode().strip())
    count = len(requests)
    panel.request("upload")
    assert len(requests) == count and not state.files
    assert "Upload requires a fresh Idle report" in panel.note.text
