"""Background bank compilation and source-linked review; never dispatches."""

import json
import threading
import uuid
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Field, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.bank_programs import compile_bank, save_draft


class BankProgramReview(Popup):
    def __init__(self, panel, **kwargs):
        self.panel = panel
        self.context = panel._context_key()
        self.program, self.bank = panel.program, panel.bank
        self.generation, self.draft = 0, None
        body = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        super().__init__(title="Review bank program", content=body, size_hint=(0.86, 0.9), **kwargs)
        body.add_widget(label("Logical tools and controller pockets", 16, height=30, bold=True))
        self.convention = Choice(
            text="Automatic tool offsets (no H mapping)",
            values=("Automatic tool offsets (no H mapping)", "H indexes match logical T numbers"),
        )
        self.convention.bind(text=lambda *_: self.compile())
        body.add_widget(self.convention)
        self.status = wrapped()
        body.add_widget(self.status)
        self.view = Field(multiline=True, readonly=True, size_hint_y=1)
        body.add_widget(self.view)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        self.export_action = Action("Export review JSON", self.export)
        actions.add_widget(self.export_action)
        actions.add_widget(Action("Recompile", self.compile))
        actions.add_widget(Action("Close", self.dismiss))
        body.add_widget(actions)
        self.bind(on_dismiss=lambda *_: setattr(self, "generation", self.generation + 1))
        self.compile()

    def compile(self):
        self.generation += 1
        generation = self.generation
        self.draft = None
        self.export_action.disabled = True
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
        mapping = "\n".join(
            f"Logical T{tool} -> controller T{pocket} / pocket {pocket}" for tool, pocket in draft.mapping
        )
        changes = []
        for line in draft.lines[:300]:
            changes.append(f"L{line.source_line}: {line.original}")
            if line.reason:
                changes.extend((f"  Draft: {line.draft or '(removed or unavailable)'}", f"  {line.reason}"))
        if len(draft.lines) > 300:
            changes.append(f"Showing first 300/{len(draft.lines)} lines; export includes every line.")
        preview = (
            mapping
            + "\n\nINHERITED MODAL STATE (no approach or spindle restart)\n"
            + "\n".join(draft.modal_restoration)
            + "\n\nREQUIRED REVIEW\n"
            + "\n".join((*draft.errors, *draft.cautions))
            + "\n\nSOURCE / DRAFT COMPARISON\n"
            + "\n".join(changes)
        )
        self.view.text = preview[:96000] + (
            "\nDisplay truncated; export contains full review." if len(preview) > 96000 else ""
        )
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
