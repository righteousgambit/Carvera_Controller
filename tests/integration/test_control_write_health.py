from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.Controller import Controller
from carveracontroller.desktop_write_health import ControlWriteHealth
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width,columns", [(300, 1), (650, 2)])
def test_actual_send_observations_render_responsively_without_commands_from_panel(width, columns, tmp_path):
    from kivy.core.window import Window
    from kivy.metrics import dp

    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    assert controller.executeCommand("M821") is True
    controller.stream.send.side_effect = OSError("synthetic hidden payload")
    assert controller.executeCommand("M105") is False
    workspace = SimpleNamespace(machine=SimpleNamespace(controller=controller), connected=True)
    panel = ControlWriteHealth(workspace, size_hint=(None, None), width=dp(width), pos=(0, 0))
    Window.add_widget(panel)
    try:
        panel.refresh()
        pump_frames(8)
        assert panel.grid.cols == columns
        assert panel.values["calls"].text == "2" and panel.values["failures"].text == "1"
        assert "live host observations" in panel.heading.text
        assert "delivery, acknowledgment or physical response" in panel.note.text
        assert panel.details.parent is None
        panel.toggle.dispatch("on_release")
        pump_frames(5)
        assert panel.details.parent is panel
        assert "host call failed · OSError" in panel.details.text
        assert "synthetic hidden payload" not in panel.details.text
        assert panel.details.height >= panel.details.texture_size[1]
        assert panel.note.height >= panel.note.texture_size[1]
        for value in panel.values.values():
            assert value.texture_size[0] <= value.width + 1
            assert value.texture_size[1] <= value.height + 1
        panel.export_to_png(str(tmp_path / f"control-write-{width}.png"))
        panel.toggle.dispatch("on_release")
        workspace.connected = False
        panel.refresh()
        pump_frames(5)
        assert "disconnected history" in panel.heading.text
        assert "Retained connection history" in panel.note.text
        assert panel.details.parent is None
        assert controller.stream.send.call_count == 2  # Only the two explicit synthetic setup writes.
    finally:
        Window.remove_widget(panel)


def test_workbench_health_page_consumes_actual_controller_diagnostics_without_sending(kivy_app, monkeypatch):
    root, workspace = kivy_app.root, kivy_app.root.desktop_workspace
    controller, panel = root.controller, workspace.control_write_health
    stream = Mock()
    monkeypatch.setattr(controller, "stream", stream)
    before = controller.receive_diagnostics()["current"]["control_writes"]["total_calls"]
    assert controller.executeCommand("M821") is True
    panel.refresh()
    assert panel.values["calls"].text == str(before + 1)
    assert panel.parent is workspace.machine_tasks.sections["Health"]
    panel.toggle.dispatch("on_release")
    pump_frames(3)
    assert panel.details.parent is panel
    panel.toggle.dispatch("on_release")
    pump_frames(3)
    assert panel.details.parent is None
    stream.send.assert_called_once()


def test_unavailable_observations_are_visible_without_reusing_stale_metrics():
    from kivy.core.window import Window

    controller = Controller(CNC(), lambda _: None)
    controller._receive_health.write_gap()
    controller._receive_health.write("command", 3, 2, 1, True)
    workspace = SimpleNamespace(machine=SimpleNamespace(controller=controller), connected=True)
    panel = ControlWriteHealth(workspace)
    Window.add_widget(panel)
    try:
        panel.refresh()
        assert panel.values["last"].text == "Unknown" and panel.values["cadence"].text == "Unknown"
        assert "1 observations unavailable" in panel.note.text
        assert panel.values["failures"].text == "0"
        workspace.machine.controller = SimpleNamespace()
        panel.refresh()
        assert "unavailable" in panel.heading.text
        assert all(value.text == "—" for value in panel.values.values())
        assert "observations unavailable" not in panel.note.text
        assert "no host write measurements" in panel.note.text
    finally:
        Window.remove_widget(panel)


def test_hidden_health_task_does_not_collect_or_rebuild_write_metrics():
    workspace = SimpleNamespace(active_section="Job", machine_tasks=SimpleNamespace(active="Health"))
    panel = ControlWriteHealth(workspace)
    panel.refresh = Mock()
    panel.refresh_if_visible()
    panel.refresh.assert_not_called()
    workspace.active_section = "Settings"
    workspace.machine_tasks.active = "Connect"
    panel.refresh_if_visible()
    panel.refresh.assert_not_called()
    workspace.machine_tasks.active = "Health"
    panel.refresh_if_visible()
    panel.refresh.assert_called_once_with()
