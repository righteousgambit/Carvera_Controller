"""Compact, selectable clearance trace without modifying stencil ownership."""

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Canvas, Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.stencilview import StencilView

from carveracontroller.desktop_components import ACCENT, AMBER, BORDER, DANGER, MUTED, Action, Choice, Surface, label
from carveracontroller.desktop_operations import content_label

COLORS = {"cutter": AMBER, "shank": (0.40, 0.65, 0.98, 1), "holder": ACCENT}


class ClearancePlot(StencilView):
    def __init__(self, on_select, **kwargs):
        super().__init__(size_hint_y=None, height=dp(190), **kwargs)
        self.report = None
        self.component = "All"
        self.scale_mm = 25
        self.y_maximum = 25
        self.selected = None
        self.rendered = ()
        self.on_select = on_select
        self.ink = Canvas()
        self.canvas.add(self.ink)
        self.bind(pos=lambda *_: self.paint(), size=lambda *_: self.paint())

    def plot_bounds(self):
        gutter, edge = min(dp(42), self.width * 0.2), min(dp(6), self.width * 0.05)
        return self.x + gutter, self.y + dp(12), max(1, self.width - gutter - edge), max(1, self.height - dp(24))

    def paint(self):
        self.ink.clear()
        if not self.report:
            self.rendered = ()
            return
        points = [
            p
            for p in self.report.points
            if p.upper_mm is not None and (self.component == "All" or p.component == self.component)
        ]
        extent = max((p.end_distance_mm for p in self.report.points), default=1) or 1
        maximum = self.scale_mm or max((p.upper_mm for p in points), default=1) or 1
        self.y_maximum = maximum
        left, bottom, width, height = self.plot_bounds()
        # Keep the lowest lower bound in every component/display bin. This is
        # render-only aggregation; every source motion remains in the report.
        bins = {}
        count = min(800, max(1, int(width / dp(2))))
        for point in points:
            center = (point.start_distance_mm + point.end_distance_mm) / 2
            bucket = min(count - 1, int(center / extent * count))
            key = (point.component, bucket)
            if key not in bins or point.lower_mm < bins[key].lower_mm:
                bins[key] = point
        self.rendered = tuple(bins.values())
        with self.ink:
            Color(*BORDER)
            for fraction in (0, 0.25, 0.5, 0.75, 1):
                y = bottom + height * fraction
                Color(*BORDER)
                Line(points=[left, y, left + width, y], width=0.7)
                tick = CoreLabel(text=f"{maximum * fraction:g}", font_name="Roboto", font_size=dp(10), color=MUTED)
                tick.refresh()
                Color(1, 1, 1, 1)
                Rectangle(
                    texture=tick.texture, pos=(self.x + dp(3), y - tick.texture.size[1] / 2), size=tick.texture.size
                )
            for point in self.rendered:
                x0 = left + width * point.start_distance_mm / extent
                x1 = left + width * point.end_distance_mm / extent
                y0 = bottom + height * min(maximum, point.lower_mm) / maximum
                y1 = bottom + height * min(maximum, point.upper_mm) / maximum
                Color(*(DANGER if point.upper_mm == 0 else COLORS[point.component]))
                Line(points=[x0, y0, max(x0 + dp(1), x1), y0], width=1.4)
                Line(points=[(x0 + x1) / 2, y0, (x0 + x1) / 2, y1], width=1)
            if self.selected:
                middle = (self.selected.start_distance_mm + self.selected.end_distance_mm) / 2
                x = left + width * middle / extent
                Color(*MUTED)
                Line(points=[x, self.y, x, self.top], width=1.1)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.rendered:
            extent = max((p.end_distance_mm for p in self.report.points), default=1) or 1
            left, bottom, width, height = self.plot_bounds()
            maximum = self.y_maximum

            def screen_distance(point):
                x0 = left + width * point.start_distance_mm / extent
                x1 = left + width * point.end_distance_mm / extent
                y = bottom + height * min(maximum, point.lower_mm) / maximum
                dx = max(x0 - touch.x, touch.x - x1, 0)
                return dx * dx + (y - touch.pos[1]) ** 2

            point = min(self.rendered, key=lambda p: (screen_distance(p), p.lower_mm))
            self.selected = point
            self.paint()
            self.on_select(point)
            return True
        return super().on_touch_down(touch)


