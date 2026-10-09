"""Local channel/resource planning; no transport, generated motion or machine binding."""

import json
import threading

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ObjectProperty
from kivy.uix.recycleboxlayout import RecycleBoxLayout
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import ACCENT, BG, DANGER, MUTED, RAISED, TEXT, Action, AdaptiveGrid, Surface
from carveracontroller.desktop_file_picker import ArtifactList
from carveracontroller.desktop_planning import PlanningCard, planning_field
from carveracontroller.machine.mill_turn_plan import MAX_BYTES, example_record, load_plan, plan_record, review_plan


class ChannelTimeline(Widget):
    """Nominal time per channel; selectable reservations and barrier arrivals."""

    def __init__(self, owner, **kwargs):
        super().__init__(size_hint_y=None, height=dp(180), **kwargs)
        self.owner = owner
        self.review = None
        self.hit_regions = []
        self.bind(size=self.draw, pos=self.draw)

    def show(self, review):
        self.review = review
        self.height = dp(max(110, len(review.plan.channels) * 40 + 24)) if review else 0
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        self.hit_regions = []
        if self.review is None:
            return
        review = self.review
        left = dp(90)
        width = max(1, self.width - left - dp(8))
        row_height = (self.height - dp(24)) / len(review.plan.channels)
        with self.canvas:
            Color(*RAISED)
            Rectangle(pos=self.pos, size=self.size)
            Color(*MUTED)
            for row, channel in enumerate(review.plan.channels):
                caption = CoreLabel(
                    text=channel, font_name="Roboto", font_size=sp(9), text_size=(dp(78), None), shorten=True
                )
                caption.refresh()
                Rectangle(
                    texture=caption.texture,
                    pos=(self.x + dp(6), self.top - dp(12) - (row + 1) * row_height + dp(7)),
                    size=caption.texture.size,
                )
            for ratio in (0, 0.5, 1):
                caption = CoreLabel(text=f"{review.duration_s * ratio:g}s", font_name="Roboto", font_size=sp(9))
                caption.refresh()
                px = self.x + left + width * ratio
                Rectangle(
                    texture=caption.texture,
                    pos=(min(self.right - caption.texture.width - dp(2), px), self.y + dp(2)),
                    size=caption.texture.size,
                )
            for item in review.steps:
                row = review.plan.channels.index(item.step.channel)
                x = self.x + left + width * item.start_s / max(1, review.duration_s)
                y = self.top - dp(12) - (row + 1) * row_height
                w = max(dp(3), width * (item.end_s - item.start_s) / max(1, review.duration_s))
                h = row_height - dp(8)
                Color(*(DANGER if item.status == "blocked" else ACCENT))
                if item.step.action == "barrier":
                    Line(points=[x, y, x, y + h], width=dp(2))
                else:
                    Rectangle(pos=(x, y), size=(w, h))
                if item.step.id == self.owner.selected_id:
                    Color(*TEXT)
                    Line(rectangle=(x - dp(2), y - dp(2), w + dp(4), h + dp(4)), width=dp(1))
                self.hit_regions.append((x, y, w, h, item.step.id))

    def on_touch_down(self, touch):
        if not self.disabled and self.collide_point(*touch.pos) and not getattr(touch, "is_mouse_scrolling", False):
            for x, y, width, height, step_id in reversed(self.hit_regions):
                if x - dp(3) <= touch.x <= x + width + dp(3) and y <= touch.y <= y + height:
                    self.owner.select_step(step_id, self.review)
                    return True
        return super().on_touch_down(touch)


class ChannelStepRow(RecycleDataViewBehavior, Action):
    owner = ObjectProperty(None, allownone=True)
    review = ObjectProperty(None, allownone=True)
    step_id = ObjectProperty(None, allownone=True)
    selected = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__("", self.inspect, halign="left", padding=(dp(8), dp(4)), **kwargs)
        self.bind(size=lambda obj, size: setattr(obj, "text_size", (max(1, size[0] - dp(16)), size[1])))

    def refresh_view_attrs(self, rv, index, data):
        if self.review is not data["review"] or self.step_id != data["step_id"]:
            self.focus = False
        result = super().refresh_view_attrs(rv, index, data)
        selected = self.selected
        self.base_color = ACCENT if selected else RAISED
        self.color = BG if selected else TEXT
        self._paint()
        return result

    def inspect(self):
        if self.owner is not None:
            self.owner.select_step(self.step_id, self.review)


class MillTurnPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(7), size_hint_y=None, **kwargs)
        self.workspace = workspace
        self.review = None
        self.selected_id = None
        self.preferred_id = None
        self.closed = False
        self.generation = 0
        self.active = False
        self.pending = None
        self.bind(minimum_height=self.setter("height"))
        self.add_widget(flowing_text("Channel and transfer planner", 24))
        self.add_widget(
            flowing_text(
                "Declared local schedule · the Carvera adapter cannot execute coordinated channels. Durations, spindle phase, grip and datums are declarations; geometry, physical synchronization and workholding remain unqualified.",
                44,
            )
        )
        actions = AdaptiveGrid(max_cols=3, min_width=135, row_height=34, spacing=dp(6))
        self.example_action = Action("Load DEMO plan", self.load_example)
        self.review_action = Action("Review schedule", self.request_review, primary=True)
        self.copy_action = Action("Copy reviewed JSON", self.copy_review, disabled=True)
        for action in (self.example_action, self.review_action, self.copy_action):
            actions.add_widget(action)
        self.add_widget(actions)
        self.status = flowing_text("Load the declared example or paste a schema-1 plan below.", 30)
        self.add_widget(self.status)
        self.timeline = ChannelTimeline(self)
        self.timeline.show(None)
        self.add_widget(self.timeline)
        self.legend = flowing_text("", 0)
        self.add_widget(self.legend)
        self.steps = ArtifactList(size_hint_y=None, height=0, do_scroll_x=False, bar_width=dp(9))
        layout = RecycleBoxLayout(
            default_size=(None, dp(56)),
            default_size_hint=(1, None),
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(4),
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.steps.add_widget(layout)
        self.steps.viewclass = ChannelStepRow
        self.add_widget(self.steps)
        self.details = flowing_text("Select a timeline reservation or step to inspect state before and after.", 40)
        self.add_widget(self.details)
        self.edit = PlanningCard("Edit selected step")
        self.duration = planning_field(self.edit.content, "Declared duration · seconds", "1")
        self.dependencies = planning_field(self.edit.content, "Wait for step IDs · comma separated")
        self.resources = planning_field(self.edit.content, "Additional resource IDs · comma separated")
        self.apply_action = Action("Apply step draft and review", self.apply_step, disabled=True)
        self.edit.content.add_widget(self.apply_action)
        self.add_widget(self.edit)
        self.expert = PlanningCard("Plan JSON · all actions and declarations")
        self.source = planning_field(self.expert.content, "Schema 1 · maximum 256 KiB", "")
        self.source.multiline = True
        self.source.height = dp(220)
        self.source.parent.height = dp(244)
        self.source.bind(text=self.invalidate)
        self.expert.content.add_widget(
            flowing_text(
                "Explicit after dependencies supplement per-channel order. Barriers require one arrival from every declared participant. Review never changes the connected machine, loaded program or scene.",
                36,
            )
        )
        self.add_widget(self.expert)

    def invalidate(self, *_):
        self.generation += 1
        self.pending = None
        self.review = None
        self.selected_id = None
        self.copy_action.disabled = self.apply_action.disabled = True
        self.timeline.show(None)
        self.steps.data = []
        self.steps.height = 0
        self.legend.text = ""
        self.details.text = "Draft changed · review again to inspect current state."
        self.status.text = "Draft changed · prior result invalidated."

    def load_example(self):
        if self.closed:
            return
        self.preferred_id = None
        self.source.text = json.dumps(example_record(), indent=2)
        self.request_review()

    def request_review(self):
        if self.closed:
            return
        self.generation += 1
        # Bound the snapshot before passing it to the single worker.
        text = self.source.text
        if len(text) > MAX_BYTES:
            self.invalidate()
            self.status.text = "Plan exceeds 256 KiB. Reduce the draft and review again."
            return
        self.review = None
        self.copy_action.disabled = self.apply_action.disabled = True
        self.timeline.show(None)
        self.steps.data = []
        self.steps.height = 0
        self.details.text = "Review pending · old state is not actionable."
        self.legend.text = ""
        request = self.generation, text
        self.status.text = "Reviewing declared schedule… · newer requests replace pending work."
        if self.active:
            self.pending = request
        else:
            self._start(request)

    def _start(self, request):
        generation, text = request
        self.active = True

        def work():
            try:
                review = review_plan(load_plan(text), cancelled=lambda: self.closed or generation != self.generation)
                error = None
            except Exception as exc:
                review, error = None, str(exc)
            Clock.schedule_once(lambda _dt: self._finish(request, review, error), 0)

        try:
            threading.Thread(target=work, name="channel-plan-review", daemon=True).start()
        except Exception as exc:
            self._finish(request, None, "Worker could not start: " + str(exc))

    def _finish(self, request, review, error):
        self.active = False
        pending, self.pending = self.pending, None
        if self.closed:
            return
        if pending is not None:
            self._start(pending)
            return
        generation, text = request
        if generation != self.generation or text != self.source.text:
            return
        if error:
            self.status.text = "Plan not admitted: " + error
            return
        self.review = review
        self.status.text = f"{review.plan.name} · {review.plan.machine_profile}\n{review.duration_s:g} s nominal · {len(review.issues)} issues · source {review.digest[:12]}"
        self.legend.text = (
            "Rows top to bottom: "
            + " · ".join(review.plan.channels)
            + "\nGreen planned · red blocked · vertical bars synchronization arrivals · nominal seconds"
        )
        self.timeline.show(review)
        self.copy_action.disabled = False
        preferred = next(
            (entry.step.id for entry in review.steps if entry.step.id == self.preferred_id), review.steps[0].step.id
        )
        self.select_step(preferred, review)

    def select_step(self, step_id, review):
        if self.closed or review is None or review is not self.review:
            return
        item = next((entry for entry in review.steps if entry.step.id == step_id), None)
        if item is None:
            return
        self.selected_id = step_id
        self.steps.height = min(dp(240), dp(60) * len(review.steps))
        self.steps.data = [
            {
                "owner": self,
                "review": review,
                "step_id": entry.step.id,
                "selected": entry.step.id == self.selected_id,
                "text": f"{entry.start_s:g}–{entry.end_s:g} s · {entry.step.channel} · {entry.status}\n{entry.step.id} · {entry.step.name}",
            }
            for entry in review.steps
        ]
        index = next(i for i, entry in enumerate(review.steps) if entry.step.id == step_id)
        self.steps.scroll_y = max(
            0, min(1, 1 - index * dp(60) / max(1, len(review.steps) * dp(60) - self.steps.height))
        )
        issues = [issue.message for issue in review.issues if step_id in issue.steps]
        self.details.text = (
            f"{item.step.name} · {item.step.action} · {item.status}\nReserved: {', '.join(item.resources) or 'none'}\nBefore: {self._state_text(item.before)}\nAfter: {self._state_text(item.after)}"
            + ("\nIssues: " + " | ".join(issues) if issues else "")
        )
        self.duration.text = str(item.step.duration_s)
        self.dependencies.text = ", ".join(item.step.after)
        self.resources.text = ", ".join(item.step.resources)
        self.apply_action.disabled = False
        self.timeline.draw()

    @staticmethod
    def _state_text(state):
        pieces = "; ".join(
            f"{p.id}: holders {','.join(p.holders)}, datum {p.datum or 'UNSET'}, attached {p.attached}, remnant {p.remnant_holder or 'none'}"
            for p in state.pieces
        )
        speeds = ", ".join(f"{spindle} {rpm:g} RPM" for spindle, rpm in state.spindle_rpm)
        pairs = ", ".join("/".join(pair) for pair in state.synchronized) or "none"
        return f"{pieces} · {speeds} · synchronized {pairs}"

    def apply_step(self):
        if self.closed or self.review is None or self.selected_id is None:
            return
        record = plan_record(self.review.plan)
        selected = next(row for row in record["steps"] if row["id"] == self.selected_id)
        try:
            selected["duration_s"] = float(self.duration.text)
        except ValueError:
            self.status.text = "Duration must be a finite numeric number of seconds."
            return
        selected["after"] = [value.strip() for value in self.dependencies.text.split(",") if value.strip()]
        selected["resources"] = [value.strip() for value in self.resources.text.split(",") if value.strip()]
        preferred = self.selected_id
        self.source.text = json.dumps(record, indent=2)
        self.preferred_id = preferred
        self.request_review()

    def copy_review(self):
        if not self.closed and self.review is not None:
            Clipboard.copy(json.dumps(plan_record(self.review.plan), indent=2))
            self.status.text += "\nReviewed declaration copied as JSON."

    def dispose(self):
        self.closed = True
        self.generation += 1
        self.pending = None
        self.review = None
        self.steps.data = []
        self.timeline.show(None)
