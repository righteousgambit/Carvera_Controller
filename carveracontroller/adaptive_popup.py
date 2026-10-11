"""Shadow monitor with validated operator recipe and outcome forms."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, cast

from kivy.clock import Clock
from kivy.graphics import Color, Line
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import Action, AdaptiveGrid, DesktopScrollView, label
from carveracontroller.machine.feed_recipe import FeedRecipe
from carveracontroller.sensor_measurements_popup import EvidenceForm, SensorMeasurementsPopup


class Trace(Widget):
    def draw(self, samples: Any, field: str, maximum: float, color: tuple[float, ...]) -> None:
        self.canvas.clear()
        if maximum <= 0 or not math.isfinite(maximum):
            return
        with self.canvas:
            Color(0.3, 0.3, 0.3, 1)
            Line(rectangle=(self.x, self.y, self.width, self.height))
            if len(samples) < 2:
                return
            end = samples[-1].timestamp
            if not math.isfinite(end):
                return
            start = end - 60
            Color(*color)
            segment: list[float] = []
            previous = None
            for sample in samples:
                value = getattr(sample, field, None)
                valid = (
                    type(value) in (int, float)
                    and math.isfinite(cast(float, value))
                    and math.isfinite(sample.timestamp)
                )
                if not valid or (previous is not None and not 0 < sample.timestamp - previous <= 0.8):
                    if len(segment) >= 4:
                        Line(points=segment, width=1.3)
                    segment = []
                previous = sample.timestamp
                if not valid or sample.timestamp < start:
                    continue
                segment.extend(
                    (
                        self.x + (sample.timestamp - start) / 60 * self.width,
                        self.y + min(1, max(0, cast(float, value) / maximum)) * self.height,
                    )
                )
            if len(segment) >= 4:
                Line(points=segment, width=1.3)


RECIPE = [
    ("cutter", "Exact cutter / physical assembly identity", "text", True),
    ("material", "Material and alloy", "text", True),
    ("operation", "Operation identity (matches loaded program)", "text", True),
    ("rpm", "Recipe spindle speed (RPM)", "positive", True),
    ("flutes", "Number of flutes", "integer", True),
    ("programmed_feed_mm_min", "Programmed cutting feed (mm/min)", "positive", True),
    ("chipload_min_mm", "Reviewed minimum chip load (mm/tooth)", "positive", True),
    ("chipload_max_mm", "Reviewed maximum chip load (mm/tooth)", "positive", True),
]
OUTCOME = [
    ("program_hash", "Exact program SHA-256", "text", True),
    ("operation", "Inspected operation identity", "text", True),
    ("dimensional_error_mm", "Observed dimensional error (mm)", "number", False),
    ("finish", "Observed surface finish", "text", False),
    ("temperature_c", "Observed temperature (°C)", "number", False),
    ("tool_condition", "Observed tool condition", "text", False),
    ("notes", "Inspection notes / measurement reference", "text", False),
]


class AdaptiveMonitorPopup(Popup):
    def __init__(self, controller: Any, **kwargs: Any) -> None:
        self.controller = controller
        super().__init__(title="Machining evidence · shadow proposals", size_hint=(0.94, 0.94), **kwargs)
        self.state: dict[str, Any] = {}
        self.context: dict[str, Any] = {}
        self.recording_problem: str | None = None
        self.restarting = False
        self.event = None
        outer = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        tabs = AdaptiveGrid(max_cols=3, min_width=150, row_height=36, spacing=dp(5))
        self.pages: dict[str, BoxLayout] = {}
        for name in ("Live evidence", "Cutter recipe", "Record outcome"):
            tabs.add_widget(Action(name, lambda *_a, selected=name: self.show_page(selected)))
            page = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
            page.bind(minimum_height=page.setter("height"))
            self.pages[name] = page
        outer.add_widget(tabs)
        self.page_manager = ScreenManager(transition=NoTransition())
        self.page_scrolls: dict[str, DesktopScrollView] = {}
        for name, page in self.pages.items():
            screen = Screen(name=name)
            scroll = DesktopScrollView(do_scroll_x=False)
            scroll.add_widget(page)
            screen.add_widget(scroll)
            self.page_manager.add_widget(screen)
            self.page_scrolls[name] = scroll
        self.scroll = self.page_scrolls["Live evidence"]
        outer.add_widget(self.page_manager)
        self.message = SensorMeasurementsPopup.note(
            "Shadow only: records proposals and observations; sends no feed changes."
        )
        outer.add_widget(self.message)
        close = Action("Close", self.dismiss)
        outer.add_widget(close)
        self.content = outer
        self.status = SensorMeasurementsPopup.note("")
        live = self.pages["Live evidence"]
        live.add_widget(self.status)
        self.baseline_note = SensorMeasurementsPopup.note("")
        live.add_widget(self.baseline_note)
        controls = AdaptiveGrid(max_cols=2, min_width=240, row_height=36, spacing=dp(5))
        self.commands: dict[str, Action] = {}
        for title, command in (
            ("Capture unloaded baseline", "baseline"),
            ("Reset baseline", "reset"),
            ("Monitor off", "off"),
            ("Shadow on", "shadow"),
        ):
            button = Action(title, lambda *_a, selected=command: self.command(selected))
            self.commands[command] = button
            controls.add_widget(button)
        live.add_widget(controls)
        live.add_widget(label("Measured spindle RPM · last 60 s · 0–15,000", 11, height=26))
        self.rpm = Trace(size_hint_y=None, height=dp(90))
        live.add_widget(self.rpm)
        live.add_widget(label("PWM drive command · last 60 s · 0–100% (not measured power)", 11, height=26))
        self.pwm = Trace(size_hint_y=None, height=dp(90))
        live.add_widget(self.pwm)
        self.path = SensorMeasurementsPopup.note("")
        live.add_widget(self.path)
        self.copy_path_button = Action("Copy full recording location", self.copy_recording_location)
        live.add_widget(self.copy_path_button)
        self.restart_button = Action("Restart local recorder (preserve prior evidence)", self.restart_recorder)
        live.add_widget(self.restart_button)
        self.refresh(0)
        recipe_initial = self.state.get("recipe") or {}
        self.recipe_form = EvidenceForm(RECIPE, recipe_initial)
        recipe_page = self.pages["Cutter recipe"]
        recipe_page.add_widget(
            SensorMeasurementsPopup.note(
                "Enter reviewed cutter/material bounds. Blank fields are unknown; no machining recommendations are invented. This recipe limits shadow proposals and does not establish physical cutting qualification."
            )
        )
        recipe_page.add_widget(self.recipe_form)
        self.recipe_status = SensorMeasurementsPopup.note("")
        recipe_page.add_widget(self.recipe_status)
        self.recipe_save = Action("Save reviewed shadow recipe", self.save_recipe, primary=True)
        recipe_page.add_widget(self.recipe_save)
        current_program = self.context.get("program") or {}
        operation = self.context.get("operation")
        if isinstance(operation, dict):
            operation = operation.get("name") or operation.get("label")
        outcome_initial = {"program_hash": current_program.get("sha256"), "operation": operation}
        self.outcome_form = EvidenceForm(OUTCOME, outcome_initial)
        self.outcome_form.fields["program_hash"].readonly = True
        outcome_page = self.pages["Record outcome"]
        outcome_page.add_widget(
            SensorMeasurementsPopup.note(
                "Tie an inspected result to the exact loaded program and operation. Unknown measurements stay blank. Saving an observation does not qualify active feed control or certify accuracy."
            )
        )
        self.outcome_new = Action("Start a new outcome for the current program", self.new_outcome)
        outcome_page.add_widget(self.outcome_new)
        outcome_page.add_widget(self.outcome_form)
        self.outcome_status = SensorMeasurementsPopup.note("")
        outcome_page.add_widget(self.outcome_status)
        self.outcome_save = Action("Save observed machining outcome", self.save_outcome, primary=True)
        outcome_page.add_widget(self.outcome_save)
        for form in (self.recipe_form, self.outcome_form):
            for field in form.fields.values():
                field.bind(text=lambda *_a: self.validate_forms())
        self.show_page("Live evidence")
        self.validate_forms()
        self.event = Clock.schedule_interval(self.refresh, 0.3)
        self.bind(on_dismiss=self.stop_refresh)

    def stop_refresh(self, *_args: Any) -> None:
        for widget in self.content.walk():
            if hasattr(widget, "focus"):
                widget.focus = False
        if self.event is not None:
            self.event.cancel()
            self.event = None

    def show_page(self, name: str) -> None:
        for widget in self.scroll.walk():
            if hasattr(widget, "focus"):
                widget.focus = False
        self.scroll = self.page_scrolls[name]
        self.page_manager.current = name
        self.scroll.scroll_y = 1
        Clock.schedule_once(lambda _dt: self.scroll.update_from_scroll(), 0)

    def refresh(self, _dt: float) -> None:
        try:
            with self.controller._adaptive_lock:
                self.state = self.controller.adaptive_monitor.snapshot()
                samples = list(self.controller.adaptive_monitor.history)
                self.context = self.controller.sensor_context_snapshot()
            recording = self.context.get("recording") or {}
            writer = recording.get("journal") or {}
            error = recording.get("error") or writer.get("error")
            self.recording_problem = (
                "Recording is disabled for this session"
                if not getattr(self.controller, "_evidence_writes_enabled", True)
                else "Recording write failed; repair the path before saving more evidence"
                if recording.get("write_failed") or error
                else None
            )
            sample = self.state.get("sample")
            if sample:
                age = max(0.0, time.monotonic() - sample["timestamp"])
                self.status.text = (
                    f"{self.state['mode'].upper()} · {sample['state']} · sample age {age:.2f} s\n"
                    f"RPM {sample['rpm']:.0f} / {sample['commanded_rpm']:.0f}; shadow feed proposal {self.state['proposed_override']:.0f}%\n"
                    f"{self.state['reason']}"
                )
            else:
                self.status.text = "Waiting for complete telemetry. " + self.state.get("reason", "")
            self.baseline_note.text = (
                "Unloaded baseline: "
                + (
                    "available for recorded operating conditions"
                    if self.state.get("baseline")
                    else "not available; capture only with an unloaded, stationary spindle already at speed"
                )
                + f". Saved outcomes: {self.state.get('outcome_count', 0)}."
            )
            recording_path = recording.get("jsonl_path") or self.controller.adaptive_log_path
            self.path.text = "Recording journal: " + (
                Path(str(recording_path)).name if recording_path else "not started"
            )
            self.copy_path_button.disabled = not recording_path
            if writer:
                self.path.text += (
                    f"\nQueued {writer.get('pending_records', 'unknown')}; "
                    f"durable {writer.get('durable', 'unknown')}; dropped {writer.get('dropped', 'unknown')}."
                )
            if self.recording_problem:
                self.path.text += "\n" + self.recording_problem
            if error or writer.get("last_submission_error"):
                self.path.text += "\nWriter error: " + str(error or writer.get("last_submission_error"))
            self.restart_button.disabled = self.restarting or not getattr(
                self.controller, "_evidence_writes_enabled", True
            )
            self.rpm.draw(samples, "rpm", 15000, (0.2, 0.7, 1, 1))
            self.pwm.draw(samples, "pwm", 1, (1, 0.7, 0.2, 1))
            for button in self.commands.values():
                button.disabled = bool(self.recording_problem)
            self.commands["baseline"].disabled = (
                bool(self.recording_problem)
                or sample is None
                or self.state.get("mode") != "shadow"
                or sample.get("state") != "Idle"
                or sample.get("feed") != 0
                or sample.get("commanded_rpm", 0) <= 0
            )
            if hasattr(self, "recipe_save"):
                self.validate_forms()
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.recording_problem = "Unable to read current evidence: " + str(exc)
            self.path.text = self.recording_problem
            for button in self.commands.values():
                button.disabled = True
            self.restart_button.disabled = self.restarting or not getattr(
                self.controller, "_evidence_writes_enabled", True
            )
            if hasattr(self, "recipe_save"):
                self.validate_forms()

    def validate_forms(self) -> None:
        self.outcome_new.disabled = bool(self.recording_problem) or not (self.context.get("program") or {}).get(
            "sha256"
        )
        for kind in ("recipe", "outcome"):
            button = self.recipe_save if kind == "recipe" else self.outcome_save
            status = self.recipe_status if kind == "recipe" else self.outcome_status
            try:
                if self.recording_problem:
                    raise ValueError(self.recording_problem)
                if kind == "recipe":
                    recipe = FeedRecipe(**self.recipe_form.values())
                    status.text = f"Reviewed bounds produce {recipe.minimum_override:.1f}–{recipe.maximum_override:.1f}% shadow override. Physical cutting outcome remains unverified."
                else:
                    self.outcome_payload()
                    status.text = "Ready to save the supplied observations against the exact program. Blank fields remain unknown."
                button.disabled = False
            except (ValueError, TypeError) as exc:
                button.disabled = True
                status.text = str(exc)

    def new_outcome(self, *_args: Any) -> None:
        if self.recording_problem or not (self.context.get("program") or {}).get("sha256"):
            self.message.text = "Current program evidence is unavailable. Existing observations are preserved; refresh after repairing the evidence source."
            return
        program = self.context.get("program") or {}
        operation = self.context.get("operation")
        if isinstance(operation, dict):
            operation = operation.get("name") or operation.get("label")
        for key, field in self.outcome_form.fields.items():
            field.text = (
                str(program.get("sha256") or "")
                if key == "program_hash"
                else str(operation or "")
                if key == "operation"
                else ""
            )
        self.message.text = "New outcome form uses the current program. Enter its inspected results; previous saved outcomes remain intact."
        self.validate_forms()

    def outcome_payload(self) -> dict[str, Any]:
        payload = self.outcome_form.values()
        current_hash = (self.context.get("program") or {}).get("sha256")
        if not current_hash or payload["program_hash"] != current_hash:
            raise ValueError("Load and inspect the exact program; its identity changed or is unavailable")
        if not any(
            payload.get(key) is not None
            for key in ("dimensional_error_mm", "finish", "temperature_c", "tool_condition")
        ):
            raise ValueError("Enter at least one measured dimension, finish, temperature or tool observation")
        return payload

    def command(self, action: str) -> bool:
        try:
            if self.recording_problem:
                raise ValueError(self.recording_problem)
            saved = self.controller.adaptiveCommand("adaptive " + action)
            if saved is not True:
                raise ValueError("Controller refused the action or could not persist its receipt")
            self.message.text = f"{action.capitalize()} recorded. Shadow only; no feed changes sent."
            self.refresh(0)
            return True
        except (ValueError, OSError, TypeError) as exc:
            self.message.text = "Not saved: " + str(exc) + ". Check the recording path and controller log."
            return False

    def restart_recorder(self, *_args: Any) -> bool:
        if self.restarting or not getattr(self.controller, "_evidence_writes_enabled", True):
            self.message.text = "Recorder restart is unavailable while replaying or already restarting."
            return False
        self.restarting = True
        self.restart_button.disabled = True
        try:
            saved = self.controller.evidenceCommand("evidence restart")
            if saved is not True:
                raise ValueError(
                    "Restart was refused; the recorder may still be writing or the destination may be unavailable. Inspect the controller log and wait for pending writes before retrying."
                )
            self.refresh(0)
            self.message.text = (
                "New local recorder established: "
                + str(self.controller.adaptive_log_path)
                + ". Prior evidence is preserved; no machine command was sent."
            )
            return True
        except (OSError, ValueError, TypeError, RuntimeError) as exc:
            self.message.text = "Recorder not restarted: " + str(exc)
            self.refresh(0)
            return False
        finally:
            self.restarting = False
            self.restart_button.disabled = not getattr(self.controller, "_evidence_writes_enabled", True)

    def copy_recording_location(self, *_args: Any) -> bool:
        from kivy.core.clipboard import Clipboard

        path = (self.context.get("recording") or {}).get("jsonl_path") or self.controller.adaptive_log_path
        if not path:
            self.message.text = "No recording location is available yet."
            return False
        try:
            Clipboard.copy(str(path))
            self.message.text = "Full recording location copied."
            return True
        except (OSError, ValueError, RuntimeError) as exc:
            self.message.text = "Unable to copy the recording location: " + str(exc)
            return False

    def save_recipe(self, *_args: Any) -> None:
        try:
            payload = self.recipe_form.values()
            FeedRecipe(**payload)
            self.save_payload("recipe", payload)
        except (ValueError, TypeError) as exc:
            self.message.text = "Not saved: " + str(exc)

    def save_outcome(self, *_args: Any) -> None:
        try:
            self.save_payload("outcome", self.outcome_payload())
        except (ValueError, TypeError) as exc:
            self.message.text = "Not saved: " + str(exc)

    def save_payload(self, kind: str, payload: dict[str, Any]) -> bool:
        try:
            if self.recording_problem:
                raise ValueError(self.recording_problem)
            saved = self.controller.adaptiveCommand(f"adaptive {kind} {json.dumps(payload, allow_nan=False)}")
            if saved is not True:
                raise ValueError("Evidence persistence failed; inspect the recording path and controller log")
            self.message.text = f"{kind.capitalize()} evidence saved. Receipt stream: {self.controller.adaptive_log_path}. Active control remains unavailable."
            self.refresh(0)
            return True
        except (ValueError, OSError, TypeError) as exc:
            self.message.text = "Not saved: " + str(exc)
            return False


def open_adaptive_monitor(controller: Any) -> AdaptiveMonitorPopup:
    popup = AdaptiveMonitorPopup(controller)
    popup.open()
    return popup
