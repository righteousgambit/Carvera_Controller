"""Live view of the shadow monitor; opening it never starts a spindle or motion."""

import time

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
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
            for sample in samples:
                value = getattr(sample, field)
                if value is None:
                    if len(segment) >= 4:
                        Line(points=segment, width=1.3)
                    segment = []
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
    layout = BoxLayout(orientation="vertical", spacing=8, padding=12)
    header = Label(text="SHADOW ONLY — logs proposals; sends no feed changes", size_hint_y=None, height=40)
    layout.add_widget(header)
    status = Label(size_hint_y=None, height=95)
    layout.add_widget(status)
    layout.add_widget(Label(text="Actual spindle RPM — last 60 s (0–15,000)", size_hint_y=None, height=25))
    rpm = Trace()
    layout.add_widget(rpm)
    layout.add_widget(Label(text="Spindle PWM drive effort — last 60 s (0–100%)", size_hint_y=None, height=25))
    pwm = Trace()
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
    popup = Popup(title="Adaptive roughing — telemetry and feed proposals", content=layout, size_hint=(0.9, 0.85))
    close = Button(text="Close", size_hint_y=None, height=40)
    close.bind(on_release=popup.dismiss)
    layout.add_widget(close)

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
                f"{state['reason']}"
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
