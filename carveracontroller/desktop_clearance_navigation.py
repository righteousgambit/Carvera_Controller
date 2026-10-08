"""Coalesced exact-byte checks before navigating captured clearance on today's path."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable

from kivy.clock import Clock

from carveracontroller.machine.geometry_changes import (
    GeometryContext,
    asset_problems,
    capture_context,
    digest_context,
    verify_context_assets,
)


@dataclass
class NavigationRequest:
    context: GeometryContext
    identity: tuple[str | None, str]
    baseline: tuple[str | None, str] | None
    baseline_digest: str
    report: object
    plot_report: object
    action: Callable[[], None]
    owner_current: Callable[[], bool]
    cancelled: threading.Event


class ClearanceNavigation:
    """One active reader and one replaceable request; no file I/O on the UI."""

    def __init__(self, panel):
        self.panel = panel
        self.request: NavigationRequest | None = None
        self.pending: NavigationRequest | None = None

    @property
    def active(self):
        return self.request is not None or self.pending is not None

    def cancel(self, *_args):
        busy = self.active
        if self.request is not None:
            self.request.cancelled.set()
        self.pending = None
        if busy:
            self._status("CAD check cancelled · captured results retained.", False)

    def _status(self, text, busy):
        self.panel.navigation_status.text = text
        self.panel.navigation_cancel.disabled = not busy

    def submit(self, action, owner_current=lambda: True):
        panel = self.panel
        try:
            context = capture_context(
                panel.workspace.machine.gcode_viewer, panel.workspace.operation_panel.program, verify_assets=False
            )
            identity = context["program"], digest_context(context)
            if panel.clearance_stale or identity != panel.clearance_identity:
                self.cancel()
                panel._invalidate_clearance()
                return
            request = NavigationRequest(
                context,
                identity,
                panel.clearance_identity,
                digest_context(panel.clearance_context),
                panel.report,
                panel.clearance_card.report,
                action,
                owner_current,
                threading.Event(),
            )
        except (ValueError, TypeError, ArithmeticError):
            self.cancel()
            self._status("CAD check unavailable · invalid selected definitions; captured results retained.", False)
            return
        self._status("Checking CAD before current-path navigation…", True)
        if self.request is not None:
            self.request.cancelled.set()
            self.pending = request
        else:
            self._launch(request)

    def _launch(self, request):
        self.request = request
        try:
            threading.Thread(target=lambda: self._verify(request), daemon=True, name="clearance-navigation").start()
        except (RuntimeError, OSError):
            self.request = None
            self._status("CAD check worker could not start · captured results retained. Select again to retry.", False)

    def _verify(self, request):
        error = None
        verified = None
        try:
            context = verify_context_assets(request.context, cancelled=request.cancelled.is_set)
            problems = asset_problems(context)
            if problems:
                error = "\n".join(problems)
            else:
                verified = context["program"], digest_context(context)
        except InterruptedError:
            pass
        except (ValueError, TypeError, ArithmeticError, OSError):
            error = "CAD verification failed; selected assets were not accepted."
        Clock.schedule_once(lambda _dt: self._finish(request, verified, error), 0)

    def _finish(self, request, verified, error):
        if self.request is not request:
            return
        self.request = None
        next_request, self.pending = self.pending, None
        if next_request is not None:
            self._launch(next_request)
            return
        if request.cancelled.is_set():
            self._status("CAD check cancelled · captured results retained.", False)
            return
        panel = self.panel
        try:
            current = panel._definition_identity()
            accepted = (
                not panel.clearance_stale
                and request.baseline == panel.clearance_identity == request.identity == current
                and request.baseline_digest == digest_context(panel.clearance_context)
                and request.report is panel.report
                and request.plot_report is panel.clearance_card.report
                and request.owner_current()
            )
        except (ValueError, TypeError, ArithmeticError):
            accepted = False
        if not accepted:
            self._status("Selection or inputs changed during CAD check · navigation not applied.", False)
            return
        if error or verified != request.identity:
            panel._invalidate_clearance()
            self._status("Current CAD rejected · " + (error or "CAD bytes differ from loaded definitions."), False)
            return
        self._status("CAD bytes checked for this navigation · physical registration unverified.", False)
        request.action()
