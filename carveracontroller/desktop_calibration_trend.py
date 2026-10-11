"""Selectable, bounded calibration charts with original receipt attribution."""

from kivy.graphics import Color, Line, Point, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    AMBER,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    Choice,
    Surface,
)
from carveracontroller.desktop_tool_custody import stamp, wrapped
from carveracontroller.machine.calibration_bench import calibration_trend

METRICS = {
    "Applied TLO": "applied_mm",
    "Raw sample mean": "mean_mm",
    "Computed sample range": "range_mm",
    "Sample standard deviation": "stdev_mm",
    "Comparable offset change": "applied_change_mm",
}
ALL = "All groups · points only"


class CalibrationTrendPlot(Widget):
    def __init__(self, selected, **kwargs):
        super().__init__(**kwargs)
        self.selected = selected
        self.points, self.segments = [], []
        self.index = None
        self.bounds = None
        self.bind(pos=self.draw, size=self.draw)

    def show(self, data, index):
        self.points, self.segments, self.index = data["points"], data["segments"], index
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        values = [p["value_mm"] for p in self.points if p["value_mm"] is not None]
        self.bounds = (min(values), max(values)) if values else None
        scale = max([abs(v) for v in values] + [0.001])
        low, high = (self.bounds[0] / scale, self.bounds[1] / scale) if values else (0, 1)
        span = max(high - low, 0.002)
        low, high = low - span * 0.1, high + span * 0.1
        left, bottom = self.x + dp(12), self.y + dp(18)
        width, height = max(1, self.width - dp(24)), max(1, self.height - dp(30))
        xy = lambda i: (
            left + width * (0.5 if len(self.points) == 1 else i / max(1, len(self.points) - 1)),
            bottom - dp(7)
            if self.points[i]["value_mm"] is None
            else bottom + height * (self.points[i]["value_mm"] / scale - low) / (high - low),
        )
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            Color(*MUTED[:3], 0.35)
            for fraction in (0, 0.5, 1):
                y = bottom + height * fraction
                Line(points=[left, y, left + width, y], width=0.7)
            Color(*ACCENT[:3], 0.65)
            for a, b in self.segments:
                Line(points=[*xy(a), *xy(b)], width=1)
            for i, point in enumerate(self.points):
                Color(*(AMBER if point["value_mm"] is None else ACCENT))
                Point(points=xy(i), pointsize=dp(3))
                if point["row_index"] == self.index:
                    Color(*TEXT)
                    Line(circle=(*xy(i), dp(6)), width=1.3)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.points and not self.disabled:
            fraction = max(0, min(1, (touch.x - self.x - dp(12)) / max(1, self.width - dp(24))))
            index = round(fraction * (len(self.points) - 1))
            self.selected(self.points[index]["row_index"])
            return True
        return super().on_touch_down(touch)


