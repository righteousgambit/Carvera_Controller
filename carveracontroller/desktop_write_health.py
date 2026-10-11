"""Actual desktop host write measurements, kept separate from ack/response."""

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, AMBER, MUTED, Action, AdaptiveGrid, Surface, label


def milliseconds(value):
    return "Unknown" if value is None else f"{value:.2f} ms"


class ControlWriteHealth(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.workspace = workspace
        self.bind(minimum_height=self.setter("height"))
        self.heading = flowing_text("Control write timing · waiting", 26)
        self.add_widget(self.heading)
        self.grid = AdaptiveGrid(max_cols=2, min_width=210, row_height=90, spacing=dp(6))
        self.values = {}
        for key, title in (
            ("last", "Last host write call"),
            ("cadence", "Mean / p95 host write"),
            ("calls", "Recorded control writes"),
            ("failures", "Failed send calls"),
        ):
            card = Surface(orientation="vertical", padding=dp(8), spacing=dp(2))
            card.add_widget(label(title, 10, MUTED, height=20))
            value = label("—", 16, ACCENT, height=42)
            value.bind(width=lambda item, width: setattr(item, "text_size", (width, None)))
            card.add_widget(value)
            self.values[key] = value
            self.grid.add_widget(card)
        self.add_widget(self.grid)
        self.note = flowing_text(
            "Host write duration does not establish delivery, acknowledgment or physical response.", 40
        )
        self.add_widget(self.note)
        self.details = flowing_text("No retained writes.", 30)
        self.toggle = Action("+ Recent write calls", self.toggle_details)
        self.add_widget(self.toggle)

    def toggle_details(self):
        if self.details.parent is self:
            self.remove_widget(self.details)
            self.toggle.text = "+ Recent write calls"
        else:
            self.add_widget(self.details)
            self.toggle.text = "− Recent write calls"

    def refresh_if_visible(self):
        if self.workspace.active_section == "Settings" and self.workspace.machine_tasks.active == "Health":
            self.refresh()

    def refresh(self):
        controller = self.workspace.machine.controller
        receive = getattr(controller, "receive_diagnostics", None)
        data = receive()["current"].get("control_writes") if receive else None
        if data is None:
            self.heading.text = "Control write timing · unavailable"
            self.heading.color = MUTED
            for value in self.values.values():
                value.text = "—"
            self.note.text = "This connection supplies no host write measurements."
            self.details.text = "This connection supplies no host write measurements."
            return
        connected = self.workspace.connected
        self.heading.text = (
            "Control write timing · live host observations"
            if connected and data["total_calls"]
            else "Control write timing · waiting for a write"
            if connected
            else "Control write timing · disconnected history"
        )
        self.heading.color = ACCENT if connected else MUTED
        self.values["last"].text = milliseconds(data["last_call_ms"])
        self.values["cadence"].text = (
            f"{data['mean_call_ms']:.2f} / {data['p95_call_ms']:.2f} ms"
            if data["mean_call_ms"] is not None and data["p95_call_ms"] is not None
            else "Unknown"
        )
        self.values["calls"].text = str(data["total_calls"])
        self.values["failures"].text = str(data["failed_calls"])
        self.values["failures"].color = AMBER if data["failed_calls"] else ACCENT
        age = data["last_call_age_s"]
        when = (
            f"Last call {age:.2f}s ago"
            if connected and age is not None
            else "Last call time unknown"
            if connected
            else "Retained connection history"
        )
        gaps = (
            f" · {data['unavailable_observations']} observations unavailable"
            if data["unavailable_observations"]
            else ""
        )
        self.note.text = (
            f"{when} · connection {data['connection_generation']}{gaps}\n"
            "Control writes only; transfer data excluded. Write duration does not establish delivery, acknowledgment or physical response."
        )
        rows = data["recent_calls"][-8:]
        self.details.text = (
            "\n".join(
                f"{row['kind'].replace('_', ' ')} · {milliseconds(row['duration_ms'])} · "
                + (
                    "call returned; delivery unverified"
                    if row["call_returned"]
                    else f"host call failed · {row['error_class'] or 'error'}; delivery unknown"
                )
                for row in rows
            )
            or "No retained writes."
        )
