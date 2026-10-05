"""Compact signal diagnostics with explicit timing limits and local export."""

import json
import os
import tempfile
import threading
import time
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from kivy.clock import Clock
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
        self.persistence = label("Telemetry storage · not started", 11, MUTED, 48)
        self.persistence.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
        self.persistence.bind(texture_size=lambda item, size: setattr(item, "height", max(dp(32), size[1])))
        self.add_widget(self.persistence)
        self.export_note = label(
            "Local diagnostics export includes observed arrivals and shadow samples.", 10, MUTED, 38
        )
        self.export_note.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
        self.export_note.bind(texture_size=lambda item, size: setattr(item, "height", max(dp(30), size[1])))
        self._exporting = False
        self.export_button = Action("Export diagnostics…", self.export)
        self.add_widget(self.export_button)
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

        storage = state.get("persistence")
        if storage is None:
            self.persistence.text = "Telemetry storage · not started"
            self.persistence.color = MUTED
        else:
            missing = storage["rejected"] + storage["failed"]
            self.persistence.color = AMBER if missing or storage["error"] else MUTED
            self.persistence.text = (
                f"Telemetry storage · {storage['written']} written · "
                f"{storage['queued'] + storage['inflight']} pending · {missing} lost\n"
                + (
                    "Stopped: " + storage["error"]
                    if storage["error"]
                    else "Closing"
                    if storage["closing"]
                    else "Background writer · flushed to OS"
                )
            )

    def export(self):
        if self._exporting:
            return

        def save(path):
            if self._exporting:
                return
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
            persistence = getattr(controller, "telemetry_persistence", None)
            record["telemetry_persistence"] = persistence() if persistence else None
            record["ui_navigation"] = self.workspace.navigation_timings.snapshot()
            record["ui_refresh"] = self.workspace.refresh_timings.snapshot()
            # Freeze observations on the UI thread; storage and JSON encoding must
            # not delay input dispatch or live telemetry/camera refresh.
            record = deepcopy(record)
            target = Path(path)
            self._exporting = True
            self.export_button.disabled = True
            self.export_note.text = f"Saving {target.name}… · live viewing continues"

            def finish(message):
                self._exporting = False
                self.export_button.disabled = False
                self.export_note.text = message

            def write():
                staged = None
                try:
                    payload = json.dumps(record, indent=2, allow_nan=False)
                    with tempfile.NamedTemporaryFile(
                        prefix=f".{target.name}.", suffix=".pending", dir=target.parent, delete=False
                    ) as temporary:
                        staged = Path(temporary.name)
                    staged.write_text(payload, encoding="utf-8")
                    if staged.read_text(encoding="utf-8") != payload:
                        raise OSError("export readback differs")
                    os.replace(staged, target)
                    staged = None
                    if target.read_text(encoding="utf-8") != payload:
                        raise OSError("export readback differs")
                    message = f"Saved and read back {target.name} · {len(record['arrivals'])} arrivals"
                except (ValueError, TypeError, OSError) as exc:
                    message = "Export failed: " + str(exc)
                    if staged is not None:
                        message += f" · partial file retained: {staged.name}"
                Clock.schedule_once(lambda _dt: finish(message), 0)

            threading.Thread(target=write, name="telemetry-diagnostics-export", daemon=True).start()

        self.workspace.choose_profile_file(save, save=True, title="Export telemetry diagnostics")
