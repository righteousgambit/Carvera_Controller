"""Local stock draft projections with explicit coordinate-frame annotations."""

import copy

from kivy.clock import Clock
from kivy.graphics import Canvas, Color, Line
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from carveracontroller.desktop_components import ACCENT, AMBER, MUTED


class StockDrawing(StencilView):
    """XY/XZ projections share one scale; origin values remain program coordinates.

    Machine work offsets are annotated separately: they are not stock dimensions
    and this schematic does not assert a measured mounting transform.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setup = None
        self.selected = ("stock_size_mm", 0)
        self.ink = Canvas()
        self.canvas.add(self.ink)
        self.annotations = []
        for _ in range(2):
            item = Label(font_size=dp(11), color=MUTED, size_hint=(None, None))
            self.annotations.append(item)
            self.add_widget(item)
        self.trigger = Clock.create_trigger(self.redraw, 0)
        self.bind(pos=self.trigger, size=self.trigger)

    def update_setup(self, setup, selected):
        self.setup = copy.deepcopy(setup)
        self.selected = selected
        self.trigger()

    def redraw(self, *_):
        self.ink.clear()
        for item in self.annotations:
            item.text = ""
        if self.setup is None or self.setup["stock_size_mm"] is None:
            return
        size = self.setup["stock_size_mm"]
        group, axis = self.selected
        half = self.width / 2
        scale = min(max(1, half - dp(70)) / size[0], max(1, self.height - dp(64)) / max(size[1:]))
        for index, vertical_axis in enumerate((1, 2)):
            width, height = size[0] * scale, size[vertical_axis] * scale
            x = self.x + index * half + (half - width) / 2
            y = self.y + dp(36) + (max(1, self.height - dp(64)) - height) / 2
            item = self.annotations[index]
            item.size = (half, dp(26))
            item.text_size = item.size
            item.pos = (self.x + index * half, self.y)
            item.text = f"{'Top · XY' if index == 0 else 'Front · XZ'} · {size[0]:g} × {size[vertical_axis]:g} mm"
            with self.ink:
                Color(*MUTED)
                Line(rectangle=(x, y, width, height), width=1)
                if group == "stock_size_mm" and axis in (0, vertical_axis):
                    Color(*ACCENT)
                    if axis == 0:
                        points = (x, y - dp(12), x + width, y - dp(12))
                        ticks = ((x, y - dp(17), x, y - dp(7)), (x + width, y - dp(17), x + width, y - dp(7)))
                    else:
                        points = (x - dp(12), y, x - dp(12), y + height)
                        ticks = ((x - dp(17), y, x - dp(7), y), (x - dp(17), y + height, x - dp(7), y + height))
                    Line(points=points, width=1.8)
                    for tick in ticks:
                        Line(points=tick, width=1.8)
                Color(*(ACCENT if group == "stock_origin_mm" else AMBER))
                Line(circle=(x, y, dp(4)), width=1.5)

    def dispose(self):
        self.trigger.cancel()
