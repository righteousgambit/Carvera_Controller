"""Linked orthographic view of a declared frame snapshot; no machine transport."""

from math import hypot

from kivy.graphics import Canvas, Color, Ellipse, Line
from kivy.metrics import dp
from kivy.uix.stencilview import StencilView

from carveracontroller.desktop_components import ACCENT, AMBER, MUTED


class FrameDiagram(StencilView):
    def __init__(self, frames, **kwargs):
        super().__init__(**kwargs)
        self.frames = tuple(frames)
        self.selected_name = self.frames[0].name
        self.view = "Isometric"
        self.projected = {}
        self.axis_segments = ()
        self.on_pick = None
        self.ink = Canvas()
        self.canvas.add(self.ink)
        self.bind(pos=self.redraw, size=self.redraw)

    def select(self, name):
        if any(frame.name == name for frame in self.frames):
            self.selected_name = name
            self.redraw()

    def projection(self, point):
        x, y, z = point
        if self.view == "Top":
            return x, y
        if self.view == "Front":
            return x, z
        if self.view == "Right":
            return y, z
        return (x - y) * 0.7071067811865476, (x + y) * 0.4082482904638631 + z * 0.8164965809277261

    def redraw(self, *_):
        self.ink.clear()
        selected = next(frame for frame in self.frames if frame.name == self.selected_name)
        extent = max(
            max(f.origin_mm[i] for f in self.frames) - min(f.origin_mm[i] for f in self.frames) for i in range(3)
        )
        glyph = max(1, extent * 0.18)
        origin = selected.origin_mm
        endpoints = tuple(
            tuple(origin[i] + selected.rotation[3 * i + axis] * glyph for i in range(3)) for axis in range(3)
        )
        locations = {frame.name: self.projection(frame.origin_mm) for frame in self.frames}
        axes = [self.projection(point) for point in endpoints]
        points = list(locations.values()) + axes
        low = tuple(min(p[i] for p in points) for i in range(2))
        high = tuple(max(p[i] for p in points) for i in range(2))
        span = max(high[0] - low[0], high[1] - low[1], 1e-6)
        scale = min(
            max(1, self.width - dp(52)) / max(high[0] - low[0], span * 0.05),
            max(1, self.height - dp(40)) / max(high[1] - low[1], span * 0.05),
        )
        center = tuple((low[i] + high[i]) / 2 for i in range(2))

        def pixel(point):
            return self.center_x + (point[0] - center[0]) * scale, self.center_y + (point[1] - center[1]) * scale

        self.projected = {name: pixel(point) for name, point in locations.items()}
        origin_pixel = pixel(self.projection(origin))
        self.axis_segments = tuple((origin_pixel, pixel(point)) for point in axes)
        with self.ink:
            for frame in self.frames:
                if frame.chain == "Derived":
                    continue
                Color(*(ACCENT if frame.chain == "Tool" else AMBER))
                if frame.parent in self.projected:
                    Line(points=(*self.projected[frame.parent], *self.projected[frame.name]), width=1.2)
                px, py = self.projected[frame.name]
                Ellipse(pos=(px - dp(3), py - dp(3)), size=(dp(6), dp(6)))
            for color, (start, end) in zip(
                ((0.95, 0.34, 0.4, 1), (0.2, 0.82, 0.65, 1), (0.3, 0.6, 1, 1)), self.axis_segments
            ):
                Color(*color)
                Line(points=(*start, *end), width=2)
                Ellipse(pos=(end[0] - dp(3), end[1] - dp(3)), size=(dp(6), dp(6)))
            Color(*AMBER)
            Line(circle=(*origin_pixel, dp(8)), width=1.5)
            Color(*MUTED)
            Line(rectangle=(*self.pos, *self.size), width=0.5)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or getattr(touch, "is_mouse_scrolling", False):
            return super().on_touch_down(touch)
        distances = [(hypot(touch.x - point[0], touch.y - point[1]), name) for name, point in self.projected.items()]
        nearby = [name for distance, name in sorted(distances) if distance <= dp(14)]
        if nearby and self.on_pick is not None:
            # Co-located origins cycle through named frames instead of silently
            # selecting an arbitrary joint. Exact identity remains in the tree.
            current = nearby.index(self.selected_name) if self.selected_name in nearby else -1
            self.on_pick(nearby[(current + 1) % len(nearby)])
            return True
        return super().on_touch_down(touch)
