"""Integrated read-only library/CAM/telemetry and calibration workbench."""

import time
from datetime import datetime, timezone

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, Field, Surface, label
from carveracontroller.machine.tool_comparison import compare_tools, finite


def dimension(value):
    return "Unknown" if value is None else f"{value:.6g} mm"


class ToolComparisonPanel(Surface):
    def __init__(self, workspace):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_y=None)
        self.workspace = workspace
        self.selected = None
        self.rows = ()
        self._signature = None
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Tool comparison & calibration", 14, height=26, bold=True))
        self.status = label("", 11, MUTED, 48)
        self.add_widget(self.status)
        self.search = Field(hint_text="Find tool number or name", height=dp(36))
        self.search.bind(text=lambda *_: self.render())
        self.add_widget(self.search)
        self.list = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None)
        self.list.bind(minimum_height=self.list.setter("height"))
        self.add_widget(self.list)
        self.detail = label("", 11, MUTED, 80)
        self.detail.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        self.detail.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(60), size[1] + dp(12))))
        self.add_widget(self.detail)
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(6))
        actions.add_widget(Action("Edit cutter library", self.open_library))
        actions.add_widget(Action("Refresh comparison", lambda: self.refresh(force=True)))
        self.add_widget(actions)

    def focus(self):
        self.workspace.select("Setup")
        self.refresh(force=True)

        def reveal(_dt):
            parent = self.parent
            while parent is not None:
                if hasattr(parent, "scroll_to"):
                    parent.scroll_to(self, padding=dp(12), animate=False)
                    break
                parent = parent.parent

        Clock.schedule_once(reveal, 0)

    def open_library(self):
        self.workspace._open_profiles()
        self.workspace.profile_library.select_kind("tools")

    def refresh(self, force=False):
        ws, viewer = self.workspace, self.workspace.machine.gcode_viewer
        history = ws.machine.tool_history
        pose = getattr(ws.machine.controller, "observed_pose", None)
        rows = compare_tools(
            viewer.library_tool_table_mm,
            viewer.tool_table,
            history,
            pose,
            connected=ws.connected,
            now=time.monotonic(),
            cam_scale=viewer.tool_unit_scale,
        )
        # Raw measurements participate so an updated report cannot leave stale details.
        reports = tuple(
            (r.tool_number, tuple((p.timestamp, p.measurements, p.max_delta, p.applied) for p in r.reports))
            for r in history.tools()
        )
        signature = (rows, reports)
        if force or signature != self._signature:
            self._signature, self.rows = signature, rows
            self.render()

    def choose(self, number):
        self.selected = number
        self.render()

    def render(self):
        query = self.search.text.strip().casefold()
        rows = [r for r in self.rows if not query or query in f"T{r.number} {r.number} {r.name}".casefold()]
        self.list.clear_widgets()
        state = self.rows[0].report_state if self.rows else "unavailable"
        self.status.text = f"{len(self.rows)} tool numbers · controller report {state}\nLibrary/CAM dimensions are declared; history is keyed by number, not physical cutter."
        for row in rows:
            active = " · Reported active" if row.reported_active else ""
            conflict = " · Diameter differs" if row.diameter_conflict else ""
            item = Action(
                f"T{row.number} · {row.name}{active}{conflict}\nLibrary Ø {dimension(row.library_diameter_mm)} · CAM Ø {dimension(row.cam_diameter_mm)}",
                lambda n=row.number: self.choose(n),
                height=dp(58),
            )
            item.halign = "left"
            item.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0] - dp(16), size[1])))
            self.list.add_widget(item)
        if not rows:
            self.list.add_widget(
                label("No matching tooling. Load a toolset, a program, or record a calibration.", 11, MUTED, 44)
            )
        row = next((r for r in self.rows if r.number == self.selected), None)
        if row is None:
            self.detail.text = (
                "Select a tool to compare its declared geometry, current report and raw calibration history."
            )
            return
        lines = [
            f"T{row.number} · {row.name}",
            f"Library diameter: {dimension(row.library_diameter_mm)} · CAM diameter: {dimension(row.cam_diameter_mm)}",
            f"Declared stickout: {dimension(row.stickout_mm)}",
            f"Current reported TLO: {dimension(row.observed_tlo_mm)} ({row.report_state}; active tool only)",
            f"Last calibration applied TLO: {dimension(row.historical_tlo_mm)}",
            "Overall length, stickout and TLO have different references; no length difference is inferred.",
        ]
        if row.diameter_conflict:
            lines.append("Diameter discrepancy: review library and CAM definitions before using this setup.")
        record = next((r for r in self.workspace.machine.tool_history.tools() if r.tool_number == row.number), None)
        if record and record.reports:
            lines.append(f"Calibration reports: {len(record.reports)} · most recent 10 shown · timestamps UTC")
            for report in reversed(record.reports[-10:]):
                stamp = finite(report.timestamp)
                try:
                    date = (
                        datetime.fromtimestamp(stamp, timezone.utc).isoformat(timespec="seconds")
                        if stamp is not None and stamp > 0
                        else "Unknown time"
                    )
                except (ValueError, OverflowError, OSError):
                    date = "Invalid timestamp"
                samples = ", ".join(dimension(finite(value)) for value in report.measurements)
                lines.append(
                    f"{date}\n  Samples: {samples or 'None'}\n  Reported spread: {dimension(finite(report.max_delta))} · applied: {dimension(finite(report.applied))}"
                )
            lines.append(
                "Spread alone does not diagnose wear, damage or seating. History is session-local and tool-number-bound."
            )
        else:
            lines.append("No calibration report recorded for this tool number.")
        self.detail.text = "\n".join(lines)
        self.detail.color = AMBER if row.diameter_conflict else MUTED
