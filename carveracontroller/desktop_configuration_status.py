"""Inline startup retrieval status; transfer ownership stays with the controller."""

from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from carveracontroller.desktop_components import AMBER, Action


class ConfigurationStatus:
    def __init__(self, workspace):
        self.workspace = workspace
        self.message = ""
        self.active = False
        self.cancel_disabled = True
        self.strip = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.note = Label(
            text="",
            font_name="Roboto",
            font_size=sp(11),
            color=AMBER,
            halign="left",
            valign="middle",
            size_hint_y=None,
            height=dp(36),
        )
        self.note.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        self.note.bind(texture_size=lambda *_: self.refresh())
        self.action = Action("Cancel retrieval", self.invoke, size_hint_x=None, width=dp(106), height=dp(30))
        self.strip.add_widget(self.note)
        self.strip.add_widget(self.action)
        self.strip.bind(width=lambda *_: self.refresh(update_text=False))

    def start(self, message):
        self.active = True
        self.cancel_disabled = False
        self.message = message
        self.refresh()

    def update(self, value, message, disabled):
        if message:
            self.message = message
        self.cancel_disabled = disabled
        self.note.text = f"{self.message} · {max(0, min(100, value)):.0f}%"
        self.refresh(update_text=False)

    def complete(self, loaded, canceled=False):
        self.active = False
        self.cancel_disabled = True
        self.message = (
            "" if loaded else "Configuration retrieval canceled" if canceled else "Machine configuration unavailable"
        )
        self.refresh()

    def error(self, message):
        self.active = False
        self.cancel_disabled = True
        self.message = message
        self.refresh()

    def invoke(self):
        if self.active:
            if not self.cancel_disabled:
                self.workspace.machine.cancelConfigurationDownload()
        else:
            self.workspace._retry_configuration()

    def refresh(self, update_text=True):
        w = self.workspace
        visible = bool(self.message)
        if visible and self.strip.parent is None:
            w.inspector.add_widget(self.strip, index=w.inspector.children.index(w.pose_context))
        elif not visible and self.strip.parent is w.inspector:
            w.inspector.remove_widget(self.strip)
        if update_text:
            self.note.text = self.message
        compact = self.strip.width < dp(300)
        self.strip.orientation = "vertical" if compact else "horizontal"
        self.action.width = min(dp(106), max(dp(40), self.strip.width))
        self.note.height = max(dp(30), self.note.texture_size[1] + dp(8))
        self.strip.height = (
            self.note.height + self.action.height + self.strip.spacing
            if compact
            else max(self.note.height, self.action.height)
        )
        self.action.text = "Cancel retrieval" if self.active else "Retry config"
        self.action.disabled = (
            self.cancel_disabled
            if self.active
            else w.app.state != "Idle"
            or not w.connected
            or w.machine.config_loading
            or w.machine.downloading
            or w.machine.uploading
        )
