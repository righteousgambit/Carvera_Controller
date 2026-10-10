"""Background before/after material sections in the retained review workbench."""

from __future__ import annotations

from kivy.graphics import Color, Line, Mesh, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.program_stock_inspection import StockSection, inspect_stock_section


class StockSectionPlot(Widget):
    """Shared equal-scale before/after views, including the full declared grid."""

    height: float

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=0, **kwargs)
        self.section: StockSection | None = None
        self.bind(pos=self.draw, size=self.draw)

    def draw(self, *_):
        self.canvas.clear()
        if self.section is None:
            return
        low_x, low_y, high_x, high_y = self.section.bounds
        width, height = high_x - low_x, high_y - low_y
        margin = dp(6)
        wanted_height = min(dp(320), max(dp(48), max(1, self.width / 2 - 2 * margin) * height / width + 2 * margin))
        if abs(self.height - wanted_height) > 1:
            self.height = wanted_height
        pane_width, pane_height = max(1, self.width / 2 - 2 * margin), max(1, self.height - 2 * margin)
        scale = min(pane_width / width, pane_height / height)
        for pane in range(2):
            x = self.x + pane * self.width / 2 + margin + (pane_width - width * scale) / 2
            y = self.y + margin + (pane_height - height * scale) / 2
            with self.canvas:
                Color(0.12, 0.15, 0.18, 1)
                Rectangle(pos=(x, y), size=(width * scale, height * scale))
            for category, rectangles in enumerate((self.section.remaining, self.section.removed)):
                if pane == 1 and category == 1:
                    continue
                vertices, indices = [], []
                for left, bottom, right, top in rectangles:
                    at = len(vertices) // 4
                    for u, v in ((left, bottom), (right, bottom), (right, top), (left, top)):
                        vertices.extend((x + (u - low_x) * scale, y + (v - low_y) * scale, 0, 0))
                    indices.extend((at, at + 1, at + 2, at, at + 2, at + 3))
                with self.canvas:
                    Color(*(ACCENT if category == 0 else (1, 0.67, 0.25, 1)))
                    Mesh(vertices=vertices, indices=indices, mode="triangles")
            with self.canvas:
                Color(0.5, 0.58, 0.65, 1)
                Line(rectangle=(x, y, width * scale, height * scale), width=dp(1))


