"""Live view of the shadow monitor; opening it never starts a spindle or motion."""

import json
import time

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget


class Trace(Widget):
    def draw(self, samples, field, maximum, color):
        self.canvas.clear()
        with self.canvas:
            Color(0.3, 0.3, 0.3, 1)
            Line(rectangle=(self.x, self.y, self.width, self.height))
            if len(samples) < 2:
                return
            end = samples[-1].timestamp
            start = end - 60
            Color(*color)
            segment = []
            previous = None
            for sample in samples:
                value = getattr(sample, field)
                if value is None or (previous is not None and not 0 < sample.timestamp - previous <= 0.8):
                    if len(segment) >= 4:
                        Line(points=segment, width=1.3)
                    segment = []
                previous = sample.timestamp
                if value is None:
                    continue
                if sample.timestamp < start:
                    continue
                segment.extend(
                    (
                        self.x + (sample.timestamp - start) / 60 * self.width,
                        self.y + min(1, max(0, value / maximum)) * self.height,
                    )
                )
            if len(segment) >= 4:
                Line(points=segment, width=1.3)


def open_adaptive_monitor(controller):
    outer = BoxLayout(orientation="vertical", spacing=6)
    scroll = ScrollView(do_scroll_x=False)
    layout = BoxLayout(orientation="vertical", spacing=8, padding=12, size_hint_y=None)
    layout.bind(minimum_height=layout.setter("height"))
    scroll.add_widget(layout)
    outer.add_widget(scroll)
    header = Label(text="SHADOW ONLY — logs proposals; sends no feed changes", size_hint_y=None, height=40)
    layout.add_widget(header)
    status = Label(size_hint_y=None, height=120, font_size=12)
    layout.add_widget(status)
    layout.add_widget(Label(text="Actual spindle RPM — last 60 s (0–15,000)", size_hint_y=None, height=25))
    rpm = Trace(size_hint_y=None, height=120)
    layout.add_widget(rpm)
    layout.add_widget(Label(text="Spindle PWM drive effort — last 60 s (0–100%)", size_hint_y=None, height=25))
    pwm = Trace(size_hint_y=None, height=120)
    layout.add_widget(pwm)
    path = Label(size_hint_y=None, height=55, font_size=12)
    layout.add_widget(path)
    controls = BoxLayout(size_hint_y=None, height=45, spacing=8)
    for text, command in (
        ("Capture unloaded baseline", "adaptive baseline"),
        ("Reset baseline", "adaptive reset"),
        ("Monitor off", "adaptive off"),
        ("Shadow on", "adaptive shadow"),
    ):
        button = Button(text=text)
        button.bind(on_release=lambda _button, cmd=command: controller.adaptiveCommand(cmd))
        controls.add_widget(button)
    layout.add_widget(controls)
    evidence_controls = BoxLayout(size_hint_y=None, height=40, spacing=8)

    def edit_evidence(kind):
        state = controller.adaptive_monitor.snapshot()
        if kind == "recipe":
            initial = {
                key: value
                for key, value in (state.get("recipe") or {}).items()
                if key not in ("minimum_override", "maximum_override", "qualification")
            }
            if not initial:
                initial = {
                    "cutter": "",
                    "material": "",
                    "operation": "",
                    "rpm": 0,
                    "flutes": 0,
                    "programmed_feed_mm_min": 0,
                    "chipload_min_mm": 0,
                    "chipload_max_mm": 0,
                }
        else:
            context = (state.get("sample") or {}).get("context") or {}
            initial = {
                "program_hash": (context.get("program") or {}).get("sha256"),
                "operation": context.get("operation"),
                "dimensional_error_mm": None,
                "finish": None,
                "temperature_c": None,
                "tool_condition": None,
                "notes": "",
            }
        body = BoxLayout(orientation="vertical", padding=10, spacing=8)
        body.add_widget(
            Label(text="Enter observed values. All feed and chip-load units are mm.", size_hint_y=None, height=35)
        )
        entry = TextInput(text=json.dumps(initial, indent=2), multiline=True)
        body.add_widget(entry)
        error = Label(text="", size_hint_y=None, height=45)
        body.add_widget(error)
        dialog = Popup(
            title="Shadow recipe" if kind == "recipe" else "Record machining outcome",
            content=body,
            size_hint=(0.85, 0.85),
        )
        buttons = BoxLayout(size_hint_y=None, height=40, spacing=8)
        save = Button(text="Save evidence")

        def submit(_button):
            try:
                payload = json.loads(entry.text)
                with controller._adaptive_lock:
                    if kind == "recipe":
                        from .machine.feed_recipe import FeedRecipe

                        FeedRecipe(**payload)
                    elif not payload.get("program_hash"):
                        raise ValueError("Load the exact program before recording an outcome")
                saved = controller.adaptiveCommand(f"adaptive {kind} {json.dumps(payload)}")
                if saved is False:
                    error.text = "Evidence could not be saved; inspect the controller log"
                    return
                dialog.dismiss()
            except (ValueError, TypeError) as exc:
                error.text = str(exc)

        save.bind(on_release=submit)
        buttons.add_widget(save)
        cancel = Button(text="Cancel")
        cancel.bind(on_release=dialog.dismiss)
        buttons.add_widget(cancel)
        body.add_widget(buttons)
        dialog.open()

    for title, kind in (("Cutter/material recipe", "recipe"), ("Record outcome", "outcome")):
        button = Button(text=title)
        button.bind(on_release=lambda _button, selected=kind: edit_evidence(selected))
        evidence_controls.add_widget(button)
    layout.add_widget(evidence_controls)
    popup = Popup(title="Adaptive roughing — telemetry and feed proposals", content=outer, size_hint=(0.9, 0.85))
    close = Button(text="Close", size_hint_y=None, height=40)
    close.bind(on_release=popup.dismiss)
    outer.add_widget(close)

    def refresh(_dt):
        with controller._adaptive_lock:
            state = controller.adaptive_monitor.snapshot()
            samples = list(controller.adaptive_monitor.history)
        sample = state["sample"]
        if sample:
            age = time.monotonic() - sample["timestamp"]
            status.text = (
                f"{state['mode'].upper()} | {sample['state']} | RPM {sample['rpm']:.0f} / {sample['commanded_rpm']:.0f}"
                f" | sample age {age:.2f} s\n"
                f"Filtered baseline droop {state['filtered_droop'] * 100:.2f}% | proposed feed {state['proposed_override']:.0f}%\n"
                f"{state['reason']}\n"
                f"Recipe: {(state.get('recipe') or {}).get('operation', 'required')} | outcomes {state.get('outcome_count', 0)}"
            )
        else:
            status.text = state["reason"]
        rpm.draw(samples, "rpm", 15000, (0.2, 0.7, 1, 1))
        pwm.draw(samples, "pwm", 1, (1, 0.7, 0.2, 1))
        path.text = str(controller.adaptive_log_path or "Waiting for complete telemetry")

    event = Clock.schedule_interval(refresh, 0.2)
    popup.bind(on_dismiss=lambda *_args: event.cancel())
    popup.open()
    refresh(0)
    return popup
