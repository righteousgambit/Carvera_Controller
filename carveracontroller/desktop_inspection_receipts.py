"""Compact, searchable inspection receipts and signed-deviation selection."""

import math

from kivy.clock import Clock
from kivy.graphics import Color, Line, Point, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    DANGER,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_planning import PlanningCard
from carveracontroller.machine.surface_inspection import sample_results


class InspectionDeviationPlot(Widget):
    """Receipt order, never interpolated measurement values or machine motion."""

    def __init__(self, selected, **kwargs):
        super().__init__(**kwargs)
        self.selected = selected
        self.rows = []
        self.limits = (None, None)
        self.index = None
        self.bind(pos=self._draw, size=self._draw)

    def show(self, rows, limits, index):
        self.rows, self.limits, self.index = rows, limits, index
        self._draw()

    def _draw(self, *_):
        self.canvas.clear()
        if not self.rows:
            return
        values = [result["deviation_mm"] for _, result in self.rows if result["deviation_mm"] is not None]
        values += [value for value in self.limits if value is not None]
        values.append(0)
        low, high = min(values), max(values)
        # Scaling by the largest magnitude avoids an overflowing high-low range.
        scale = max(abs(low), abs(high), 0.001)
        low, high = low / scale, high / scale
        span = max(0.002, high - low)
        low, high = low - span * 0.12, high + span * 0.12
        x, y = self.x + dp(8), self.y + dp(12)
        width, height = max(1, self.width - dp(16)), max(1, self.height - dp(24))
        px = lambda index: x + width * (0.5 if len(self.rows) == 1 else index / (len(self.rows) - 1))
        py = lambda value: y + height * (value / scale - low) / (high - low)
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            lower, upper = self.limits
            if lower is not None and upper is not None:
                Color(*ACCENT[:3], 0.14)
                Rectangle(pos=(x, py(lower)), size=(width, max(1, py(upper) - py(lower))))
                Color(*ACCENT[:3], 0.5)
                for limit in self.limits:
                    Line(points=[x, py(limit), x + width, py(limit)], width=1)
            Color(*MUTED)
            Line(points=[x, py(0), x + width, py(0)], width=1)
            groups = {}
            for i, (_, result) in enumerate(self.rows):
                deviation = result["deviation_mm"]
                groups.setdefault(result["state"], []).extend(
                    (px(i), y - dp(5) if deviation is None else py(deviation))
                )
            for state, points in groups.items():
                Color(
                    *(
                        DANGER
                        if state == "outside_declared_limits"
                        else ACCENT
                        if state == "within_declared_limits"
                        else MUTED
                    )
                )
                Point(points=points, pointsize=dp(3))
            if self.index is not None:
                Color(*TEXT)
                Line(points=[px(self.index), y - dp(8), px(self.index), y + height], width=dp(1))

    def on_touch_down(self, touch):
        if self.rows and not self.disabled and self.collide_point(*touch.pos):
            if getattr(touch, "is_mouse_scrolling", False):
                return super().on_touch_down(touch)
            ratio = min(1, max(0, (touch.x - self.x - dp(8)) / max(1, self.width - dp(16))))
            self.selected(round(ratio * (len(self.rows) - 1)))
            return True
        return super().on_touch_down(touch)


