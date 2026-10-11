import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_backend_transactions import exchange_pending, require_idle_transaction
from carveracontroller.desktop_probe_settings import ProbeSettingsPanel
from carveracontroller.desktop_tool_exchange import ToolExchangePanel
from carveracontroller.machine.desktop_control_owner import ControlBinding, DesktopControlOwner
from tests.integration.conftest import pump_frames
from tests.integration.test_backend_connection import wait_for
from tests.integration.test_backend_job_file import backend_job  # noqa: F401 - fixture dependency
from tests.integration.test_backend_job_run import backend_run, prepare_run  # noqa: F401 - fixture
from tests.integration.test_backend_tool_exchange import exchange_workbench, prepared  # noqa: F401 - fixture


@pytest.mark.parametrize("owner", ["job", "probe"])
def test_another_unfinished_workflow_blocks_exchange_before_submission(exchange_workbench, owner):  # noqa: F811
    panel, _backend, ws, state, requests = exchange_workbench
    review = prepared(panel)
    if owner == "job":
        ws.job_file_panel = SimpleNamespace(busy=False, run_panel=SimpleNamespace(active=True, journaling=False))
    else:
        ws.probe_settings_panel = SimpleNamespace(busy=True)
    panel.exchange(review)
    assert state.exchange_commands == []
    assert not any(m == "operation" and p["operation"] == "tool.change" for m, p in requests)


def test_acknowledged_exchange_blocks_probe_write_and_job_upload_on_same_lease(exchange_workbench, tmp_path):  # noqa: F811
    panel, _backend, ws, _state, _requests = exchange_workbench
    review = prepared(panel)
    panel.exchange(review)
    wait_for(lambda: not panel.busy)
    assert exchange_pending(ws)
    for requester in ("probe", "job"):
        with pytest.raises(ValueError, match="tool exchange"):
            require_idle_transaction(ws, requester)
    probe = ProbeSettingsPanel(ws, storage_root=tmp_path / "probe")
    try:
        with pytest.raises(ValueError, match="tool exchange"):
            probe._binding(write=True)
    finally:
        probe.dispose()
    # The same remembered operation must not follow a replacement owner.
    ws.control_owner.binding = None
    panel.refresh()
    assert panel.observation_review is None and panel.operation_binding is not None
    assert not exchange_pending(ws)
    assert panel.latest_record["phase"] == "exchange_acknowledged"


def test_pending_exchange_prevents_reviewed_job_start_but_keeps_urgent_controls_separate(backend_run, tmp_path):  # noqa: F811
    file_panel, _backend, ws, state, requests, _setup = backend_run
    rp = prepare_run(backend_run)
    ws.job_file_panel = file_panel
    ws.loaded_toolset = {"id": "local-bank"}
    ws.machine.gcode_viewer = SimpleNamespace(
        library_tool_table_mm={
            2: ToolDefinition(2, ToolType.FLAT_END_MILL, 6.35, description="Declared T2"),
        }
    )
    exchange = ToolExchangePanel(ws, storage_root=tmp_path / "exchange", size_hint=(None, None), width=dp(650))
    ws.tool_exchange_panel = exchange
    Window.add_widget(exchange)
    timer = Clock.schedule_interval(lambda _dt: exchange.refresh(), 0.1)
    try:
        exchange.operation_binding = (rp.run.file.session_id, rp.run.file.connection_id)
        assert not rp.can_control("job.start")
        rp.dispatch_run("job.start", reviewed_run=rp.run)
        assert rp.run.phase == "review" and "tool exchange" in rp.note.text
        assert not any(m == "operation" and p["operation"] == "job.start" for m, p in requests)
        assert not any(command.startswith(b"play ") for command in state.wire)
        with pytest.raises(ValueError, match="tool exchange"):
            file_panel._validate_job("upload")
        # Realtime stop/hold are owned by the backend panel, independent of
        # this idle-workflow admission helper; its availability is preserved.
        _backend._controls()
        assert not _backend.hold_action.disabled and not _backend.abort_action.disabled
    finally:
        timer.cancel()
        exchange.dispose()
        Window.remove_widget(exchange)


def test_file_journal_defers_only_cache_polling_while_status_events_continue(backend_job, monkeypatch):  # noqa: F811
    panel, backend, ws, state, requests, _setup = backend_job
    panel.freeze()
    wait_for(lambda: not panel.busy and panel.job is not None)
    entered, release = threading.Event(), threading.Event()
    original = panel._journal

    def slow_journal(*args, **kwargs):
        if panel.job.phase == "upload_pending":
            entered.set()
            assert release.wait(4)
        return original(*args, **kwargs)

    monkeypatch.setattr(panel, "_journal", slow_journal)
    before = len(requests)
    cursor = backend.client.status_receipts()["latest_sequence"]
    panel.request("upload")
    try:
        wait_for(entered.is_set)
        wait_for(lambda: backend.client.status_receipts(cursor)["latest_sequence"] > cursor)
        pump_frames(4)
        assert ws._backend_file_transaction_owner is panel
        assert panel.busy and len(requests) == before and not state.files
        backend._controls()
        assert not backend.hold_action.disabled and not backend.abort_action.disabled
    finally:
        release.set()
    wait_for(lambda: not panel.busy)
    assert ws._backend_file_transaction_owner is None
    assert panel.job.phase == "uploaded"
    after = len(requests)
    wait_for(lambda: len(requests) > after)
    assert requests[-1][0] == "snapshot"


@pytest.mark.parametrize("running", [True, False])
def test_legacy_watchdog_cannot_retire_gui_transport_for_selected_backend(kivy_app, monkeypatch, running):
    root = kivy_app.root
    ws = root.desktop_workspace
    owner = DesktopControlOwner()
    owner.binding = ControlBinding("selected-private-child", "selected-connection")
    monkeypatch.setattr(ws, "control_owner", owner)
    monkeypatch.setattr(
        ws, "backend_panel", SimpleNamespace(client=SimpleNamespace(snapshot=lambda: {"running": running}))
    )
    controller = root.controller
    stream = Mock()
    monkeypatch.setattr(controller, "stream", stream)
    monkeypatch.setattr(root, "uploading", False)
    monkeypatch.setattr(root, "downloading", False)
    monkeypatch.setattr(controller, "machine_response_age", Mock(return_value=10000))
    monkeypatch.setattr(controller, "record_receive_loss", Mock())
    monkeypatch.setattr(controller, "close", Mock())
    assert not controller.command_owner_available()
    root.blink_state()
    assert controller.stream is stream and owner.backend_selected
    controller.close.assert_not_called()
    controller.record_receive_loss.assert_not_called()
    stream.close.assert_not_called()
