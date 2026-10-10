"""Candidate-tool access matrix, retained witnesses and direct cell navigation."""

from __future__ import annotations

from collections import Counter

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.calculation_progress import CalculationProgress, calculation_status
from carveracontroller.machine.stock_tool_reach import ToolReachStudy, review_tool_reach


class StockToolReachControls(PlanningCard):
    def __init__(self, target):
        super().__init__("Compare candidate-tool access")
        self.target = target
        self.result: ToolReachStudy | None = None
        self.summaries = {}
        self.generation = self.page = self.contact_page = 0
        self.progress = self.progress_event = None
        self.content.add_widget(
            flowing_text(
                "Review every excess-stock cell across all states. Compare retained cutters and locate the limiting target or noncutting body.",
                45,
            )
        )
        fields = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.candidates = planning_field(fields, "Candidate tool IDs · blank = all", "")
        self.clearance = planning_field(fields, "Above stock/target · mm", "1")
        self.content.add_widget(fields)
        for field in (self.candidates, self.clearance):
            field.bind(text=self.clear)
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.review = Action("Compare tool access", self.calculate, disabled=True)
        self.cancel_button = Action("Cancel comparison", lambda: self.owner.cancel(), disabled=True)
        actions.add_widget(self.review)
        actions.add_widget(self.cancel_button)
        self.content.add_widget(actions)
        self.status = flowing_text("Compare a part target first. No toolpaths or machine commands are generated.", 45)
        self.content.add_widget(self.status)
        filters = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.state = planning_choice(filters, "Retained stock state", ("No study",))
        self.tool = planning_choice(filters, "Candidate cutter", ("No study",))
        self.content.add_widget(filters)
        self.state.bind(text=self.filter_changed)
        self.tool.bind(text=self.filter_changed)
        self.metrics = flowing_text("No candidate-tool access retained.", 45)
        self.content.add_widget(self.metrics)
        self.cells = planning_choice(self.content, "All excess cells · 64 per page", ("No study",))
        self.cells.bind(text=self.display_witness)
        paging = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous cells", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next cells", lambda: self.change_page(1), disabled=True)
        paging.add_widget(self.previous)
        paging.add_widget(self.next)
        self.content.add_widget(paging)
        self.show = Action("Inspect selected cell", self.show_cell, disabled=True)
        self.content.add_widget(self.show)
        self.details = flowing_text("Select a cell to inspect its retained contact evidence.", 45)
        self.content.add_widget(self.details)
        witnesses = PlanningCard("Complete contact witnesses")
        self.witness_card = witnesses
        self.contact = planning_choice(witnesses.content, "All records · 64 per page", ("No contact",))
        self.contact.bind(text=self.display_contact)
        contact_pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.contact_previous = Action("Previous witnesses", lambda: self.change_contact_page(-1), disabled=True)
        self.contact_next = Action("Next witnesses", lambda: self.change_contact_page(1), disabled=True)
        contact_pages.add_widget(self.contact_previous)
        contact_pages.add_widget(self.contact_next)
        witnesses.content.add_widget(contact_pages)
        self.witness = flowing_text("No contact witness selected.", 45)
        witnesses.content.add_widget(self.witness)
        self.content.add_widget(witnesses)
        scope = PlanningCard("Access coverage & limits")
        self.scope = flowing_text("No retained study.", 45)
        scope.content.add_widget(self.scope)
        self.content.add_widget(scope)

    @property
    def owner(self):
        return self.target.sections.surfaces.review.card.owner

    def clear(self, *_):
        self.generation += 1
        self.result = None
        self.summaries = {}
        self.page = 0
        self.state.values = self.tool.values = ("No study",)
        self.state.text = self.tool.text = "No study"
        self.status.text = "Review the current complete target comparison and candidate tools."
        self.metrics.text = self.scope.text = "No retained study."
        self.render_page()

    def stop_progress(self):
        if self.progress_event is not None:
            self.progress_event.cancel()
            self.progress_event = None
        if self.progress is not None:
            self.progress.finish("stopped")

    def tick(self, *_):
        if not self.owner.running or self.owner.closed:
            self.stop_progress()
        elif self.progress is not None:
            self.status.text = calculation_status(
                self.progress.snapshot(), cancelling=self.owner.cancel_event.is_set()
            ).replace("segments", "work items")

    def set_busy(self, busy):
        if not busy:
            self.stop_progress()
        self.review.disabled = busy or self.target.result is None
        self.cancel_button.disabled = not busy
        for control in (self.candidates, self.clearance, self.state, self.tool, self.cells, self.contact):
            control.disabled = busy
        count = len(self.current_rows())
        self.previous.disabled = busy or self.page == 0
        self.next.disabled = busy or (self.page + 1) * 64 >= count
        self.show.disabled = busy or self.selected_row() is None
        self.contact_previous.disabled = busy or self.contact_page == 0
        self.contact_next.disabled = busy or (self.contact_page + 1) * 64 >= len(self.current_contacts())

    def current_rows(self):
        if self.result is None or self.state.text not in self.result.states or not self.tool.text.startswith("T"):
            return ()
        return self.result.states[self.state.text].get(int(self.tool.text[1:]), ())

    def selected_row(self):
        if not self.cells.text.partition(".")[0].isdigit():
            return None
        index = int(self.cells.text.partition(".")[0]) - 1
        rows = self.current_rows()
        return rows[index] if 0 <= index < len(rows) else None

    def filter_changed(self, *_):
        self.page = 0
        if self.result is not None and self.state.text in self.summaries and self.tool.text.startswith("T"):
            counts = self.summaries[self.state.text].get(int(self.tool.text[1:]), {})
            self.metrics.text = (
                "\n".join(f"{name}: {count} cells" for name, count in counts.items()) or "No excess-stock centers."
            )
        self.render_page()

    def render_page(self):
        start = self.page * 64
        rows = self.current_rows()
        self.cells.values = tuple(
            f"{start + i + 1}. {row.query.cell} · {row.status} · {', '.join(row.limiting_components) or 'no contact'}"
            for i, row in enumerate(rows[start : start + 64])
        ) or ("No excess cells",)
        self.cells.text = self.cells.values[0]
        self.display_witness()
        self.set_busy(self.owner.running)

    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.current_rows()) - 1) // 64), self.page + delta))
        self.render_page()

    def display_witness(self, *_):
        row = self.selected_row()
        if row is None:
            self.details.text = "No excess-cell access outcome selected."
        else:
            q = row.query
            self.details.text = (
                f"{self.state.text} · T{q.tool} · cell {q.cell}\n{row.status}\n"
                f"Program +Z {q.start_program_mm} → {q.end_program_mm} mm\n"
                f"{len(q.target_contacts)} target-face witnesses / {len(q.containment)} containment witnesses / {len(row.stock_contacts)} stock-body estimates\n"
                + "\n".join(q.declaration_gaps + q.model_notes)
            )
            if q.target_contacts:
                c = q.target_contacts[0]
                self.details.text += f"\nFirst retained face record: {c.component}, original triangle {c.triangle}, feasible t={c.witness.sample}, barycentric {c.witness.barycentric}. Not an earliest-entry certificate."
            if row.stock_contacts:
                c = row.stock_contacts[0]
                self.details.text += f"\nStock body: {c.component}, estimated fraction {c.first_fraction}; {c.method}"
        self.show.disabled = self.owner.running or row is None
        self.contact_page = 0
        self.render_contacts()

    def current_contacts(self):
        row = self.selected_row()
        return row.query.target_contacts + row.query.containment + row.stock_contacts if row else ()

    def render_contacts(self):
        start = self.contact_page * 64
        records = self.current_contacts()
        self.contact.values = tuple(
            f"{start + i + 1}. {c.component} · "
            + (
                f"target triangle {c.triangle}"
                if hasattr(c, "triangle")
                else f"target {c.classification}"
                if hasattr(c, "classification")
                else "stock body estimate"
            )
            for i, c in enumerate(records[start : start + 64])
        ) or ("No contact",)
        self.contact.text = self.contact.values[0]
        self.display_contact()
        self.contact_previous.disabled = self.owner.running or self.contact_page == 0
        self.contact_next.disabled = self.owner.running or start + 64 >= len(records)

    def change_contact_page(self, delta):
        self.contact_page = max(0, min(max(0, (len(self.current_contacts()) - 1) // 64), self.contact_page + delta))
        self.render_contacts()

    def display_contact(self, *_):
        records = self.current_contacts()
        index = int(self.contact.text.partition(".")[0]) - 1 if self.contact.text.partition(".")[0].isdigit() else -1
        if not 0 <= index < len(records):
            self.witness.text = "No retained contact for this cell/tool/state. Coverage gaps still apply."
            return
        c = records[index]
        if hasattr(c, "triangle"):
            self.witness.text = f"{c.component} · original target triangle {c.triangle}\nFeasible pose t={c.witness.sample}\nExact point {c.witness.point}\nBarycentric {c.witness.barycentric}\nSquared radial distance {c.witness.radial_distance_squared}\nThis witness is not a certified first-entry time."
        elif hasattr(c, "classification"):
            self.witness.text = f"{c.component} · target {c.classification}\nClosed-solid point {c.point_program_mm} mm"
        else:
            self.witness.text = f"{c.component} · {c.obstacle}\nGrid body estimate at t={c.first_fraction}\nTip {c.first_tip}\nObstacle bounds {c.obstacle_bounds}\n{c.method}"

    def calculate(self):
        analysis = self.target.result
        if self.owner.running or analysis is None:
            return
        try:
            tools = (
                tuple(int(n.strip().removeprefix("T")) for n in self.candidates.text.split(","))
                if self.candidates.text.strip()
                else None
            )
            clearance = float(self.clearance.text)
        except ValueError:
            self.status.text = "Use comma-separated retained tool IDs and a finite clearance in mm."
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("Candidate-tool access")
        observation = self.progress
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)

        def work(cancelled):
            def progress(name, done, total):
                if observation.snapshot()["phase"] != name:
                    observation.phase(name, total)
                observation.advance(done)

            result = review_tool_reach(analysis, tools, clearance_mm=clearance, cancelled=cancelled, progress=progress)
            summaries = {
                label: {n: dict(Counter(row.status for row in rows)) for n, rows in tools.items()}
                for label, tools in result.states.items()
            }
            return result, summaries

        def complete(delivery):
            if self.target.result is not analysis or self.generation != generation:
                self.status.text = "Target or tool inputs changed; complete study withheld."
                return
            result, self.summaries = delivery
            self.result = result
            self.state.values = tuple(result.states)
            self.tool.values = tuple(f"T{n}" for n in result.tools)
            self.tool.text = self.tool.values[0]
            self.state.text = (
                self.target.variant.text if self.target.variant.text in result.states else self.state.values[0]
            )
            self.status.text = f"Complete: {result.logical_outcomes} state/tool/cell outcomes · {result.unique_queries} shared target chords\n{result.target_nodes} target nodes / {result.target_faces} face queries; {result.cell_work} complete cell-work bound."
            self.scope.text = (
                f"Target SHA256 {analysis.target.source_sha256}\nStock {analysis.target.stock} · move {analysis.segment_index} · source line {analysis.line}\nSolid counts {result.solid_counts}\n"
                + result.qualification
            )
            self.filter_changed()

        self.owner._start(work, complete, error_target=self.status)

    def show_cell(self):
        row = self.selected_row()
        if self.owner.running or row is None or self.result is None or self.target.result is not self.result.analysis:
            return
        self.target.variant.text = self.state.text
        axis = {"XY": 2, "XZ": 1, "YZ": 0}[self.target.sections.plane.text]
        self.target.sections.layer.text = str(row.query.cell[axis])
        self.target.view_section(selected_cell=row.query.cell)
        self.target.allowance.tool.text = f"T{row.query.tool}"
