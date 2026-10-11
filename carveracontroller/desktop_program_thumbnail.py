"""Read-only XY thumbnail of captured, resolved program segments."""

from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.widget import Widget


class ProgramThumbnail(Widget):
    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(100), **kwargs)
        self.segments = ()
        self.bind(pos=self.paint, size=self.paint)

    def set_segments(self, segments):
        self.segments = tuple(segments)
        self.paint()

    def paint(self, *_):
        self.canvas.clear()
        if not self.segments:
            return
        points = [point for segment in self.segments for point in (segment.start_mm, segment.end_mm)]
        low = [min(point[a] for point in points) for a in (0, 1)]
        high = [max(point[a] for point in points) for a in (0, 1)]
        scale = min(
            max(1, self.width - dp(16)) / max(1, high[0] - low[0]),
            max(1, self.height - dp(16)) / max(1, high[1] - low[1]),
        )
        center = [(low[a] + high[a]) / 2 for a in (0, 1)]
        with self.canvas:
            for segment in self.segments:
                Color(0.45, 0.53, 0.62, 0.8) if segment.rapid else Color(0.23, 0.80, 0.72, 1)
                Line(
                    points=[
                        value
                        for point in (segment.start_mm, segment.end_mm)
                        for value in (
                            self.center_x + (point[0] - center[0]) * scale,
                            self.center_y + (point[1] - center[1]) * scale,
                        )
                    ],
                    width=1,
                )
