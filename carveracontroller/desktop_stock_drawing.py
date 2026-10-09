"""Local stock draft projections with explicit coordinate-frame annotations."""

import copy
from math import cos, pi, sin

from kivy.clock import Clock
from kivy.graphics import Canvas, Color, Line, Mesh, PopMatrix, PushMatrix, Scale, Translate
from kivy.metrics import dp
from kivy.uix.label import Label
from kivy.uix.stencilview import StencilView

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.stock_projection import project_stock
from carveracontroller.desktop_components import ACCENT, AMBER, MUTED
from carveracontroller.machine.component_loads import ComponentLoads


class StockDrawing(StencilView):
    """XY/XZ projections share one scale; origin values remain program coordinates.

    Selecting machine work offsets projects the declared stock and program zero
    in machine coordinates; this does not assert a measured mounting transform.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.register_event_type("on_dimension_selected")
        self.dimension_targets = []
        self.rotation_outline = ()
        self.offset_projections = ()
        self.origin_projections = ()
        self.size_projections = ()
        self.disposed = False
        self.stock_model = None
        self.imported_projections = ()
        self.projection_key = None
        self.prepared_key = None
        self.prepared_projection = None
        self.projection_error = None
        self.projection_loads = ComponentLoads(lambda callback: Clock.schedule_once(lambda _dt: callback(), 0))
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
        if self.disposed:
            return
        self.setup = copy.deepcopy(setup)
        self.baseline = copy.deepcopy(baseline)
        self.selected = selected
        if self.stock_model is not None:
            self._prepare_projection()
        else:
            self.projection_key = None
            self.prepared_projection = None
            self.projection_loads.invalidate("stock")
        self.trigger()

    def _prepare_projection(self):
        if self.disposed or self.setup is None:
            return
        frame = {
            "stock_size_mm": "stock",
            "stock_origin_mm": "program",
            "work_offset_mm": "machine",
            "stock_rotation_deg": "rotation",
        }[self.selected[0]]
        source, setup, baseline = self.stock_model, self.setup, self.baseline or self.setup
        key = (
            source.source_sha256,
            source.source_units,
            source.minimum_mm,
            source.maximum_mm,
            frame,
            *(
                tuple(record[name]) if name != "stock_rotation_deg" else record.get(name, 0)
                for record in (setup, baseline)
                for name in ("stock_origin_mm", "work_offset_mm", "stock_rotation_deg")
            ),
        )
        if key == self.projection_key and self.projection_error is None:
            return
        self.projection_key, self.projection_error = key, None

        def cancelled():
            return self.disposed or self.projection_key != key

        def work():
            return (
                project_stock(source, setup, frame, cancelled=cancelled),
                project_stock(source, baseline, frame, cancelled=cancelled),
            )

        def finish(result, error):
            if self.disposed or self.setup is None or self.projection_key != key:
                return
            self.prepared_projection, self.projection_error = result, error
            self.prepared_key = key
            self.trigger()

        self.projection_loads.submit("stock", work, finish)

    def redraw(self, *_):
        self.ink.clear()
        self.dimension_targets = []
        self.rotation_outline = ()
        self.offset_projections = ()
        self.origin_projections = ()
        self.size_projections = ()
        self.imported_projections = ()
        for item in self.annotations:
            item.text = ""
        if self.setup is None or self.setup["stock_size_mm"] is None:
            return
        if "stock_source" in self.setup:
            self._draw_imported()
            return
        size = self.setup["stock_size_mm"]
        group, axis = self.selected
        if group == "work_offset_mm":
            self._draw_offset(size, axis)
            return
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
        previous_size = self.baseline.get("stock_size_mm") if group == "stock_size_mm" and self.baseline else None
        sizing_extent = tuple(max(size[i], previous_size[i]) for i in range(3)) if previous_size else size
        scale = min(
            max(1, half - dp(70)) / max(sizing_extent[0], extent_x if rotating else size[0]),
            max(1, self.height - dp(64)) / max(*sizing_extent[1:], extent_y if rotating else size[1]),
        )
        size_projections = []
        for index, vertical_axis in enumerate((1, 2)):
            width, height = size[0] * scale, size[vertical_axis] * scale
            x = self.x + index * half + (half - sizing_extent[0] * scale) / 2
            y = self.y + dp(36) + (max(1, self.height - dp(64)) - sizing_extent[vertical_axis] * scale) / 2
            item = self.annotations[index]
            item.size = (half, dp(26))
            item.text_size = item.size
            item.pos = (self.x + index * half, self.y)
            frame = "Unrotated stock frame" if self.setup.get("stock_rotation_deg", 0) else "Stock frame"
            item.text = f"{frame} · {'XY' if index == 0 else 'XZ'} · {size[0]:g} × {size[vertical_axis]:g} mm"
            if "stock_source" in self.setup:
                item.text = "Imported envelope · " + item.text
            if rotating and index == 0:
                item.text = f"Stock center frame · XY rotation {angle:g}°"
                if "stock_source" in self.setup:
                    item.text = "Imported envelope · " + item.text
                self._draw_rotation(corners, x, y, width, height, scale, stock.stock_rotation_deg)
                continue
            previous_rectangle = (
                (x, y, previous_size[0] * scale, previous_size[vertical_axis] * scale) if previous_size else None
            )
            if group == "stock_size_mm":
                size_projections.append(
                    {"draft": (x, y, width, height), "previous": previous_rectangle, "scale": scale}
                )
            with self.ink:
                if previous_rectangle is not None:
                    Color(*MUTED)
                    px, py, pw, ph = previous_rectangle
                    Line(
                        points=(px, py, px + pw, py, px + pw, py + ph, px, py + ph),
                        close=True,
                        width=1,
                        dash_length=dp(4),
                        dash_offset=dp(3),
                    )
                Color(*(ACCENT if group == "stock_size_mm" else MUTED))
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
        self.size_projections = tuple(size_projections)

    def _draw_imported(self):
        """GPU line batches use worker-prepared source edges, with shared scale."""
        if self.stock_model is None or self.prepared_key != self.projection_key or not self.prepared_projection:
            self.annotations[0].text = (
                "Source mesh unavailable"
                if self.stock_model is None
                else "Source drawing unavailable"
                if self.projection_error
                else "Preparing source drawing…"
            )
            self.annotations[0].pos = (self.x, self.center_y)
            self.annotations[0].size = (self.width, dp(24))
            return
        draft, previous = self.prepared_projection
        group, selected = self.selected
        lower, span = [], []
        for view in (0, 1):
            points = [
                draft.views[view].minimum,
                draft.views[view].maximum,
                previous.views[view].minimum,
                previous.views[view].maximum,
            ]
            if group in ("stock_origin_mm", "work_offset_mm"):
                points.append((0, 0))
                if group == "work_offset_mm":
                    vertical = view + 1
                    points.extend(
                        (record["work_offset_mm"][0], record["work_offset_mm"][vertical])
                        for record in (self.setup, self.baseline or self.setup)
                    )
            low = tuple(min(p[i] for p in points) for i in (0, 1))
            high = tuple(max(p[i] for p in points) for i in (0, 1))
            lower.append(low)
            span.append(tuple(max(1, high[i] - low[i]) for i in (0, 1)))
        half = self.width / 2
        scale = min(
            max(1, half - dp(70)) / max(p[0] for p in span), max(1, self.height - dp(64)) / max(p[1] for p in span)
        )
        projections = []
        for view, vertical in enumerate((1, 2)):
            x = self.x + view * half + (half - span[view][0] * scale) / 2 - lower[view][0] * scale
            y = self.y + dp(36) + (max(1, self.height - dp(64)) - span[view][1] * scale) / 2 - lower[view][1] * scale
            with self.ink:
                PushMatrix()
                Translate(x, y)
                Scale(scale, scale, 1)
                for which, projection in enumerate((previous, draft)):
                    Color(*(MUTED if which == 0 else ACCENT))
                    for vertices, indices in projection.views[view].batches:
                        Mesh(vertices=vertices, indices=indices, mode="lines")
                PopMatrix()
                Color(*AMBER)
                if group == "stock_rotation_deg":
                    cx, cy = x + draft.pivot[0] * scale, y + draft.pivot[vertical] * scale
                    Line(circle=(cx, cy, dp(3)), width=1.5)
                    if view == 0:
                        angle = self.setup.get("stock_rotation_deg", 0) * pi / 180
                        radius = dp(24)
                        ray = (cx, cy, cx + radius * cos(angle), cy + radius * sin(angle))
                        Line(points=ray, width=1.8)
                        self.dimension_targets.append(((group, None), ray))
                elif group in ("stock_origin_mm", "work_offset_mm"):
                    point = draft.corner if group == "stock_origin_mm" else self.setup["work_offset_mm"]
                    px, py = x + point[0] * scale, y + point[vertical] * scale
                    Line(points=(x - dp(4), y, x + dp(4), y), width=1)
                    Line(points=(x, y - dp(4), x, y + dp(4)), width=1)
                    for axis, ray in ((0, (x, y, px, y)), (vertical, (px, y, px, py))):
                        Color(*(ACCENT if selected == axis else AMBER))
                        Line(points=ray, width=1.8)
                        self.dimension_targets.append(((group, axis), ray))
                    Line(circle=(px, py, dp(4)), width=1.5)
            frame = {
                "stock_size_mm": "Source stock frame",
                "stock_origin_mm": "Unrotated program frame",
                "work_offset_mm": "Declared machine frame",
                "stock_rotation_deg": "Rotated stock frame",
            }[group]
            label = self.annotations[view]
            label.size, label.pos = (half, dp(26)), (self.x + view * half, self.y)
            label.text_size = label.size
            label.text = f"{frame} · {'XY' if view == 0 else 'XZ'} · source mesh edges"
            projections.append(
                {"draft": draft.views[view], "previous": previous.views[view], "scale": scale, "zero": (x, y)}
            )
        self.imported_projections = tuple(projections)

    def _draw_offset(self, size, selected_axis):
        """Project declared stock and program zero using the simulation transform."""
        models = []
        footprints = []
        for setup in (self.setup, self.baseline or self.setup):
            model = MachineSetup(
                work_offset_mm=setup["work_offset_mm"],
                stock_size_mm=setup["stock_size_mm"],
                stock_origin_mm=setup["stock_origin_mm"],
                stock_rotation_deg=setup.get("stock_rotation_deg", 0),
            )
            models.append(model)
            if model.stock_size_mm is None:
                footprints.append(())
                continue
            low = model.stock_origin_mm
            dimensions = model.stock_size_mm
            footprints.append(
                tuple(
                    model.machine_point(model.stock_point(tuple(low[i] + dimensions[i] * bit[i] for i in range(3))))
                    for bit in ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1))
                )
            )
        all_points = [(0, 0, 0), *(model.work_offset_mm for model in models), *footprints[0], *footprints[1]]
        lower = [min(point[i] for point in all_points) for i in range(3)]
        span = [max(1, max(point[i] for point in all_points) - lower[i]) for i in range(3)]
        half = self.width / 2
        scale = min(max(1, half - dp(70)) / span[0], max(1, self.height - dp(64)) / max(span[1:]))
        projections = []
        for index, vertical in enumerate((1, 2)):
            x = self.x + index * half + (half - span[0] * scale) / 2 - lower[0] * scale
            y = self.y + dp(36) + (max(1, self.height - dp(64)) - span[vertical] * scale) / 2 - lower[vertical] * scale

            def project(point, x=x, y=y, vertical=vertical):
                return x + point[0] * scale, y + point[vertical] * scale

            draft, previous = (project(model.work_offset_mm) for model in models)
            outlines = []
            with self.ink:
                Color(*MUTED)
                Line(points=(x - dp(5), y, x + dp(5), y), width=1.2)
                Line(points=(x, y - dp(5), x, y + dp(5)), width=1.2)
                for which, footprint in enumerate(footprints):
                    if not footprint:
                        outlines.append(())
                        continue
                    points = tuple(project(point) for point in footprint)
                    # XY is the rotated lower face; XZ uses its projected envelope.
                    if vertical == 1:
                        outline = points[:4]
                    else:
                        left, right = min(p[0] for p in points), max(p[0] for p in points)
                        bottom, top = min(p[1] for p in points), max(p[1] for p in points)
                        outline = ((left, bottom), (right, bottom), (right, top), (left, top))
                    outlines.append(outline)
                    Color(*(ACCENT if which == 0 else MUTED))
                    Line(
                        points=tuple(c for point in outline for c in point),
                        close=True,
                        width=1.3 if which == 0 else 1,
                        dash_length=0 if which == 0 else dp(4),
                        dash_offset=0 if which == 0 else dp(3),
                    )
                Color(*MUTED)
                Line(circle=(*previous, dp(3)), width=1)
                Line(points=(*previous, *draft), width=1, dash_length=dp(3), dash_offset=dp(3))
                for axis, ray in ((0, (x, y, draft[0], y)), (vertical, (draft[0], y, *draft))):
                    Color(*(ACCENT if axis == selected_axis else MUTED))
                    Line(points=ray, width=1.8)
                    self.dimension_targets.append((("work_offset_mm", axis), ray))
                Color(*ACCENT)
                Line(circle=(*draft, dp(4)), width=1.5)
            projections.append(
                {"zero": (x, y), "draft": draft, "previous": previous, "scale": scale, "outlines": tuple(outlines)}
            )
            label = self.annotations[index]
            label.size = (half, dp(26))
            label.text_size = label.size
            label.pos = (self.x + index * half, self.y)
            label.text = f"Declared machine frame · {'XY footprint' if vertical == 1 else 'XZ envelope'}"
        self.offset_projections = tuple(projections)

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
            Line(points=(cx, cy, cx + radius, cy), width=1, dash_length=dp(3), dash_offset=dp(3))
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
        self.projection_loads.close()
        self.prepared_projection = None
        self.stock_model = None
        self.imported_projections = ()
        self.dimension_targets = []
        self.rotation_outline = ()
        self.offset_projections = ()
        self.origin_projections = ()
        self.size_projections = ()
        self.trigger.cancel()
