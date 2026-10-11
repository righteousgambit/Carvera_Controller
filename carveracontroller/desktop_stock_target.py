"""Source-bound part target comparison inside the retained stock workbench."""

from __future__ import annotations

from math import ceil, floor
from pathlib import Path

from kivy.graphics import Color, Line, Mesh, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.desktop_stock_allowance import StockAllowanceControls
from carveracontroller.desktop_stock_allowance_summary import StockAllowanceSummaryControls
from carveracontroller.desktop_stock_generated_finish import StockGeneratedFinishControls
from carveracontroller.desktop_stock_tool_reach import StockToolReachControls
from carveracontroller.machine.program_stock_inspection import StockSection, reconstruct_stock_move
from carveracontroller.machine.stock_target import (
    StockTarget,
    TargetAnalysis,
    analyze_stock_target,
    prepare_stock_target,
    target_sections,
)


class TargetPlot(Widget):
    height: float

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=0, **kwargs)
        self.sections: tuple[StockSection, ...] = ()
        self.pick_cell = None
        self.grid_shape = (1, 1, 1)
        self.selected = None
        self.frame = None
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *_):
        self.canvas.clear()
        self.frame = None
        if not self.sections:
            return
        low_x, low_y, high_x, high_y = self.sections[0].bounds
        width, height = high_x - low_x, high_y - low_y
        margin = dp(8)
        wanted = min(dp(280), max(dp(70), (self.width - 2 * margin) * height / width + 2 * margin))
        if abs(self.height - wanted) > 1:
            self.height = wanted
        scale = min(max(1, self.width - 2 * margin) / width, max(1, self.height - 2 * margin) / height)
        x, y = self.x + (self.width - width * scale) / 2, self.y + (self.height - height * scale) / 2
        self.frame = x, y, width * scale, height * scale
        with self.canvas:
            Color(0.1, 0.13, 0.16, 1)
            Rectangle(pos=(x, y), size=(width * scale, height * scale))
        for section, color in zip(self.sections, ((0.17, 0.48, 0.42, 1), (1, 0.67, 0.25, 1), (0.91, 0.29, 0.36, 1))):
            vertices, indices = [], []
            for left, bottom, right, top in section.remaining:
                at = len(vertices) // 4
                for u, v in ((left, bottom), (right, bottom), (right, top), (left, top)):
                    vertices.extend((x + (u - low_x) * scale, y + (v - low_y) * scale, 0, 0))
                indices.extend((at, at + 1, at + 2, at, at + 2, at + 3))
            with self.canvas:
                Color(*color)
                Mesh(vertices=vertices, indices=indices, mode="triangles")
        with self.canvas:
            Color(0.5, 0.58, 0.65, 1)
            Line(rectangle=(x, y, width * scale, height * scale), width=dp(1))

        if self.selected is not None:
            u, v = self.selected
            axes = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}[self.sections[0].plane]
            cw, ch = width * scale / self.grid_shape[axes[0]], height * scale / self.grid_shape[axes[1]]
            with self.canvas:
                Color(0.85, 0.93, 1, 1)
                Line(rectangle=(x + u * cw, y + v * ch, cw, ch), width=dp(2))

    def select_at(self, px, py):
        if self.frame is None or not self.sections or self.pick_cell is None:
            return False
        x, y, width, height = self.frame
        if not x <= px < x + width or not y <= py < y + height:
            return False
        section = self.sections[0]
        u, v, layer = {"XY": (0, 1, 2), "XZ": (0, 2, 1), "YZ": (1, 2, 0)}[section.plane]
        cell = [0, 0, 0]
        cell[u] = min(self.grid_shape[u] - 1, floor((px - x) / width * self.grid_shape[u]))
        cell[v] = min(self.grid_shape[v] - 1, floor((py - y) / height * self.grid_shape[v]))
        cell[layer] = section.layer
        if self.pick_cell(tuple(cell)) is False:
            return False
        self.selected = cell[u], cell[v]
        self.draw()
        return True

    def on_touch_down(self, touch):
        if self.select_at(*touch.pos):
            return True
        return super().on_touch_down(touch)


