import json
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.graphics import Line

from carveracontroller.adaptive_popup import Trace
from carveracontroller.desktop_telemetry import TelemetryDiagnostics
from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample
from carveracontroller.machine.telemetry_log import TelemetryLog
from carveracontroller.machine.ui_stalls import UIStallMonitor
from carveracontroller.machine.ui_timing import NavigationTimings
from tests.integration.conftest import pump_frames


@pytest.mark.parametrize("width", [360, 650])
def test_explicit_recording_recovery_stays_responsive_and_exports_retained_gap(tmp_path, monkeypatch, width):
    from kivy.clock import Clock

    from carveracontroller.CNC import CNC
    from carveracontroller.Controller import Controller

    monkeypatch.setenv("KIVY_HOME", str(tmp_path))
    controller = Controller(CNC(), lambda _: None)
    controller.stream = Mock()
    previous = controller._adaptive_log = TelemetryLog(tmp_path / "failed.jsonl")
    previous.path.write_bytes(b"partial failed record")
    monkeypatch.setattr(previous, "_write", Mock(side_effect=OSError("disk full")))
    assert previous.submit({"packet": 1}) and previous.drain(2)["error"]
    destination = tmp_path / "recovery-export.json"
    workspace = SimpleNamespace(
        connected=True,
        navigation_timings=NavigationTimings(),
        refresh_timings=NavigationTimings(),
        machine=SimpleNamespace(controller=controller),
        choose_profile_file=lambda callback, **_: callback(destination),
    )
    panel = TelemetryDiagnostics(workspace, size_hint_x=None, width=width)

    def update():
        panel.update(
            {**controller.adaptive_monitor.snapshot(), "persistence": controller.telemetry_persistence()}, True
        )

    entered, release = threading.Event(), threading.Event()
    original = TelemetryLog._write

    def blocked(writer, record):
        if record.get("record_type") == "telemetry_recovery_gap":
            entered.set()
            assert release.wait(3)
        original(writer, record)

    monkeypatch.setattr(TelemetryLog, "_write", blocked)
    update()
    assert not panel.resume_button.disabled
    try:
        panel.resume_button.dispatch("on_release")
        assert entered.wait(1)
        update()
        assert panel.resume_button.disabled and "Starting" in panel.resume_button.text
        assert controller._adaptive_log is previous
        ticks = []
        Clock.schedule_once(lambda dt: ticks.append(dt), 0)
        pump_frames(2)
        assert ticks
        assert not controller.resume_telemetry_logging()
    finally:
        release.set()
    deadline = time.monotonic() + 3
    while controller._telemetry_recovery.snapshot()["current"]["state"] == "pending" and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert controller._telemetry_recovery.snapshot()["current"]["state"] == "resumed"
    update()
    assert panel.resume_button.disabled and "gap retained" in panel.recovery_note.text
    assert "Earlier segments: 1 lost" in panel.persistence.text
    pump_frames(3)
    assert panel.resume_button.width <= width
    panel.export()
    deadline = time.monotonic() + 3
    while panel._exporting and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    result = json.loads(destination.read_text())["telemetry_persistence"]
    assert result["prior_lost_records"] == 1
    assert result["recovery"]["current"]["gap_record_sha256"]
    assert result["recovery"]["current"]["boundary"]["previous"]["error"]
    assert previous.path.read_bytes() == b"partial failed record"
    controller.stop_telemetry_logging(2)
    controller.stream.send.assert_not_called()


def test_gap_trace_does_not_draw_a_continuous_line_across_missing_observations():
    trace = Trace(size=(600, 100))
    samples = [Sample(t, "Run", 12000, 12000, None, 600, 100, (0, 0, 0)) for t in (0, 0.2, 1.4, 1.6)]
    trace.draw(samples, "rpm", 15000, (1, 1, 1, 1))
    segments = [list(item.points) for item in trace.canvas.children if isinstance(item, Line) and item.points]
    assert len(segments) == 2
    assert segments[0][-2] < segments[1][0]


