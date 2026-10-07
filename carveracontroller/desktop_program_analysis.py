"""Local dialect and bounded cubic review; never changes controller configuration."""

import math

from kivy.graphics import Color, Line, Point, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    MUTED,
    RAISED,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    Surface,
    label,
)

DIALECTS = {"Carvera": "carvera", "LinuxCNC · G5 study": "linuxcnc"}


class AnalysisSettings(Surface):
    def __init__(self, owner):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.owner = owner
        self.applied = ("carvera", 0.01, 10000)
        self.add_widget(label("Local analysis settings", 12, height=24))
        self.dialect = Choice(text="Carvera", values=list(DIALECTS))
        self.add_widget(self.dialect)
        fields = AdaptiveGrid(max_cols=2, min_width=170, row_height=36, spacing=dp(5))
        self.tolerance = Field(text="0.01", hint_text="Spline position bound · mm")
        self.budget = Field(text="10000", hint_text="Maximum spline segments · whole job")
        fields.add_widget(self.tolerance)
        fields.add_widget(self.budget)
        self.add_widget(label("Position bound (mm) / whole-job segment limit", 11, MUTED, 24))
        self.add_widget(fields)
        from carveracontroller.desktop_operations import content_label

        self.status = content_label()
        self.add_widget(self.status)
        self.apply_action = Action("Apply & reanalyze", self.apply, disabled=True)
        self.add_widget(self.apply_action)
        self.dialect.bind(text=self.refresh)
        self.refresh()

    def reset(self):
        self.applied = ("carvera", 0.01, 10000)
        self.dialect.text, self.tolerance.text, self.budget.text = "Carvera", "0.01", "10000"
        self.refresh()

    def refresh(self, *_):
        study = self.dialect.text != "Carvera"
        self.tolerance.disabled = self.budget.disabled = not study
        self.apply_action.disabled = not bool(self.owner.analysis_filename)
        dialect, tolerance, budget = self.applied
        self.status.text = (
            f"Applied: {dialect}"
            + (f" · position bound {tolerance:g} mm · ≤{budget} spline segments" if dialect == "linuxcnc" else "")
            + "\nAnalysis only. Source bytes, upload dialect and connected-machine capabilities are unchanged. "
            "LinuxCNC studies use their own geometry view; backend execution remains unqualified."
        )

    def apply(self):
        if not self.owner.analysis_filename:
            return
        try:
            dialect = DIALECTS[self.dialect.text]
            if dialect == "carvera":
                values = (dialect, 0.01, 10000)
            else:
                tolerance = float(self.tolerance.text)
                budget = int(self.budget.text)
                if not math.isfinite(tolerance) or tolerance <= 0 or not 1 <= budget <= 100000:
                    raise ValueError("Use a positive finite mm bound and an integer segment limit from 1 to 100000.")
                values = (dialect, tolerance, budget)
        except (KeyError, ValueError, OverflowError) as exc:
            self.status.text = "Draft not applied: " + str(exc)
            return
        self.applied = values
        self.owner.load(self.owner.analysis_filename, analysis_settings=values)
        self.refresh()


class CubicPlot(Widget):
    def __init__(self):
        super().__init__(size_hint_y=None, height=dp(180))
        self.controls = self.points = self.overview = self.screen_points = ()
        self.bind(pos=self.draw, size=self.draw)

    def show(self, controls, points, overview=()):
        self.controls, self.points, self.overview = controls, points, overview
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        self.screen_points = ()
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            if not self.controls:
                return
            xs, ys = zip(*((p[0], p[1]) for p in self.controls))
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            scale = min(
                max(1, self.width - dp(24)) / max(max(xs) - min(xs), 1e-9),
                max(1, self.height - dp(24)) / max(max(ys) - min(ys), 1e-9),
            )

            def project(p):
                return self.center_x + (p[0] - cx) * scale, self.center_y + (p[1] - cy) * scale

            controls = tuple(project(p) for p in self.controls)
            Color(*MUTED[:3], 0.6)
            Line(points=[v for p in controls for v in p], width=0.7)
            Point(points=[v for p in controls for v in p], pointsize=dp(3))
            Color(*ACCENT[:3], 0.3)
            if len(self.overview) > 1:
                Line(points=[v for p in self.overview for v in project(p)], width=0.8)
            self.screen_points = tuple(project(p) for p in self.points)
            Color(*ACCENT)
            if len(self.screen_points) > 1:
                Line(points=[v for p in self.screen_points for v in p], width=1.3)


class CubicReview(Surface):
    PAGE_SEGMENTS = 256

    def __init__(self):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.identity = self.block = None
        self.page = 0
        self.points = ()
        self.overview = ()
        self.add_widget(label("Bounded cubic · work-frame XY", 12, height=24))
        self.plot = CubicPlot()
        self.add_widget(self.plot)
        from carveracontroller.desktop_operations import content_label

        self.note = content_label()
        self.add_widget(self.note)
        actions = AdaptiveGrid(max_cols=2, min_width=130, row_height=30, spacing=dp(5))
        self.previous = Action("Previous curve section", lambda: self.step(-1))
        self.next = Action("Next curve section", lambda: self.step(1))
        actions.add_widget(self.previous)
        actions.add_widget(self.next)
        self.add_widget(actions)

    def show(self, program, line):
        identity = (program.file_hash, program.dialect, line, id(program)) if program else None
        if identity == self.identity:
            return bool(self.block)
        self.identity, self.page = identity, 0
        self.block = program.spline_block(line) if program else None
        self.points = program.spline_points(line) if self.block else ()
        stride = max(1, math.ceil((len(self.points) - 1) / 1024))
        overview = self.points[::stride]
        self.overview = overview + (self.points[-1],) if overview and overview[-1] != self.points[-1] else overview
        self.refresh()
        return bool(self.block)

    def step(self, direction):
        if self.block:
            self.page = max(0, min((self.block.segments - 1) // self.PAGE_SEGMENTS, self.page + direction))
            self.refresh()

    def refresh(self):
        if not self.block:
            self.plot.show((), ())
            self.note.text = "No resolved cubic on the selected source line."
            self.previous.disabled = self.next.disabled = True
            return
        first = self.page * self.PAGE_SEGMENTS
        last = min(first + self.PAGE_SEGMENTS, self.block.segments)
        self.plot.show(self.block.control_points_mm, self.points[first : last + 1], self.overview)
        self.previous.disabled = first == 0
        self.next.disabled = last == self.block.segments
        self.note.text = (
            f"Source line {self.block.line_number} · program text SHA256 {self.identity[0]}\n"
            f"Segments {first + 1}–{last} of {self.block.segments} · exact section\n"
            f"Position error bound ≤{self.block.maximum_error_bound_mm:.6g} mm / requested {self.block.tolerance_mm:g} mm\n"
            + "\n".join(f"Control {i}: XYZ {tuple(p)} mm" for i, p in enumerate(self.block.control_points_mm, 1))
            + "\nBright teal: exact converted section. Dim teal: coarse whole-curve context, "
            "without a display-simplification error bound. Gray: complete control polygon. Equal XY scale; "
            "work-frame geometry only. Tangent/length accuracy, machine registration, clearance and execution unqualified."
        )
