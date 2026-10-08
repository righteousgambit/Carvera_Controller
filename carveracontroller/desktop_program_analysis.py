"""Local dialect and bounded cubic review; never changes controller configuration."""

import math

from kivy.graphics import Color, Line, Point, Rectangle
from kivy.metrics import dp
from kivy.uix.stencilview import StencilView

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

DIALECTS = {"Carvera": "carvera", "LinuxCNC · spline study": "linuxcnc"}


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


class CubicPlot(StencilView):
    def __init__(self):
        super().__init__(size_hint_y=None, height=dp(180))
        self.controls = self.points = self.overview = self.screen_points = ()
        self.axes = (0, 1)
        self.fit_section = False
        self.show_controls = True
        self.bind(pos=self.draw, size=self.draw)

    def show(self, controls, points, overview=(), axes=(0, 1)):
        self.controls, self.points, self.overview = controls, points, overview
        self.axes = axes
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        self.screen_points = ()
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            if not self.controls:
                return
            u, v = self.axes
            bounds = self.points if self.fit_section and self.points else self.controls
            xs, ys = zip(*((p[u], p[v]) for p in bounds))
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            scale = min(
                max(1, self.width - dp(24)) / max(max(xs) - min(xs), 1e-9),
                max(1, self.height - dp(24)) / max(max(ys) - min(ys), 1e-9),
            )

            def project(p):
                return self.center_x + (p[u] - cx) * scale, self.center_y + (p[v] - cy) * scale

            if self.show_controls:
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
    PAGE_DATA = 16

    def __init__(self):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None)
        self.bind(minimum_height=self.setter("height"))
        self.identity = self.block = None
        self.page = 0
        self.data_page = 0
        self.points = ()
        self.overview = ()
        self.title = label("Bounded spline · work-frame XY", 12, height=24)
        self.add_widget(self.title)
        self.plot = CubicPlot()
        self.add_widget(self.plot)
        view_options = AdaptiveGrid(max_cols=2, min_width=150, row_height=30, spacing=dp(5))
        self.framing = Choice(text="Fit whole spline", values=["Fit whole spline", "Fit current section"])
        self.control_visibility = Choice(
            text="Show control polygon", values=["Show control polygon", "Hide control polygon"]
        )
        view_options.add_widget(self.framing)
        view_options.add_widget(self.control_visibility)
        self.add_widget(view_options)
        self.framing.bind(text=self.update_view)
        self.control_visibility.bind(text=self.update_view)
        from carveracontroller.desktop_operations import content_label

        self.note = content_label()
        self.add_widget(self.note)
        actions = AdaptiveGrid(max_cols=2, min_width=130, row_height=30, spacing=dp(5))
        self.previous = Action("Previous curve section", lambda: self.step(-1))
        self.next = Action("Next curve section", lambda: self.step(1))
        actions.add_widget(self.previous)
        actions.add_widget(self.next)
        self.curve_actions = actions
        data_actions = AdaptiveGrid(max_cols=2, min_width=130, row_height=30, spacing=dp(5))
        self.previous_data = Action("Previous control data", lambda: self.step_data(-1))
        self.next_data = Action("Next control data", lambda: self.step_data(1))
        data_actions.add_widget(self.previous_data)
        data_actions.add_widget(self.next_data)
        self.data_actions = data_actions
        self.paging = None

    def update_view(self, *_):
        self.plot.fit_section = self.framing.text == "Fit current section"
        self.plot.show_controls = self.control_visibility.text == "Show control polygon"
        self.refresh()

    def sync_paging(self, segments, data_count):
        paging = (segments > self.PAGE_SEGMENTS, data_count > self.PAGE_DATA)
        if paging == self.paging:
            return
        self.paging = paging
        for panel in (self.curve_actions, self.data_actions):
            if panel.parent is self:
                self.remove_widget(panel)
        for visible, panel in zip(paging, (self.curve_actions, self.data_actions)):
            if visible:
                self.add_widget(panel)

    def show(self, program, line):
        identity = (program.file_hash, program.dialect, line, id(program)) if program else None
        if identity == self.identity:
            return bool(self.block)
        self.identity, self.page, self.data_page = identity, 0, 0
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

    def step_data(self, direction):
        if self.block:
            count = len(self.block.original_control_points_mm or self.block.control_points_mm)
            if hasattr(self.block, "data"):
                count = max(count, len(self.block.data.curve.knots))
            self.data_page = max(0, min((count - 1) // self.PAGE_DATA, self.data_page + direction))
            self.refresh()

    def refresh(self):
        if not self.block:
            self.framing.disabled = self.control_visibility.disabled = True
            self.sync_paging(0, 0)
            self.plot.show((), ())
            self.note.text = "No resolved spline on the selected source line."
            self.previous.disabled = self.next.disabled = True
            self.previous_data.disabled = self.next_data.disabled = True
            return
        self.framing.disabled = self.control_visibility.disabled = False
        plane = getattr(self.block, "plane", "G17")
        projection, axes = {"G17": ("XY", (0, 1)), "G18": ("XZ", (0, 2)), "G19": ("YZ", (1, 2))}[plane]
        self.title.text = f"Bounded {self.block.source_command} · work-frame {projection}"
        first = self.page * self.PAGE_SEGMENTS
        last = min(first + self.PAGE_SEGMENTS, self.block.segments)
        controls = self.block.original_control_points_mm or self.block.control_points_mm
        self.plot.show(controls, self.points[first : last + 1], self.overview, axes)
        self.previous.disabled = first == 0
        self.next.disabled = last == self.block.segments
        data_first = self.data_page * self.PAGE_DATA
        data_last = data_first + self.PAGE_DATA
        count = len(controls)
        source = f"source line {self.block.line_number}"
        rows = [f"Control {i}: XYZ {tuple(p)} mm" for i, p in enumerate(controls[data_first:data_last], data_first + 1)]
        if hasattr(self.block, "data"):
            data = self.block.data
            count = max(count, len(data.curve.knots))
            source = f"source lines {data.start_line}–{data.end_line}; motion on closure {self.block.line_number}"
            rows = [
                f"Control {i + 1}: XYZ {tuple(controls[i])} mm · weight {data.curve.weights[i]:g} · "
                + (
                    f"source line {data.control_source_lines[i]}"
                    if data.control_source_lines[i] is not None
                    else "implicit pre-block position"
                )
                for i in range(data_first, min(data_last, len(controls)))
            ]
            rows += [
                f"Knot {i + 1}: {value:g}" for i, value in enumerate(data.curve.knots[data_first:data_last], data_first)
            ]
            rows.insert(
                0,
                f"Degree {data.curve.degree} · interpreter {data.interpreter_revision} · data SHA256 {data.source_sha256}",
            )
        self.previous_data.disabled = data_first == 0
        self.next_data.disabled = data_last >= count
        self.sync_paging(self.block.segments, count)
        self.note.text = (
            f"{self.block.source_command} {source} · program text SHA256 {self.identity[0]}\n"
            f"Segments {first + 1}–{last} of {self.block.segments} · exact section\n"
            f"Position error bound ≤{self.block.maximum_error_bound_mm:.6g} mm / requested {self.block.tolerance_mm:g} mm\n"
            + f"Control/knot data {data_first + 1}–{min(data_last, count)} of {count}\n"
            + "\n".join(rows)
            + "\nBright teal: exact converted section. Dim teal: coarse whole-curve context, "
            "without a display-simplification error bound. "
            + (
                "Gray: complete control polygon. "
                if self.plot.show_controls
                else "Control polygon hidden; original data retained. "
            )
            + (
                "Current-section framing; outside context clipped. "
                if self.plot.fit_section
                else "Whole-spline framing. "
            )
            + f"Equal {projection} scale; "
            "work-frame geometry only. Tangent/length accuracy, machine registration, clearance and execution unqualified."
        )
