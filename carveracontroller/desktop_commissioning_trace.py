"""Historical joint motion chart with time-based sample selection."""

from kivy.graphics import Color, Line, Point, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import ACCENT, AMBER, MUTED, RAISED, TEXT


class JointTracePlot(Widget):
    def __init__(self, selected, **kwargs):
        super().__init__(size_hint_y=None, height=dp(170), **kwargs)
        self.selected = selected
        self.trace = None
        self.cursor = 0
        self.time_bounds = (0, 1)
        self.bind(pos=self.draw, size=self.draw)

    def show(self, trace, cursor):
        self.trace, self.cursor = trace, cursor
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        points = self.trace.points if self.trace else ()
        values = [value for point in points for value in point.values]
        scale = max([abs(value) for value in values] + [1e-9])
        low, high = (min(values) / scale, max(values) / scale) if values else (0, 1)
        span = max(high - low, 0.002)
        low, high = low - span * 0.1, high + span * 0.1
        self.time_bounds = (points[0].elapsed, points[-1].elapsed) if points else (0, 1)
        t0, t1 = self.time_bounds
        left, bottom = self.x + dp(12), self.y + dp(12)
        width, height = max(1, self.width - dp(24)), max(1, self.height - dp(24))

        def xy(point, series):
            return (
                left + width * (0.5 if t1 == t0 else (point.elapsed - t0) / (t1 - t0)),
                bottom + height * (point.values[series] / scale - low) / (high - low),
            )

        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            Color(*MUTED[:3], 0.35)
            for fraction in (0, 0.5, 1):
                y = bottom + height * fraction
                Line(points=[left, y, left + width, y], width=0.7)
            if self.trace:
                for series, _name in enumerate(self.trace.names):
                    Color(*(ACCENT if series == 0 else AMBER))
                    for a, b in self.trace.segments:
                        Line(points=[*xy(points[a], series), *xy(points[b], series)], width=1)
                    for point in points:
                        Point(points=xy(point, series), pointsize=dp(2))
                        if point.sample == self.cursor:
                            Color(*TEXT)
                            Line(circle=(*xy(point, series), dp(5)), width=1.2)
                            Color(*(ACCENT if series == 0 else AMBER))

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.trace and self.trace.points and not self.disabled:
            fraction = max(0, min(1, (touch.x - self.x - dp(12)) / max(1, self.width - dp(24))))
            t0, t1 = self.time_bounds
            target = t0 + fraction * (t1 - t0)
            point = min(self.trace.points, key=lambda point: abs(point.elapsed - target))
            self.selected(point.sample)
            return True
        return super().on_touch_down(touch)