class StockTargetControls(PlanningCard):
    def __init__(self, sections):
        super().__init__("Compare actual part target")
        self.sections = sections
        self.target: StockTarget | None = None
        self.result: TargetAnalysis | None = None
        self.generation = self.display_generation = 0
        self.content.add_widget(
            flowing_text(
                "Declare a closed STL in this stock's grid coordinates, before stock rotation/tilt and WCS placement.",
                45,
            )
        )
        self.path = planning_field(self.content, "Part target STL", "")
        self.pick = Action("Choose part STL…", self.choose)
        self.content.add_widget(self.pick)
        options = AdaptiveGrid(max_cols=2, min_width=145, row_height=78, spacing=dp(6))
        self.units = planning_choice(options, "STL source units", ("Choose source units", "mm", "inch"))
        self.translation = planning_field(options, "Translation X, Y, Z · mm", "0, 0, 0")
        self.content.add_widget(options)
        for field in (self.path, self.units, self.translation):
            field.bind(text=self.clear)
        self.compare = Action("Load & compare target", self.calculate, disabled=True)
        self.reload = Action("Reload target bytes", lambda: self.calculate(reload=True), disabled=True)
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        actions.add_widget(self.compare)
        actions.add_widget(self.reload)
        self.content.add_widget(actions)
        self.status = flowing_text("No part target retained. No automatic centering or clipping.", 45)
        self.content.add_widget(self.status)
        self.variant = planning_choice(self.content, "Display stock state", ("No target comparison",))
        self.variant.bind(text=self.display_changed)
        self.view = Action("View target section", self.view_section, disabled=True)
        self.content.add_widget(self.view)
        self.legend = flowing_text(
            "Green: part target · amber: excess stock · red: missing target material. Uses section plane/layer above.",
            45,
        )
        self.content.add_widget(self.legend)
        self.plot = TargetPlot()
        self.content.add_widget(self.plot)
        self.allowance = StockAllowanceControls(self)
        self.plot.pick_cell = self.pick_cell
        self.content.add_widget(self.allowance)
        self.allowance_summary = StockAllowanceSummaryControls(self)
        self.content.add_widget(self.allowance_summary)
        self.tool_reach = StockToolReachControls(self)
        self.content.add_widget(self.tool_reach)
        self.generated_finish = StockGeneratedFinishControls(self)
        self.content.add_widget(self.generated_finish)
        limits = PlanningCard("Target identity & limits")
        self.scope = flowing_text("No retained target.", 35)
        limits.content.add_widget(self.scope)
        self.content.add_widget(limits)

    def pick_cell(self, cell):
        if self.sections.surfaces.review.card.owner.running:
            return False
        self.allowance.select_cell(cell)
        return True

    def choose(self):
        owner = self.sections.surfaces.review.card.owner
        if owner.running:
            return
        owner.workspace.choose_asset_file(
            lambda path: setattr(self.path, "text", str(path)),
            suffixes=(".stl",),
            title="Choose nominal part target STL",
        )

    def invalidate_fit(self, *_):
        self.generation += 1
        self.result = None
        self.allowance_summary.clear()
        self.tool_reach.clear()
        self.generated_finish.clear()
        if hasattr(self, "status"):
            self.status.text = "Target comparison cleared; compare the current selection."
        self.variant.values = ("No target comparison",)
        self.variant.text = self.variant.values[0]
        self.display_changed()

    def clear(self, *_):
        self.target = None
        self.invalidate_fit()
        self.scope.text = "No retained target."
        self.status.text = "No part target retained. Explicit units and placement required."
        self.set_busy(self.sections.surfaces.review.card.owner.running)

    def selection_changed(self):
        row = self.sections.target
        if self.target is not None and (row is None or row.second != self.target.stock):
            self.target = None
            self.scope.text = "No retained target for this stock selection."
        self.invalidate_fit()
        self.status.text = (
            "Compare this selected move against the retained target."
            if self.target
            else "Load a target for the selected stock instance."
        )
        self.set_busy(self.sections.surfaces.review.card.owner.running)

    def display_changed(self, *_):
        self.display_generation += 1
        self.plot.sections = ()
        self.plot.selected = None
        self.allowance.clear()
        self.plot.height = 0
        self.plot.draw()
        self.view.disabled = self.result is None

    def set_busy(self, busy):
        for control in (self.path, self.pick, self.units, self.translation):
            control.disabled = busy
        self.compare.disabled = busy or self.sections.target is None
        self.reload.disabled = busy or self.target is None or self.sections.target is None
        self.variant.disabled = busy
        self.view.disabled = busy or self.result is None
        self.compare.text = "Compare target" if self.target else "Load & compare target"
        self.allowance.set_busy(busy)
        self.allowance_summary.set_busy(busy)
        self.tool_reach.set_busy(busy)
        self.generated_finish.set_busy(busy)

    def calculate(self, *, reload=False):
        surfaces = self.sections.surfaces
        owner = surfaces.review.card.owner
        review, row = surfaces.result, self.sections.target
        if owner.running or review is None or row is None or review.stock_evolution is None:
            return
        try:
            if self.units.text not in ("mm", "inch") or not self.path.text.strip():
                raise ValueError("Choose a target STL and explicitly select its source units")
            translation = tuple(float(v.strip()) for v in self.translation.text.split(","))
            if len(translation) != 3:
                raise ValueError("Translation needs X, Y, Z in mm")
        except ValueError as exc:
            self.status.text = str(exc)
            return
        signature = (self.path.text, self.units.text, self.translation.text)
        cached = self.sections.cached_state(review, row)
        retained = None if reload else self.target
        comparison = self.sections.finishing.result
        generation = self.generation
        self.status.text = "Validating closed target and comparing complete stock grids…"

        def work(cancelled):
            state = cached or reconstruct_stock_move(
                review.body_review,
                review.stock_evolution,
                review.rotating_envelopes,
                row.second,
                row.segment_index,
                cancelled=cancelled,
            )
            target = retained or prepare_stock_target(
                state,
                row.second,
                signature[0].strip(),
                units=signature[1],
                translation_mm=translation,
                cancelled=cancelled,
            )
            return state, analyze_stock_target(target, state, comparison, cancelled=cancelled)

        def complete(output):
            state, result = output
            if (
                surfaces.result is not review
                or self.generation != generation
                or self.sections.target is not row
                or signature != (self.path.text, self.units.text, self.translation.text)
                or self.sections.finishing.result is not comparison
            ):
                self.status.text = "Review, selection or comparison changed; target result withheld."
                return
            self.sections.remember_state(review, row, state)
            self.target, self.result = result.target, result
            self.allowance.clear()
            self.allowance_summary.clear()
            self.tool_reach.clear()
            self.generated_finish.clear()
            self.status.text = (
                f"{Path(result.target.source_path).name} · target centers {result.target_grid_mm3:.6g} mm³\n"
                + "\n".join(
                    f"{label}: excess {fit.excess_mm3:.6g}; missing {fit.missing_mm3:.6g}; newly missing {result.newly_missing_mm3[label]:.6g} mm³"
                    for label, fit in result.fits.items()
                )
                + "\nMissing centers indicate potential overcut/insufficient stock; physical result unverified."
            )
            self.scope.text = (
                f"{result.target.source_path}\nSHA256 {result.target.source_sha256}\nSource {result.target.source_units} · translation {result.target.translation_mm} mm\n"
                f"Closed solid volume {result.target.solid_volume_mm3:.6g} mm³ · {result.cell_work} cell-work\n"
                + result.qualification
            )
            self.variant.values = tuple(result.fits)
            self.variant.text = "After selected move"
            self.allowance.refresh_tools()
            self.set_busy(False)

        owner._start(work, complete, error_target=self.status)

    def view_section(self, *, selected_cell=None):
        owner = self.sections.surfaces.review.card.owner
        result, label = self.result, self.variant.text
        if owner.running or result is None or label not in result.fits:
            return
        try:
            layer = int(self.sections.layer.text) if self.sections.layer.text.strip() else None
            if layer is not None and (
                not self.sections.layer.text.strip().isascii() or not self.sections.layer.text.strip().isdecimal()
            ):
                raise ValueError("Cell layer must be a nonnegative integer or blank")
        except ValueError as exc:
            self.status.text = str(exc)
            return
        plane = self.sections.plane.text
        signature = (plane, self.sections.layer.text)
        generation = self.display_generation

        def complete(output):
            if (
                self.result is not result
                or self.display_generation != generation
                or self.variant.text != label
                or signature != (self.sections.plane.text, self.sections.layer.text)
            ):
                self.status.text = "Target section selection changed; result withheld."
                return
            snapshot = result.target.target
            self.plot.grid_shape = tuple(
                ceil((b - a) / snapshot["resolution_mm"]) for a, b in zip(snapshot["minimum"], snapshot["maximum"])
            )
            self.plot.sections = output
            if selected_cell is not None:
                self.allowance.select_cell(selected_cell)
                u, v = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}[plane]
                self.plot.selected = selected_cell[u], selected_cell[v]
            self.plot.draw()
            self.legend.text = f"{label} · stock-local {plane}, layer {output[0].layer}/{output[0].layers - 1}\nGreen: target · amber: excess · red: missing target centers."

        owner._start(
            lambda cancelled: target_sections(result, label, plane, layer, cancelled=cancelled),
            complete,
            error_target=self.status,
        )
