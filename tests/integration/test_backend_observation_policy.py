"""A late cache read must preserve the current observation policy."""

from concurrent.futures import Future
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_backend import BackendPanel
from carveracontroller.headless.client import Response
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("connected", [False, True])
def test_late_snapshot_preserves_current_polling_policy(background, connected):
    future, next_request = Future(), Future()
    state = {
        "session_id": "cache-session",
        "ready": True,
        "running": True,
        "last_response_age_s": 0,
        "pending_requests": 0,
        "last_machine_snapshot": {
            "connected": connected,
            "connection_id": "cache-connection",
            "unknown_outcome": False,
            "transfer_active": False,
        },
    }
    client = SimpleNamespace(snapshot=lambda: state, submit=Mock(side_effect=[future, next_request]), close=Mock())
    workspace = SimpleNamespace(
        selected_machine_profile=None,
        active_section="Settings" if connected else "Job",
        machine_tasks=SimpleNamespace(active="Backend"),
    )
    panel = BackendPanel(workspace)
    panel.client = client
    panel.monitoring = connected
    try:
        panel.request("snapshot", background=background)
        panel.monitoring = not connected
        future.set_result(
            Response(
                {"id": "cache-request", "ok": True, "result": state["last_machine_snapshot"]}, "a" * 64, "b" * 64, 1, 1
            )
        )
        pump_frames(4)
        assert panel.monitoring is (not connected)
        assert client.submit.call_count == 1
        assert not panel.busy and not panel.polling
        assert (
            "Reported connection: connected" if connected else "Reported connection: disconnected"
        ) in panel.status.text
    finally:
        panel.dispose()
