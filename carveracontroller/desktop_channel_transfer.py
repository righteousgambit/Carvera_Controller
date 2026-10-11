"""Cancellable exact-byte channel-plan file exchange with checked UI publication."""

from __future__ import annotations

import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.popup import Popup

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, Surface
from carveracontroller.machine.channel_plan_file import PlanFile, commit_plan_file, prepare_plan_file, read_plan_file


class ChannelPlanTransfer(Popup):
    def __init__(self, panel, path, *, save):
        self.panel, self.path, self.save = panel, Path(path), save
        self.generation, self.text, self.review = panel.generation, panel.source.text, panel.review
        self.cancelled, self.decision = threading.Event(), threading.Event()
        self.closed, self.approved, self.publishing = False, False, False
        self.active = True
        body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
        super().__init__(
            title="Save reviewed channel plan" if save else "Load and review channel plan",
            content=body,
            size_hint=(0.8, None),
            height=dp(230),
            auto_dismiss=False,
        )
        self.status = flowing_text("Preparing exact declared plan bytes… Current plan retained until acceptance.", 55)
        body.add_widget(self.status)
        self.cancel = Action("Cancel", self.dismiss, height=dp(34))
        body.add_widget(self.cancel)
        self.bind(on_dismiss=self._close)
        body.bind(minimum_height=self._fit)
        Window.bind(size=self._fit)
        self._fit()
        panel.file_transfer = self
        panel.refresh_file_controls()
        self.open()
        try:
            threading.Thread(target=self._run, daemon=True, name="channel-plan-file").start()
        except Exception as exc:
            self._finish(None, "File worker could not start: " + str(exc))

    def _fit(self, *_):
        self.height = min(Window.height * 0.85, max(dp(220), self.content.minimum_height + dp(80)))

    def dismiss(self, *args, **kwargs):
        if self.active and self.publishing:
            return None
        return super().dismiss(*args, **kwargs)

    def _close(self, *_):
        Window.unbind(size=self._fit)
        self.closed = True
        self.cancelled.set()
        self.decision.set()
        # Retain the running owner until its worker returns, even after Cancel.
        # An OS-blocked read cannot cause successive clicks to launch more readers.
        if not self.active and self.panel.file_transfer is self:
            self.panel.file_transfer = None
        self.panel.refresh_file_controls()

    def current(self):
        panel = self.panel
        return (
            not self.closed
            and not self.cancelled.is_set()
            and not panel.closed
            and panel.file_transfer is self
            and panel.generation == self.generation
            and panel.source.text == self.text
            and panel.review is self.review
        )

    def _approve(self, *_):
        self.approved = self.current()
        if self.approved:
            self.publishing = True
            self.cancel.disabled = True
            self.status.text = "Publishing complete new plan file…"
        self.decision.set()

    def _run(self):
        prepared, error = None, None
        result: PlanFile | dict[str, object] | None = None
        try:
            if self.save:
                prepared = prepare_plan_file(self.path, self.text, cancelled=self.cancelled.is_set)
                Clock.schedule_once(self._approve, 0)
                while not self.decision.wait(0.05):
                    if self.cancelled.is_set():
                        raise ValueError("Channel-plan export cancelled")
                if not self.approved:
                    raise ValueError("Draft changed or export cancelled; destination retained")
                result = commit_plan_file(prepared)
            else:
                result = read_plan_file(self.path, cancelled=self.cancelled.is_set)
        except Exception as exc:
            error = str(exc)
        finally:
            if prepared is not None:
                try:
                    prepared.temporary.unlink(missing_ok=True)
                except OSError as exc:
                    error = "Prepared plan cleanup failed: " + str(exc)
        Clock.schedule_once(lambda _dt: self._finish(result, error), 0)

    def _finish(self, result, error):
        current = self.current()
        self.active = False
        self.cancel.disabled = False
        self.cancel.text = "Close"
        panel = self.panel
        if self.closed or panel.closed:
            if panel.closed:
                self.dismiss()
            if panel.file_transfer is self:
                panel.file_transfer = None
            panel.refresh_file_controls()
            return
        if not error and not self.save and not current:
            error = "Draft changed while loading; current plan retained"
        if error:
            self.status.text = "File operation not accepted: " + error
        elif self.save:
            panel.file_receipt = result
            self.status.text = f"Saved exact reviewed declarations · {result['bytes']} bytes\nSHA-256 {result['sha256']}\n{result['path']}"
        else:
            # Clear this transaction before assigning admitted source, which
            # invalidates old analyses. The detached review is then installed.
            panel.file_transfer = None
            panel.preferred_id = None
            panel.source.text = result.text
            panel._finish((panel.generation, result.text), result.review, None)
            panel.file_receipt = {
                "path": result.path,
                "sha256": result.sha256,
                "bytes": len(result.text.encode("utf-8")),
                "observed_at": result.observed_at,
            }
            self.status.text = f"Loaded declared plan · {len(result.review.issues)} review issues\nSHA-256 {result.sha256}\n{result.path}"
        if self.save and not error and not current:
            self.status.text += "\nCurrent draft has changed since this captured export."
        panel.file_status.text = self.status.text
        if panel.file_transfer is self:
            panel.file_transfer = None
        panel.refresh_file_controls()
