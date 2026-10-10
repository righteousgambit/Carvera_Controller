"""Whole retained-stock allowance summary with direct worst-cell navigation."""

from __future__ import annotations

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice
from carveracontroller.machine.calculation_progress import CalculationProgress, calculation_status
from carveracontroller.machine.stock_allowance_summary import AllowanceSummary, summarize_target_allowance


class StockAllowanceSummaryControls(PlanningCard):
    def __init__(self, target):
        super().__init__("Whole-stock allowance summary")
        self.target = target
        self.result: AllowanceSummary | None = None
        self.generation = 0
        self.progress = None
        self.progress_event = None
        self.queries = 0
        self.calculate_button = Action("Summarize all states", self.calculate, disabled=True)
        self.content.add_widget(self.calculate_button)
        self.status = flowing_text("Compare a declared part target first. All excess/missing centers are included.", 45)
        self.content.add_widget(self.status)
        self.state = planning_choice(self.content, "Inspect state", ("No allowance summary",))
        self.state.bind(text=self.display)
        self.metrics = flowing_text("No retained summary.", 45)
        self.content.add_widget(self.metrics)
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.excess = Action("Show excess peak", lambda: self.show_peak("excess"), disabled=True)
        self.missing = Action("Show missing peak", lambda: self.show_peak("missing"), disabled=True)
        actions.add_widget(self.excess)
        actions.add_widget(self.missing)
        self.content.add_widget(actions)
        details = PlanningCard("Summary identity & limits")
        self.details = flowing_text("No retained summary.", 45)
        details.content.add_widget(self.details)
        self.content.add_widget(details)

    def clear(self):
        self.generation += 1
        self.result = None
        self.state.values = ("No allowance summary",)
        self.state.text = self.state.values[0]
        self.metrics.text = self.details.text = "No retained summary."
        self.status.text = "Summarize the current complete target comparison."
        self.display()

    def tick_progress(self, *_):
        owner = self.target.sections.surfaces.review.card.owner
        if not owner.running or owner.closed:
            self.stop_progress()
            return
        if self.progress is not None:
            self.status.text = (
                calculation_status(self.progress.snapshot(), cancelling=owner.cancel_event.is_set()).replace(
                    "segments", "state-cell visits"
                )
                + f" · {self.queries} center queries"
            )

    def stop_progress(self):
        if self.progress_event is not None:
            self.progress_event.cancel()
            self.progress_event = None
        if self.progress is not None:
            self.progress.finish("stopped")

    def set_busy(self, busy):
        if not busy:
            self.stop_progress()
        self.calculate_button.disabled = busy or self.target.result is None
        self.state.disabled = busy
        state = self.result.states.get(self.state.text) if self.result else None
        self.excess.disabled = busy or state is None or state.excess_peak is None
        self.missing.disabled = busy or state is None or state.missing_peak is None

    def display(self, *_):
        state = self.result.states.get(self.state.text) if self.result else None
        if state:
            lines = [f"{self.state.text} · {state.excess_centers} excess / {state.missing_centers} missing centers"]
            for title, peak in (("Largest excess", state.excess_peak), ("Deepest missing", state.missing_peak)):
                if peak is None:
                    lines.append(f"{title}: no centers in this category")
                else:
                    low, high = peak.cell_distance_interval_mm
                    lines.append(
                        f"{title}: signed {peak.signed_center_distance_mm:.6g} mm · cell {peak.cell}\nCell interval [{low:.6g}, {high:.6g}] mm · source triangle {peak.nearest.triangle} ({peak.nearest.feature})"
                    )
            self.metrics.text = "\n".join(lines)
        self.set_busy(self.target.sections.surfaces.review.card.owner.running)

    def calculate(self):
        owner = self.target.sections.surfaces.review.card.owner
        analysis = self.target.result
        if owner.running or analysis is None:
            return
        generation = self.generation
        self.status.text = "Computing complete all-state excess and missing distances…"
        self.stop_progress()
        self.progress = CalculationProgress("Target allowance masks")
        self.queries = 0
        self.progress_event = Clock.schedule_interval(self.tick_progress, 0.25)

        def work(cancelled):
            observation = self.progress
            begun = False

            def progress(done, total, queries):
                nonlocal begun
                self.queries = queries
                if observation is not None:
                    if not begun:
                        observation.phase("All-state target allowance", total)
                        begun = True
                    observation.advance(done)

            return summarize_target_allowance(analysis, cancelled=cancelled, progress=progress)

        def complete(result):
            if self.target.result is not analysis or self.generation != generation:
                self.status.text = "Target comparison changed; complete summary withheld."
                return
            self.result = result
            self.status.text = f"Complete: {result.cell_work} state-cell visits · {result.center_queries} unique center queries\nPositive distance is excess outside target; negative distance is missing inside target."
            self.state.values = tuple(result.states)
            self.state.text = (
                self.target.variant.text if self.target.variant.text in result.states else self.state.values[0]
            )
            self.details.text = (
                f"Target SHA256 {analysis.target.source_sha256}\nStock {analysis.target.stock} · source line {analysis.line} · move {analysis.segment_index}\n{result.distance_nodes} hierarchy nodes / {result.distance_faces} triangle minima\nCell half diagonal {result.half_diagonal_mm:.6g} mm\n"
                + result.qualification
            )
            self.display()

        owner._start(work, complete, error_target=self.status)

    def show_peak(self, category):
        owner = self.target.sections.surfaces.review.card.owner
        if owner.running or self.result is None or self.target.result is not self.result.analysis:
            return
        state = self.result.states.get(self.state.text)
        if state is None:
            return
        peak = state.excess_peak if category == "excess" else state.missing_peak
        if peak is None:
            return
        self.target.variant.text = self.state.text
        plane = self.target.sections.plane.text
        layer_axis = {"XY": 2, "XZ": 1, "YZ": 0}[plane]
        self.target.sections.layer.text = str(peak.cell[layer_axis])
        self.target.view_section(selected_cell=peak.cell)
