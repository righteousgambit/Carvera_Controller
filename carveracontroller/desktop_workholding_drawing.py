"""CAD-derived vise envelopes and placement references for local drafts."""

import math

from kivy.graphics import Color, Line
from kivy.metrics import dp

from carveracontroller.addons.machine_simulation.workholding import component_envelopes, projected_envelopes
from carveracontroller.desktop_components import ACCENT, AMBER, MUTED
from carveracontroller.desktop_stock_drawing import StockDrawing


def outline(points):
    """Convex boundary of a projected component envelope, preserving rotation."""
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    halves = []
    for sequence in (points, reversed(points)):
        half = []
        for point in sequence:
            while len(half) >= 2 and cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half)
    return halves[0][:-1] + halves[1][:-1]


class WorkholdingDrawing(StockDrawing):
    def __init__(self, profile, **kwargs):
        self.envelopes, self.pivot = component_envelopes(profile)
        super().__init__(**kwargs)

    def redraw(self, *_):
        self.ink.clear()
        self.dimension_targets = []
        self.placed = ()
        for item in self.annotations:
            item.text = ""
        if self.setup is None or not self.envelopes:
            return
        offset = self.setup["workholding_offset_mm"]
        angle, jaw = self.setup["workholding_rotation_deg"], self.setup["jaw_offset_mm"]
        placed = projected_envelopes(self.envelopes, self.pivot, offset, angle, jaw)
        jaw_zero = projected_envelopes(self.envelopes, self.pivot, offset, angle, 0)
        self.placed = placed
        half = self.width / 2
        for index, vertical_axis in enumerate((1, 2)):
            points = [(0, 0), (offset[0], offset[vertical_axis])]
            polygons = [(outline((p[0], p[vertical_axis]) for p in corners), movable) for corners, movable in placed]
            points.extend(point for polygon, _ in polygons for point in polygon)
            if self.selected[0] == "jaw_offset_mm":
                points.extend((p[0], p[vertical_axis]) for corners, movable in jaw_zero if movable for p in corners)
            low = tuple(min(p[i] for p in points) for i in (0, 1))
            high = tuple(max(p[i] for p in points) for i in (0, 1))
            span = tuple(max(1, high[i] - low[i]) for i in (0, 1))
            available = (max(1, half - dp(40)), max(1, self.height - dp(46)))
            scale = min(available[i] / span[i] for i in (0, 1))
            left = self.x + index * half + (half - span[0] * scale) / 2
            bottom = self.y + dp(30) + (available[1] - span[1] * scale) / 2

            def pixel(point, left=left, low=low, scale=scale, bottom=bottom):
                return left + (point[0] - low[0]) * scale, bottom + (point[1] - low[1]) * scale

            with self.ink:
                for polygon, movable in polygons:
                    Color(*(ACCENT if movable and self.selected[0] == "jaw_offset_mm" else MUTED))
                    Line(points=[v for p in polygon for v in pixel(p)], close=True, width=1.5)
                origin, shifted = pixel((0, 0)), pixel((offset[0], offset[vertical_axis]))
                Color(*AMBER)
                Line(points=[origin[0] - dp(5), origin[1], origin[0] + dp(5), origin[1]], width=1)
                Line(points=[origin[0], origin[1] - dp(5), origin[0], origin[1] + dp(5)], width=1)
                Line(circle=(*shifted, dp(4)), width=1.5)
                elbow = pixel((offset[0], 0))
                for axis, a, b in ((0, origin, elbow), (vertical_axis, elbow, shifted)):
                    Color(*(ACCENT if self.selected == ("workholding_offset_mm", axis) else MUTED))
                    Line(points=[*a, *b], width=1.8)
                    self.dimension_targets.append((("workholding_offset_mm", axis), (*a, *b)))
                if index == 0:
                    radius = dp(18)
                    Color(*(ACCENT if self.selected[0] == "workholding_rotation_deg" else MUTED))
                    arc = [
                        v
                        for i in range(33)
                        for v in (
                            shifted[0] + radius * math.cos(math.radians(angle * i / 32)),
                            shifted[1] + radius * math.sin(math.radians(angle * i / 32)),
                        )
                    ]
                    Line(points=arc, width=1.8)
                    self.dimension_targets.extend(
                        (("workholding_rotation_deg", None), arc[i : i + 4]) for i in range(0, len(arc) - 2, 2)
                    )
                for (old, movable), (new, _) in zip(jaw_zero, placed):
                    if not movable:
                        continue
                    if self.selected[0] == "jaw_offset_mm":
                        Color(*MUTED)
                        boundary = outline((p[0], p[vertical_axis]) for p in old)
                        Line(
                            points=[v for p in boundary for v in pixel(p)],
                            close=True,
                            dash_length=dp(4),
                            dash_offset=dp(4),
                        )
                    a = pixel(tuple(sum(p[i] for p in old) / len(old) for i in (0, vertical_axis)))
                    b = pixel(tuple(sum(p[i] for p in new) / len(new) for i in (0, vertical_axis)))
                    Color(*(ACCENT if self.selected[0] == "jaw_offset_mm" else MUTED))
                    Line(points=[*a, *b], width=1.8)
                    self.dimension_targets.append((("jaw_offset_mm", None), (*a, *b)))
                    Line(circle=(*b, dp(3)), width=1.3)
            item = self.annotations[index]
            item.size, item.pos = (half, dp(26)), (self.x + index * half, self.y)
            item.text_size = item.size
            item.text = "Top · XY" if index == 0 else "Front · XZ"
