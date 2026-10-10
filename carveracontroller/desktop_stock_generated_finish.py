"""Detached geometry-derived finishing path, complete replay and result inspection."""

from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType
from typing import cast

from kivy.clock import Clock
from kivy.graphics import Color, Line, Mesh, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.addons.manufacturing_simulation import StockVolume
from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.calculation_progress import CalculationProgress, calculation_status
from carveracontroller.machine.program_stock_evolution import StockEvolution
from carveracontroller.machine.stock_generated_finish import GeneratedFinish, generate_stock_finish
from carveracontroller.machine.stock_target import target_sections


class GeneratedPathPlot(Widget):
    def __init__(self):
        super().__init__(size_hint_y=None, height=0)
        self.plan = None
        self.plane = "XY"
        self.selected = None
        self.signature = None
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *_):
        if self.plan is None or not self.plan.moves:
            self.canvas.clear()
            self.signature = None
            self.height = 0
            return
        wanted = min(dp(260), max(dp(150), self.width * 0.56))
        if abs(self.height - wanted) > 1:
            self.height = wanted
            return
        signature = (id(self.plan), self.plane, tuple(self.pos), tuple(self.size))
        if signature != self.signature:
            axes = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}[self.plane]
            coordinates = [(p[axes[0]], p[axes[1]]) for m in self.plan.moves for p in (m.start, m.end)]
            low = tuple(min(p[a] for p in coordinates) for a in (0, 1))
            high = tuple(max(p[a] for p in coordinates) for a in (0, 1))
            scale = min(
                max(1, self.width - dp(20)) / max(high[0] - low[0], 1),
                max(1, self.height - dp(20)) / max(high[1] - low[1], 1),
            )
            origin = (
                self.x + (self.width - (high[0] - low[0]) * scale) / 2,
                self.y + (self.height - (high[1] - low[1]) * scale) / 2,
            )

            def point(p):
                return origin[0] + (p[axes[0]] - low[0]) * scale, origin[1] + (p[axes[1]] - low[1]) * scale

            self.project_point = point
            self.canvas.clear()
            with self.canvas:
                Color(0.08, 0.1, 0.13, 1)
                Rectangle(pos=self.pos, size=self.size)
                for cutting, color in ((False, (0.32, 0.38, 0.45, 1)), (True, (0.2, 0.8, 0.72, 1))):
                    vertices, indices = [], []
                    for move in self.plan.moves:
                        if move.cutting == cutting:
                            for p in (move.start, move.end):
                                indices.append(len(vertices) // 4)
                                vertices.extend((*point(p), 0, 0))
                    Color(*color)
                    Mesh(vertices=vertices, indices=indices, mode="lines")
                Color(1, 0.7, 0.25, 1)
                self.highlight = Line(points=[], width=dp(2))
            self.signature = signature
        if self.selected is not None and 0 <= self.selected < len(self.plan.moves):
            move = self.plan.moves[self.selected]
            self.highlight.points = (*self.project_point(move.start), *self.project_point(move.end))
        else:
            self.highlight.points = []


class StockGeneratedFinishControls(PlanningCard):
    def __init__(self, target):
        super().__init__("Generate finishing raster")
        from carveracontroller.desktop_stock_target import TargetPlot

        self.target = target
        self.result: GeneratedFinish | None = None
        self.generation = self.page = self.contact_page = self.section_generation = 0
        self.progress = self.progress_event = None
        self.content.add_widget(
            flowing_text(
                "Generate a layered flat-mill top-envelope path from the retained target. Compare its removal across all stock states.",
                45,
            )
        )
        options = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.tool = planning_choice(options, "Retained flat mill", ("No flat tool",))
        self.stepover = planning_field(options, "Stepover · mm", "0.5")
        self.length = planning_field(options, "Horizontal patch length · mm", "1")
        self.allowance = planning_field(options, "Axial stock allowance · mm", "0.05")
        self.stepdown = planning_field(options, "Layer depth · mm", "0.25")
        self.clearance = planning_field(options, "Above target & stock · mm", "1")
        self.content.add_widget(options)
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.generate = Action("Generate & compare", self.calculate, disabled=True)
        self.cancel_button = Action("Cancel generation", lambda: self.owner.cancel(), disabled=True)
        actions.add_widget(self.generate)
        actions.add_widget(self.cancel_button)
        self.content.add_widget(actions)
        self.status = flowing_text(
            "Compare a retained target first. Generated paths remain detached from the loaded program.", 45
        )
        self.content.add_widget(self.status)
        view = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.state = planning_choice(view, "Stock comparison state", ("No generated path",))
        self.plane = planning_choice(view, "Path & stock section", ("XY", "XZ", "YZ"))
        self.content.add_widget(view)
        self.metrics = flowing_text("No generated finishing comparison.", 45)
        self.content.add_widget(self.metrics)
        self.plot = GeneratedPathPlot()
        self.content.add_widget(self.plot)
        self.content.add_widget(
            flowing_text(
                "Teal: intended cutting · gray: transfer/retract · amber: selected move. Stock-frame millimetres; declared +Z tool axis.",
                35,
            )
        )
        self.moves = planning_choice(self.content, "All generated moves · 64 per page", ("No generated path",))
        self.moves.bind(text=self.display_move)
        paging = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous moves", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next moves", lambda: self.change_page(1), disabled=True)
        paging.add_widget(self.previous)
        paging.add_widget(self.next)
        self.content.add_widget(paging)
        self.detail = flowing_text("No selected generated move.", 45)
        self.content.add_widget(self.detail)
        support = PlanningCard("Continuous surface support witness")
        self.support = flowing_text("No retained supporting face.", 45)
        support.content.add_widget(self.support)
        self.content.add_widget(support)
        after = PlanningCard("Resulting stock & contact evidence")
        self.after_card = after
        self.section = Action("Inspect finish stock", self.view_stock, disabled=True)
        after.content.add_widget(self.section)
        after.content.add_widget(
            flowing_text(
                "Green: target · amber: remaining excess · red: missing target. Uses the selected plane and current section layer.",
                45,
            )
        )
        self.stock_plot = TargetPlot()
        after.content.add_widget(self.stock_plot)
        self.contacts = planning_choice(after.content, "All target/stock records · 64 per page", ("No contacts",))
        self.contacts.bind(text=self.display_contact)
        contact_pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.contact_previous = Action("Previous contacts", lambda: self.change_contact_page(-1), disabled=True)
        self.contact_next = Action("Next contacts", lambda: self.change_contact_page(1), disabled=True)
        contact_pages.add_widget(self.contact_previous)
        contact_pages.add_widget(self.contact_next)
        after.content.add_widget(contact_pages)
        self.witness = flowing_text("No contact evidence selected.", 45)
        after.content.add_widget(self.witness)
        self.content.add_widget(after)
        limits = PlanningCard("Generated path identity & coverage")
        self.scope = flowing_text("No retained generated path.", 45)
        limits.content.add_widget(self.scope)
        self.content.add_widget(limits)
        for field in (self.tool, self.stepover, self.length, self.allowance, self.stepdown, self.clearance):
            field.bind(text=self.clear)
        self.state.bind(text=self.display_state)
        self.plane.bind(text=self.display_state)

    @property
    def owner(self):
        return self.target.sections.surfaces.review.card.owner

    def clear(self, *_):
        self.generation += 1
        self.section_generation += 1
        self.result = None
        self.page = self.contact_page = 0
        self.state.values = ("No generated path",)
        self.state.text = self.state.values[0]
        self.plot.plan = None
        self.plot.draw()
        self.stock_plot.sections = ()
        self.stock_plot.height = 0
        self.stock_plot.draw()
        self.metrics.text = self.scope.text = "No retained generated finishing comparison."
        self.status.text = "Review the current target and generation parameters."
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
        analysis = self.target.result
        values = (
            tuple(
                f"T{n}"
                for n, g in sorted(cast(StockEvolution, analysis.target.bindings[1]).inputs.tools.items())
                if g.shape == "flat"
            )
            if analysis
            else ("No flat tool",)
        )
        self.tool.values = values or ("No flat tool",)
        if self.tool.text not in self.tool.values:
            self.tool.text = self.tool.values[0]
        self.generate.disabled = busy or analysis is None or self.tool.text == "No flat tool"
        self.cancel_button.disabled = not busy
        for field in (
            self.tool,
            self.stepover,
            self.length,
            self.allowance,
            self.stepdown,
            self.clearance,
            self.state,
            self.plane,
            self.moves,
            self.contacts,
        ):
            field.disabled = busy
        count = len(self.result.moves) if self.result else 0
        self.previous.disabled = busy or self.page == 0
        self.next.disabled = busy or (self.page + 1) * 64 >= count
        self.section.disabled = busy or self.result is None
        self.contact_previous.disabled = busy or self.contact_page == 0
        self.contact_next.disabled = busy or (self.contact_page + 1) * 64 >= len(self.records())

    def calculate(self):
        analysis = self.target.result
        if self.owner.running or analysis is None:
            return
        try:
            tool = int(self.tool.text.removeprefix("T"))
            options = {
                "stepover_mm": float(self.stepover.text),
                "patch_length_mm": float(self.length.text),
                "allowance_mm": float(self.allowance.text),
                "stepdown_mm": float(self.stepdown.text),
                "clearance_mm": float(self.clearance.text),
            }
        except ValueError:
            self.status.text = "Choose a retained flat mill and numeric millimetre parameters."
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("Generate finishing raster")
        observation = self.progress
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)

        def work(cancelled):
            def progress(name, done, total):
                if observation.snapshot()["phase"] != name:
                    observation.phase(name, total)
                observation.advance(done)

            return generate_stock_finish(
                analysis,
                tool,
                cancelled=cancelled,
                progress=progress,
                stepover_mm=options["stepover_mm"],
                patch_length_mm=options["patch_length_mm"],
                allowance_mm=options["allowance_mm"],
                stepdown_mm=options["stepdown_mm"],
                clearance_mm=options["clearance_mm"],
            )

        def complete(plan):
            if self.target.result is not analysis or self.generation != generation:
                self.status.text = "Target or generator inputs changed; complete path withheld."
                return
            self.result = plan
            self.plot.plan = plan
            self.state.values = tuple(plan.states)
            self.state.text = (
                self.target.variant.text if self.target.variant.text in plan.states else self.state.values[0]
            )
            self.page = 0
            self.status.text = f"Complete: T{plan.tool} · {len(plan.patches)} target patches / {len(plan.moves)} generated moves / {len(plan.states)} independent stock states\nDetached geometric plan; loaded program preserved."
            self.scope.text = (
                f"Target SHA256 {analysis.target.source_sha256}\nStock {analysis.target.stock} · source line {analysis.line}\n{plan.target_nodes} target nodes / {plan.target_faces} original face queries / {plan.cell_work} replay cell-work\nSolid counts {plan.solid_counts}\n"
                + "\n".join(plan.declaration_gaps)
                + "\n"
                + plan.qualification
            )
            self.display_state()
            self.render_page()

        self.owner._start(work, complete, error_target=self.status)

    def display_state(self, *_):
        self.section_generation += 1
        self.stock_plot.sections = ()
        self.stock_plot.height = 0
        self.stock_plot.draw()
        self.plot.plane = self.plane.text
        self.plot.draw()
        if self.result and self.state.text in self.result.states:
            state = self.result.states[self.state.text]
            self.metrics.text = f"{self.state.text}: remove {state.removed_mm3:.6g} mm³ · excess {state.before.excess_mm3:.6g} → {state.after.excess_mm3:.6g} mm³\nMissing target {state.before.missing_mm3:.6g} → {state.after.missing_mm3:.6g} mm³ · {len(state.contacts)} stock-contact estimates / {len(self.result.target_contacts)} shared target-body records"
        self.contact_page = 0
        self.render_contacts()

    def render_page(self):
        rows = self.result.moves if self.result else ()
        start = self.page * 64
        self.moves.values = tuple(
            f"{start + i + 1}. {m.kind} · patch {m.patch + 1} · layer {m.layer}"
            for i, m in enumerate(rows[start : start + 64])
        ) or ("No generated path",)
        self.moves.text = self.moves.values[0]
        self.display_move()
        self.set_busy(self.owner.running)

    def change_page(self, delta):
        count = len(self.result.moves) if self.result else 0
        self.page = max(0, min(max(0, (count - 1) // 64), self.page + delta))
        self.render_page()

    def display_move(self, *_):
        token = self.moves.text.partition(".")[0]
        index = int(token) - 1 if token.isdecimal() else -1
        self.plot.selected = index if index >= 0 else None
        if self.result and 0 <= index < len(self.result.moves):
            move = self.result.moves[index]
            patch = self.result.patches[move.patch]
            machine_start = tuple(a + b for a, b in zip(move.start, self.result.stock_offset_mm))
            machine_end = tuple(a + b for a, b in zip(move.end, self.result.stock_offset_mm))

            def coordinates(point):
                return ", ".join(f"{value:.6g}" for value in point)

            self.detail.text = f"Move {index + 1}: {move.kind} · layer {move.layer}\nStock start ({coordinates(move.start)}) mm\nStock end ({coordinates(move.end)}) mm\nIntended machine tip ({coordinates(machine_start)}) to ({coordinates(machine_end)}) mm\nPatch {move.patch + 1} · finish height {patch.tip_z_mm:g} mm · Axial allowance {self.result.allowance_mm:g} mm."
            if patch.witness is not None:
                self.support.text = f"Patch {move.patch + 1}: continuous square footprint {patch.rectangle}\nExact supporting target triangle {patch.witness.triangle}\nPoint {patch.witness.point}\nBarycentric {patch.witness.barycentric}\nMaximum over all clipped target faces, containing the circular cutter throughout the horizontal patch.\nAxial allowance {self.result.allowance_mm:g} mm + numerical margin {self.result.numerical_margin_mm:g} mm; upward-rounded tip {patch.tip_z_mm!r} mm. Displayed coordinates above are rounded."
            else:
                self.support.text = "No retained supporting face."
        else:
            self.detail.text = "No selected generated move."
            self.support.text = "No retained supporting face."
        self.plot.draw()

    def records(self):
        if self.result is None or self.state.text not in self.result.states:
            return ()
        return tuple(("target", r) for r in self.result.target_contacts) + tuple(
            ("stock", r) for r in self.result.states[self.state.text].contacts
        )

    def render_contacts(self):
        rows = self.records()
        start = self.contact_page * 64
        self.contacts.values = tuple(
            f"{start + i + 1}. {kind} · move {r.move + 1} · {r.contact.component}"
            for i, (kind, r) in enumerate(rows[start : start + 64])
        ) or ("No contact records",)
        self.contacts.text = self.contacts.values[0]
        self.display_contact()
        self.set_busy(self.owner.running)

    def change_contact_page(self, delta):
        self.contact_page = max(0, min(max(0, (len(self.records()) - 1) // 64), self.contact_page + delta))
        self.render_contacts()

    def display_contact(self, *_):
        token = self.contacts.text.partition(".")[0]
        index = int(token) - 1 if token.isdecimal() else -1
        rows = self.records()
        if not 0 <= index < len(rows):
            self.witness.text = "No detected declared contact in this result. Coverage gaps remain explicit."
            return
        kind, row = rows[index]
        self.page = row.move // 64
        self.render_page()
        self.moves.text = self.moves.values[row.move % 64]
        contact = row.contact
        if hasattr(contact, "triangle"):
            self.witness.text = f"Target {contact.component} · move {row.move + 1} · original face {contact.triangle}\nFeasible pose {contact.witness.sample}\nPoint {contact.witness.point}; barycentric {contact.witness.barycentric}\nRetained witness is not certified earliest entry."
        elif hasattr(contact, "classification"):
            self.witness.text = (
                f"Target {contact.component}: {contact.classification} at {contact.point_program_mm} mm."
            )
        else:
            self.witness.text = f"Stock {contact.component} · move {row.move + 1}\nGrid estimate t={contact.first_fraction}; tip {contact.first_tip}\nBounds {contact.obstacle_bounds}\nRecorded before removal; simulation does not qualify this contact for machining."

    def view_stock(self):
        plan = self.result
        if self.owner.running or plan is None or self.state.text not in plan.states:
            return
        label, plane = self.state.text, self.plane.text
        try:
            raw = self.target.sections.layer.text.strip()
            layer = int(raw) if raw else None
        except ValueError:
            self.status.text = "Section layer must be an integer or blank."
            return
        generation = self.section_generation
        detached = replace(plan.analysis, fits=MappingProxyType({label: plan.states[label].after}))

        def work(cancelled):
            grid = StockVolume.from_snapshot(plan.analysis.target.target, cancelled=cancelled)
            return target_sections(detached, label, plane, layer, cancelled=cancelled), grid.shape

        def complete(output):
            if self.result is not plan or self.section_generation != generation:
                self.status.text = "Generated result view changed; section withheld."
                return
            self.stock_plot.sections, self.stock_plot.grid_shape = output
            self.stock_plot.draw()

        self.owner._start(work, complete, error_target=self.status)
