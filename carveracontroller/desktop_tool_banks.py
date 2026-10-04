"""Tool-bank preparation board; no tool change, offset write or playback command."""

import copy

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, Choice, Field, Surface, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.tool_bank_review import BankReviewStore, capture_bank, inspect_bank


class ToolBankPanel(Surface):
    def __init__(self, operations, store=None):
        super().__init__(orientation="vertical", spacing=dp(7), padding=dp(10), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.operations = operations
        self.workspace = operations.workspace
        self.store = store or BankReviewStore()
        self.program, self.bank, self.record = None, None, None
        self.expected_revision = None
        self.current_context = None
        self.drafts = {}
        self._signature = None
        self.choices = {}
        self._loading = False
        self.heading = label("Prepare tool banks", 14, height=26, bold=True)
        self.add_widget(self.heading)
        self.selector = Choice(text="Choose a bank", values=())
        self.selector.bind(text=self._select_bank)
        self.add_widget(self.selector)
        self.summary = wrapped()
        self.add_widget(self.summary)
        self.stage_summary = wrapped()
        self.add_widget(self.stage_summary)
        self.grid = AdaptiveGrid(max_cols=2, min_width=240, row_height=184, spacing=dp(8))
        self.add_widget(self.grid)
        self.note = Field(hint_text="Preparation note (saved locally)", height=dp(38))
        self.add_widget(self.note)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        self.save_action = Action("Save current definitions", self.save)
        actions.add_widget(self.save_action)
        actions.add_widget(Action("Refresh evidence", self.refresh))
        actions.add_widget(Action("Reload saved preparation", self.restore))
        self.add_widget(actions)
        self.result = wrapped()
        self.add_widget(self.result)
        self.reentry = wrapped()
        self.add_widget(self.reentry)
        self.rows = []
        self.refresh()

    def context(self):
        ws = self.workspace
        machine = getattr(ws, "selected_machine_profile", None)
        profiles = getattr(ws, "profile_store", None)
        custody = getattr(ws.machine, "tool_custody", None)
        return machine, profiles.data["tools"] if profiles else [], custody

    def load(self, program):
        self._remember()
        self.program = program
        self.banks = tuple(bank for bank in program.plan_tool_banks() if bank.slots) if program else ()
        self.options = {f"Bank {b.index} · lines {b.start_line}–{b.end_line}": b for b in self.banks}
        self._loading = True
        self.selector.values = tuple(self.options)
        self.selector.text = next(iter(self.options), "Choose a bank")
        self._loading = False
        self.bank = self.banks[0] if self.banks else None
        self._activate()

    def _select_bank(self, _obj, value):
        if self._loading:
            return
        self._remember()
        self.bank = self.options.get(value)
        self._activate()

    def _remember(self):
        if self.current_context is not None:
            self.drafts[self.current_context] = copy.deepcopy(
                (self.record, self.expected_revision, self.choices, self.note.text)
            )

    def _activate(self):
        key = self._context_key()
        if key in self.drafts:
            self.current_context = key
            self.record, self.expected_revision, self.choices, note = copy.deepcopy(self.drafts[key])
            self.note.text = note
            self.result.text = "Preparation draft restored for this program, machine and bank."
            self.refresh()
        else:
            self.restore()

    def restore(self):
        machine, _profiles, _custody = self.context()
        self.current_context = self._context_key()
        self.drafts.pop(self.current_context, None)
        self.store.reload()
        self.record = (
            self.store.get(self.program.file_hash, machine["id"], self.bank.index)
            if self.program and self.bank and machine and not self.store.error
            else None
        )
        self.expected_revision = self.record["revision"] if self.record else None
        self.choices = {b["pocket"]: b["assembly_id"] for b in self.record["bindings"]} if self.record else {}
        self.note.text = self.record["note"] if self.record else ""
        self.result.text = (
            "Saved preparation restored." if self.record else "No saved preparation for this program, machine and bank."
        )
        self.refresh()

    def _context_key(self):
        machine, _profiles, _custody = self.context()
        return (
            self.program.file_hash if self.program else None,
            machine["id"] if machine else None,
            self.bank.index if self.bank else None,
        )

    def refresh_if_changed(self):
        machine, _profiles, custody = self.context()
        store = getattr(self.workspace, "profile_store", None)
        endpoint = getattr(getattr(self.workspace.machine, "controller", None), "connection_address", None)
        signature = (
            self._context_key(),
            getattr(custody, "generation", None),
            getattr(store, "generation", None),
            endpoint,
        )
        if signature != self._signature:
            self._signature = signature
            self.refresh()

    def choose(self, pocket, assembly_id):
        if self._loading:
            return
        previous_choices = dict(self.choices)
        if assembly_id:
            self.choices[pocket] = assembly_id
        else:
            self.choices.pop(pocket, None)
        machine, profiles, custody = self.context()
        try:
            new = capture_bank(self.program, self.bank, machine["id"], self.choices, custody, profiles, self.note.text)
            # Refreshing or selecting another pocket must not silently rebind an
            # existing choice to a revised assembly/design.
            old = {b["pocket"]: b for b in self.record["bindings"]} if self.record else {}
            new["bindings"] = [old.get(b["pocket"], b) if b["pocket"] != pocket else b for b in new["bindings"]]
            self.record = new
            self.result.text = "Unsaved preparation · selection does not move or declare a tool."
        except (ValueError, AttributeError, TypeError) as exc:
            self.choices = previous_choices
            self.result.text = str(exc)
        self.refresh()

    def save(self):
        machine, profiles, custody = self.context()
        try:
            if not machine or not custody or not self.program or not self.bank:
                raise ValueError("Choose a machine profile and a parsed program first")
            record = capture_bank(
                self.program, self.bank, machine["id"], self.choices, custody, profiles, self.note.text
            )
            self.store.save(record, self.expected_revision)
            self.record, self.expected_revision = record, record["revision"]
            self.result.text = "Preparation saved against current definitions. Physical mapping, measurements and re-entry remain separate checks."
        except (OSError, ValueError) as exc:
            self.result.text = str(exc)
        self.refresh()

    def review_assembly(self, pocket, tool):
        comparison = getattr(self.workspace, "tool_comparison", None)
        if comparison is None:
            return
        comparison.focus()
        comparison.choose(pocket)
        if comparison.custody.parent is None:
            comparison.toggle_custody()
        comparison.custody.selected_id = self.choices.get(pocket)
        comparison.custody.refresh(force=True)
        comparison.custody.result.text = f"Bank {self.bank.index}: candidate pocket {pocket} serves program T{tool}. Declarations and receipt attribution do not establish the controller's tool/pocket mapping."

    def preview(self, pocket, tool):
        try:
            identity = self.choices.get(pocket)
            if not identity:
                raise ValueError("Choose an assembly first")
            self.workspace.preview_assembly(identity, tool)
            self.result.text = f"Selected assembly previewed at program T{tool}; physical pocket {pocket} is unchanged."
        except (OSError, ValueError) as exc:
            self.result.text = str(exc)

    def refresh(self):
        if self._context_key() != self.current_context:
            self._remember()
            self._activate()
            return
        self.grid.clear_widgets()
        machine, profiles, custody = self.context()
        available = bool(machine and custody and self.program and self.bank)
        self.save_action.disabled = not available
        self.rows = []
        if not available:
            self.summary.text = (
                "No ATC tool changes found in this program."
                if self.program and not self.banks
                else "Choose a machine profile and a local program to prepare its physical tool banks."
            )
            self.stage_summary.text = self.store.error or "Preparation is local; no controller commands are sent."
            self.reentry.text = ""
            return
        bank = self.bank
        name = machine.get("name") or machine["id"]
        self.summary.text = f"{name} · Bank {bank.index}/{len(self.banks)} · source lines {bank.start_line}–{bank.end_line}\nParsed program {self.program.file_hash[:12]} · {'reload boundary' if bank.reload_required else 'initial loading'}"
        endpoint = str(getattr(getattr(self.workspace.machine, "controller", None), "connection_address", "") or "")
        try:
            self.rows = inspect_bank(
                self.program, bank, self.record, custody, profiles, endpoint, machine_id=machine["id"]
            )
        except ValueError as exc:
            self.stage_summary.text = str(exc)
            self.reentry.text = "Reload the matching preparation before continuing."
            return
        selected = sum(row["assembly"] is not None for row in self.rows)
        declared = sum(not any("declaration" in issue for issue in row["issues"]) for row in self.rows)
        measured = sum(bool(row["applicable"]) for row in self.rows)
        total = len(self.rows)
        self.stage_summary.text = f"1 · Assemblies {selected}/{total}    2 · Pocket declarations {declared}/{total}    3 · Attributed receipts {measured}/{total}\n4 · Controller mapping, safe stop, offset validation and re-entry are not established by this preparation."
        self.stage_summary.color = AMBER
        assembly_options = {f"{a['name']} · {a['id'][:8]}": a["id"] for a in custody.assemblies()}
        for row in self.rows:
            pocket, tool = row["pocket"], row["tool"]
            card = Surface(orientation="vertical", spacing=dp(4), padding=dp(8))
            card.add_widget(label(f"Pocket {pocket} / Program T{tool}", 12, height=24, bold=True))
            selected_id = self.choices.get(pocket)
            selected_name = next(
                (name for name, identity in assembly_options.items() if identity == selected_id), "Choose assembly"
            )
            selector = Choice(text=selected_name, values=("Choose assembly", *assembly_options), height=dp(32))
            selector.bind(text=lambda _obj, value, p=pocket: self.choose(p, assembly_options.get(value)))
            card.add_widget(selector)
            status = label(
                "\n".join(row["issues"][:2]) or "Current definition, declaration and attributed receipt", 10, MUTED, 66
            )
            card.add_widget(status)
            actions = BoxLayout(spacing=dp(5), size_hint_y=None, height=dp(32))
            actions.add_widget(Action("Details", lambda p=pocket, t=tool: self.review_assembly(p, t), height=dp(32)))
            actions.add_widget(
                Action("Preview", lambda p=pocket, t=tool: self.preview(p, t), height=dp(32), disabled=not selected_id)
            )
            card.add_widget(actions)
            self.grid.add_widget(card)
        self.reentry.text = "Reload sequence: verified stop/retract; reload physical pockets; reconcile identities; calibrate replacements; verify controller tool/pocket mapping and offsets; review re-entry.\nThe original program is not split or rewritten here; this board never starts or resumes machining."
        if self.store.error:
            self.result.text = "Persistence error: " + self.store.error