@pytest.mark.parametrize("width", [360, 650])
def test_diagnostics_layout_and_export_preserve_unknown_timing_and_send_nothing(tmp_path, width):
    monitor = AdaptiveMonitor()
    monitor.observe(Sample(1, "Idle", 0, 0, None, 0, 100, (0, 0, 0)))
    monitor.quality.record(1.2, missing=("S",))
    transport = Mock()
    persistence = {
        "written": 7,
        "queued": 1,
        "inflight": 1,
        "rejected": 2,
        "failed": 0,
        "error": None,
        "closing": False,
    }
    destination = tmp_path / "quality.json"
    workspace = SimpleNamespace(
        connected=True,
        navigation_timings=NavigationTimings(),
        refresh_timings=NavigationTimings(limit=60),
        machine=SimpleNamespace(
            controller=SimpleNamespace(
                adaptive_monitor=monitor,
                _adaptive_lock=threading.Lock(),
                stream=transport,
                telemetry_persistence=lambda: dict(persistence),
            )
        ),
        choose_profile_file=lambda callback, **_: callback(destination),
    )
    # A rare freeze must still be exportable after routine refreshes overwrite
    # the recent ring. These deterministic clocks do not claim native latency.
    now = [0.0]
    workspace.refresh_timings = NavigationTimings(limit=2, clock=lambda: now[0])
    workspace.stall_monitor = UIStallMonitor(
        clock=lambda: now[0], capture=lambda _: [{"file": "sample.py", "function": "wait", "line": 10}]
    )
    slow = workspace.refresh_timings.begin("periodic_refresh", "Setup")
    now[0] = 5.0
    workspace.stall_monitor.check()
    workspace.stall_monitor.heartbeat("Monitor")
    workspace.refresh_timings.finish(slow, completed=True)
    for _ in range(3):
        fast = workspace.refresh_timings.begin("periodic_refresh", "Monitor")
        now[0] += 0.001
        workspace.refresh_timings.finish(fast, completed=True)
    panel = TelemetryDiagnostics(workspace, size_hint_x=None, width=width)
    panel.update(monitor.snapshot(1.3), True)
    panel.update({**monitor.snapshot(1.3), "persistence": persistence}, True)
    pump_frames(5)
    assert panel.heading.text == "Signal quality · incomplete"
    assert panel.metrics["coverage"].text == "1 / 2"
    assert "Latest packet missing: S" in panel.detail.text
    assert "one-way delay" in panel.detail.text and "unknown" in panel.detail.text
    assert "7 written" in panel.persistence.text and "2 pending" in panel.persistence.text
    assert "2 lost" in panel.persistence.text
    assert panel.detail.height >= panel.detail.texture_size[1]
    panel.export()
    deadline = time.monotonic() + 5
    while panel._exporting and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel._exporting
    result = json.loads(destination.read_text())
    assert result["quality"]["one_way_transport_delay_s"] is None
    assert len(result["arrivals"]) == 2
    assert len(result["samples"]) == 1
    assert result["ui_navigation"]["records"] == []
    assert result["ui_refresh"]["retention_limit"] == 2
    assert len(result["ui_refresh"]["records"]) == 2
    assert result["ui_refresh"]["slowest"]["callback_s"]["callback_s"] == 5.0
    assert result["ui_refresh"]["slowest"]["callback_s"]["target"] == "Setup"
    assert result["ui_stalls"]["records"][0]["heartbeat_gap_s"] == 5.0
    assert result["ui_stalls"]["records"][0]["samples"][0]["stack"][0]["function"] == "wait"
    assert result["telemetry_persistence"] == persistence
    assert "do not prove screen presentation" in result["ui_navigation"]["limits"]
    assert "Saved and read back" in panel.export_note.text
    transport.send.assert_not_called()
    panel.update(monitor.snapshot(1.3), False)
    assert panel.heading.text.endswith("disconnected") and panel.metrics["age"].text == "—"


def test_slow_export_keeps_clock_live_and_freezes_observations(tmp_path, monkeypatch):
    monitor = AdaptiveMonitor()
    monitor.observe(Sample(1, "Idle", 0, 0, None, 0, 100, (0, 0, 0)))
    destination = tmp_path / "slow.json"
    workspace = SimpleNamespace(
        connected=True,
        navigation_timings=NavigationTimings(),
        refresh_timings=NavigationTimings(),
        machine=SimpleNamespace(
            controller=SimpleNamespace(adaptive_monitor=monitor, _adaptive_lock=threading.Lock(), stream=Mock())
        ),
        choose_profile_file=lambda callback, **_: callback(destination),
    )
    panel = TelemetryDiagnostics(workspace)
    entered, release = threading.Event(), threading.Event()
    original_write = Path.write_text
    ui_thread = threading.get_ident()
    writers = []

    def slow_write(path, payload, *args, **kwargs):
        writers.append(threading.get_ident())
        entered.set()
        assert release.wait(5), "test did not release storage"
        return original_write(path, payload, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", slow_write)
    panel.export()
    try:
        assert entered.wait(2)
        assert panel._exporting and panel.export_button.disabled
        from kivy.clock import Clock

        ticks = []
        Clock.schedule_once(lambda _dt: ticks.append(True), 0)
        pump_frames(2)
        assert ticks == [True]  # UI work proceeds while storage is blocked.
        panel.export()
        assert len(writers) == 1 and writers[0] != ui_thread
        monitor.observe(Sample(2, "Run", 12000, 11900, None, 600, 100, (1, 0, 0)))
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while panel._exporting and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel._exporting and not panel.export_button.disabled
    saved = json.loads(destination.read_text())
    assert len(saved["samples"]) == 1 and saved["samples"][0]["state"] == "Idle"
    workspace.machine.controller.stream.send.assert_not_called()


def test_export_failure_reenables_control_without_success_receipt(tmp_path, monkeypatch):
    monitor = AdaptiveMonitor()
    workspace = SimpleNamespace(
        connected=False,
        navigation_timings=NavigationTimings(),
        refresh_timings=NavigationTimings(),
        machine=SimpleNamespace(controller=SimpleNamespace(adaptive_monitor=monitor, _adaptive_lock=threading.Lock())),
        choose_profile_file=lambda callback, **_: callback(tmp_path / "failure.json"),
    )
    panel = TelemetryDiagnostics(workspace)
    (tmp_path / "failure.json").write_bytes(b"previous valid export")
    monkeypatch.setattr(Path, "read_text", lambda *_args, **_kwargs: "corrupt readback")
    panel.export()
    deadline = time.monotonic() + 5
    while panel._exporting and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel._exporting and not panel.export_button.disabled
    assert panel.export_note.text.startswith("Export failed: export readback differs")
    assert (tmp_path / "failure.json").read_bytes() == b"previous valid export"
    assert len(list(tmp_path.glob(".failure.json.*.pending"))) == 1
