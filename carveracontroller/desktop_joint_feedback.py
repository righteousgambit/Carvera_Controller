"""Time-based feedback inspection; chart selections never seek or move a machine."""

from dataclasses import dataclass

from kivy.metrics import dp

from carveracontroller.desktop_commissioning_trace import JointTracePlot
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Surface, label


@dataclass(frozen=True)
class FeedbackPoint:
    sample: int
    elapsed: float
    values: tuple[float, ...]


@dataclass(frozen=True)
class FeedbackPlotData:
    names: tuple[str, ...]
    points: tuple[FeedbackPoint, ...]
    segments: tuple[tuple[int, int], ...]


class JointFeedbackPanel(Surface):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.review = None
        self.identity = None
        self.cursor = 0
        self.page = 0
        self.selected_series = None
        self.add_widget(label("Supplied feedback trace · local inspection", 12, height=26))
        choices = AdaptiveGrid(max_cols=2, min_width=140, row_height=36, spacing=dp(5))
        self.joint = Choice(text="Joint", values=[])
        self.metric = Choice(text="Reported position", values=[])
        choices.add_widget(self.joint)
        choices.add_widget(self.metric)
        self.add_widget(choices)
        self.plot = JointTracePlot(self.select)
        self.add_widget(self.plot)
        from carveracontroller.desktop_operations import content_label

        self.note = content_label()
        self.add_widget(self.note)
        controls = AdaptiveGrid(max_cols=4, min_width=100, row_height=30, spacing=dp(5))
        self.previous = Action("Previous samples", lambda: self.step_page(-1))
        self.next = Action("Next samples", lambda: self.step_page(1))
        controls.add_widget(self.previous)
        controls.add_widget(self.next)
        controls.add_widget(Action("Previous point", lambda: self.select(self.cursor - 1)))
        controls.add_widget(Action("Next point", lambda: self.select(self.cursor + 1)))
        self.add_widget(controls)
        self.joint.bind(text=self.change_selection)
        self.metric.bind(text=self.change_selection)

    def show(self, review, identity):
        if self.identity == identity and self.review is review:
            return
        self.review, self.identity = review, identity
        self.cursor = self.page = 0
        self.joint.values = [item.name for item in review.demands] if review else []
        if self.joint.text not in self.joint.values:
            self.joint.text = self.joint.values[0] if self.joint.values else "Joint"
        self.change_selection()

    def change_selection(self, *_):
        self.cursor = self.page = 0
        available = [item.metric for item in self.review.series if item.name == self.joint.text] if self.review else []
        self.metric.values = available
        if self.metric.text not in available:
            self.metric.text = available[0] if available else "Reported position"
        self.refresh()

    def select(self, cursor):
        series = self.selected_series
        if not series or not series.times:
            return
        self.cursor = max(0, min(cursor, len(series.times) - 1))
        self.page = self.cursor // 200
        self.refresh()

    def step_page(self, direction):
        self.select((self.page + direction) * 200)

    def refresh(self):
        series = (
            next((s for s in self.review.series if (s.name, s.metric) == (self.joint.text, self.metric.text)), None)
            if self.review
            else None
        )
        self.selected_series = series
        count = len(series.times) if series else 0
        first, last = self.page * 200, min((self.page + 1) * 200, count)
        points = (
            tuple(FeedbackPoint(index, series.times[index], (series.values[index],)) for index in range(first, last))
            if series
            else ()
        )
        trace = FeedbackPlotData((self.metric.text,), points, tuple((i - 1, i) for i in range(1, len(points))))
        self.plot.show(trace, self.cursor)
        self.previous.disabled = self.page == 0
        self.next.disabled = last >= count
        if not count:
            self.note.text = (
                "No samples for this metric · derivatives need sufficient positions; commands may be absent."
            )
            return
        base = "mm" if series.kind == "linear" else "deg"
        suffix = {"Velocity": "/s", "Acceleration": "/s²", "Jerk": "/s³"}.get(series.metric, "")
        self.note.text = (
            f"{series.name} · {series.metric} · {base}{suffix} · points {first + 1}–{last} of {count}\n"
            f"Selected {self.cursor + 1}: t {series.times[self.cursor]:.6g} s · value {series.values[self.cursor]:.6g} {base}{suffix}\n"
            f"Displayed time {points[0].elapsed:.6g}–{points[-1].elapsed:.6g} s · sample range "
            f"{min(p.values[0] for p in points):.6g}–{max(p.values[0] for p in points):.6g} {base}{suffix}\n"
            f"Maximum supplied gap {self.review.maximum_gap_seconds:.6g} s · click nearest point or use point controls. "
            "Lines connect supplied/derived samples only; between-sample peaks and clock alignment are unqualified."
        )
