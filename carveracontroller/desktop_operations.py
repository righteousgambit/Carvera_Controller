"""Program operations and bank review. Selection changes preview only."""

import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import ACCENT, MUTED, RAISED, Action, Surface, label
from carveracontroller.machine.program_operations import ProgramOperations


class OperationPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.generation = 0
        self.program = None
        self.selected_operation = None
        self.rows = []
        self.add_widget(label("Operations", 15, height=26, bold=True))
        self.note = label("Choose a local program to inspect operations and tool banks.", 11, MUTED, 44)
        self.add_widget(self.note)
        self.items = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None, height=0)
        self.items.bind(minimum_height=self.items.setter("height"))
        self.add_widget(self.items)
        self.detail = label("", 11, MUTED, 0)
        self.add_widget(self.detail)
        self.banks = label("", 11, MUTED, 0)
        self.add_widget(self.banks)

    def load(self, filename):
        self.generation += 1
        generation = self.generation
        self.items.clear_widgets()
        self.program = None
        self.selected_operation = None
        self.rows = []
        self.detail.text, self.detail.height = "", 0
        self.banks.text, self.banks.height = "", 0
        if not filename:
            self.note.text = "Choose a local program to inspect operations and tool banks."
            return
        self.note.text = "Reading program operations…"

        def parse():
            try:
                path = Path(filename)
                if path.stat().st_size > 64 * 1024 * 1024:
                    raise ValueError("Operation analysis limit is 64 MB")
                program = ProgramOperations.from_text(path.read_text(encoding="utf-8", errors="strict"))
                error = None
            except (OSError, ValueError, UnicodeError) as exc:
                program, error = None, str(exc)
            Clock.schedule_once(lambda _dt: self._loaded(generation, program, error), 0)

        threading.Thread(target=parse, daemon=True).start()

    def _loaded(self, generation, program, error):
        if generation != self.generation:
            return
        self.program = program
        if error:
            self.note.text = "Operations unavailable: " + error
            return
        self.note.text = f"{len(program.operations)} operations · select to inspect and seek preview"
        for operation in program.operations:
            tools = ", ".join(f"T{n}" for n in operation.tool_ids) or "No tool selected"
            duration = (
                f"{operation.estimated_seconds / 60:.1f} min nominal"
                if operation.estimated_seconds is not None
                else "Time unknown"
            )
            row = Action(
                f"{operation.name} · {tools} · {duration}", lambda op=operation: self.select(op), height=dp(36)
            )
            self.rows.append((operation, row))
            self.items.add_widget(row)
        banks = program.plan_tool_banks()
        text = []
        for bank in banks:
            assignments = " · ".join(f"Slot {slot} → T{tool}" for slot, tool in bank.slots)
            text.append(f"Bank {bank.index}: lines {bank.start_line}–{bank.end_line}\n{assignments}")
            if bank.reload_required:
                text.append("Reload required · review and reconcile physical tools before continuing")
        self.banks.text = "\n".join(text)
        self.banks.height = dp(max(44, 32 * len(text)))

    def select(self, operation):
        self.selected_operation = operation
        for item, row in self.rows:
            row.base_color = ACCENT if item.id == operation.id else RAISED
            row._paint()
        self.workspace.machine.gcode_viewer.set_distance_by_lineidx(operation.start_line, 0)
        bounds = f"\nProgram bounds (mm): {operation.bounds_mm}" if operation.bounds_mm else "\nBounds unavailable"
        warnings = "\n" + "\n".join(operation.warnings) if operation.warnings else ""
        self.detail.text = f"{operation.name} · lines {operation.start_line}–{operation.end_line}" + bounds + warnings
        self.detail.height = dp(max(64, 20 * (3 + len(operation.warnings))))
