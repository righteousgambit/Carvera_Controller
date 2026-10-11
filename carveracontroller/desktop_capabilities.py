"""Read-only capability inspector with explanations and related workspace links."""

import time

from kivy.metrics import dp, sp
from kivy.uix.label import Label

from carveracontroller.desktop_components import (
    ACCENT,
    AMBER,
    BG,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    Surface,
    label,
)
from carveracontroller.machine.capability_map import capability_rows


def flowing_text(text, minimum_height):
    # The fixed-height label helper binds text_size to both dimensions. Using it
    # here feeds a clipped texture height back into the label's own height.
    item = Label(
        text=text,
        font_name="Roboto",
        font_size=sp(11),
        color=MUTED,
        size_hint_y=None,
        height=dp(minimum_height),
        halign="left",
        valign="middle",
    )
    item.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
    item.bind(texture_size=lambda widget, size: setattr(widget, "height", max(dp(minimum_height), size[1])))
    item.text_size = (item.width, None)
    return item


class CapabilityPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.workspace = workspace
        self.rows = []
        self.selected_key = "status"
        self.buttons = {}
        self._tiles = {}
        self.expanded = False
        self._fingerprint = None
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Machine capabilities", 13, bold=True, height=24))
        self.summary = flowing_text("Awaiting current machine identity", 30)
        self.add_widget(self.summary)
        self.add_widget(flowing_text("Protocol support does not qualify hardware or physical execution.", 20))
        filters = AdaptiveGrid(max_cols=2, min_width=150, row_height=34, spacing=dp(6))
        self.search = Field(hint_text="Find a capability", height=dp(34))
        self.filter = Choice(
            text="All capabilities",
            values=(
                "All capabilities",
                "Protocol available",
                "Needs verification",
                "Simulation only",
                "Not detected",
                "Unsupported by adapter",
            ),
            height=dp(34),
        )
        self.search.bind(text=lambda *_: self.render_overview())
        self.filter.bind(text=lambda *_: self.render_overview())
        filters.add_widget(self.search)
        filters.add_widget(self.filter)
        self.add_widget(filters)
        self.overview = AdaptiveGrid(max_cols=3, min_width=190, row_height=52, spacing=dp(6))
        self.add_widget(self.overview)
        self.result_note = flowing_text("", 20)
        self.add_widget(self.result_note)
        self.state = flowing_text("Selected: Live machine position · Needs verification", 26)
        self.add_widget(self.state)
        controls = AdaptiveGrid(max_cols=2, min_width=140, row_height=34, spacing=dp(6))
        self.details_button = Action("Show details", self.toggle_details, height=dp(34))
        self.detail = flowing_text("", 40)
        self.open_button = Action("Open related workbench", self.open_related)
        controls.add_widget(self.details_button)
        controls.add_widget(self.open_button)
        self.add_widget(controls)

    def toggle_details(self):
        self.expanded = not self.expanded
        self.details_button.text = "Hide details" if self.expanded else "Show details"
        if self.expanded:
            self.add_widget(self.detail)
        else:
            self.remove_widget(self.detail)

    def select_capability(self, key):
        if any(row["key"] == key for row in self.rows):
            self.selected_key = key
            self.show_selected()

    def render_overview(self):
        query = self.search.text.strip().casefold()
        visible = []
        for row in self.rows:
            searchable = " ".join(row[name] for name in ("title", "section", "state", "prerequisite", "alternative"))
            if self.filter.text != "All capabilities" and row["state"] != self.filter.text:
                continue
            if query in searchable.casefold():
                visible.append(row)
        visible_keys = {row["key"] for row in visible}
        for key, button in self.buttons.items():
            if key not in visible_keys:
                button.focus = False
        self.overview.clear_widgets()
        self.buttons = {}
        for row in visible:
            button = self._tiles.get(row["key"])
            if button is None:
                button = Action("", lambda key=row["key"]: self.select_capability(key), height=dp(52))
                button.font_size = sp(10)
                button.halign = "left"
                button.valign = "middle"
                button.bind(size=lambda widget, size: setattr(widget, "text_size", (size[0] - dp(14), size[1])))
                self._tiles[row["key"]] = button
            button.text = f"{row['title']}\n{row['state']}"
            self.buttons[row["key"]] = button
            self.overview.add_widget(button)
        shown = len(self.buttons)
        self.result_note.text = (
            f"{shown} of {len(self.rows)} capabilities"
            if shown
            else "No matching capabilities. Clear search or change the filter."
        )
        self.paint_selection()

    def paint_selection(self):
        for key, button in self.buttons.items():
            selected = key == self.selected_key
            button.base_color = ACCENT if selected else RAISED
            button.color = BG if selected else TEXT
            button._paint()

    def refresh(self):
        controller = self.workspace.machine.controller
        with controller._adaptive_lock:
            observations = dict(controller._capability_observations)
        self.rows = capability_rows(observations, connected=self.workspace.connected, now=time.monotonic())
        fingerprint = tuple((r["key"], r["state"], r["reason"], r["source"]) for r in self.rows)
        identity = (observations.get("model"), observations.get("firmware"), observations.get("generation"))
        if (fingerprint, identity) == self._fingerprint:
            return
        self._fingerprint = (fingerprint, identity)
        available = sum(row["state"] == "Protocol available" for row in self.rows)
        self.summary.text = (
            f"{identity[0] or 'Unobserved model'} · {identity[1] or 'Unobserved firmware'} · session {identity[2] or 0}\n"
            f"{available}/{len(self.rows)} protocols available from current observations"
        )
        self.render_overview()
        self.show_selected()

    def show_selected(self):
        row = next((r for r in self.rows if r["key"] == self.selected_key), None)
        if row is None:
            return
        self.state.text = f"Selected: {row['title']} · {row['state']}"
        self.state.color = ACCENT if row["state"] == "Protocol available" else AMBER
        self.detail.text = (
            f"{row['reason']}\nPrerequisites: {row['prerequisite']}\n"
            f"Alternative: {row['alternative']}\nEvidence: {row['source']}"
        )
        self.open_button.text = "Open " + {"Overview": "Position", "Settings": "Machine"}.get(
            row["section"], row["section"]
        )
        if row["key"] == "mill_turn":
            self.open_button.text = "Open channel planner"
        self.paint_selection()

    def open_related(self):
        row = next((r for r in self.rows if r["key"] == self.selected_key), None)
        if row:
            self.workspace.select("Job" if row["section"] == "Program" else row["section"])
            if row["key"] == "mill_turn" and hasattr(self.workspace, "machine_tasks"):
                self.workspace.machine_tasks.show("Channels")
