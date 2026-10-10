"""Detached all-move machine clearance with source-linked evidence navigation."""

from __future__ import annotations

from typing import Any

from kivy.clock import Clock
from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.calculation_progress import CalculationProgress, calculation_status
from carveracontroller.machine.program_surface_clearance import (
    contact_triangles,
    group_member_contact,
    occupancy_witness,
    rotating_witness,
)
from carveracontroller.machine.stock_generated_clearance import GeneratedMachineClearance, review_generated_finish


class GeneratedMachineControls(PlanningCard):
    def __init__(self, generated):
        super().__init__("Whole-path machine clearance")
        from carveracontroller.desktop_program_surfaces import SurfaceContactPlot

        self.generated = generated
        self.result: GeneratedMachineClearance | None = None
        self.rows: tuple[tuple[str, Any], ...] = ()
        self.generation = self.page = 0
        self.progress = self.progress_event = None
        self.content.add_widget(
            flowing_text(
                "Review every generated move against the retained moving machine, workholding and ATC. Keeps the generated stock comparisons and loaded program separate.",
                45,
            )
        )
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.review = Action("Review whole path", self.calculate, disabled=True)
        self.cancel_button = Action("Cancel review", lambda: self.owner.cancel(), disabled=True)
        actions.add_widget(self.review)
        actions.add_widget(self.cancel_button)
        self.content.add_widget(actions)
        self.status = flowing_text("Generate a retained finishing comparison first.", 40)
        self.content.add_widget(self.status)
        self.choice = planning_choice(self.content, "All machine results · 64 per page", ("No machine review",))
        self.choice.bind(text=self.select)
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous results", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next results", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        self.pair = planning_field(self.content, "Original triangle pair · zero based", "0")
        self.pair.bind(text=self.select)
        self.detail = flowing_text("No machine result selected.", 45)
        self.content.add_widget(self.detail)
        self.plot = SurfaceContactPlot()
        self.content.add_widget(self.plot)
        scope = PlanningCard("Whole-path identity & coverage")
        self.scope = flowing_text("No retained generated machine review.", 45)
        scope.content.add_widget(self.scope)
        self.content.add_widget(scope)

    @property
    def owner(self):
        return self.generated.owner

    def clear(self):
        self.generation += 1
        self.result = None
        self.rows = ()
        self.page = 0
        self.status.text = "Generate or review the current complete finishing path."
        self.scope.text = "No retained generated machine review."
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
        self.review.disabled = busy or self.generated.result is None
        self.cancel_button.disabled = not busy
        self.choice.disabled = busy
        self.pair.disabled = busy
        self.previous.disabled = busy or self.page == 0
        self.next.disabled = busy or (self.page + 1) * 64 >= len(self.rows)

    def calculate(self):
        plan = self.generated.result
        parent = self.generated.target.sections.surfaces.result
        if self.owner.running or plan is None or parent is None:
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("Whole generated machine path")
        observation = self.progress
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)

        def work(cancelled):
            def progress(phase, done, total):
                if observation.snapshot()["phase"] != phase:
                    observation.phase(phase, total)
                observation.advance(done)

            result = review_generated_finish(plan, parent, cancelled=cancelled, progress=progress)
            scene = result.scene
            rows = (
                tuple(("group", r) for r in scene.groups)
                + tuple(("solid", r) for r in scene.occupancy)
                + tuple(("rotating", r) for r in scene.rotating)
                + tuple(("gap", r) for r in scene.gaps)
            )
            return result, rows

        def complete(delivery):
            if (
                self.generation != generation
                or self.generated.result is not plan
                or self.generated.target.sections.surfaces.result is not parent
            ):
                self.status.text = "Generated path, target or machine review changed; complete result withheld."
                return
            self.result, self.rows = delivery
            scene = self.result.scene
            self.page = 0
            self.status.text = f"Complete: {len(plan.moves)} moves · T{plan.tool} · {len(self.result.included_bodies)} bodies\n{scene.refined_pairs} CAD pairs / {scene.rigid_reused_pairs} verified geometric queries reused\n{len(scene.groups)} contact groups · {len(scene.occupancy)} solid intervals · {len(scene.rotating)} rotating records · {len(scene.gaps)} geometry gaps / {len(plan.declaration_gaps)} assembly notes. Inspect evidence before machining."
            self.scope.text = (
                f"Proposal SHA256 {self.result.proposal_sha256}\nTarget SHA256 {plan.analysis.target.source_sha256}\nSelected initial stock replaced: {self.result.replaced_initial_stock}\nIncluded: {', '.join(self.result.included_bodies)}\nBroad: {scene.body_review.tested_pairs} pair memberships / {scene.body_review.intervals} unique intervals\nCAD: {scene.nodes} nodes / {scene.triangle_pairs} face pairs · unique groups/members {scene.group_counts}\n{len(plan.states)} independent stock-state comparisons remain attached; no current physical stock claim.\n"
                + "\n".join(plan.declaration_gaps)
                + "\n"
                + self.result.qualification
            )
            self.render_page()

        self.owner._start(work, complete, error_target=self.status)

    def render_page(self):
        start = self.page * 64
        self.choice.values = tuple(
            f"{start + i + 1}. {kind} · move {r.segment_index + 1}"
            for i, (kind, r) in enumerate(self.rows[start : start + 64])
        ) or ("No machine results",)
        self.choice.text = self.choice.values[0]
        self.select()
        self.set_busy(self.owner.running)

    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.rows) - 1) // 64), self.page + delta))
        self.pair.text = "0"
        self.render_page()

    def select(self, *_):
        self.plot.geometry = ()
        self.plot.height = 0
        token = self.choice.text.partition(".")[0]
        index = int(token) - 1 if token.isdecimal() else -1
        if self.result is None or not 0 <= index < len(self.rows):
            self.detail.text = "No machine result selected."
            self.plot.draw()
            return
        kind, row = self.rows[index]
        scene = self.result.scene
        move = self.result.plan.moves[row.segment_index]
        self.generated.page = row.segment_index // 64
        self.generated.render_page()
        self.generated.moves.text = self.generated.moves.values[row.segment_index % 64]
        names = f"{row.first} / {row.second}"
        self.detail.text = f"Move {row.segment_index + 1}: {move.kind} · layer {move.layer} · T{row.tool}\n{names}\n"
        if kind == "group":
            try:
                member = int(self.pair.text)
                if not 0 <= member < len(row.group.triangle_pairs):
                    raise ValueError("Triangle pair index outside the complete contact group")
                self.plot.geometry = contact_triangles(scene, group_member_contact(row, member))
                self.plot.primary_count = 1
                self.detail.text += f"Exact contact interval [{row.group.lower}, {row.group.upper}]\nPair {member + 1}/{len(row.group.triangle_pairs)} · original faces {row.group.triangle_pairs[member]}\nNominal midpoint; XY left / XZ right."
            except ValueError as exc:
                self.detail.text += str(exc)
        elif kind == "solid":
            self.detail.text += f"Closed solid {row.interval.state} · [{row.interval.lower}, {row.interval.upper}]"
            witness = occupancy_witness(scene, row)
            if witness is not None:
                self.plot.geometry = ((witness, witness, witness),)
                self.plot.primary_count = 1
        elif kind == "rotating":
            self.plot.geometry, witness = rotating_witness(scene, row)
            self.plot.primary_count = max(1, len(self.plot.geometry) - 1)
            self.detail.text += f"Section {row.result.section_index + 1} · {row.result.state}\nOriginal face {row.result.witness_triangle} · world witness {witness}\nExistence witness, not certified earliest contact. {row.result.reason}"
        else:
            self.detail.text += row.reason
        self.plot.height = dp(180) if self.plot.geometry else 0
        self.plot.draw()
