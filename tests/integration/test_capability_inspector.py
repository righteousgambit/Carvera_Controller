import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_capabilities import CapabilityPanel
from tests.integration.conftest import pump_frames


@pytest.fixture
def mounted_panel():
    from kivy.core.window import Window
    from kivy.metrics import dp

    panels = []

    def create(workspace, width):
        panel = CapabilityPanel(workspace, size_hint_x=None, width=dp(width))
        panels.append(panel)
        Window.add_widget(panel)
        return panel

    yield create
    for panel in panels:
        Window.remove_widget(panel)


@pytest.mark.parametrize("width", [360, 650])
def test_capability_selection_navigation_and_stale_readback_are_read_only(width, monkeypatch, mounted_panel):
    monkeypatch.setattr("carveracontroller.desktop_capabilities.time", SimpleNamespace(monotonic=lambda: 10.2))
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
    panel = mounted_panel(workspace, width)
    panel.refresh()
    pump_frames(5)
    assert panel.detail.text_size[1] is None
    assert panel.summary.text_size[1] is None
    assert "Evidence: identity:community:2.1.0c:" in panel.detail.text
    assert panel.detail.parent is None
    panel.details_button.dispatch("on_release")
    assert panel.detail.parent is panel
    panel.buttons["rigid_tapping"].dispatch("on_release")
    pump_frames(5)
    assert "Rigid tapping · Unsupported by adapter" in panel.state.text
    assert "thread-milling" in panel.detail.text
    assert panel.detail.height >= panel.detail.texture_size[1]
    panel.width = 300
    pump_frames(5)
    assert panel.detail.text_size[1] is None
    assert panel.detail.height >= panel.detail.texture_size[1]
    panel.open_related()
    workspace.select.assert_called_once_with("Setup")
    panel.buttons["inverse_time"].dispatch("on_release")
    panel.open_related()
    workspace.select.assert_called_with("Job")
    workspace.connected = False
    panel.refresh()
    assert "Needs verification" in panel.state.text
    assert "Disconnected" in panel.detail.text
    transport.send.assert_not_called()


@pytest.mark.parametrize("width,columns", [(300, 1), (650, 3)])
def test_overview_filtering_selection_and_observation_changes(width, columns, monkeypatch, tmp_path, mounted_panel):
    now = [10.2]
    monkeypatch.setattr("carveracontroller.desktop_capabilities.time", SimpleNamespace(monotonic=lambda: now[0]))
    transport = Mock()
    observations = {"generation": 2, "model": "C1", "firmware": "2.1.0c", "status_at": 10, "has_atc": True}
    controller = SimpleNamespace(
        _adaptive_lock=threading.RLock(), stream=transport, _capability_observations=observations
    )
    workspace = SimpleNamespace(connected=True, machine=SimpleNamespace(controller=controller), select=Mock())
    panel = mounted_panel(workspace, width)
    panel.refresh()
    pump_frames(5)
    assert len(panel.buttons) == 12 and panel.overview.cols == columns
    assert panel.detail.parent is None
    assert "8/12 protocols available" in panel.summary.text
    first = panel.buttons["status"]
    panel.refresh()
    assert panel.buttons["status"] is first  # Polls preserve keyboard focus targets.
    panel.search.text = "thread-milling"
    pump_frames(3)
    assert list(panel.buttons) == ["rigid_tapping"]
    panel.buttons["rigid_tapping"].dispatch("on_release")
    panel.details_button.dispatch("on_release")
    assert panel.selected_key == "rigid_tapping" and panel.detail.parent is panel
    assert "Encoder synchronization" in panel.detail.text
    panel.search.text = ""
    panel.filter.text = "Simulation only"
    pump_frames(3)
    assert set(panel.buttons) == {"rotary", "tcp"}
    assert "Selected: Rigid tapping" in panel.state.text  # Filtering never silently changes selection.
    panel.buttons["tcp"].dispatch("on_release")
    tcp_button = panel.buttons["tcp"]
    tcp_button.focus = True
    panel.open_button.dispatch("on_release")
    workspace.select.assert_called_once_with("Scene")
    panel.search.text = "no such capability"
    assert not panel.buttons and "No matching" in panel.result_note.text
    assert not tcp_button.focus  # Filtered-out tiles cannot keep keyboard ownership.
    panel.search.text = ""
    panel.filter.text = "All capabilities"
    now[0] = 11
    panel.refresh()
    pump_frames(3)
    assert "0/12 protocols available" in panel.summary.text
    assert all("Protocol available" not in button.text for button in panel.buttons.values())
    assert panel.selected_key == "tcp" and "stale" in panel.detail.text
    assert panel.buttons["tcp"] is tcp_button
    observations["status_at"] = 11
    panel.refresh()
    assert "8/12 protocols available" in panel.summary.text
    panel.details_button.dispatch("on_release")
    assert panel.detail.parent is None
    pump_frames(5)
    assert all(button.text_size[0] > 0 for button in panel.buttons.values())
    panel.export_to_png(str(tmp_path / f"capability-overview-{width}.png"))
    transport.send.assert_not_called()
