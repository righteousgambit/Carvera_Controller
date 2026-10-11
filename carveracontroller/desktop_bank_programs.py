"""Background bank compilation and source-linked review; never dispatches."""

import json
import threading
import uuid
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Field, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.bank_programs import compile_bank, save_draft


class BankProgramReview(BoxLayout):
    def __init__(self, panel, **kwargs):
        self.panel = panel
        self.context = panel._context_key()
        self.program, self.bank = panel.program, panel.bank
        self.generation, self.draft = 0, None
        self.section, self.page = "Mapping", 0
        self.page_size = 60
        self.section_actions = {}
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(8), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        body = self
        body.add_widget(label("Logical tools and controller pockets", 16, height=24, bold=True))
        self.convention = Choice(
            text="Automatic tool offsets (no H mapping)",
            values=("Automatic tool offsets (no H mapping)", "H indexes match logical T numbers"),
        )
        self.convention.bind(text=lambda *_: self.compile())
        body.add_widget(self.convention)
        self.status = wrapped()
        body.add_widget(self.status)
        navigation = AdaptiveGrid(max_cols=4, min_width=120, row_height=32, spacing=dp(5))
        for section in ("Mapping", "Modes & checks", "Source changes", "Full source"):
            action = Action(section, lambda section=section: self.select_section(section), height=dp(32))
            self.section_actions[section] = action
            navigation.add_widget(action)
        body.add_widget(navigation)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        self.export_action = Action("Export review JSON", self.export)
        actions.add_widget(self.export_action)
        actions.add_widget(Action("Recompile", self.compile))
        actions.add_widget(Action("Close review", self.dismiss))
        body.add_widget(actions)
        self.view = Field(multiline=True, readonly=True, height=dp(220))
        body.add_widget(self.view)
        self.source_navigation = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(5))
        self.previous_action = Action("Previous", lambda: self.turn_page(-1), size_hint_x=0.7, height=dp(32))
        self.next_action = Action("Next", lambda: self.turn_page(1), size_hint_x=0.7, height=dp(32))
        self.line_input = Field(hint_text="Source line", height=dp(32), size_hint_x=0.8)
        self.line_input.bind(on_text_validate=lambda *_: self.go_to_line())
        self.line_action = Action("Go to line", self.go_to_line, height=dp(32), size_hint_x=0.9)
        for widget in (self.previous_action, self.next_action, self.line_input, self.line_action):
            self.source_navigation.add_widget(widget)
        body.add_widget(self.source_navigation)
        self.page_status = wrapped()
        body.add_widget(self.page_status)
        self.compile()

    def open(self):
        if self.parent is None:
            self.panel.add_widget(self, index=self.panel.children.index(self.panel.program_review_action))
            Clock.schedule_once(self.reveal, 0)

    def reveal(self, _dt):
        ancestor = self.parent
        while ancestor is not None:
            if isinstance(ancestor, ScrollView):
                ancestor.scroll_to(self, padding=dp(8), animate=False)
                break
            ancestor = ancestor.parent

    def dismiss(self):
        self.generation += 1
        if self.parent:
            self.parent.remove_widget(self)

    def compile(self):
        self.generation += 1
        generation = self.generation
        self.draft = None
        self.export_action.disabled = True
        self.view.text = ""
        self.page_status.text = ""
        self.status.text = "Compiling source-linked review in the background…"
        mode = "logical_h" if self.convention.text.startswith("H indexes") else "automatic"

        def run():
            try:
                draft, error = compile_bank(self.program, self.bank, offset_mode=mode), None
            except (ValueError, OSError) as exc:
                draft, error = None, str(exc)
            Clock.schedule_once(lambda _dt: self.loaded(generation, draft, error), 0)

        threading.Thread(target=run, daemon=True).start()

    def loaded(self, generation, draft, error):
        if generation != self.generation:
            return
        if self.panel._context_key() != self.context:
            self.status.text = "Program, machine or bank changed. Close and reopen this review."
            return
        if error:
            self.status.text = error
            return
        self.draft = draft
        self.export_action.disabled = False
        self.status.text = (
            f"Bank {draft.bank_index} · {len(draft.errors)} compilation errors · local draft only. "
            "Physical stop, reload, calibrated offsets and qualified re-entry remain required."
        )
        self.page = 0
        self.render_section()

    def select_section(self, section):
        if section not in self.section_actions:
            return
        self.section, self.page = section, 0
        self.render_section()

    def source_rows(self):
        if not self.draft:
            return ()
        if self.section == "Source changes":
            return tuple(line for line in self.draft.lines if line.reason)
        return self.draft.lines

    def turn_page(self, direction):
        pages = max(1, (len(self.source_rows()) + self.page_size - 1) // self.page_size)
        self.page = min(pages - 1, max(0, self.page + direction))
        self.render_section()

    def go_to_line(self):
        if not self.draft or self.panel._context_key() != self.context:
            self.page_status.text = "Review context changed; reopen before navigating."
            return
        try:
            number = int(self.line_input.text.strip())
        except ValueError:
            self.page_status.text = "Enter a whole source line number."
            return
        rows = self.draft.lines
        index = next((i for i, line in enumerate(rows) if line.source_line == number), None)
        if index is None:
            self.page_status.text = f"Source line must be in this bank: {self.bank.start_line}–{self.bank.end_line}."
            return
        self.section, self.page = "Full source", index // self.page_size
        self.render_section()
        marker = f"L{number}:"
        # Move the read-only text cursor to the actual source locator, rather
        # than merely opening a page containing it.
        offset = self.view.text.find(marker)
        if offset >= 0:
            self.view.cursor = self.view.get_cursor_from_index(offset)
            self.view.select_text(offset, offset + len(marker))

    def render_section(self):
        source = self.section in ("Source changes", "Full source")
        for section, action in self.section_actions.items():
            action.disabled = section == self.section
        for widget in self.source_navigation.children:
            widget.disabled = not source or not self.draft
        if not self.draft:
            return
        draft = self.draft
        if self.section == "Mapping":
            text = "\n".join(
                f"Logical T{tool} -> controller T{pocket} / pocket {pocket}" for tool, pocket in draft.mapping
            )
            text += "\n\nFixed six-pocket candidate mapping. Physical identities and installed offsets still require reconciliation."
            self.page_status.text = (
                f"Bank {draft.bank_index} · source lines {self.bank.start_line}–{self.bank.end_line}"
            )
        elif self.section == "Modes & checks":
            text = "INHERITED MODAL STATE (no approach or spindle restart)\n"
            text += "\n".join(draft.modal_restoration) or "No known inherited modes"
            text += "\n\nCOMPILATION ERRORS\n" + ("\n".join(draft.errors) or "None")
            text += "\n\nREQUIRED REVIEW\n" + "\n".join(draft.cautions)
            self.page_status.text = f"{len(draft.errors)} errors · {len(draft.cautions)} review requirements"
        else:
            rows = self.source_rows()
            pages = max(1, (len(rows) + self.page_size - 1) // self.page_size)
            self.page = min(self.page, pages - 1)
            start = self.page * self.page_size
            lines = []
            for line in rows[start : start + self.page_size]:
                lines.append(f"L{line.source_line}: {line.original}")
                if line.reason:
                    lines.extend((f"  Draft: {line.draft or '(removed or unavailable)'}", f"  {line.reason}"))
            text = "\n".join(lines) or "No source transformations in this bank."
            self.page_status.text = f"Page {self.page + 1}/{pages} · {len(rows)} {'changed' if self.section == 'Source changes' else 'source'} lines · export retains the complete review"
            self.previous_action.disabled = self.page == 0
            self.next_action.disabled = self.page == pages - 1
        self.view.text = text[:96000]
        if len(text) > 96000:
            self.page_status.text += " · this page exceeds the display limit; export retains its full text"
        self.view.cursor = (0, 0)

    def export(self):
        if not self.draft or self.panel._context_key() != self.context:
            self.status.text = "Review context changed; recompile before exporting."
            return
        destination = Path.home() / ".carvera" / "bank-drafts"
        path = destination / f"bank-{self.bank.index}-{uuid.uuid4().hex}.json"
        try:
            destination.mkdir(parents=True, exist_ok=True)
            save_draft(path, self.draft)
            saved = json.loads(path.read_text())
            if saved != self.draft.to_dict():
                raise ValueError("Export readback does not match reviewed draft")
        except (ValueError, OSError) as exc:
            self.status.text = f"Export failed: {exc}"
            return
        self.status.text = f"Review JSON saved and read back: {path}. No runnable program was exported."
