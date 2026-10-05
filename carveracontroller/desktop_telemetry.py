"""Compact signal diagnostics with explicit timing limits and local export."""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from kivy.metrics import dp

from carveracontroller.desktop_components import ACCENT, AMBER, MUTED, Action, AdaptiveGrid, Surface, label


def milliseconds(value):
    return "Unknown" if value is None else f"{value * 1000:.0f} ms"


class TelemetryDiagnostics(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.workspace = workspace
        self.bind(minimum_height=self.setter("height"))
        self.heading = label("Signal quality · waiting", 13, bold=True, height=28)
        self.add_widget(self.heading)
        grid = AdaptiveGrid(max_cols=2, min_width=210, row_height=66, spacing=dp(8))
        self.metrics = {}
        for key, title in (
            ("age", "Latest status arrival"),
            ("cadence", "Mean / p95 interval"),
            ("coverage", "Complete spindle packets"),
            ("gaps", "Arrival gaps"),
        ):
            card = Surface(orientation="vertical", padding=dp(8), spacing=dp(2))
            card.add_widget(label(title, 10, MUTED, 18))
            value = label("—", 15, height=28)
            self.metrics[key] = value
            card.add_widget(value)
            grid.add_widget(card)
        self.add_widget(grid)
        self.detail = label("Waiting for status packets", 11, MUTED, 100)
        self.detail.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
        self.detail.bind(texture_size=lambda item, size: setattr(item, "height", max(dp(42), size[1])))
        self.add_widget(self.detail)
        self.export_note = label(
            "Local diagnostics export includes observed arrivals and shadow samples.", 10, MUTED, 38
        )
        self.export_note.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
        self.export_note.bind(texture_size=lambda item, size: setattr(item, "height", max(dp(30), size[1])))
        self.add_widget(Action("Export diagnostics…", self.export))
        self.add_widget(self.export_note)

    def update(self, state, connected):
        q = state["telemetry_quality"]
        status = q["state"] if connected else "disconnected"
        self.heading.text = "Signal quality · " + status
        self.heading.color = ACCENT if status == "receiving" else AMBER
        self.metrics["age"].text = milliseconds(q["arrival_age_s"]) if connected else "—"
        self.metrics["cadence"].text = milliseconds(q["mean_interval_s"]) + " / " + milliseconds(q["p95_interval_s"])
        self.metrics["coverage"].text = f"{q['complete_packets']} / {q['window_packets']}"
        self.metrics["gaps"].text = f"{q['gap_count']} · max {milliseconds(q['maximum_interval_s'])}"
        change = q["rpm_observed_minimum_change"]
        self.detail.text = (
            f"Window {q['window_duration_s']:.1f}s · {q['incomplete_packets']} incomplete · "
            f"{q['invalid_packets']} invalid · {q['rejected_timestamps']} rejected timestamps\n"
            f"PWM present in {q['pwm_packets']} packets · smallest observed RPM change "
            + (f"{change:g}" if change is not None else "unknown (no changes)")
            + "\n"
            f"Poll target {milliseconds(q['expected_poll_interval_s'])} · "
            f"droop filter {milliseconds(state['filter_time_constant_s'])}\n"
            "Arrival timing is measured here. Firmware sampling age, one-way delay, sensor resolution "
            "and feed-command response latency are unknown. Shadow proposals do not prove control-loop performance."
        )
        if q["latest_missing"]:
            self.detail.text += "\nLatest packet missing: " + ", ".join(q["latest_missing"])

    def export(self):
        def save(path):
            controller = self.workspace.machine.controller
            with controller._adaptive_lock:
                now = time.monotonic()
                monitor = controller.adaptive_monitor
                record = {
                    "schema_version": 1,
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "connected_at_export": self.workspace.connected,
                    "connection_generation": getattr(controller, "_connection_generation", None),
                    "machine_address": getattr(self.workspace.machine, "past_machine_addr", None),
                    "monitor": monitor.snapshot(now),
                    **monitor.quality.export(now),
                    "samples": [sample.__dict__ for sample in monitor.history],
                    "timing_limit": "Desktop arrival timestamps; firmware timing and actuator response unmeasured",
                }
            record["ui_navigation"] = self.workspace.navigation_timings.snapshot()
            record["ui_refresh"] = self.workspace.refresh_timings.snapshot()
            try:
                target = Path(path)
                payload = json.dumps(record, indent=2, allow_nan=False)
                target.write_text(payload)
                if target.read_text() != payload:
                    raise OSError("export readback differs")
                self.export_note.text = f"Saved and read back {target.name} · {len(record['arrivals'])} arrivals"
            except (ValueError, OSError) as exc:
                self.export_note.text = "Export failed: " + str(exc)

        self.workspace.choose_profile_file(save, save=True, title="Export telemetry diagnostics")