class StockSectionControls(PlanningCard):
    def __init__(self, surfaces):
        super().__init__("Before / after material")
        self.surfaces = surfaces
        self.target = None
        self.content.add_widget(
            flowing_text(
                "Select a stock-history move, then reconstruct a section. Current machine setup is preserved.", 40
            )
        )
        options = AdaptiveGrid(max_cols=2, min_width=145, row_height=78, spacing=dp(6))
        self.plane = planning_choice(options, "Stock-local section", ("XY", "XZ", "YZ"))
        self.layer = planning_field(options, "Cell layer · blank = middle", "")
        self.plane.bind(text=self.options_changed)
        self.layer.bind(text=self.options_changed)
        self.content.add_widget(options)
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=40, spacing=dp(6))
        self.prepare = Action("Reconstruct section", self.calculate, disabled=True)
        self.inspect = Action("Inspect source", surfaces.inspect_source, disabled=True)
        actions.add_widget(self.prepare)
        actions.add_widget(self.inspect)
        self.content.add_widget(actions)
        navigation = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous stock move", lambda: self.step(-1), disabled=True)
        self.next = Action("Next stock move", lambda: self.step(1), disabled=True)
        navigation.add_widget(self.previous)
        navigation.add_widget(self.next)
        self.content.add_widget(navigation)
        self.status = flowing_text("No material section reconstructed.", 40)
        self.content.add_widget(self.status)
        self.legend = flowing_text(
            "Before left / after right · green: remaining · amber: removed by this move · dark: empty", 40
        )
        self.content.add_widget(self.legend)
        headings = AdaptiveGrid(max_cols=2, min_width=1, row_height=24, spacing=dp(6))
        headings.add_widget(flowing_text("Before", 24))
        headings.add_widget(flowing_text("After", 24))
        self.content.add_widget(headings)
        self.plot = StockSectionPlot()
        self.content.add_widget(self.plot)
        limits = PlanningCard("Section frame & estimate limits")
        limits.content.add_widget(
            flowing_text(
                "Section follows the stock's own grid axes, before its declared rotation/tilt and WCS transform. "
                "Each rectangle covers complete classified cells; it does not span a cavity or missing cell. "
                "Removal classifies cell centers. Empty cells do not establish whole-cell physical removal or clearance. "
                "Prefix replay retains unresolved-command and ATC coverage gaps; physical registration remains unverified.",
                70,
            )
        )
        self.content.add_widget(limits)

    def clear(self):
        self.target = None
        self.options_changed()
        self.set_busy(False)

    def options_changed(self, *_):
        self.plot.section = None
        self.plot.height = 0
        self.plot.draw()
        self.status.text = "No section for this selection · reconstruct the retained move to inspect material."

    def set_target(self, row):
        if self.target is not row:
            self.target = row
            self.options_changed()
        self.set_busy(self.surfaces.review.card.owner.running)

    def set_busy(self, busy):
        self.plane.disabled = self.layer.disabled = busy
        self.prepare.disabled = self.inspect.disabled = busy or self.target is None
        result = self.surfaces.result
        count = len(result.body_review.segments) if result is not None else 0
        self.previous.disabled = busy or self.target is None or self.target.segment_index == 0
        self.next.disabled = busy or self.target is None or self.target.segment_index + 1 >= count

    def step(self, delta):
        if self.target is None or self.surfaces.review.card.owner.running:
            return
        target = self.target.segment_index + delta
        for index, (kind, row) in enumerate(self.surfaces.rows):
            if kind == "stock history" and row.second == self.target.second and row.segment_index == target:
                self.surfaces.page = index // 64
                self.surfaces.refresh()
                self.surfaces.choice.text = self.surfaces.choice.values[index % 64]
                self.surfaces.select()
                return

    def calculate(self):
        owner = self.surfaces.review.card.owner
        result, row = self.surfaces.result, self.target
        if owner.running or result is None or row is None or result.stock_evolution is None:
            return
        try:
            text = self.layer.text.strip()
            if text and (not text.isascii() or not text.isdecimal()):
                raise ValueError("Cell layer must be a zero-based integer or blank for the middle layer")
            layer = int(text) if text else None
        except (ValueError, TypeError) as exc:
            self.status.text = str(exc)
            return
        plane = self.plane.text
        signature = (plane, self.layer.text)
        self.status.text = f"Reconstructing {row.second} at L{row.line} · bounded background work…"

        def complete(section):
            if (
                self.surfaces.result is not result
                or self.target is not row
                or (self.plane.text, self.layer.text) != signature
            ):
                self.status.text = "Selection changed during reconstruction; section withheld."
                return
            self.plot.section = section
            self.plot.height = dp(220)
            self.plot.draw()
            normal = {"XY": "Z", "XZ": "Y", "YZ": "X"}[section.plane]
            self.status.text = (
                f"{section.stock}\nL{section.line} · T{section.tool} · move {section.segment_index + 1}\n"
                f"Stock-local {section.plane} at {normal}{section.coordinate_mm:.6g} mm · layer {section.layer}/{section.layers - 1}\n"
                f"Whole stock: {section.before_mm3:.6g} to {section.after_mm3:.6g} mm³\n"
                "Stock-local cell estimate · physical registration unverified."
            )

        owner._start(
            lambda cancelled: inspect_stock_section(
                result.body_review,
                result.stock_evolution,
                result.rotating_envelopes,
                row.second,
                row.segment_index,
                plane,
                layer,
                cancelled=cancelled,
            ),
            complete,
            error_target=self.status,
        )
