"""Cancellable, exact-byte setup change review with bounded desktop pages."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Optional

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action, Choice, DesktopScrollView, Surface
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.geometry_changes import (
    GeometryChange,
    GeometryContext,
    affected_operations,
    asset_problems,
    capture_context,
    context_changes,
    digest_context,
    verify_context_assets,
)
from carveracontroller.machine.program_operations import Operation

ReviewOutcome = tuple[
    Optional[GeometryContext], tuple[GeometryChange, ...], tuple[Operation, ...], tuple[str, ...], Optional[str]
]


class GeometryChangeReview(Popup):
    """Detach definitions on the UI; verify bytes and dependencies on a worker."""

    page_size = 12

    def __init__(self, panel, result=None):
        self.panel = panel
        self.closed = threading.Event()
        self.active = True
        self.page = 0
        self.entries: tuple[tuple[str, str | Operation], ...] = ()
        self.clearance = result == "clearance" or (result is None and panel.rest_context is None)
        self.result_name = "Captured clearance" if self.clearance else "Residual result"
        self.baseline = deepcopy(self._baseline())
        self.baseline_digest = digest_context(self.baseline)
        viewer = panel.workspace.machine.gcode_viewer
        program = panel.workspace.operation_panel.program
        self.context = capture_context(viewer, program, verify_assets=False)
        self.definition_digest = digest_context(self.context)
        self.operations = tuple(program.operations) if program else ()
        content = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
        super().__init__(title="Geometry change impact", content=content, size_hint=(None, None))
        self.bind(on_dismiss=self._close)
        Window.bind(size=self._fit)
        self._fit()
        if panel.rest_context is not None and panel.clearance_context is not None:
            selector = Choice(
                text="Captured clearance" if self.clearance else "Residual stock",
                values=("Residual stock", "Captured clearance"),
                size_hint_y=None,
                height=dp(36),
            )

            def select_result(_choice, value):
                self.dismiss()
                panel.review_changes("clearance" if value == "Captured clearance" else "residual")

            selector.bind(text=select_result)
            content.add_widget(selector)
        self.summary = content_label(f"Comparing: {self.result_name}\nVerifying CAD bytes and affected operations…")
        content.add_widget(self.summary)
        self.scroll = DesktopScrollView(do_scroll_x=False)
        self.rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.scroll.add_widget(self.rows)
        content.add_widget(self.scroll)
        self.pages = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.previous = Action("Previous", lambda: self.move_page(-1), disabled=True)
        self.page_label = content_label("Preparing…")
        self.next = Action("Next", lambda: self.move_page(1), disabled=True)
        for widget in (self.previous, self.page_label, self.next):
            self.pages.add_widget(widget)
        content.add_widget(self.pages)
        content.add_widget(Action("Close", self.dismiss, height=dp(36)))
        self.open()
        try:
            threading.Thread(target=self._prepare, daemon=True, name="geometry-change-review").start()
        except (RuntimeError, OSError):
            self.active = False
            self.summary.text = "Change review worker could not start; previous results preserved."
            self.page_label.text = "Review unavailable"

    def _fit(self, *_args):
        self.size = (min(Window.width * 0.88, dp(700)), min(Window.height * 0.85, dp(550)))

    def _close(self, *_args):
        self.closed.set()
        self.active = False
        Window.unbind(size=self._fit)
        if getattr(self.panel, "change_review", None) is self:
            self.panel.change_review = None

    def _baseline(self):
        return self.panel.clearance_context if self.clearance else self.panel.rest_context

    def _prepare(self):
        outcome: ReviewOutcome
        try:
            current = verify_context_assets(self.context, cancelled=self.closed.is_set)
            changes = context_changes(self.baseline, current) if self.baseline else ()
            operations = affected_operations(changes, self.operations)
            problems = asset_problems(current)
            if self.closed.is_set():
                return
            outcome = current, changes, operations, problems, None
        except InterruptedError:
            return
        except (ValueError, TypeError, ArithmeticError, OSError) as exc:
            outcome = None, (), (), (), str(exc)
        Clock.schedule_once(lambda _dt: self._finish(outcome), 0)

    def _finish(self, outcome: ReviewOutcome):
        if self.closed.is_set():
            return
        self.active = False
        current, changes, operations, problems, error = outcome
        workspace = self.panel.workspace
        selected = capture_context(
            workspace.machine.gcode_viewer, workspace.operation_panel.program, verify_assets=False
        )
        if self.definition_digest != digest_context(selected) or self.baseline_digest != digest_context(
            self._baseline()
        ):
            self.summary.text = "Inputs changed while checking CAD; reopen change review for the current setup."
            self.page_label.text = "Older request · not applied"
            return
        if error or current is None:
            self.summary.text = "Change review failed: " + (error or "CAD context unavailable")
            self.page_label.text = "Review unavailable"
            return
        if changes or problems:
            self.panel.hide_single_residual()
            self.panel.note.text = f"{self.result_name} is older; review the changed inputs and recompute."
        self.summary.text = (
            f"Comparing: {self.result_name}\n{len(changes)} changed inputs · {len(operations)} affected operations\n"
            + (
                f"{self.result_name} is older; recompute before continuing or exporting."
                if changes or problems
                else f"No changed inputs against {self.result_name.lower()}."
                if self.baseline
                else f"No {self.result_name.lower()} baseline yet. Calculate it to establish one."
            )
        )
        entries: list[tuple[str, str | Operation]] = [
            (
                "text",
                f"Program: {current['program'] or 'none'}\nStock: {current['stock']['size_mm']} mm · origin {current['stock']['origin_mm']} mm\n{len(current['tools'])} program tools · {len(current['components'])} CAD component selections",
            )
        ]
        if problems:
            entries.append(("text", "CAD requires attention\n" + "\n".join(problems)))
        entries.extend(
            ("text", f"{change.title}\nPrevious: {change.before}\nCurrent: {change.after}") for change in changes
        )
        if self.baseline:
            entries.append(
                ("text", "Previous context: " + self.baseline_digest + "\nCurrent context: " + digest_context(current))
            )
        entries.extend(("operation", operation) for operation in operations)
        entries.append(
            (
                "text",
                "Dependencies identify affected operations, not collision regions. Stock subtraction remains approximate; holder/machine clearance and physical offsets are unqualified.",
            )
        )
        self.entries = tuple(entries)
        self._render_page()

    def move_page(self, delta):
        self.page = max(0, min((len(self.entries) - 1) // self.page_size, self.page + delta))
        self._render_page()

    def _render_page(self):
        if self.closed.is_set():
            return
        self.rows.clear_widgets()
        start = self.page * self.page_size
        for _kind, value in self.entries[start : start + self.page_size]:
            if isinstance(value, str):
                self.rows.add_widget(content_label(value))
            else:
                operation = value

                def inspect(operation=operation):
                    self.dismiss()
                    self.panel.workspace.operation_panel.select(operation)
                    self.panel.workspace.select("Program")

                self.rows.add_widget(
                    Action(
                        f"Inspect {operation.name} · lines {operation.start_line}–{operation.end_line}",
                        inspect,
                        height=dp(36),
                    )
                )
        self.scroll.scroll_y = 1
        self.previous.disabled = self.page == 0
        self.next.disabled = start + self.page_size >= len(self.entries)
        self.page_label.text = f"{self.page + 1}/{max(1, (len(self.entries) + self.page_size - 1) // self.page_size)} · {len(self.entries)} rows"
