"""Read-only capability inspector with explanations and related workspace links."""

import time

from kivy.metrics import dp, sp
from kivy.uix.label import Label

from carveracontroller.desktop_components import ACCENT, AMBER, MUTED, Action, Choice, Surface, label
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
        self._fingerprint = None
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(label("Machine capabilities", 13, bold=True, height=24))
        self.summary = flowing_text("Awaiting current machine identity", 48)
        self.choice = Choice(text="Live machine position", values=())
        self.choice.bind(text=lambda *_: self.show_selected())
        self.state = label("Needs verification", 14, AMBER, 30)
        self.detail = flowing_text("", 60)
        self.open_button = Action("Open related workbench", self.open_related)
        for widget in (self.summary, self.choice, self.state, self.detail, self.open_button):
            self.add_widget(widget)

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
        self.choice.values = tuple(r["title"] for r in self.rows)
        self.summary.text = (
            f"{identity[0] or 'Unobserved model'} · {identity[1] or 'Unobserved firmware'} · session {identity[2] or 0}\n"
            "Protocol availability does not qualify accessories or physical execution."
        )
        self.show_selected()

    def show_selected(self):
        row = next((r for r in self.rows if r["title"] == self.choice.text), None)
        if row is None:
            return
        self.state.text = row["state"]
        self.state.color = ACCENT if row["state"] == "Protocol available" else AMBER
        self.detail.text = (
            f"{row['reason']}\nPrerequisites: {row['prerequisite']}\n"
            f"Alternative: {row['alternative']}\nEvidence: {row['source']}"
        )
        self.open_button.text = "Open " + {"Overview": "Position", "Settings": "Machine"}.get(
            row["section"], row["section"]
        )

    def open_related(self):
        row = next((r for r in self.rows if r["title"] == self.choice.text), None)
        if row:
            self.workspace.select("Job" if row["section"] == "Program" else row["section"])
