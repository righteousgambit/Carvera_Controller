"""A bounded calibration evidence bench, opened from tool and assembly views."""

import time

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_calibration_trend import CalibrationTrend
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Surface, label, release_screen_focus
from carveracontroller.desktop_tool_custody import stamp, wrapped
from carveracontroller.machine.calibration_bench import (
    assembly_calibrations,
    post_placement_receipts,
    sample_statistics,
)
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_bank_review import mapped_offset_status


def dimension(value):
    return "Unknown" if value is None else f"{value:.6g} mm"


class CalibrationBench(Surface):
    def __init__(self, comparison):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(8), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.comparison = comparison
        self.scope = Choice(
            text="Selected assembly" if comparison.custody.selected_id else "Selected tool number",
            values=("Selected assembly", "Selected tool number"),
        )
        self.add_widget(self.scope)
        self.identity = wrapped()
        self.add_widget(self.identity)
        self.observed = wrapped()
        self.add_widget(self.observed)
        self.section = Choice(text="Trends", values=("Trends", "Latest report", "Receipt history"))
        self.add_widget(self.section)
        self.content = BoxLayout(orientation="vertical", size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.add_widget(self.content)
        self.metrics = AdaptiveGrid(max_cols=2, min_width=225, row_height=74, spacing=dp(6))
        self.trend = CalibrationTrend()
        self.history = wrapped()
        self.section.bind(text=self.show_section)
        self.show_section()
        self.add_widget(
            wrapped_with_text(
                "Sample spread and offset changes describe reported measurements. They do not identify wear, "
                "damage or physical seating. Applied TLO, nominal stickout and overall length use different references."
            )
        )
        self.add_widget(Action("Refresh measurements", self.refresh))
        self.scope.bind(text=lambda *_: self.refresh())
        self._signature = None
        self._assembly_key = None
        self._assembly = None
        self._placement = None
        self._offset_key = None
        self._offset_receipts = []
        self._rows = []
        self.refresh()

    def show_section(self, *_):
        for item in self.content.children:
            release_screen_focus(item)
        self.content.clear_widgets()
        self.content.add_widget(
            {"Trends": self.trend, "Latest report": self.metrics, "Receipt history": self.history}[self.section.text]
        )

    def refresh(self, *_):
        ws = self.comparison.workspace
        custody = self.comparison.custody
        number = self.comparison.selected
        machine_id = (getattr(ws, "selected_machine_profile", None) or {}).get("id")
        assembly_key = (id(custody.store), custody.store.generation, custody.selected_id, machine_id)
        if assembly_key != self._assembly_key:
            self._assembly_key = assembly_key
            self._assembly = custody.selected()
            self._placement = next(
                (
                    p
                    for (machine, _slot), p in custody.store.locations().items()
                    if machine == machine_id and self._assembly and p["assembly_id"] == self._assembly["id"]
                ),
                None,
            )
        assembly = self._assembly
        signature = (
            self.scope.text,
            number,
            assembly["revision_id"] if assembly else None,
            custody.store.generation,
            id(custody.store),
            machine_id,
        )
        if self.scope.text == "Selected assembly":
            if signature != self._signature:
                self._rows = assembly_calibrations(custody.store.events, assembly["id"]) if assembly else []
            self.identity.text = (
                f"{assembly['name']} · current revision {assembly['revision_id'][:8]}\n"
                "Receipts retain their original revision and source; attribution is an operator assertion."
                if assembly
                else "Select a physical assembly in its passport, then reopen or refresh this bench."
            )
            latest = self._rows[-1]["receipt"] if self._rows else None
            number = self._placement["slot"] if self._placement else latest["tool_number"] if latest else number
        else:
            record = next((r for r in ws.machine.tool_history.tools() if r.tool_number == number), None)
            reports = record.reports if record else []
            signature += (tuple(reports),)
            if signature != self._signature:
                self._rows = [
                    {
                        "statistics": sample_statistics(report.to_dict()),
                        "receipt": {
                            "id": "session-local",
                            "report": report.to_dict(),
                            "endpoint": "Unknown",
                            "tool_number": number,
                        },
                        "revision_id": None,
                        "applied_change_mm": None,
                        "previous_receipt_id": None,
                    }
                    for report in reports
                ]
            self.identity.text = f"Tool number T{number if number is not None else 'unknown'} · session-local reports\nPhysical assembly, revision and connection attribution are unknown; no trend baseline is inferred."
        pose = getattr(ws.machine.controller, "observed_pose", None)
        fresh = ws.connected and isinstance(pose, ObservedPose) and pose.fresh(time.monotonic()) and pose.tool == number
        self.observed.text = (
            f"Current-spindle reported T{number} TLO: {dimension(pose.tool_length_mm)} · fresh status only; identity unverified"
            if fresh
            else "Current-spindle TLO comparison unavailable · selected tool must match fresh connected status"
        )
        if self.scope.text == "Selected assembly":
            endpoint = getattr(ws.machine.controller, "connection_address", "")
            offset_key = (signature, endpoint)
            if offset_key != self._offset_key:
                self._offset_key = offset_key
                self._offset_receipts = post_placement_receipts(self._rows, assembly, self._placement, endpoint)
            offset = mapped_offset_status(
                {
                    "controller_tool": self._placement["slot"] if self._placement else number,
                    "controller_applicable": self._offset_receipts,
                },
                pose if ws.connected else None,
                time.monotonic(),
            )
            self.observed.text += "\n" + offset["detail"] + " · numeric comparison only; physical identity unverified"
        if signature == self._signature:
            return
        self._signature = signature
        self.trend.show(self._rows)
        self.metrics.clear_widgets()
        stats = self._rows[-1]["statistics"] if self._rows else sample_statistics({})
        for title, value in (
            ("Samples", str(stats["count"])),
            ("Sample mean", dimension(stats["mean_mm"])),
            ("Computed range", dimension(stats["range_mm"])),
            ("Sample standard deviation", dimension(stats["stdev_mm"])),
            ("Controller-reported spread", dimension(stats["reported_spread_mm"])),
            ("Calibration applied TLO", dimension(stats["applied_mm"])),
        ):
            card = Surface(orientation="vertical", padding=dp(8), spacing=dp(4))
            card.add_widget(label(title, 10, height=24))
            card.add_widget(label(value, 13, height=30, bold=True))
            self.metrics.add_widget(card)
        lines = [f"{len(self._rows)} reports · latest 10 shown · numeric offsets are not seating diagnoses"]
        for row in reversed(self._rows[-10:]):
            event, statistics = row["receipt"], row["statistics"]
            samples = event["report"]["measurements"]
            sample_text = ", ".join(f"{v:g}" if type(v) in (int, float) else repr(v) for v in samples[:20])
            if len(samples) > 20:
                sample_text += f" · {len(samples) - 20} more retained in raw receipt"
            lines.append(
                f"{stamp(event['report']['timestamp'])} · {event['endpoint'] or 'Unknown source'} · T{event['tool_number']}\n"
                f"Revision {(row['revision_id'] or 'unversioned')[:8]} · receipt {event['id'][:8]}\n"
                f"Samples: {sample_text}\n"
                f"Computed range {dimension(statistics['range_mm'])} · reported {dimension(statistics['reported_spread_mm'])}"
                + (" · spread differs from raw samples" if statistics["spread_agrees"] is False else "")
                + f"\nApplied TLO {dimension(statistics['applied_mm'])} · comparable change {dimension(row['applied_change_mm'])}"
            )
        self.history.text = "\n\n".join(lines)


def wrapped_with_text(text):
    item = wrapped()
    item.text = text
    return item


def open_calibration_bench(comparison):
    bench = CalibrationBench(comparison)
    custody = comparison.custody
    custody.dialog("Calibration bench", [bench], None, "Close")
    event = Clock.schedule_interval(bench.refresh, 0.5)
    bench.refresh_event = event
    custody.popup.bind(on_dismiss=lambda *_: event.cancel())
    comparison.calibration_bench = bench