class CalibrationTrend(Surface):
    PAGE = 60

    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.rows, self.groups = [], {}
        self.start, self.index = 0, None
        self._updating = False
        controls = AdaptiveGrid(max_cols=2, min_width=160, row_height=36, spacing=dp(6))
        self.metric = Choice(text="Applied TLO", values=tuple(METRICS))
        self.group = Choice(text=ALL, values=(ALL,))
        controls.add_widget(self.metric)
        controls.add_widget(self.group)
        self.add_widget(controls)
        self.summary = wrapped()
        self.add_widget(self.summary)
        self.plot = CalibrationTrendPlot(self.select, size_hint_y=None, height=dp(180))
        self.add_widget(self.plot)
        self.axis = wrapped()
        self.add_widget(self.axis)
        navigation = AdaptiveGrid(max_cols=2, min_width=100, row_height=32, spacing=dp(6))
        self.older = Action("Older reports", lambda: self.page(-1), height=dp(32))
        self.newer = Action("Newer reports", lambda: self.page(1), height=dp(32))
        navigation.add_widget(self.older)
        navigation.add_widget(self.newer)
        self.previous = Action("Previous receipt", lambda: self.step(-1), height=dp(32))
        self.following = Action("Next receipt", lambda: self.step(1), height=dp(32))
        navigation.add_widget(self.previous)
        navigation.add_widget(self.following)
        self.add_widget(navigation)
        self.detail = wrapped()
        self.add_widget(self.detail)
        self.metric.bind(text=lambda *_: self.render())
        self.group.bind(text=lambda *_: self.change_group())
        self.show([])

    @staticmethod
    def receipt_key(row, index):
        event = row["receipt"]
        return (
            event["id"],
            row["revision_id"],
            event["endpoint"],
            event["tool_number"],
            event["report"].get("timestamp"),
            index if event["id"] == "session-local" else None,
        )

    def show(self, rows):
        selected_key = (
            self.receipt_key(self.rows[self.index], self.index)
            if self.index is not None and self.index < len(self.rows)
            else None
        )
        group_key = self.groups.get(self.group.text)
        old_start = self.start
        self._updating = True
        self.rows = rows
        keys = list(
            dict.fromkeys((r["revision_id"], r["receipt"]["endpoint"], r["receipt"]["tool_number"]) for r in rows)
        )
        self.groups = {
            f"{i + 1}. {(revision or 'unversioned')[:8]} · {source or 'Unknown'} · T{tool}": (revision, source, tool)
            for i, (revision, source, tool) in enumerate(keys)
        }
        self.group.values = (ALL, *self.groups)
        self.group.text = next((name for name, key in self.groups.items() if key == group_key), ALL)
        retained = next((i for i, row in enumerate(rows) if self.receipt_key(row, i) == selected_key), None)
        self.start = (
            min(old_start, max(0, self.total() - self.PAGE))
            if retained is not None
            else max(0, self.total() - self.PAGE)
        )
        self.index = retained if retained is not None else len(rows) - 1 if rows else None
        self._updating = False
        self.render()

    def total(self):
        key = self.groups.get(self.group.text)
        return sum(
            key is None or (r["revision_id"], r["receipt"]["endpoint"], r["receipt"]["tool_number"]) == key
            for r in self.rows
        )

    def change_group(self):
        if not self._updating:
            self.start = max(0, self.total() - self.PAGE)
            self.index = None
            self.render()

    def page(self, direction):
        self.start = max(0, min(max(0, self.total() - self.PAGE), self.start + direction * self.PAGE))
        self.render()

    def step(self, direction):
        points = self.plot.points
        if points:
            position = next((i for i, p in enumerate(points) if p["row_index"] == self.index), 0)
            self.select(points[max(0, min(len(points) - 1, position + direction))]["row_index"])

    def select(self, index):
        self.index = index
        self.render()

    def render(self):
        if self._updating:
            return
        data = calibration_trend(
            self.rows, METRICS[self.metric.text], group=self.groups.get(self.group.text), start=self.start
        )
        self.plot.show(data, self.index)
        count = len(data["points"])
        missing = sum(p["value_mm"] is None for p in data["points"])
        self.summary.text = (
            f"Reports {self.start + 1}–{self.start + count} of {data['total']} · {missing} unknown values"
            if count
            else "No calibration reports in this selection"
        )
        self.summary.text += "\nCapture order · select a point to inspect its receipt; amber points are unknown."
        self.axis.text = (
            f"Displayed values {self.plot.bounds[0]:.6g} to {self.plot.bounds[1]:.6g} mm · numerical scale only"
            if self.plot.bounds
            else "No finite values to plot"
        )
        self.axis.text += "\nLines require comparable revision/source/tool receipts; gaps and scatter are retained."
        self.older.disabled = self.start == 0
        self.newer.disabled = self.start + count >= data["total"]
        visible = {p["row_index"] for p in data["points"]}
        if self.index not in visible:
            self.index = data["points"][-1]["row_index"] if count else None
            self.plot.show(data, self.index)
        position = next((i for i, p in enumerate(data["points"]) if p["row_index"] == self.index), None)
        self.previous.disabled = position is None or position == 0
        self.following.disabled = position is None or position == count - 1
        if self.index is None:
            self.detail.text = "Select or capture calibration evidence to inspect it here."
            return
        row = self.rows[self.index]
        event, report = row["receipt"], row["receipt"]["report"]
        samples = report.get("measurements", ())
        raw = ", ".join(f"{v:g}" if type(v) in (int, float) else repr(v) for v in samples[:20])
        selected_value = data["points"][position]["value_mm"]
        value_text = "Unknown" if selected_value is None else f"{selected_value:.6g} mm"
        self.detail.text = (
            f"{self.metric.text}: {value_text}\n"
            f"Receipt {event['id']} · capture #{self.index + 1}\n"
            f"Measured {stamp(report.get('timestamp', 0))} · {event['endpoint'] or 'Unknown source'} · T{event['tool_number']}\n"
            f"Definition {row['revision_id'] or 'unversioned'}\nRaw samples: {raw or 'None'}"
            + (f" · {len(samples) - 20} more retained in original receipt" if len(samples) > 20 else "")
            + f"\nComparable prior receipt: {row['previous_receipt_id'] or 'None; no baseline inferred'}"
        )
