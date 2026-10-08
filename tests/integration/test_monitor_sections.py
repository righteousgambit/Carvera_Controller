import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import Action
from carveracontroller.desktop_inspectors import build_monitor
from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_monitor_sections_keep_actions_at_the_top_and_never_send_commands(width):
    page = BoxLayout(orientation="vertical", spacing=10, size=(width, 620), size_hint=(None, None))
    controller = SimpleNamespace(adaptiveCommand=Mock())
    workspace = SimpleNamespace(
        _page=lambda *_args, **_kwargs: page,
        _guarded=lambda text, action, *_args: Action(text, action),
        machine=SimpleNamespace(controller=controller),
        app=SimpleNamespace(state="Idle"),
    )
    build_monitor(workspace)
    pump_frames(4)
    assert workspace.monitor_sections.current == "Signal"
    workspace.monitor_section_buttons["Decision"].dispatch("on_release")
    pump_frames(4)
    assert workspace.monitor_sections.current == "Decision"
    workspace.monitor_section_buttons["Diagnostics"].dispatch("on_release")
    pump_frames(4)
    assert workspace.monitor_sections.current == "Diagnostics"
    diagnostics = workspace.telemetry_diagnostics
    order = list(reversed(diagnostics.children))
    assert order[0] is diagnostics.heading
    assert diagnostics.export_button.parent is order[1]
    assert diagnostics.resume_button.parent is order[1]
    assert diagnostics.export_button.y > diagnostics.metrics["age"].y
    workspace.monitor_section_buttons["Baseline"].dispatch("on_release")
    assert workspace.monitor_sections.current == "Baseline"
    workspace.monitor_section_buttons["Signal"].dispatch("on_release")
    assert workspace.monitor_sections.current == "Signal"
    controller.adaptiveCommand.assert_not_called()


