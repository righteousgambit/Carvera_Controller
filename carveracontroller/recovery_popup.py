"""Explicit operator review of a locally reconstructed recovery approach.

Opening, refreshing and previewing never execute a machine command. Only the
explicit Run action calls the supplied executor after fresh evidence checks.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action, AdaptiveGrid, DesktopScrollView, Field
from carveracontroller.sensor_measurements_popup import EvidenceForm, SensorMeasurementsPopup

CHECKS = (
    ("position_verified", "Homing / physical position checked"),
    ("origin_verified", "Work origins and coordinate system checked"),
    ("tool_offset_verified", "Installed tool and length offset checked"),
    ("clearance_verified", "Machine-Z approach clearance checked"),
    ("program_verified", "Exact machine file and selected line checked"),
)


class VerificationCheck(Action):
    """Keyboard-operable checkbox with an explicit label and no default approval."""

    def __init__(self, title: str, changed: Callable[[], None]) -> None:
        self.title = title
        self.checked = False
        self.changed = changed
        super().__init__("[ ] " + title, self.toggle)

    def set_checked(self, checked: bool) -> None:
        self.checked = checked
        self.text = ("[x] " if checked else "[ ] ") + self.title

    def toggle(self, *_args: Any) -> None:
        if self.disabled:
            return
        self.set_checked(not self.checked)
        self.changed()


class RecoveryReviewPopup(Popup):
    def __init__(
        self,
        controller: Any,
        start_line: int,
        plan_provider: Callable[[int, dict[str, Any]], dict[str, Any]],
        on_execute: Callable[[int, dict[str, Any]], bool],
        **kwargs: Any,
    ) -> None:
        if type(start_line) is not int or start_line < 1:
            raise ValueError("Select a positive recovery line")
        self.controller = controller
        self.start_line = start_line
        self.plan_provider = plan_provider
        self.on_execute = on_execute
        self.assessment: dict[str, Any] = {}
        self.scope: str | None = None
        self.read_error: str | None = None
        self.plan: dict[str, Any] | None = None
        self.plan_scope: str | None = None
        self.plan_clearance: float | None = None
        self.verified_signature: str | None = None
        self.executing = False
        self.event = None
        super().__init__(
            title=f"Review recovery · line {start_line}", size_hint=(0.94, 0.94), auto_dismiss=False, **kwargs
        )
        outer = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        self.scroll = DesktopScrollView(do_scroll_x=False)
        body = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        self.scroll.add_widget(body)
        outer.add_widget(self.scroll)
        self.status = SensorMeasurementsPopup.note("")
        body.add_widget(self.status)
        body.add_widget(
            SensorMeasurementsPopup.note(
                "Check physical position, origins, installed tool and the approach. The local program hash does not prove the bytes or line boundary on the machine; verify the exact machine file and selected line. Firmware position derives from issued steps. Opening or previewing this dialog sends no motion."
            )
        )
        self.form = EvidenceForm(
            [
                ("clearance_machine_z_mm", "Verified machine-coordinate clearance Z (mm)", "number", True),
                ("operator_note", "Verification note / reference", "text", True),
            ]
        )
        body.add_widget(self.form)
        self.preview_button = Action("1. Build and inspect approach preview", self.preview, primary=True)
        body.add_widget(self.preview_button)
        self.preview_summary = SensorMeasurementsPopup.note("No approach has been previewed for this scope.")
        body.add_widget(self.preview_summary)
        self.preview_text = Field(readonly=True, multiline=True, size_hint_y=None, height=dp(160))
        body.add_widget(self.preview_text)
        checks = AdaptiveGrid(max_cols=2, min_width=310, row_height=42, spacing=dp(5))
        self.checks = {key: VerificationCheck(title, self.confirmation_changed) for key, title in CHECKS}
        for check in self.checks.values():
            checks.add_widget(check)
        body.add_widget(checks)
        self.verification_status = SensorMeasurementsPopup.note("")
        body.add_widget(self.verification_status)
        self.verify_button = Action("2. Record these operator verifications", self.verify)
        body.add_widget(self.verify_button)
        self.message = SensorMeasurementsPopup.note("Preview the exact approach before recording your checks.")
        outer.add_widget(self.message)
        controls = AdaptiveGrid(max_cols=2, min_width=240, row_height=36, spacing=dp(5))
        self.run_button = Action("3. Run reviewed recovery", self.run, danger=True)
        self.close_button = Action("Cancel", self.dismiss)
        controls.add_widget(self.run_button)
        controls.add_widget(self.close_button)
        outer.add_widget(controls)
        self.content = outer
        self.form.fields["clearance_machine_z_mm"].bind(text=lambda *_a: self.input_changed(True))
        self.form.fields["operator_note"].bind(text=lambda *_a: self.input_changed(False))
        self.bind(on_dismiss=self.stop_refresh)
        self.refresh(0)
        self.event = Clock.schedule_interval(self.refresh, 0.3)

    def stop_refresh(self, *_args: Any) -> None:
        for widget in self.content.walk():
            if hasattr(widget, "focus"):
                widget.focus = False
        if self.event is not None:
            self.event.cancel()
            self.event = None

    def set_start_line(self, start_line: int) -> None:
        if type(start_line) is not int or start_line < 1:
            raise ValueError("Select a positive recovery line")
        if start_line != self.start_line:
            self.start_line = start_line
            self.title = f"Review recovery · line {start_line}"
            self.invalidate_scope()
            self.refresh(0)

    def invalidate_plan(self) -> None:
        self.plan = None
        self.plan_scope = None
        self.plan_clearance = None
        self.preview_text.text = ""
        self.preview_summary.text = "No current approach preview. Rebuild and review it."
        self.checks["program_verified"].set_checked(False)
        self.verified_signature = None

    def invalidate_scope(self) -> None:
        for check in self.checks.values():
            check.set_checked(False)
        self.invalidate_plan()
        self.message.text = (
            "Recovery scope changed. Earlier checks and preview are invalid; inspect and verify the current state."
        )

    def input_changed(self, plan_changed: bool) -> None:
        self.verified_signature = None
        if plan_changed:
            self.checks["clearance_verified"].set_checked(False)
            self.invalidate_plan()
        self.update_actions()

    def confirmation_changed(self) -> None:
        self.verified_signature = None
        self.update_actions()

    def refresh(self, _dt: float = 0) -> None:
        try:
            assessment = self.controller.recovery_assessment(self.start_line)
            if not isinstance(assessment, dict) or not isinstance(assessment.get("blockers"), list):
                raise ValueError("Malformed recovery assessment")
            scope = assessment.get("scope")
            if scope is not None and (not isinstance(scope, str) or len(scope) != 64):
                raise ValueError("Exact recovery scope unavailable")
            if self.scope != scope:
                if self.scope is not None or self.plan is not None:
                    self.invalidate_scope()
                self.scope = scope
            self.assessment = assessment
            self.read_error = None
            self.status.text = (
                f"Line {self.start_line} · local program SHA-256 {assessment.get('program_hash') or 'unknown'}\n"
                + (
                    "Current assessment permits verified recovery."
                    if assessment.get("allowed") is True
                    else "Current blockers: " + "; ".join(assessment["blockers"])
                )
            )
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self.read_error = str(exc)
            self.invalidate_scope()
            self.status.text = "Recovery evidence unavailable: " + str(exc)
        self.update_actions()

    def plan_current(self) -> bool:
        try:
            clearance = self.form.values()["clearance_machine_z_mm"]
        except ValueError:
            return False
        return bool(
            self.plan is not None
            and self.scope is not None
            and self.plan_scope == self.scope
            and self.plan_clearance == clearance
        )

    def verification_payload(self) -> dict[str, Any]:
        if self.read_error or self.scope is None:
            raise ValueError("Refresh a valid current recovery scope first")
        if not self.plan_current():
            raise ValueError("Build and inspect the current approach preview first")
        if not all(check.checked for check in self.checks.values()):
            raise ValueError("Complete all five operator verification checks")
        return {
            "start_line": self.start_line,
            "scope": self.scope,
            **self.form.values(),
            **{key: check.checked for key, check in self.checks.items()},
        }

    def signature(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, allow_nan=False)

    def update_actions(self) -> None:
        if not hasattr(self, "run_button"):
            return
        self.checks["program_verified"].disabled = not self.plan_current() or self.executing
        try:
            self.form.values()
            self.preview_button.disabled = bool(self.read_error) or self.scope is None or self.executing
        except ValueError:
            self.preview_button.disabled = True
        try:
            signature = self.signature(self.verification_payload())
            self.verify_button.disabled = self.executing
            verified = signature == self.verified_signature
            self.verification_status.text = (
                "Operator verification saved durably for this exact scope."
                if verified
                else "All checks supplied. Record them before running."
            )
        except (ValueError, TypeError) as exc:
            self.verify_button.disabled = True
            verified = False
            self.verification_status.text = str(exc)
        self.run_button.disabled = (
            self.executing or self.read_error is not None or not verified or self.assessment.get("allowed") is not True
        )

    def preview(self, *_args: Any) -> None:
        self.refresh(0)
        try:
            if self.read_error or self.scope is None:
                raise ValueError("Current recovery evidence is unavailable")
            values = self.form.values()
            assessment = dict(self.assessment, clearance_machine_z_mm=values["clearance_machine_z_mm"])
            scope = self.scope
            candidate = self.plan_provider(self.start_line, assessment)
            # Freeze the supplied local plan and reject non-JSON/NaN values.
            plan = json.loads(json.dumps(candidate, allow_nan=False))
            commands = plan.get("commands") if isinstance(plan, dict) else None
            if (
                not isinstance(commands, list)
                or not commands
                or any(not isinstance(command, str) or not command.strip() or "\x00" in command for command in commands)
            ):
                raise ValueError("Preview provider did not return a complete command list")
            self.refresh(0)
            if self.read_error or self.scope != scope or self.form.values() != values:
                raise ValueError("Recovery scope changed while preparing the preview")
            self.invalidate_plan()
            self.plan = plan
            self.plan_scope = scope
            self.plan_clearance = values["clearance_machine_z_mm"]
            self.preview_text.text = "\n".join(commands)
            self.preview_text.cursor = (0, 0)
            self.preview_summary.text = str(
                plan.get("summary")
                or "Inspect every approach command, then check the reviewed-program confirmation below."
            )
            self.message.text = (
                "Preview ready. No commands have been sent; complete the physical checks and record them."
            )
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self.invalidate_plan()
            self.message.text = "Preview unavailable: " + str(exc)
        self.update_actions()

    def verify(self, *_args: Any) -> bool:
        self.refresh(0)
        try:
            payload = self.verification_payload()
            signature = self.signature(payload)
            saved = self.controller.recoveryCommand("recovery verify " + signature)
            if saved is not True:
                raise ValueError(
                    "Verification was refused or not saved; inspect current blockers and the recording path"
                )
            self.refresh(0)
            if self.read_error or self.signature(self.verification_payload()) != signature:
                raise ValueError("Recovery scope changed during verification; inspect and verify again")
            if self.assessment.get("allowed") is not True:
                raise ValueError("Current recovery assessment still has blockers")
            self.verified_signature = signature
            self.message.text = "Operator verification receipt saved. Recheck the approach before selecting Run."
            self.update_actions()
            return True
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self.verified_signature = None
            self.message.text = "Not verified: " + str(exc)
            self.update_actions()
            return False

    def run(self, *_args: Any) -> bool:
        if self.executing:
            return False
        self.refresh(0)
        try:
            if self.read_error or self.assessment.get("allowed") is not True:
                raise ValueError("Current recovery assessment has blockers")
            if self.signature(self.verification_payload()) != self.verified_signature:
                raise ValueError("Current checks need a durable verification receipt")
            if self.plan is None:
                raise ValueError("Current approach preview is unavailable")
            self.executing = True
            self.update_actions()
            # Consume authorization before invoking the callback: a refusal or
            # exception cannot accidentally retry the same physical action.
            plan = self.plan
            self.verified_signature = None
            self.message.text = "Starting the reviewed recovery approach…"
            succeeded = self.on_execute(self.start_line, plan)
            if succeeded is not True:
                raise ValueError("Controller refused the recovery; inspect its log and verify again")
            self.stop_refresh()
            self.dismiss()
            return True
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            self.message.text = "Recovery was not confirmed started: " + str(exc)
            return False
        finally:
            self.executing = False
            self.update_actions()
