"""Compact declared/feedback study views with independent selection state."""

from kivy.metrics import dp

from carveracontroller.desktop_components import ACCENT, RAISED, TEXT, Action, AdaptiveGrid, Surface


class MotionStudyViews(Surface):
    def __init__(self, path, feedback, **kwargs):
        super().__init__(orientation="vertical", padding=0, spacing=dp(5), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.path, self.feedback = path, feedback
        self.report = self.identity = None
        self.mode = "Overview"
        self.tabs = AdaptiveGrid(max_cols=3, min_width=100, row_height=34, spacing=dp(5))
        self.actions = {}
        for name in ("Overview", "Declared path", "Feedback"):
            action = Action(name, lambda selected=name: self.select(selected))
            self.actions[name] = action
            self.tabs.add_widget(action)
        self.add_widget(self.tabs)
        self.refresh()

    def show(self, report, identity):
        changed = self.report is not report or self.identity != identity
        self.report, self.identity = report, identity
        self.path.show(report, identity)
        self.feedback.show(report.feedback if report else None, identity)
        if changed:
            self.mode = "Declared path" if report and report.path_points else "Overview"
        self.refresh()

    def select(self, mode):
        if mode not in self.actions or self.actions[mode].disabled:
            return
        self.mode = mode
        self.refresh()

    def refresh(self):
        available = {
            "Overview": True,
            "Declared path": bool(self.report and self.report.path_points),
            "Feedback": bool(self.report and self.report.feedback),
        }
        if not available[self.mode]:
            self.mode = "Overview"
        for name, action in self.actions.items():
            action.disabled = not available[name]
            if self.report is None or action.disabled:
                action.focus = False
            action.base_color = ACCENT if name == self.mode else RAISED
            action._paint()
            action.color = (0.02, 0.08, 0.1, 1) if name == self.mode else TEXT
        chosen = {"Declared path": self.path, "Feedback": self.feedback}.get(self.mode)
        for panel in (self.path, self.feedback):
            if panel.parent is self and panel is not chosen:
                self.remove_widget(panel)
        if chosen is not None and chosen.parent is None:
            self.add_widget(chosen)
        if chosen is not self.feedback:
            self.feedback.plot.focus = False
