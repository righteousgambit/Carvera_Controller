import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_backend import BackendPanel
from carveracontroller.headless.client import SupervisorClient
from tests.integration.conftest import pump_frames


def wait_for(predicate):
    end = time.monotonic() + 6
    while not predicate() and time.monotonic() < end:
        pump_frames(1, sleep=0.005)
    assert predicate()


@pytest.mark.parametrize("width,columns", [(300, 1), (650, 2)])
def test_actual_private_backend_panel_start_snapshot_catalog_paging_and_stop_are_read_only(width, columns, tmp_path):
    from kivy.core.window import Window
    from kivy.metrics import dp

    methods, clients = [], []

    class RecordingClient(SupervisorClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            clients.append(self)

        def submit(self, method, params=None):
            methods.append(method)
            return super().submit(method, params)

    controller = Mock()
    workspace = SimpleNamespace(
        selected_machine_profile={"host": "127.0.0.1", "port": 2222}, machine=SimpleNamespace(controller=controller)
    )
    panel = BackendPanel(workspace, client_factory=RecordingClient, size_hint=(None, None), width=dp(width), pos=(0, 0))
    Window.add_widget(panel)
    try:
        panel.start_action.dispatch("on_release")
        wait_for(lambda: panel.client is not None and not panel.busy)
        assert "ready" in panel.heading.text and "disconnected" in panel.status.text
        assert clients[0].snapshot()["last_machine_snapshot"]["connected"] is False
        assert methods == ["snapshot"]
        panel.catalog_action.dispatch("on_release")
        wait_for(lambda: not panel.busy)
        assert methods == ["snapshot", "catalog"]
        assert len(panel.catalog) > 8 and "declared backend operations" in panel.catalog_note.text
        before = panel.catalog_rows.text
        panel.next.dispatch("on_release")
        pump_frames(4)
        assert panel.catalog_rows.text != before and panel.catalog_page == 1
        assert len(methods) == 2
        assert panel.actions.cols == columns
        for item in (panel.heading, panel.note, panel.status, panel.catalog_note, panel.catalog_rows):
            assert item.height >= item.texture_size[1]
        panel.export_to_png(str(tmp_path / f"backend-{width}.png"))
        pid = clients[0].snapshot()["pid"]
        assert pid is not None
        panel.stop_action.dispatch("on_release")
        wait_for(lambda: panel.client is None and not panel.busy)
        assert "stopped" in panel.heading.text and clients[0]._process.poll() is not None
        assert not any(worker.is_alive() for worker in clients[0]._threads)
        assert methods == ["snapshot", "catalog"]
        controller.assert_not_called()
        assert controller.method_calls == []
    finally:
        panel.dispose()
        Window.remove_widget(panel)
        for client in clients:
            client.close()


def test_real_machine_workbench_contains_backend_panel_without_launching_or_sending(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.backend_panel
    assert panel.parent is workspace.machine_tasks.sections["Backend"]
    assert panel.client is None and panel.busy is False
    workspace.machine_tasks.show("Backend")
    pump_frames(4)
    assert panel.client is None and panel.heading.text == "Local backend · stopped"
    workspace.machine_tasks.show("Connect")


def test_hidden_backend_task_does_not_poll_or_rebuild_metrics():
    workspace = SimpleNamespace(active_section="Job", machine_tasks=SimpleNamespace(active="Backend"))
    panel = BackendPanel(workspace)
    panel.refresh = Mock()
    panel.refresh_if_visible()
    panel.refresh.assert_not_called()
    workspace.active_section = "Settings"
    workspace.machine_tasks.active = "Health"
    panel.refresh_if_visible()
    panel.refresh.assert_not_called()
    workspace.machine_tasks.active = "Backend"
    panel.refresh_if_visible()
    panel.refresh.assert_called_once_with()
    panel.dispose()


def test_disposal_during_slow_start_retains_child_ownership_and_ignores_late_ui_result():
    entered, release, stopped = threading.Event(), threading.Event(), threading.Event()
    clients = []

    class SlowClient:
        def __init__(self, *args):
            clients.append(self)

        def start(self):
            entered.set()
            assert release.wait(4)

        def close(self):
            stopped.set()

        def snapshot(self):
            return {"ready": False, "running": not stopped.is_set()}

    panel = BackendPanel(SimpleNamespace(selected_machine_profile=None), client_factory=SlowClient)
    panel.start()
    assert entered.wait(4)
    panel.dispose()
    previous = panel.heading.text
    release.set()
    wait_for(stopped.is_set)
    pump_frames(4)
    assert panel.closed and panel.heading.text == previous and len(clients) == 1


def test_failed_shutdown_keeps_ownership_and_does_not_claim_stopped_or_start_replacement():
    class FailingClient:
        fail = True

        def close(self):
            if self.fail:
                raise OSError("synthetic shutdown refusal")

        def snapshot(self):
            return {"ready": False, "running": True}

    panel = BackendPanel(SimpleNamespace(selected_machine_profile=None))
    client = FailingClient()
    panel.client = client
    panel.stop()
    wait_for(lambda: not panel.busy)
    assert panel.client is client and "shutdown pending" in panel.heading.text
    assert panel.start_action.disabled and not panel.stop_action.disabled
    panel.start()
    assert panel.client is client
    client.fail = False
    panel.stop()
    wait_for(lambda: panel.client is None)
    assert "stopped" in panel.heading.text
    panel.dispose()
