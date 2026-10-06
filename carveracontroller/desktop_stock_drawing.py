"""Local stock draft projections with explicit coordinate-frame annotations."""

import copy
from math import cos, pi, sin

from kivy.clock import Clock
from kivy.graphics import Canvas, Color, Line
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.desktop_components import ACCENT, AMBER, MUTED


class StockDrawing(StencilView):
    """XY/XZ projections share one scale; origin values remain program coordinates.

    Machine work offsets are annotated separately: they are not stock dimensions
    and this schematic does not assert a measured mounting transform.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_dimension_selected")
        self.dimension_targets = []
        self.rotation_outline = ()
        self.origin_projections = ()
        self.disposed = False
        self.setup = None
        self.baseline = None
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

    def update_setup(self, setup, selected, baseline=None):
        self.setup = copy.deepcopy(setup)
        self.baseline = copy.deepcopy(baseline)
        self.selected = selected
        self.trigger()

    def redraw(self, *_):
        self.ink.clear()
        self.dimension_targets = []
        self.rotation_outline = ()
        self.origin_projections = ()
        for item in self.annotations:
            item.text = ""
        if self.setup is None or self.setup["stock_size_mm"] is None:
            return
        size = self.setup["stock_size_mm"]
        group, axis = self.selected
        if group == "stock_origin_mm":
            self._draw_origin(size, axis)
            return
        half = self.width / 2
        rotating = group == "stock_rotation_deg"
        angle = self.setup.get("stock_rotation_deg", 0)
        stock = MachineSetup(stock_size_mm=tuple(size), stock_rotation_deg=angle)
        corners = tuple(
            stock.stock_point(point)[:2]
            for point in ((0, 0, 0), (size[0], 0, 0), (size[0], size[1], 0), (0, size[1], 0))
        )
        extent_x = max(point[0] for point in corners) - min(point[0] for point in corners)
        extent_y = max(point[1] for point in corners) - min(point[1] for point in corners)
        scale = min(
            max(1, half - dp(70)) / max(size[0], extent_x if rotating else size[0]),
            max(1, self.height - dp(64)) / max(*size[1:], extent_y if rotating else size[1]),
        )
        for index, vertical_axis in enumerate((1, 2)):
            width, height = size[0] * scale, size[vertical_axis] * scale
            x = self.x + index * half + (half - width) / 2
            y = self.y + dp(36) + (max(1, self.height - dp(64)) - height) / 2
            item = self.annotations[index]
            item.size = (half, dp(26))
            item.text_size = item.size
            item.pos = (self.x + index * half, self.y)
            frame = "Unrotated stock frame" if self.setup.get("stock_rotation_deg", 0) else "Stock frame"
            item.text = f"{frame} · {'XY' if index == 0 else 'XZ'} · {size[0]:g} × {size[vertical_axis]:g} mm"
            if rotating and index == 0:
                item.text = f"Stock center frame · XY rotation {angle:g}°"
                self._draw_rotation(corners, x, y, width, height, scale, stock.stock_rotation_deg)
                continue
            with self.ink:
                Color(*MUTED)
                Line(rectangle=(x, y, width, height), width=1)
                for dimension in (0, vertical_axis):
                    Color(*(ACCENT if group == "stock_size_mm" and axis == dimension else MUTED))
                    if dimension == 0:
                        points = (x, y - dp(12), x + width, y - dp(12))
                        ticks = ((x, y - dp(17), x, y - dp(7)), (x + width, y - dp(17), x + width, y - dp(7)))
                    else:
                        points = (x - dp(12), y, x - dp(12), y + height)
                        ticks = ((x - dp(17), y, x - dp(7), y), (x - dp(17), y + height, x - dp(7), y + height))
                    Line(points=points, width=1.8)
                    for tick in ticks:
                        Line(points=tick, width=1.8)
                    self.dimension_targets.append((("stock_size_mm", dimension), points))
                Color(*(ACCENT if group == "stock_origin_mm" else AMBER))
                Line(circle=(x, y, dp(4)), width=1.5)

    def _draw_origin(self, size, selected_axis):
        """Place unrotated corners against program zero, without mounting claims."""
        origin = self.setup["stock_origin_mm"]
        previous = self.baseline["stock_origin_mm"] if self.baseline else None
        half = self.width / 2
        lower = [min(0, origin[i], previous[i] if previous else origin[i]) for i in range(3)]
        upper = [max(0, origin[i] + size[i], previous[i] if previous else origin[i]) for i in range(3)]
        span = [max(1, upper[i] - lower[i]) for i in range(3)]
        scale = min(max(1, half - dp(70)) / span[0], max(1, self.height - dp(64)) / max(span[1:]))
        projections = []
        for index, vertical in enumerate((1, 2)):
            x = self.x + index * half + (half - span[0] * scale) / 2 - lower[0] * scale
            y = self.y + dp(36) + (max(1, self.height - dp(64)) - span[vertical] * scale) / 2 - lower[vertical] * scale
            corner = (x + origin[0] * scale, y + origin[vertical] * scale)
            old = (x + previous[0] * scale, y + previous[vertical] * scale) if previous else None
            projections.append({"zero": (x, y), "draft": corner, "previous": old, "scale": scale})
            label = self.annotations[index]
            label.size = (half, dp(26))
            label.text_size = label.size
            label.pos = (self.x + index * half, self.y)
            label.text = f"Program frame · unrotated {'XY' if index == 0 else 'XZ'} corner"
            rays = ((0, (x, y, corner[0], y)), (vertical, (corner[0], y, *corner)))
            with self.ink:
                Color(*MUTED)
                Line(points=(x - dp(5), y, x + dp(5), y), width=1.2)
                Line(points=(x, y - dp(5), x, y + dp(5)), width=1.2)
                if old is not None:
                    Line(points=(x, y, *old), width=1, dash_length=dp(4), dash_offset=dp(3))
                    Line(circle=(*old, dp(3)), width=1)
                Line(rectangle=(*corner, size[0] * scale, size[vertical] * scale), width=1)
                for axis, ray in rays:
                    Color(*(ACCENT if selected_axis == axis else MUTED))
                    Line(points=ray, width=1.8)
                    self.dimension_targets.append((("stock_origin_mm", axis), ray))
                Color(*ACCENT)
                Line(circle=(*corner, dp(4)), width=1.5)
        self.origin_projections = tuple(projections)

    def _draw_rotation(self, corners, x, y, width, height, scale, angle):
        """Show the same center rotation used by the stock mesh, without WCS claims."""
        self.rotation_outline = tuple((x + a * scale, y + b * scale) for a, b in corners)
        cx, cy = x + width / 2, y + height / 2
        radius = max(dp(14), min(width, height) * 0.35)
        radians = angle * pi / 180
        ray = (cx, cy, cx + radius * cos(radians), cy + radius * sin(radians))
        steps = max(1, int(abs(angle) / 5))
        arc = tuple(
            coordinate
            for step in range(steps + 1)
            for coordinate in (cx + radius * cos(radians * step / steps), cy + radius * sin(radians * step / steps))
        )
        with self.ink:
            Color(*MUTED)
            Line(rectangle=(x, y, width, height), width=1, dash_length=dp(4), dash_offset=dp(3))
            Line(points=(cx, cy, cx + radius, cy), width=1, dash_length=dp(3))
            Color(*ACCENT)
            Line(
                points=tuple(coordinate for point in self.rotation_outline for coordinate in point),
                close=True,
                width=1.8,
            )
            Line(points=arc, width=1.5)
            Line(points=ray, width=1.8)
            Line(circle=(cx, cy, dp(3)), width=1.5)
        self.dimension_targets.append((("stock_rotation_deg", None), ray))

    def dimension_at(self, position):
        if self.disposed or self.setup is None or not self.opacity or not self.collide_point(*position):
            return None
        nearest, distance = None, dp(12)
        for key, (x0, y0, x1, y1) in self.dimension_targets:
            dx, dy = x1 - x0, y1 - y0
            length = dx * dx + dy * dy
            fraction = max(0, min(1, ((position[0] - x0) * dx + (position[1] - y0) * dy) / length)) if length else 0
            gap = ((position[0] - x0 - fraction * dx) ** 2 + (position[1] - y0 - fraction * dy) ** 2) ** 0.5
            if gap < distance:
                nearest, distance = key, gap
        return nearest

    def on_dimension_selected(self, key):
        """Request selection of a validated editor field; never changes geometry."""

    def on_touch_down(self, touch):
        if self.disposed or self.setup is None or not self.opacity:
            return False
        key = self.dimension_at(touch.pos)
        if key is not None and not getattr(touch, "is_mouse_scrolling", False):
            touch.ud[self] = (key, touch.pos)
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            key, start = touch.ud.pop(self, (None, touch.pos))
            moved = sum((a - b) ** 2 for a, b in zip(start, touch.pos)) ** 0.5
            if key is not None and moved <= dp(8) and self.dimension_at(touch.pos) == key:
                self.dispatch("on_dimension_selected", key)
            return True
        return super().on_touch_up(touch)

    def dispose(self):
        self.disposed = True
        self.dimension_targets = []
        self.rotation_outline = ()
        self.origin_projections = ()
        self.trigger.cancel()
