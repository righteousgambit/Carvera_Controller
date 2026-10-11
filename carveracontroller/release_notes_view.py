"""Render bounded release-note pages only while the update dialog is visible."""

from kivy.metrics import dp
from kivy.properties import BooleanProperty, StringProperty
from kivy.uix.boxlayout import BoxLayout

from .desktop_components import MUTED, Action, Field, label
from .machine.release_notes import note_pages


class ReleaseNotesView(BoxLayout):
    text = StringProperty("")
    active = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(8), **kwargs)
        self._pages = None
        self._index = 0
        self.body = Field(multiline=True, readonly=True, size_hint_y=1)
        self.add_widget(self.body)
        controls = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        self.previous = Action("Previous", lambda: self.move(-1), size_hint_x=None, width=dp(100))
        self.next = Action("Next", lambda: self.move(1), size_hint_x=None, width=dp(100))
        self.caption = label("Notes appear when Updates opens", 11, MUTED, 38)
        controls.add_widget(self.previous)
        controls.add_widget(self.caption)
        controls.add_widget(self.next)
        self.add_widget(controls)
        self.bind(text=self._changed, active=self._visibility)
        self._visibility()

    def _changed(self, *_args):
        self._pages = None
        self._index = 0
        if self.active:
            self._show()

    def _visibility(self, *_args):
        if self.active:
            self._show()
        else:
            self.body.focus = False
            self.body.text = ""
            self.previous.disabled = self.next.disabled = True

    def _show(self):
        if self._pages is None:
            self._pages = note_pages(self.text)
        self.body.text = self._pages[self._index]
        self.body.cursor = (0, 0)
        self.previous.disabled = self._index == 0
        self.next.disabled = self._index == len(self._pages) - 1
        self.caption.text = (
            f"Page {self._index + 1} of {len(self._pages)} • full notes retained"
            if self.text
            else "Waiting for release notes"
        )

    def move(self, delta):
        if not self.active:
            return
        self._index = max(0, min(len(self._pages) - 1, self._index + delta))
        self._show()
