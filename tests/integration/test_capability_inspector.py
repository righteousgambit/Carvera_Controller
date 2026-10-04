import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_capabilities import CapabilityPanel
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_capability_selection_navigation_and_stale_readback_are_read_only(width, monkeypatch):
    monkeypatch.setattr("carveracontroller.desktop_capabilities.time.monotonic", lambda: 10.2)
    transport = Mock()
    controller = SimpleNamespace(
        _adaptive_lock=threading.RLock(),
        stream=transport,
        _capability_observations={
            "generation": 1,
            "model": "C1",
            "firmware": "2.1.0c",
            "status_at": 10,
            "has_atc": True,
        },
    )
    workspace = SimpleNamespace(connected=True, machine=SimpleNamespace(controller=controller), select=Mock())
    panel = CapabilityPanel(workspace, size_hint_x=None, width=width)
    panel.refresh()
    pump_frames(5)
    assert panel.detail.text_size[1] is None
    assert panel.summary.text_size[1] is None
    assert "Evidence: identity:community:2.1.0c:" in panel.detail.text
    panel.choice.text = "Rigid tapping"
    pump_frames(5)
    assert panel.state.text == "Unsupported by adapter"
    assert "thread-milling" in panel.detail.text
    assert panel.detail.height >= panel.detail.texture_size[1]
    panel.width = 300
    pump_frames(5)
    assert panel.detail.text_size[1] is None
    assert panel.detail.height >= panel.detail.texture_size[1]
    panel.open_related()
    workspace.select.assert_called_once_with("Setup")
    panel.choice.text = "Inverse-time feed"
    panel.open_related()
    workspace.select.assert_called_with("Job")
    workspace.connected = False
    panel.refresh()
    assert panel.state.text == "Needs verification"
    assert "Disconnected" in panel.detail.text
    transport.send.assert_not_called()