class InspectionReceiptPanel(PlanningCard):
    PAGE_SIZE = 12
    FILTERS = ("All receipts", "Outside limits", "Unevaluated", "Within limits", "Untoleranced")
    STATES = dict(
        zip(FILTERS[1:], ("outside_declared_limits", "unevaluated", "within_declared_limits", "untoleranced"))
    )

    def __init__(self):
        super().__init__("Receipt history & deviations")
        self.feature = None
        self.rows = []
        self.filtered = []
        self.selected_id = None
        self.page = 0
        self.buttons = []
        controls = AdaptiveGrid(max_cols=2, min_width=145, row_height=40, spacing=dp(6))
        self.search = Field(hint_text="Find receipt…")
        self.filter = Choice(text=self.FILTERS[0], values=self.FILTERS)
        controls.add_widget(self.search)
        controls.add_widget(self.filter)
        self.content.add_widget(controls)
        self.status = content_label("No retained receipts.")
        self.content.add_widget(self.status)
        self.plot = InspectionDeviationPlot(self.select, height=dp(130), size_hint_y=None)
        self.content.add_widget(self.plot)
        self.legend = content_label(
            "Signed normal deviation · horizontal = filtered receipt order; shaded band = declared limits. Green = within limits, red = outside, grey = untoleranced; grey marks below the plot = unevaluated. Click to inspect; no interpolation."
        )
        self.content.add_widget(self.legend)
        self.details = content_label("Select a retained receipt to inspect its provenance.")
        self.content.add_widget(self.details)
        self.choices = BoxLayout(orientation="vertical", size_hint_y=None, height=0, spacing=dp(5))
        self.choices.bind(minimum_height=self.choices.setter("height"))
        self.receipt_scroll = ScrollView(do_scroll_x=False, size_hint_y=None, height=0)
        self.receipt_scroll.add_widget(self.choices)
        self.choices.bind(
            minimum_height=lambda _widget, height: setattr(self.receipt_scroll, "height", min(dp(240), height))
        )
        self.content.add_widget(self.receipt_scroll)
        navigation = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous receipts", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next receipts", lambda: self.change_page(1), disabled=True)
        navigation.add_widget(self.previous)
        navigation.add_widget(self.next)
        self.content.add_widget(navigation)
        self.search.bind(text=self._filter_changed)
        self.filter.bind(text=self._filter_changed)

    def show(self, feature, *, draft=False):
        self.draft = draft
        prior = self.feature
        old_last = self.rows[-1][0]["id"] if self.rows else None
        self.feature = feature
        self.rows = list(zip(feature["samples"], sample_results(feature))) if feature is not None else []
        if prior is None or feature is None or prior["id"] != feature["id"]:
            self.selected_id = None
            self.page = 0
        elif self.rows and self.rows[-1][0]["id"] != old_last:
            self.selected_id = self.rows[-1][0]["id"]
        self._filter_changed()

    def _filter_changed(self, *_):
        needle = self.search.text.strip().casefold()
        state = self.STATES.get(self.filter.text)
        self.filtered = [
            (sample, result)
            for sample, result in self.rows
            if (state is None or result["state"] == state)
            and (
                not needle
                or needle
                in "\n".join(
                    (
                        sample["id"],
                        sample["source_ref"],
                        sample["registration_ref"],
                        sample["calibration_ref"],
                        sample["observed_at"],
                    )
                ).casefold()
            )
        ]
        ids = [sample["id"] for sample, _ in self.filtered]
        if self.selected_id not in ids:
            self.selected_id = ids[-1] if ids else None
        self.page = ids.index(self.selected_id) // self.PAGE_SIZE if self.selected_id is not None else 0
        self._paint()

    def reveal(self, receipt_id):
        """Reveal an exact retained identity, clearing filters that could hide it."""
        if not any(sample["id"] == receipt_id for sample, _ in self.rows):
            return False
        if not self.expanded:
            self.toggle()
        self.search.text = ""
        self.filter.text = "All receipts"
        self._filter_changed()
        self.select(next(i for i, (sample, _) in enumerate(self.filtered) if sample["id"] == receipt_id))
        return True

    def select(self, index):
        if not 0 <= index < len(self.filtered):
            return
        self.selected_id = self.filtered[index][0]["id"]
        self.page = index // self.PAGE_SIZE
        self._paint()

    def change_page(self, delta):
        page = self.page + delta
        if 0 <= page < math.ceil(len(self.filtered) / self.PAGE_SIZE):
            self.select(page * self.PAGE_SIZE)

    def _paint(self):
        self.choices.clear_widgets()
        self.buttons = []
        ids = [sample["id"] for sample, _ in self.filtered]
        selected = ids.index(self.selected_id) if self.selected_id in ids else None
        self.plot.show(self.filtered, self.feature["limits_mm"] if self.feature else (None, None), selected)
        self.plot.height = dp(130) if self.filtered else 0
        values = [result["deviation_mm"] for _, result in self.filtered if result["deviation_mm"] is not None]
        if self.feature:
            values += [value for value in self.feature["limits_mm"] if value is not None]
        values.append(0)
        self.legend.text = (
            f"Values and limits: {min(values):+.5g} to {max(values):+.5g} mm · zero included\n"
            "Horizontal = filtered receipt order. Shaded band = declared limits; green = within, red = outside, grey = untoleranced. Grey marks below the plot are unevaluated. Click to inspect; no interpolation."
        )
        pages = max(1, math.ceil(len(self.filtered) / self.PAGE_SIZE))
        state = "proposed entries" if getattr(self, "draft", False) else "retained receipts"
        self.status.text = f"{len(self.filtered)} of {len(self.rows)} {state} · page {self.page + 1}/{pages}"
        self.previous.disabled = self.page == 0
        self.next.disabled = self.page >= pages - 1
        start = self.page * self.PAGE_SIZE
        for i, (sample, result) in enumerate(self.filtered[start : start + self.PAGE_SIZE], start):
            value = result["deviation_mm"]
            deviation = "Not evaluated" if value is None else f"{value:+.5f} mm"
            caption = f"{sample['source_ref'][:72]}\n{deviation} · {result['state'].replace('_', ' ')}"
            action = Action(caption, lambda index=i: self.select(index), height=dp(54))
            action.bind(width=lambda button, width: setattr(button, "text_size", (max(dp(10), width - dp(12)), None)))
            action.bind(texture_size=lambda button, size: setattr(button, "height", max(dp(54), size[1] + dp(12))))
            action.base_color = ACCENT if i == selected else RAISED
            action.color = BG if i == selected else TEXT
            action._paint()
            self.choices.add_widget(action)
            self.buttons.append(action)
        selected_button = next((button for i, button in enumerate(self.buttons, start) if i == selected), None)
        if selected_button is not None:
            Clock.schedule_once(
                lambda _dt: (
                    self.receipt_scroll.scroll_to(selected_button, padding=dp(4), animate=False)
                    if selected_button.parent is self.choices
                    else None
                ),
                0,
            )
        if selected is None:
            self.details.text = (
                "No receipts match the current filter."
                if self.rows
                else "No retained receipts. Measurement conformance is unknown."
            )
            return
        sample, result = self.filtered[selected]
        value = result["deviation_mm"]
        reason = (
            (
                "Raw trigger coordinates cannot be compared as compensated ball centers."
                if sample["kind"] == "raw_trigger"
                else "A registration and a probe compensation reference are both required."
            )
            if value is None
            else "Numerical comparison uses declared geometry and references; measurement accuracy remains unverified."
        )
        self.details.text = "\n".join(
            (
                ("Proposed entry " if getattr(self, "draft", False) else "Receipt ") + sample["id"],
                f"Source: {sample['source_ref']}",
                "Signed deviation: " + ("not evaluated" if value is None else f"{value:+.5f} mm"),
                "Comparison: " + result["state"].replace("_", " "),
                reason,
                "XYZ: " + " / ".join(format(v, ".6g") for v in sample["position_mm"]) + " mm",
                "Coordinate kind: " + sample["kind"].replace("_", " "),
                "Registration: " + (sample["registration_ref"] or "unknown"),
                "Compensation: " + (sample["calibration_ref"] or "unknown"),
                "Observed: " + (sample["observed_at"] or "unknown"),
                "Record time: assigned when retained"
                if getattr(self, "draft", False)
                else f"Recorded Unix time: {sample['recorded_at']:.6f}",
                "Frame: " + sample["frame"],
                "Evidence: " + sample["source_class"],
            )
        )
