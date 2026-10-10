"""Selected-cell allowance and retained target-only tool approach evidence."""

from __future__ import annotations

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.desktop_stock_approach import StockApproachControls
from carveracontroller.machine.stock_allowance import CellAllowance, inspect_target_cell


class StockAllowanceControls(PlanningCard):
    def __init__(self, target):
        super().__init__("Inspect selected cell & tool approach")
        self.target = target
        self.result: CellAllowance | None = None
        self.generation = self.page = 0
        self.rows: tuple[str, ...] = ()
        self.content.add_widget(
            flowing_text(
                "Click a target-section cell or enter its grid indices. Distance uses retained triangles; approach is a separate local review.",
                42,
            )
        )
        self.cell = planning_field(self.content, "Grid cell X, Y, Z · zero based", "0, 0, 0")
        options = AdaptiveGrid(max_cols=2, min_width=145, row_height=62, spacing=dp(6))
        self.tool = planning_choice(options, "Declared cutter", ("Distance only",))
        self.clearance = planning_field(options, "Approach above stock · mm", "1")
        self.content.add_widget(options)
        for field in (self.cell, self.tool, self.clearance):
            field.bind(text=self.clear)
        self.inspect = Action("Inspect cell", self.calculate, disabled=True)
        self.content.add_widget(self.inspect)
        self.status = flowing_text("Choose a retained target comparison.", 45)
        self.content.add_widget(self.status)
        self.contacts = planning_choice(
            self.content, "All target / stock contacts · 64 per page", ("No contact review",)
        )
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous contacts", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next contacts", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        details = PlanningCard("Witness & coverage")
        self.details = flowing_text("No cell inspection retained.", 45)
        details.content.add_widget(self.details)
        self.content.add_widget(details)
        self.machine_approach = StockApproachControls(self)
        self.content.add_widget(self.machine_approach)

    def clear(self, *_):
        self.generation += 1
        self.target.plot.selected = None
        self.target.plot.draw()
        self.result = None
        self.machine_approach.clear()
        self.rows = ()
        self.page = 0
        self.details.text = "No cell inspection retained."
        self.status.text = "Inspect the current cell and stock state."
        self.render_page()

    def set_busy(self, busy):
        self.machine_approach.set_busy(busy)
        for control in (self.cell, self.tool, self.clearance, self.contacts):
            control.disabled = busy
        self.inspect.disabled = busy or self.target.result is None
        self.previous.disabled = busy or self.page == 0
        self.next.disabled = busy or (self.page + 1) * 64 >= len(self.rows)

    def refresh_tools(self):
        result = self.target.result
        self.tool.values = (
            ("Distance only",) + tuple(f"T{n}" for n in result.target.bindings[1].inputs.tools)
            if result
            else ("Distance only",)
        )
        if self.tool.text not in self.tool.values:
            self.tool.text = "Distance only"

    def select_cell(self, cell):
        self.cell.text = ", ".join(str(v) for v in cell)
        if not self.expanded:
            self.toggle()
        self.status.text = "Selected cell; inspect to calculate distance and optional approach."

    def calculate(self):
        owner = self.target.sections.surfaces.review.card.owner
        analysis, label = self.target.result, self.target.variant.text
        if owner.running or analysis is None or label not in analysis.fits:
            return
        try:
            parts = tuple(v.strip() for v in self.cell.text.split(","))
            if len(parts) != 3 or any(not v.isascii() or not v.isdecimal() for v in parts):
                raise ValueError("Cell needs three nonnegative integer grid indices")
            cell = int(parts[0]), int(parts[1]), int(parts[2])
            tool = None if self.tool.text == "Distance only" else int(self.tool.text.removeprefix("T"))
            clearance = float(self.clearance.text)
        except ValueError as exc:
            self.status.text = str(exc)
            return
        signature = (self.cell.text, self.tool.text, self.clearance.text)
        generation = self.generation
        self.status.text = "Querying complete target surface and declared insertion…"

        def complete(result):
            if (
                self.target.result is not analysis
                or self.target.variant.text != label
                or self.generation != generation
                or signature != (self.cell.text, self.tool.text, self.clearance.text)
            ):
                self.status.text = "Cell, target or state changed; inspection withheld."
                return
            self.result = result
            self.machine_approach.clear()
            low, high = result.cell_distance_interval_mm
            self.status.text = f"{label} · cell {result.cell} · {result.category}\nSigned center distance {result.signed_distance_mm:.6g} mm · cell interval [{low:.6g}, {high:.6g}] mm\nClosest {result.nearest.feature} on source triangle {result.nearest.triangle}; negative is inside target."
            approach = result.approach
            self.rows = (
                tuple(
                    f"Target · {c.component} · triangle {c.triangle} · witness t={float(c.witness.sample):.6g}"
                    for c in approach.target_contacts
                )
                + tuple(f"Stock estimate · {c.component} · {c.obstacle}" for c in approach.stock_contacts)
                if approach
                else ()
            )
            self.page = 0
            self.render_page()
            self.details.text = (
                f"Grid center {result.center_grid_mm} mm\nProgram center {result.center_program_mm} mm\nNearest source point {tuple(float(v) for v in result.nearest.point)} mm\nBarycentric {tuple(float(v) for v in result.nearest.barycentric)}\nExact squared distance {result.nearest.distance_squared}\n{result.distance_nodes} hierarchy nodes / {result.distance_faces} triangles\n"
                + result.qualification
            )
            if approach:
                self.status.text += f"\nT{approach.tool}: {len(approach.target_contacts)} target surface contacts; {len(approach.stock_contacts)} noncutting stock estimates."
                self.details.text += (
                    f"\nApproach {approach.start} → {approach.end} mm\n"
                    + approach.qualification
                    + "\n"
                    + "\n".join(approach.coverage)
                )
            self.set_busy(False)

        owner._start(
            lambda cancelled: inspect_target_cell(
                analysis, label, cell, tool=tool, approach_clearance_mm=clearance, cancelled=cancelled
            ),
            complete,
            error_target=self.status,
        )

    def render_page(self):
        start = self.page * 64
        self.contacts.values = tuple(
            f"{start + i + 1}. {row}" for i, row in enumerate(self.rows[start : start + 64])
        ) or (
            "No contact review"
            if self.result is None or self.result.approach is None
            else "No contacts within declared coverage",
        )
        self.contacts.text = self.contacts.values[0]
        self.previous.disabled = self.page == 0
        self.next.disabled = start + 64 >= len(self.rows)

    def change_page(self, delta):
        self.page = max(0, min(max(0, (len(self.rows) - 1) // 64), self.page + delta))
        self.render_page()
