"""Declared tool-tip geometry linked to signed axis demand; local inspection only."""

from kivy.graphics import Color, Line, Point, Rectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    Choice,
    Surface,
    label,
)


class DeclaredPathPlot(Widget):
    def __init__(self, selected, **kwargs):
        super().__init__(size_hint_y=None, height=dp(200), **kwargs)
        self.selected = selected
        self.coordinates = ()
        self.cursor = 0
        self.screen_points = ()
        self.bind(pos=self.draw, size=self.draw)

    def show(self, coordinates, cursor):
        self.coordinates, self.cursor = coordinates, cursor
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        self.screen_points = ()
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            if not self.coordinates:
                return
            # One scale for both axes preserves shape, including circular table paths.
            xs, ys = zip(*self.coordinates)
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            width, height = max(1, self.width - dp(24)), max(1, self.height - dp(24))
            scale = min(width / max(max(xs) - min(xs), 1e-9), height / max(max(ys) - min(ys), 1e-9))
            self.screen_points = tuple(
                (self.center_x + (x - cx) * scale, self.center_y + (y - cy) * scale) for x, y in self.coordinates
            )
            Color(*MUTED[:3], 0.35)
            Line(points=[self.x + dp(12), self.center_y, self.right - dp(12), self.center_y], width=0.7)
            Color(*ACCENT)
            if len(self.screen_points) > 1:
                Line(points=[value for point in self.screen_points for value in point], width=1.2)
            Point(points=[value for point in self.screen_points for value in point], pointsize=dp(2))
            Color(*TEXT)
            Line(circle=(*self.screen_points[self.cursor], dp(5)), width=1.2)

    def on_touch_down(self, touch):
        if getattr(touch, "button", "left") != "left":
            return False
        if self.collide_point(*touch.pos) and self.screen_points and not self.disabled:
            self.selected(
                min(
                    range(len(self.screen_points)),
                    key=lambda i: sum((a - b) ** 2 for a, b in zip(self.screen_points[i], touch.pos)),
                )
            )
            return True
        return super().on_touch_down(touch)


class DeclaredPathPanel(Surface):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(5), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.review = self.identity = None
        self.cursor = 0
        self.add_widget(label("Declared path & axis demand · local inspection", 12, height=26))
        choices = AdaptiveGrid(max_cols=3, min_width=130, row_height=36, spacing=dp(5))
        self.frame = Choice(text="Work frame", values=["Work frame", "World frame"])
        self.plane = Choice(text="XY", values=["XY", "XZ", "YZ"])
        self.joint = Choice(text="Joint", values=[])
        for choice in (self.frame, self.plane, self.joint):
            choices.add_widget(choice)
            choice.bind(text=self.refresh)
        self.add_widget(choices)
        self.plot = DeclaredPathPlot(lambda index: self.select((self.cursor // 200) * 200 + index))
        self.add_widget(self.plot)
        from carveracontroller.desktop_operations import content_label

        self.note = content_label()
        self.add_widget(self.note)
        controls = AdaptiveGrid(max_cols=4, min_width=120, row_height=30, spacing=dp(5))
        self.previous = Action("Previous pose", lambda: self.select(self.cursor - 1))
        self.next = Action("Next pose", lambda: self.select(self.cursor + 1))
        controls.add_widget(self.previous)
        controls.add_widget(self.next)
        controls.add_widget(Action("Previous 200 poses", lambda: self.select((self.cursor // 200 - 1) * 200)))
        controls.add_widget(Action("Next 200 poses", lambda: self.select((self.cursor // 200 + 1) * 200)))
        self.add_widget(controls)

    def show(self, review, identity):
        if self.review is review and self.identity == identity:
            return
        self.review, self.identity, self.cursor = review, identity, 0
        self.joint.values = [item.name for item in review.joint_demands] if review else []
        if self.joint.text not in self.joint.values:
            self.joint.text = self.joint.values[0] if self.joint.values else "Joint"
        self.refresh()

    def select(self, cursor):
        if self.review and self.review.path_points:
            self.cursor = max(0, min(cursor, len(self.review.path_points) - 1))
            self.refresh()

    def refresh(self, *_):
        # Choice callbacks can fire while the panel is being assembled.
        if not hasattr(self, "plot"):
            return
        points = self.review.path_points if self.review else ()
        axes = {"XY": (0, 1), "XZ": (0, 2), "YZ": (1, 2)}[self.plane.text]
        tips = [point.work_tip_mm if self.frame.text == "Work frame" else point.world_tip_mm for point in points]
        first = (self.cursor // 200) * 200
        self.plot.show(tuple((tip[axes[0]], tip[axes[1]]) for tip in tips[first : first + 200]), self.cursor - first)
        self.previous.disabled = not points or self.cursor == 0
        self.next.disabled = not points or self.cursor == len(points) - 1
        if not points:
            self.note.text = "No declared path samples supplied."
            return
        point, tip = points[self.cursor], tips[self.cursor]
        demand = next(item for item in self.review.joint_demands if item.name == self.joint.text)
        unit = "mm" if demand.kind == "linear" else "deg"
        rate = dict(point.incoming_rates).get(demand.name)
        rate_text = f"{rate:.6g} {unit}/s" if rate is not None else "unknown at initial pose"
        self.note.text = (
            f"Pose {self.cursor + 1} of {len(points)} · displayed {first + 1}–{min(first + 200, len(points))} · declared t {point.elapsed:.6g} s\n"
            f"{self.frame.text} tip XYZ: {tip[0]:.6g}, {tip[1]:.6g}, {tip[2]:.6g} mm · {self.plane.text} equal-scale projection\n"
            f"{demand.name}: {dict(point.positions)[demand.name]:.6g} {unit} · preceding interval velocity {rate_text}\n"
            f"Declared velocity limit {demand.limit_per_second:g} {unit}/s · click nearest projected pose or use pose controls. "
            "Overlapping projections select the first nearest pose. Sampled chords only; acceleration, blending, "
            "collision checks and alignment to feedback clocks remain unqualified."
        )
