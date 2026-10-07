"""Bounded drawings of the explicitly opted-in ideal radial model."""

from __future__ import annotations

import math

from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import ACCENT, AMBER, MUTED, RAISED, AdaptiveGrid, Surface, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.cutting_parameters import CuttingParameters


class CuttingDiagram(Widget):
    def __init__(self, mode, **kwargs):
        super().__init__(**kwargs)
        self.mode = mode
        self.result = None
        self.samples = ()
        self.bind(pos=self.draw, size=self.draw)

    def show(self, result):
        self.result = result
        # Fixed sampling bounds redraw cost independently of program size.
        self.samples = (
            tuple(
                (
                    i * result.radial_engagement_degrees / 120,
                    math.sin(math.radians(i * result.radial_engagement_degrees / 120)),
                )
                for i in range(121)
            )
            if result is not None and result.radial_engagement_degrees is not None
            else ()
        )
        if result is not None and result.ideal_max_chip_mm == 0:
            self.samples = tuple((angle, 0.0) for angle, _ in self.samples)
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            if not self.samples:
                return
            left, bottom = self.x + dp(16), self.y + dp(16)
            width, height = max(1, self.width - dp(32)), max(1, self.height - dp(32))
            if self.mode == "arc":
                radius = min(width, height) * 0.42
                cx, cy = left + width / 2, bottom + height / 2
                Color(*MUTED)
                Line(circle=(cx, cy, radius), width=1)
                Color(*ACCENT)
                points = [
                    coordinate
                    for angle, _ in self.samples
                    for coordinate in (
                        cx + radius * math.sin(math.radians(angle)),
                        cy - radius * math.cos(math.radians(angle)),
                    )
                ]
                Line(points=points, width=dp(3))
                for angle in (0, self.samples[-1][0]):
                    Line(
                        points=[
                            cx,
                            cy,
                            cx + radius * math.sin(math.radians(angle)),
                            cy - radius * math.cos(math.radians(angle)),
                        ],
                        width=1,
                    )
            else:
                Color(*MUTED[:3], 0.35)
                for fraction in (0, 0.5, 1):
                    Line(points=[left, bottom + height * fraction, left + width, bottom + height * fraction], width=0.7)
                    Line(points=[left + width * fraction, bottom, left + width * fraction, bottom + height], width=0.7)
                # Both axes retain their full scale, so different widths are comparable.
                Color(*AMBER)
                Line(points=[left, bottom + height, left + width, bottom + height], width=1)
                Color(*ACCENT)
                Line(
                    points=[
                        coordinate
                        for angle, factor in self.samples
                        for coordinate in (left + width * angle / 180, bottom + height * factor)
                    ],
                    width=dp(2),
                )


class CuttingVisualReview(Surface):
    def __init__(self):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.summary = wrapped()
        self.add_widget(self.summary)
        self.grid = AdaptiveGrid(max_cols=2, min_width=260, row_height=260, spacing=dp(8))
        self.plots, self.captions = [], []
        for mode, title in (("arc", "Ideal peripheral engagement"), ("chip", "Chip thickness over engagement")):
            card = Surface(orientation="vertical", padding=dp(6), spacing=dp(4))
            card.add_widget(label(title, 12, height=26, bold=True))
            plot = CuttingDiagram(mode)
            card.add_widget(plot)
            caption = wrapped()
            card.add_widget(caption)
            self.plots.append(plot)
            self.captions.append(caption)
            self.grid.add_widget(card)
        self.add_widget(self.grid)
        self.show(None)

    def show(self, result: CuttingParameters | None):
        available = result is not None and result.radial_engagement_degrees is not None
        for plot in self.plots:
            plot.show(result if available else None)
        self.grid.opacity = 1 if available else 0
        self.grid._reflow()
        self.grid.size_hint_y = None
        # Remove unavailable cards from layout rather than leave empty chart space.
        if available and self.grid.parent is None:
            self.add_widget(self.grid)
        elif not available and self.grid.parent is self:
            self.remove_widget(self.grid)
        if result is None or result.radial_engagement_degrees is None:
            self.summary.text = (
                "Visual engagement unassessed · enable the ideal radial model and review current inputs."
            )
            return
        self.summary.text = "Ideal geometry · 90° entering edge / straight wall · no stock-contact simulation"
        self.captions[
            0
        ].text = f"Teal: {result.radial_engagement_degrees:.4g}° arc on a {result.diameter_mm:g} mm cutter. End rays bound the arc; no rotation direction is inferred."
        self.captions[
            1
        ].text = f"X: angle 0–180° · Y: 0–{result.chip_mm_tooth:.4g} mm. Amber: nominal feed/tooth; teal: ideal thickness. Maximum {result.ideal_max_chip_mm:.4g} mm."
