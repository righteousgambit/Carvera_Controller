"""Tool-bank preparation board; no tool change, offset write or playback command."""

import copy
import time

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import AMBER, MUTED, Action, AdaptiveGrid, Choice, Field, Surface, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_bank_review import BankReviewStore, capture_bank, inspect_bank, mapped_offset_status


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
        filter_row = AdaptiveGrid(max_cols=2, min_width=170, row_height=34, spacing=dp(6))
        self.filter_choice = Choice(
            text="All pockets", values=("All pockets", "Missing evidence", "Selected assemblies")
        )
        self.filter_choice.bind(text=lambda *_: self.refresh())
        filter_row.add_widget(self.filter_choice)
        self.visible_count = label("", 11, MUTED, 34)
        filter_row.add_widget(self.visible_count)
        self.add_widget(filter_row)
        self.grid = AdaptiveGrid(max_cols=2, min_width=240, row_height=210, spacing=dp(8))
        self.add_widget(self.grid)
        self.note = Field(hint_text="Preparation note (saved locally)", height=dp(38))
        self.add_widget(self.note)
        actions = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(6))
        self.save_action = Action("Save preparation", self.save)
        actions.add_widget(self.save_action)
        actions.add_widget(Action("Refresh evidence", self.refresh))
        actions.add_widget(Action("Reload saved", self.restore))
        self.add_widget(actions)
        self.program_review_action = Action("Review mapped bank program", self.review_program)
        self.add_widget(self.program_review_action)
        self.result = wrapped()
        self.add_widget(self.result)
        self.reentry = wrapped()
        self.add_widget(self.reentry)
        self.rows = []
        self.evidence_review = None
        self.refresh()

    def context(self):
        ws = self.workspace
        machine = getattr(ws, "selected_machine_profile", None)
        profiles = getattr(ws, "profile_store", None)
        custody = getattr(ws.machine, "tool_custody", None)
        return machine, profiles.data["tools"] if profiles else [], custody

    def review_program(self):
        if not self.program or not self.bank:
            return
        from carveracontroller.desktop_bank_programs import BankProgramReview

        previous = getattr(self, "program_review", None)
        if previous:
            previous.dismiss()
        self.program_review = BankProgramReview(self)
        self.program_review.open()

    def load(self, program):
        previous = getattr(self, "program_review", None)
        if previous:
            previous.dismiss()
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
        previous = getattr(self, "program_review", None)
        if previous:
            previous.dismiss()
        self._remember()
        self.bank = self.options.get(value)
        self._activate()

    def _remember(self):
        if self.current_context is not None:
            self.drafts[self.current_context] = copy.deepcopy(
                (self.record, self.expected_revision, self.choices, self.note.text)
            )

    def _activate(self):
        if self.evidence_review:
            self.evidence_review.dismiss()
        previous = getattr(self, "program_review", None)
        if previous:
            previous.dismiss()
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
        pose = getattr(getattr(self.workspace.machine, "controller", None), "observed_pose", None)
        observed = (
            (pose.fresh(time.monotonic()), pose.tool, pose.tool_length_mm) if isinstance(pose, ObservedPose) else None
        )
        signature = (
            self._context_key(),
            getattr(custody, "generation", None),
            getattr(store, "generation", None),
            endpoint,
            observed,
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

    def review_evidence(self, pocket):
        if self.evidence_review:
            self.evidence_review.dismiss()
        self.evidence_review = PocketEvidenceReview(self, pocket)
        self.add_widget(self.evidence_review, index=self.children.index(self.grid))
        Clock.schedule_once(self.evidence_review.reveal, 0)

    def refresh(self):
        if self._context_key() != self.current_context:
            self._remember()
            self._activate()
            return
        self.grid.clear_widgets()
        machine, profiles, custody = self.context()
        available = bool(machine and custody and self.program and self.bank)
        self.save_action.disabled = not available
        self.program_review_action.disabled = not bool(self.program and self.bank)
        self.rows = []
        if not available:
            self.summary.text = (
                "No ATC tool changes found in this program."
                if self.program and not self.banks
                else "Choose a machine profile and a local program to prepare its physical tool banks."
            )
            self.stage_summary.text = self.store.error or "Preparation is local; no controller commands are sent."
            self.reentry.text = ""
            self.visible_count.text = "No pockets to review"
            if self.evidence_review:
                self.evidence_review.dismiss()
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
            self.visible_count.text = "Evidence unavailable"
            if self.evidence_review:
                self.evidence_review.refresh()
            return
        selected = sum(row["assembly"] is not None for row in self.rows)
        declared = sum(not any("declaration" in issue for issue in row["issues"]) for row in self.rows)
        measured = sum(bool(row["applicable"]) for row in self.rows)
        controller_measured = sum(bool(row["controller_applicable"]) for row in self.rows)
        pose = getattr(getattr(self.workspace.machine, "controller", None), "observed_pose", None)
        for row in self.rows:
            row["offset_status"] = mapped_offset_status(row, pose, time.monotonic())
        matched = sum(row["offset_status"]["state"] == "matched" for row in self.rows)
        total = len(self.rows)
        self.stage_summary.text = (
            f"1 · Assemblies {selected}/{total}    2 · Pocket declarations {declared}/{total}"
            f"    3 · Logical-tool receipts {measured}/{total}\n"
            f"Mapped controller receipts after declared placement {controller_measured}/{total}. "
            f"Current-spindle TLO comparisons {matched}/{total}.\n"
            "Controller mapping, safe stop and re-entry remain unverified; TLO comparison does not identify physical tools."
        )
        self.stage_summary.color = AMBER
        assembly_options = {f"{a['name']} · {a['id'][:8]}": a["id"] for a in custody.assemblies()}
        visible_rows = [
            row
            for row in self.rows
            if self.filter_choice.text == "All pockets"
            or (self.filter_choice.text == "Missing evidence" and (row["issues"] or not row["controller_applicable"]))
            or (self.filter_choice.text == "Selected assemblies" and row["assembly"] is not None)
        ]
        self.visible_count.text = f"{len(visible_rows)} / {total} pockets shown"
        if self.evidence_review:
            self.evidence_review.refresh()
        for row in visible_rows:
            pocket, tool = row["pocket"], row["tool"]
            card = Surface(orientation="vertical", spacing=dp(4), padding=dp(8))
            card.add_widget(
                label(f"Pocket {pocket} · Program T{tool} / Controller T{pocket}", 12, height=24, bold=True)
            )
            selected_id = self.choices.get(pocket)
            selected_name = next(
                (name for name, identity in assembly_options.items() if identity == selected_id), "Choose assembly"
            )
            selector = Choice(text=selected_name, values=("Choose assembly", *assembly_options), height=dp(32))
            selector.bind(text=lambda _obj, value, p=pocket: self.choose(p, assembly_options.get(value)))
            card.add_widget(selector)
            status = label(
                (
                    f"Controller T{pocket} receipt: "
                    + (
                        "after declared placement"
                        if row["controller_applicable"]
                        else "missing after declared placement"
                    )
                    + "\n"
                    + row["offset_status"]["detail"]
                    + "\n"
                    + ("\n".join(row["issues"][:2]) or "Current definition, declaration and logical-tool receipt")
                ),
                10,
                MUTED,
                88,
            )
            card.add_widget(status)
            actions = BoxLayout(spacing=dp(5), size_hint_y=None, height=dp(32))
            actions.add_widget(Action("Evidence", lambda p=pocket: self.review_evidence(p), height=dp(32)))
            actions.add_widget(Action("Assembly", lambda p=pocket, t=tool: self.review_assembly(p, t), height=dp(32)))
            actions.add_widget(
                Action("Preview", lambda p=pocket, t=tool: self.preview(p, t), height=dp(32), disabled=not selected_id)
            )
            card.add_widget(actions)
            self.grid.add_widget(card)
        self.reentry.text = (
            "Local preparation only · review pocket evidence and the mapped bank program before any reload."
        )
        if self.store.error:
            self.result.text = "Persistence error: " + self.store.error


class PocketEvidenceReview(Surface):
    """Concentrated local review of every issue and attributed raw receipt."""

    def __init__(self, panel, pocket):
        super().__init__(orientation="vertical", spacing=dp(6), padding=dp(10), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.panel, self.pocket = panel, pocket
        self.receipt_index = 0
        self.sample_page = 0
        self._scroll_reset = Clock.create_trigger(self._reset_view, 0)
        self.heading = wrapped()
        self.add_widget(self.heading)
        controls = AdaptiveGrid(max_cols=3, min_width=130, row_height=32, spacing=dp(5))
        self.section = Choice(text="Assessment", values=("Assessment", "Raw receipts"), height=dp(32))
        self.section.bind(text=lambda *_: self.refresh())
        controls.add_widget(self.section)
        controls.add_widget(Action("Refresh evidence", panel.refresh, height=dp(32)))
        controls.add_widget(Action("Close evidence", self.dismiss, height=dp(32)))
        self.add_widget(controls)
        self.view = Field(multiline=True, readonly=True, height=dp(220))
        self.add_widget(self.view)
        self.navigation = AdaptiveGrid(max_cols=4, min_width=130, row_height=32, spacing=dp(5))
        self.receipt_previous = Action("Previous receipt", lambda: self.turn_receipt(-1), height=dp(32))
        self.receipt_next = Action("Next receipt", lambda: self.turn_receipt(1), height=dp(32))
        self.samples_previous = Action("Previous samples", lambda: self.turn_samples(-1), height=dp(32))
        self.samples_next = Action("Next samples", lambda: self.turn_samples(1), height=dp(32))
        for action in (self.receipt_previous, self.receipt_next, self.samples_previous, self.samples_next):
            self.navigation.add_widget(action)
        self.refresh()

    def turn_receipt(self, direction):
        self.receipt_index += direction
        self.sample_page = 0
        self.refresh()

    def turn_samples(self, direction):
        self.sample_page += direction
        self.refresh()

    def reveal(self, _dt):
        ancestor = self.parent
        while ancestor is not None:
            if isinstance(ancestor, ScrollView):
                ancestor.scroll_to(self, padding=dp(8), animate=False)
                break
            ancestor = ancestor.parent

    def _reset_view(self, _dt):
        # Kivy queues text relayout and cursor-to-end after assignment. Reset
        # after that work, and reject callbacks belonging to a closed review.
        if self.parent is not None and self.panel.evidence_review is self:
            self.view.cursor = (0, 0)
            self.view.scroll_y = 0

    def dismiss(self):
        self._scroll_reset.cancel()
        if self.parent:
            self.parent.remove_widget(self)
        if self.panel.evidence_review is self:
            self.panel.evidence_review = None

    def refresh(self):
        previous_text = self.view.text
        row = next((r for r in self.panel.rows if r["pocket"] == self.pocket), None)
        if row is None:
            self.heading.text = "Pocket evidence unavailable · refresh the matching bank"
            self.view.text = "No current bank row. This view sends no machine commands."
            self._scroll_reset()
            for action in self.navigation.children:
                action.disabled = True
            return
        self.heading.text = f"Pocket {self.pocket} · Program T{row['tool']} / Controller T{row['controller_tool']}"
        assembly, profile = row["assembly"], row["profile"]
        if self.section.text == "Assessment":
            issues = row["issues"]
            self.view.text = (
                "Assembly: "
                + (assembly["name"] if assembly else "not selected")
                + "\nAssembly ID: "
                + (assembly["id"] if assembly else "—")
                + "\nRevision: "
                + (assembly["revision_id"] if assembly else "—")
                + "\nCutter: "
                + (profile["name"] if profile else "missing")
                + f"\nLogical-tool receipts: {len(row['applicable'])}"
                + f"\nMapped receipts after placement: {len(row['controller_applicable'])}"
                + "\n\n"
                + row["offset_status"]["detail"]
                + "\n\nUnresolved preparation checks:\n"
                + (
                    "\n".join(f"• {issue}" for issue in issues)
                    if issues
                    else "No definition/declaration/logical-receipt issues."
                )
                + (
                    "\n• No mapped controller receipt after declared placement"
                    if not row["controller_applicable"]
                    else ""
                )
                + "\n\nReload sequence: verified stop/retract; reload physical pockets; reconcile identities; calibrate replacements; verify controller tool/pocket mapping and offsets; review re-entry."
                + "\n\nNumeric TLO agreement does not identify a physical tool. Controller mapping, safe stop, re-entry and cutting qualification remain separate checks."
            )
        else:
            reports = row["reports"]
            if not reports:
                self.view.text = "No calibration receipts attributed to this assembly revision."
                for action in self.navigation.children:
                    action.disabled = True
            else:
                self.receipt_index = max(0, min(self.receipt_index, len(reports) - 1))
                receipt = reports[self.receipt_index]
                report = receipt["report"]
                samples = report["measurements"]
                pages = max(1, (len(samples) + 79) // 80)
                self.sample_page = max(0, min(self.sample_page, pages - 1))
                begin = self.sample_page * 80
                logical = {r["id"] for r in row["applicable"]}
                mapped = {r["id"] for r in row["controller_applicable"]}
                roles = [
                    name
                    for name, identities in (("logical tool", logical), ("mapped controller tool", mapped))
                    if receipt["id"] in identities
                ]
                self.view.text = (
                    f"Receipt {self.receipt_index + 1}/{len(reports)} · {receipt['id']}"
                    f"\nEndpoint: {receipt['endpoint']} · reported T{receipt['tool_number']}"
                    f"\nCaptured: {receipt['at']:g} · measured: {report['timestamp']:g}"
                    f"\nApplied TLO: {report.get('applied')} mm · spread: {report['max_delta']:g} mm"
                    + "\nCurrent applicability: "
                    + (", ".join(roles) or "neither logical nor mapped current receipt")
                    + f"\n\nRaw samples (mm), page {self.sample_page + 1}/{pages} · "
                    f"samples {begin + 1}–{min(begin + 80, len(samples))}/{len(samples)}:\n"
                    + ", ".join(f"{v:g}" for v in samples[begin : begin + 80])
                )
                self.receipt_previous.disabled = self.receipt_index == 0
                self.receipt_next.disabled = self.receipt_index == len(reports) - 1
                self.samples_previous.disabled = self.sample_page == 0
                self.samples_next.disabled = self.sample_page == pages - 1
        if self.section.text == "Raw receipts":
            if self.navigation.parent is None:
                self.add_widget(self.navigation)
        elif self.navigation.parent:
            self.remove_widget(self.navigation)
        if self.view.text != previous_text:
            self._scroll_reset()
