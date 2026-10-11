"""Reviewed-tool stock continuation comparison; no current-scene mutation."""

from __future__ import annotations

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.program_stock_inspection import reconstruct_stock_move
from carveracontroller.machine.stock_finishing import FinishContact, FinishingComparison, compare_stock_continuation


class StockFinishControls(PlanningCard):
    def __init__(self, sections):
        super().__init__("Compare finishing continuation")
        self.sections = sections
        self.result: FinishingComparison | None = None
        self.tool_ids: tuple[int, ...] = ()
        options = AdaptiveGrid(max_cols=2, min_width=145, row_height=78, spacing=dp(6))
        self.tool = planning_choice(options, "Substitute reviewed tool", ("No reviewed tool",))
        self.end_line = planning_field(options, "Through source line · blank = end", "")
        self.tool.bind(text=self.invalidate)
        self.end_line.bind(text=self.invalidate)
        self.content.add_widget(options)
        self.compare = Action("Compare following moves", self.calculate, disabled=True)
        self.content.add_widget(self.compare)
        self.status = flowing_text(
            "Select a stock-history move. Compare the following intended tip path with one reviewed tool.", 45
        )
        self.content.add_widget(self.status)
        limits = PlanningCard("Comparison scope & limits")
        limits.content.add_widget(
            flowing_text(
                "Both variants start from the same reconstructed stock and follow the same intended tip path. "
                "One uses the planned tools; the other substitutes one reviewed tool. Planned material is a comparison "
                "baseline, not a nominal finished-part target. Cell-center removal does not prove physical clearance. "
                "Machine/fixture collision, changed tool-length joint poses, forces, ATC and execution are separate. "
                "Uncertified curve chords retain material in both variants.",
                65,
            )
        )
        self.content.add_widget(limits)
        self.contacts = planning_choice(self.content, "Retained stock contact", ("No comparison",))
        self.contacts.bind(text=self.show_contact)
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous contacts", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next contacts", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        self.detail = flowing_text("", 0)
        self.content.add_widget(self.detail)
        self.source = Action("Inspect contact source", self.inspect_source, disabled=True)
        self.content.add_widget(self.source)
        self.page = 0
        self.rows: tuple[tuple[str, FinishContact], ...] = ()

    def invalidate(self, *_):
        self.result = None
        if hasattr(self.sections, "part_target"):
            self.sections.part_target.invalidate_fit()
        self.rows = ()
        self.page = 0
        self.contacts.values = ("No comparison",)
        self.contacts.text = "No comparison"
        self.detail.text = ""
        self.previous.disabled = self.next.disabled = self.source.disabled = True

    def clear(self):
        self.invalidate()
        review = self.sections.surfaces.result
        self.tool_ids = tuple(sorted(review.stock_evolution.inputs.tools)) if review and review.stock_evolution else ()
        self.tool.values = tuple(f"T{number}" for number in self.tool_ids) or ("No reviewed tool",)
        if self.tool.text not in self.tool.values:
            self.tool.text = self.tool.values[0]
        self.status.text = "Select a stock-history move. Compare planned tools and a substituted tool on the following intended tip path."

    def set_busy(self, busy):
        row = self.sections.target
        review = self.sections.surfaces.result
        self.tool.disabled = self.end_line.disabled = busy
        self.compare.disabled = (
            busy
            or row is None
            or review is None
            or not self.tool_ids
            or row.segment_index + 1 >= len(review.body_review.segments)
        )

    def calculate(self):
        surfaces = self.sections.surfaces
        owner = surfaces.review.card.owner
        review, row = surfaces.result, self.sections.target
        if owner.running or review is None or row is None or review.stock_evolution is None:
            return
        try:
            if self.tool.text not in self.tool.values or not self.tool_ids:
                raise ValueError("Choose a tool from this retained review")
            number = self.tool_ids[self.tool.values.index(self.tool.text)]
            text = self.end_line.text.strip()
            if text and (not text.isascii() or not text.isdecimal()):
                raise ValueError("Source line must be an integer or blank for the end")
            end = int(text) if text else None
        except (ValueError, TypeError) as exc:
            self.status.text = str(exc)
            return
        signature = (self.tool.text, self.end_line.text)
        cached = self.sections.cached_state(review, row)
        self.status.text = "Comparing both following tip paths against remaining stock…"

        def work(cancelled):
            state = cached or reconstruct_stock_move(
                review.body_review,
                review.stock_evolution,
                review.rotating_envelopes,
                row.second,
                row.segment_index,
                cancelled=cancelled,
            )
            return state, compare_stock_continuation(
                review.body_review,
                review.stock_evolution,
                review.rotating_envelopes,
                state,
                row.second,
                number,
                end,
                cancelled=cancelled,
            )

        def complete(output):
            state, comparison = output
            if (
                surfaces.result is not review
                or self.sections.target is not row
                or (self.tool.text, self.end_line.text) != signature
            ):
                self.status.text = "Selection changed during comparison; result withheld."
                return
            self.sections.remember_state(review, row, state)
            self.result = comparison
            self.sections.part_target.invalidate_fit()
            self.status.text = (
                f"{comparison.stock} · following move {state.segment_index + 1}, through L{comparison.end_line}\n"
                f"Planned tools: remove {comparison.planned.removed_mm3:.6g}; leave {comparison.planned.remaining_mm3:.6g} mm³\n"
                f"T{number}: remove {comparison.candidate.removed_mm3:.6g}; leave {comparison.candidate.remaining_mm3:.6g} mm³\n"
                f"Versus plan: {comparison.extra_removed_mm3:.6g} mm³ extra removal; {comparison.extra_remaining_mm3:.6g} mm³ extra stock\n"
                f"Stock contacts: planned {len(comparison.planned.contacts)}; T{number} {len(comparison.candidate.contacts)}\n"
                "Stock-only cell estimate; planned result is not a nominal part target."
            )
            self.rows = tuple(("planned", r) for r in comparison.planned.contacts) + tuple(
                (f"T{number}", r) for r in comparison.candidate.contacts
            )
            self.page = 0
            self.refresh_contacts()
            self.sections.set_busy(False)

        owner._start(work, complete, error_target=self.status)

    def refresh_contacts(self):
        start = self.page * 64
        self.contacts.values = tuple(
            f"{start + index + 1} · {kind} L{row.line} · {row.contact.component}"
            for index, (kind, row) in enumerate(self.rows[start : start + 64])
        ) or ("No stock contact estimates",)
        self.contacts.text = self.contacts.values[0]
        self.previous.disabled = self.page == 0
        self.next.disabled = start + 64 >= len(self.rows)
        self.show_contact()

    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.rows) - 1) // 64), self.page + delta))
        self.refresh_contacts()

    def show_contact(self, *_):
        self.source.disabled = not self.rows or self.contacts.text not in self.contacts.values
        if self.source.disabled:
            return
        kind, row = self.rows[self.page * 64 + self.contacts.values.index(self.contacts.text)]
        contact = row.contact
        self.detail.text = (
            f"{kind} · L{row.line} T{row.tool} · {contact.component}\n"
            f"Estimated chord entry: {contact.first_fraction}; source parameter: {contact.source_ratio}\n"
            "Stock-local envelope contact before removal; machine and fixture clearance are separate."
        )

    def inspect_source(self):
        if self.result is None or self.source.disabled:
            return
        surfaces = self.sections.surfaces
        panel = surfaces.review.card.owner.workspace.operation_panel
        if panel.program is None or panel.program.file_hash != surfaces.result.body_review.program_hash:
            self.status.text = "Loaded source differs; contact navigation withheld."
            return
        _, row = self.rows[self.page * 64 + self.contacts.values.index(self.contacts.text)]
        panel.inspect_line(row.line, seek=True)
