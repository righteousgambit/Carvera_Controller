"""Responsive before/after modal-state inspection; no command actions."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout

from carveracontroller.desktop_components import ACCENT, MUTED, TEXT, Action, Surface, label
from carveracontroller.machine.modal_inspection import modal_facts, modal_notes


class ModalInspectorPanel(Surface):
    def __init__(self, text_factory, reveal, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.text_factory = text_factory
        self.reveal = reveal
        self.move = None
        self.changes_only = True
        self.facts = ()
        self.rows = {}
        header = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(32))
        header.add_widget(label("Modal state · before / after", 12, height=32, bold=True))
        self.filter_action = Action("Show all", self.toggle_filter, size_hint_x=None, width=dp(90), height=32)
        header.add_widget(self.filter_action)
        self.add_widget(header)
        self.status = text_factory()
        self.add_widget(self.status)
        self.table = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        self.table.bind(minimum_height=self.table.setter("height"))
        self.add_widget(self.table)
        self.notes = text_factory()
        self.add_widget(self.notes)
        self.bind(width=self._resize_rows)

    def inspect(self, move):
        self.move = move
        self.facts = modal_facts(move) if move else ()
        self.notes.text = "\n".join(modal_notes(move)) if move else ""
        self._render()

    def toggle_filter(self):
        self.changes_only = not self.changes_only
        self._render()
        if self.parent:
            self.reveal(self, align_top=True)

    def _render(self):
        self.table.clear_widgets()
        self.rows = {}
        self.filter_action.text = "Show all" if self.changes_only else "Changes only"
        if not self.move:
            self.status.text = "Select a source line to inspect its program state."
            return
        changed = sum(fact.changed for fact in self.facts)
        self.status.text = (
            f"Line {self.move.line_number} · {changed} changed fields · values before and after this block"
            + (
                "\nNo tracked modal changes on this line. Show all to inspect inherited values."
                if not changed and self.changes_only
                else ""
            )
        )
        for fact in self.facts:
            if self.changes_only and not fact.changed:
                continue
            row = Surface(orientation="vertical", padding=dp(7), spacing=dp(3), size_hint_y=None)
            row.bind(minimum_height=row.setter("height"))
            title = self.text_factory(fact.title + (" · changed" if fact.changed else " · inherited"))
            title.color = ACCENT if fact.changed else MUTED
            row.add_widget(title)
            values = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
            values.bind(minimum_height=values.setter("height"))
            entering = self.text_factory("Before: " + fact.before)
            leaving = self.text_factory("After: " + fact.after)
            entering.color = MUTED
            leaving.color = TEXT
            values.add_widget(entering)
            values.add_widget(leaving)
            row.add_widget(values)
            self.table.add_widget(row)
            self.rows[fact.key] = (values, entering, leaving)
        self._resize_rows()

    def _resize_rows(self, *_):
        for values, _entering, _leaving in self.rows.values():
            values.cols = 1 if self.width < dp(420) else 2