class ClearanceCard(Surface):
    def __init__(self, seek, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.seek = seek
        self.report = None
        self.add_widget(label("Minimum clearance per motion · mm", 13, height=28, bold=True))
        self.summary = content_label("Calculate material removal, then review clearances to plot the captured setup.")
        self.add_widget(self.summary)
        controls = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.component = Choice(text="All", values=("All", "cutter", "shank", "holder"))
        self.scale = Choice(text="25 mm", values=("5 mm", "25 mm", "Auto"))
        controls.add_widget(self.component)
        controls.add_widget(self.scale)
        self.add_widget(controls)
        self.plot = ClearancePlot(self.select)
        self.add_widget(self.plot)
        self.axes = content_label(
            "Y: 0–25 mm · X: cumulative resolved motion distance · cutter amber / body blue / holder teal"
        )
        self.add_widget(self.axes)
        self.details = content_label(
            "Select a motion interval. Each horizontal mark is the minimum over that entire motion; it is not an instantaneous position trace."
        )
        self.add_widget(self.details)
        self.inspect = Action("Inspect selected motion", lambda: self.seek(self.plot.selected), height=dp(34))
        self.add_widget(self.inspect)
        self.component.bind(text=lambda *_: self.update_plot())
        self.scale.bind(text=lambda *_: self.update_plot())

    def set_report(self, report):
        self.report = self.plot.report = report
        self.plot.selected = None
        unknown = sum(p.upper_mm is None for p in report.points)
        coverage = f"{report.processed_segments}/{report.total_segments} motions examined"
        if report.scope_lines:
            coverage += f" · lines {report.scope_lines[0]}–{report.scope_lines[1]}"
        if report.cancelled or report.budget_exhausted:
            coverage += " · PARTIAL: " + ("cancelled" if report.cancelled else "calculation budget reached")
        self.summary.text = f"{coverage} · numerical tolerance {report.tolerance_mm:g} mm\n{unknown} orientation intervals unknown. {report.qualification}. Initial-stock checks include material already removed."
        if report.unknown_components:
            self.summary.text += "\nUnknown: " + "; ".join(report.unknown_components)
        self.details.text = (
            "Select a plotted motion interval to inspect its source and assembly section."
            if report.points
            else "No modeled obstacle pairs were available; clearance is unknown."
        )
        self.update_plot()

    def update_plot(self):
        self.plot.component = self.component.text
        if self.plot.selected and self.component.text != "All" and self.plot.selected.component != self.component.text:
            self.plot.selected = None
            self.details.text = "Select a motion interval for this component."
        self.plot.scale_mm = None if self.scale.text == "Auto" else float(self.scale.text.split()[0])
        self.plot.paint()
        if self.report and not self.plot.rendered:
            self.details.text = "No numeric trace for this selection: geometry, orientation or obstacle inputs are missing. Clearance remains unknown."
        points = self.report.points if self.report else ()
        extent = max((p.end_distance_mm for p in points), default=0)
        maximum = self.plot.y_maximum
        self.axes.text = f"Y: 0–{maximum:g} mm · X: 0–{extent:,.2f} mm resolved motion\nCutter amber · body blue · holder teal · contact red. Values above the Y range are clipped; selection retains exact values. Display bins retain their smallest lower bound."

    def select(self, point):
        self.plot.selected = point
        value = (
            f"{point.lower_mm:.4f}–{point.upper_mm:.4f} mm"
            if point.upper_mm is not None
            else f"≥ {point.lower_mm:.4f} mm lower bound; exact clearance unknown"
        )
        section = point.section
        self.details.text = f"Line {point.line} · T{point.tool_id} · {point.component} near {point.obstacle}\nClearance: {value}\n{point.method}\nSection: tip +{section.low_mm:.3f}–{section.high_mm:.3f} mm · radius {section.radius_mm:.3f} mm\n{section.source}"
        if point.upper_mm == 0:
            self.details.text += "\nPotential envelope contact; contact position within this motion is not localized."
