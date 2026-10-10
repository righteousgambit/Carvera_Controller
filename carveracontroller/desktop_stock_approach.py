"""Detached full-machine approach review beside retained target/stock evidence."""

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
from carveracontroller.machine.stock_approach_clearance import ApproachClearance, review_stock_approach


class StockApproachControls(PlanningCard):
    def __init__(self, allowance):
        super().__init__("Full machine approach")
        # Lazy import avoids the enclosing surface/stock-card import cycle.
        from carveracontroller.desktop_program_surfaces import SurfaceContactPlot

        self.allowance = allowance
        self.result: ApproachClearance | None = None
        self.generation = self.page = 0
        self.rows: tuple[tuple[str, Any], ...] = ()
        self.progress = self.progress_event = None
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.calculate_button = Action("Review machine", self.calculate, disabled=True)
        self.cancel_button = Action("Cancel review", lambda: self.owner.cancel(), disabled=True)
        actions.add_widget(self.calculate_button)
        actions.add_widget(self.cancel_button)
        self.content.add_widget(actions)
        self.status = flowing_text("Inspect a declared tool approach first. This detached review sends no motion.", 45)
        self.content.add_widget(self.status)
        self.choice = planning_choice(self.content, "Machine results · 64 per page", ("No machine review",))
        self.choice.bind(text=self.select)
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous results", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next results", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        self.pair = planning_field(self.content, "Original triangle pair · zero based", "0")
        self.pair.bind(text=self.select)
        self.detail = flowing_text("No retained machine result.", 40)
        self.content.add_widget(self.detail)
        self.plot = SurfaceContactPlot()
        self.content.add_widget(self.plot)
        scope = PlanningCard("Included geometry & review identity")
        self.scope = flowing_text("No retained machine result.", 40)
        scope.content.add_widget(self.scope)
        self.content.add_widget(scope)

    @property
    def owner(self):
        return self.allowance.target.sections.surfaces.review.card.owner

    def clear(self):
        self.generation += 1
        self.result = None
        self.rows = ()
        self.page = 0
        self.status.text = "Inspect the current tool approach before full machine review."
        self.detail.text = self.scope.text = "No retained machine result."
        self.render_page()
        self.set_busy(self.owner.running)

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
            self.status.text = calculation_status(self.progress.snapshot(), cancelling=self.owner.cancel_event.is_set())

    def set_busy(self, busy):
        if not busy:
            self.stop_progress()
        inspection = self.allowance.result
        self.calculate_button.disabled = busy or inspection is None or inspection.approach is None
        self.cancel_button.disabled = not busy or self.progress_event is None
        self.choice.disabled = self.pair.disabled = busy
        self.previous.disabled = busy or self.page == 0
        self.next.disabled = busy or (self.page + 1) * 64 >= len(self.rows)

    def calculate(self):
        inspection = self.allowance.result
        parent = self.allowance.target.sections.surfaces.result
        if self.owner.running or inspection is None or inspection.approach is None or parent is None:
            return
        generation = self.generation
        self.stop_progress()
        self.progress = CalculationProgress("Full machine CAD / solids")
        self.progress_event = Clock.schedule_interval(self.tick, 0.25)
        self.status.text = "Reviewing full declared machine geometry continuously…"

        def complete(result):
            if (
                self.generation != generation
                or self.allowance.result is not inspection
                or self.allowance.target.sections.surfaces.result is not parent
            ):
                self.status.text = "Cell, stock or machine review changed; approach withheld."
                return
            self.result = result
            scene = result.scene
            self.rows = (
                tuple(("group", row) for row in scene.groups)
                + tuple(("solid", row) for row in scene.occupancy)
                + tuple(("rotating", row) for row in scene.rotating)
                + tuple(("gap", row) for row in scene.gaps)
            )
            self.page = 0
            self.status.text = f"T{inspection.approach.tool} · {len(result.included_bodies)} declared bodies · {scene.triangles} triangles\n{len(scene.groups)} contact groups · {len(scene.occupancy)} solid intervals · {len(scene.rotating)} rotating results · {len(scene.gaps)} geometry gaps\nTarget: {len(inspection.approach.target_contacts)} contacts; remaining stock: {len(inspection.approach.stock_contacts)} noncutting estimates."
            self.scope.text = (
                f"Proposal SHA256 {result.proposal_sha256}\nMachine tip {result.machine_start_mm} → {result.machine_end_mm} mm\nSelected initial stock replaced: {result.replaced_initial_stock}\nIncluded: {', '.join(result.included_bodies)}\n"
                + result.qualification
                + "\nTool coverage: "
                + "; ".join(inspection.approach.coverage)
            )
            self.render_page()
            self.set_busy(False)

        self.owner._start(
            lambda cancelled: review_stock_approach(inspection, parent, cancelled=cancelled),
            complete,
            error_target=self.status,
        )

    def render_page(self):
        start = self.page * 64
        self.choice.values = tuple(
            f"{start + i + 1}. {kind} · {getattr(row, 'first', getattr(row, 'cylinder', 'tool'))} / {getattr(row, 'second', getattr(row, 'other', 'geometry'))}"
            for i, (kind, row) in enumerate(self.rows[start : start + 64])
        ) or ("No machine review" if self.result is None else "No results within declared coverage",)
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
        index = self.page * 64 + (
            self.choice.values.index(self.choice.text) if self.choice.text in self.choice.values else 0
        )
        if self.result is None or index >= len(self.rows):
            self.plot.draw()
            return
        kind, row = self.rows[index]
        scene = self.result.scene
        self.pair.disabled = kind != "group" or self.owner.running
        self.detail.text = (
            f"Detached candidate insertion · T{row.tool}\n{row.first} / {row.second}\n"
            if hasattr(row, "first")
            else f"Detached candidate insertion · T{row.tool}\n{row.cylinder} / {row.other}\n"
        )
        if kind == "group":
            try:
                member = int(self.pair.text)
                if not 0 <= member < len(row.group.triangle_pairs):
                    raise ValueError("Triangle pair index outside this complete contact group")
                contact = group_member_contact(row, member)
                self.plot.geometry = contact_triangles(scene, contact)
                self.plot.primary_count = 1
                self.detail.text += f"Contact parameter [{float(row.group.lower):.6g}, {float(row.group.upper):.6g}]\nPair {member + 1} / {len(row.group.triangle_pairs)} · original triangles {row.group.triangle_pairs[member]}\nNominal midpoint pose · XY left / XZ right. Exact interval remains in the retained report."
            except ValueError as exc:
                self.detail.text += str(exc)
        elif kind == "solid":
            self.detail.text += f"Closed solid {row.interval.state}\nParameter [{float(row.source_lower_ratio):.6g}, {float(row.source_upper_ratio):.6g}] · open endpoints retain possible surface contacts."
            witness = occupancy_witness(scene, row)
            if witness:
                self.plot.geometry = ((witness, witness, witness),)
                self.plot.primary_count = 1
        elif kind == "rotating":
            self.detail.text += f"Declared rotating section {row.result.section_index + 1} · {row.result.state.replace('_', ' ')}\nOriginal obstacle triangle {row.result.witness_triangle}"
            self.plot.geometry, witness = rotating_witness(scene, row)
            if witness is not None:
                self.detail.text += (
                    f"\nWorld witness {tuple(round(v, 6) for v in witness)} mm · existence witness, not first contact."
                )
            if row.result.reason:
                self.detail.text += "\n" + row.result.reason
            self.plot.primary_count = max(1, len(self.plot.geometry) - 1)
        else:
            self.detail.text += row.reason
        self.plot.height = dp(180) if self.plot.geometry else 0
        self.plot.draw()
