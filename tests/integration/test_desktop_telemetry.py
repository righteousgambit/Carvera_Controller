"""Operator signal feedback is local and remains honest about capture state."""

from types import SimpleNamespace
from unittest.mock import Mock

from carveracontroller.desktop_telemetry import TelemetryDiagnostics
from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample
from tests.integration.conftest import pump_frames


def test_capture_feedback_updates_and_wraps_without_machine_commands(kivy_app):
    transport = Mock()
    workspace = SimpleNamespace(machine=SimpleNamespace(controller=SimpleNamespace(executeCommand=transport)))
    panel = TelemetryDiagnostics(workspace, size_hint_x=None, width=420)
    monitor = AdaptiveMonitor()
    monitor.capture_baseline()
    for n in range(12):
        monitor.observe(Sample(n * 0.2, "Idle", 12000, 12000, 0.3, 0, 100, (0, 0, 0)))
    panel.update(monitor.snapshot(2.2), True)
    pump_frames(3)
    assert "2.2 / 5.0s" in panel.baseline_progress.text
    assert "12 stationary samples" in panel.baseline_progress.text
    assert "cutter clear" in panel.baseline_progress.text
    assert panel.baseline_progress.text_size[0] <= 420
    assert panel.baseline_progress.height >= panel.baseline_progress.texture_size[1]
    monitor.tick(4)
    panel.update(monitor.snapshot(4), True)
    assert "fault latched" in panel.baseline_progress.text
    panel.update(monitor.snapshot(4), False)
    assert "connect" in panel.baseline_progress.text
    monitor.capture_baseline()
    for n in range(28):
        monitor.observe(Sample(4.1 + n * 0.2, "Idle", 12000, 12000, 0.3, 0, 100, (0, 0, 0)))
    panel.update(monitor.snapshot(9.5), True)
    assert "12,000 RPM" in panel.baseline_progress.text
    assert "range 0 RPM" in panel.baseline_progress.text
    monitor.enabled = False
    panel.update(monitor.snapshot(9.5), True)
    assert "monitor off" in panel.baseline_progress.text
    transport.assert_not_called()