def test_decision_inspector_displays_observed_evidence_and_suppresses_disconnected_proposal(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    controller = workspace.machine.controller
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    now = time.monotonic()
    for n in range(27):
        monitor.observe(Sample(now - 6.8 + n * 0.2, "Idle", 12000, 12000, 0.3, 0, 100, (0, 0, 0)))
    monitor.observe(Sample(now - 1.4, "Run", 11800, 12000, None, 600, 100, (1, 2, 3)))
    for n in range(7):
        monitor.observe(Sample(now - 1.2 + n * 0.2, "Run", 11950, 12000, None, 480, 80, (n, 2, 3)))
    monkeypatch.setattr(controller, "adaptive_monitor", monitor)
    monkeypatch.setattr(controller, "executeCommand", Mock())
    workspace.select("Monitor")
    workspace.monitor_section_buttons["Decision"].dispatch("on_release")
    pump_frames(4)
    workspace._refresh_monitor(True)
    panel = workspace.adaptive_decision_panel
    assert "shadow proposal" in panel.summary.text
    assert "PWM: unavailable" in panel.fields["signals"].text
    assert "100% → 80%" in panel.fields["response"].text
    assert "+150 RPM" in panel.fields["response"].text
    assert "does not establish a causal response" in panel.fields["response"].text
    assert "X 6.000" in panel.fields["motion"].text
    assert "Executed source line, operation and camera exposure association: unverified" in panel.fields["motion"].text
    workspace._refresh_monitor(False)
    assert "No current feed proposal" in panel.summary.text
    assert "Live connection unavailable" in panel.fields["response"].text
    pump_frames(4)
    for field in panel.fields.values():
        assert field.height >= field.texture_size[1]
    controller.executeCommand.assert_not_called()


def test_hidden_decision_inspector_is_not_refreshed(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    workspace.select("Monitor")
    workspace.monitor_section_buttons["Diagnostics"].dispatch("on_release")
    monkeypatch.setattr(workspace.adaptive_decision_panel, "update", Mock())
    workspace._refresh_monitor(False)
    workspace.adaptive_decision_panel.update.assert_not_called()


def test_fresh_telemetry_does_not_hide_latched_fault_or_show_a_feed_proposal(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    controller = kivy_app.root.controller
    monitor = controller.adaptive_monitor
    now = time.monotonic()
    monkeypatch.setattr(monitor, "last", Sample(now, "Idle", 12000, 12000, 0.4, 0, 100, (0, 0, 0)))
    monkeypatch.setattr(monitor, "baseline", {"rpm": 12000})
    monkeypatch.setattr(monitor, "fault", "telemetry stale: would hold; shadow sends no commands")
    monkeypatch.setattr(monitor, "reason", monitor.fault)
    monkeypatch.setattr(controller, "executeCommand", Mock())
    workspace.select("Monitor")
    workspace.monitor_section_buttons["Diagnostics"].dispatch("on_release")
    monkeypatch.setattr(workspace.trace_rpm, "draw", Mock())
    monkeypatch.setattr(workspace.trace_pwm, "draw", Mock())
    workspace._refresh_monitor(True)
    assert "Current complete telemetry fresh" in workspace.monitor_reason.text
    assert "Latched monitor fault" in workspace.monitor_reason.text
    assert workspace.monitor_feed.value.text == "—"
    assert "Fault latched" in workspace.monitor_feed.detail.text
    assert monitor.fault  # Display changes cannot clear the latch.
    workspace.trace_rpm.draw.assert_not_called()
    workspace.trace_pwm.draw.assert_not_called()
    workspace.monitor_section_buttons["Signal"].dispatch("on_release")
    workspace._refresh_monitor(True)
    workspace.trace_rpm.draw.assert_called_once()
    workspace.trace_pwm.draw.assert_called_once()
    controller.executeCommand.assert_not_called()


def test_palette_opens_monitor_sections_and_rechecks_export_availability(kivy_app, monkeypatch):
    from carveracontroller.desktop_commands import workspace_commands

    workspace = kivy_app.root.desktop_workspace
    commands = {command.id: command for command in workspace_commands(workspace)}
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", Mock())
    for section in ("signal", "decision", "diagnostics", "baseline"):
        assert commands[f"monitor.{section}"].invoke()
        assert workspace.monitor_sections.current == section.title()
    exporter = Mock()
    monkeypatch.setattr(workspace.telemetry_diagnostics, "export", exporter)
    command = {item.id: item for item in workspace_commands(workspace)}["monitor.export"]
    monkeypatch.setattr(workspace.telemetry_diagnostics, "_exporting", True)
    assert not command.invoke()
    exporter.assert_not_called()
    monkeypatch.setattr(workspace.telemetry_diagnostics, "_exporting", False)
    assert command.invoke()
    exporter.assert_called_once_with()
    workspace.machine.controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("issue", ["failure", "gap", "prior", "healthy", "not_started"])
def test_recording_alert_is_global_and_opens_diagnostics_without_resuming(kivy_app, monkeypatch, issue):
    workspace = kivy_app.root.desktop_workspace
    controller = workspace.machine.controller
    storage = {"error": None, "rejected": 0, "failed": 0, "prior_lost_records": 0}
    if issue == "failure":
        storage["error"] = "disk full"
    elif issue == "gap":
        storage["rejected"] = 1
    elif issue == "prior":
        storage["prior_lost_records"] = 10
    elif issue == "not_started":
        storage = None
    monkeypatch.setattr(controller, "telemetry_persistence", lambda: storage)
    monkeypatch.setattr(workspace.telemetry_diagnostics, "update", Mock())
    monkeypatch.setattr(controller, "resume_telemetry_logging", Mock())
    monkeypatch.setattr(controller, "executeCommand", Mock())
    workspace.select("Job")
    workspace._refresh_monitor(False)
    alert = workspace.recording_alert
    active = issue not in ("healthy", "not_started")
    assert alert.disabled is not active
    assert bool(alert.width) == active
    assert bool(alert.opacity) == active
    if active:
        assert ("stopped" in alert.text) == (issue == "failure")
        alert.dispatch("on_release")
        assert workspace.active_section == "Monitor"
        assert workspace.monitor_sections.current == "Diagnostics"
    controller.resume_telemetry_logging.assert_not_called()
    controller.executeCommand.assert_not_called()
