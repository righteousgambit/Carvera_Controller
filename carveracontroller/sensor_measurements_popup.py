"""Operator forms for measurement evidence; no motion/configuration commands."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Callable, Protocol

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, DesktopScrollView, Field, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.probe_evidence import MATCH_FIELDS, ProbeEvidenceStore, finite, setter_trends


class MeasurementMachine(Protocol):
    probe_evidence: ProbeEvidenceStore
    measurement_declarations: dict[str, Any]


UNKNOWN = "Unknown / not recorded"


def stamp(value: Any) -> str:
    try:
        return datetime.fromtimestamp(float(value), timezone.utc).strftime("%m-%d %H:%M UTC")
    except (ValueError, TypeError, OverflowError, OSError):
        return "Unknown time"


class EvidenceForm(BoxLayout):
    """Labelled responsive fields; blanks represent unknown values."""

    def __init__(
        self, specs: list[tuple[str, str, str, bool]], initial: dict[str, Any] | None = None, **kwargs: Any
    ) -> None:
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(4), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.specs = specs
        self.fields: dict[str, Field] = {}
        grid = AdaptiveGrid(max_cols=2, min_width=280, row_height=68, spacing=dp(6))
        self.add_widget(grid)
        for key, title, _kind, required in specs:
            cell = BoxLayout(orientation="vertical", spacing=dp(2))
            cell.add_widget(label(title + (" *" if required else " (optional)"), 11, height=26))
            value = (initial or {}).get(key)
            field = Field(text="" if value is None else str(value), multiline=False, height=dp(36), size_hint_y=None)
            field.hint_text = "Required" if required else "Leave blank if unknown"
            self.fields[key] = field
            cell.add_widget(field)
            grid.add_widget(cell)

    def values(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, title, kind, required in self.specs:
            raw = self.fields[key].text.strip()
            if not raw:
                if required:
                    raise ValueError(title + " is required")
                result[key] = None
                continue
            if kind == "text":
                if len(raw) > 512 or any(ord(c) < 32 for c in raw):
                    raise ValueError(title + " must be a single line of at most 512 characters")
                result[key] = raw
            else:
                try:
                    value = finite(float(raw), kind in ("positive", "integer"))
                except ValueError as exc:
                    raise ValueError(
                        title
                        + " must be a finite "
                        + ("positive " if kind in ("positive", "integer") else "")
                        + "number"
                    ) from exc
                if kind == "nonnegative" and value < 0:
                    raise ValueError(title + " cannot be negative")
                if kind == "integer":
                    if value != int(value):
                        raise ValueError(title + " must be a whole number")
                    result[key] = int(value)
                else:
                    result[key] = value
        return result


class DirectionSamples(BoxLayout):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(orientation="vertical", size_hint_y=None, spacing=dp(4), **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.rows: list[tuple[Field, Field]] = []
        self.on_change: Callable[[], None] | None = None
        self.row_box = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.row_box.bind(minimum_height=self.row_box.setter("height"))
        self.add_widget(label("Approach angle (degrees)  |  raw calibration diameter (mm)", 11, height=30))
        self.add_widget(self.row_box)
        for _ in range(3):
            self.add_row()
        self.add_widget(Action("Add another measured direction", self.add_row))

    def add_row(self, *_args: Any) -> None:
        row = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))
        angle = Field(hint_text="Angle", multiline=False)
        diameter = Field(hint_text="Raw diameter", multiline=False)
        row.add_widget(angle)
        row.add_widget(diameter)
        self.rows.append((angle, diameter))
        angle.bind(text=lambda *_a: self.on_change() if self.on_change else None)
        diameter.bind(text=lambda *_a: self.on_change() if self.on_change else None)
        self.row_box.add_widget(row)

    def values(self) -> list[dict[str, float]]:
        samples = []
        for index, (angle, diameter) in enumerate(self.rows, 1):
            a, d = angle.text.strip(), diameter.text.strip()
            if not a and not d:
                continue
            if not a or not d:
                raise ValueError(f"Direction row {index}: enter both angle and raw diameter")
            try:
                samples.append({"angle_degrees": finite(float(a)), "measured_diameter": finite(float(d), True)})
            except ValueError as exc:
                raise ValueError(f"Direction row {index}: use a finite angle and positive diameter") from exc
        if len({s["angle_degrees"] % 360 for s in samples}) < 3:
            raise ValueError("Enter at least three distinct measured directions")
        return samples


SETUP = [
    ("probe_identity", "Physical probe name / serial", "text", False),
    ("seat_revision", "Probe or tool seating revision", "text", False),
    ("configuration_id", "Reviewed calibration / settings identity", "text", False),
    ("reference_id", "Reference artifact name / serial", "text", False),
    ("orientation_deg", "Actual probe orientation (degrees)", "number", False),
    ("approach_direction", "Actual diameter approach angle (degrees)", "number", False),
    ("approach_feed_mm_min", "Probe approach feed (mm/min)", "positive", False),
    ("configured_tip_diameter_mm", "Configured effective tip diameter (mm)", "positive", False),
    ("assembly_id", "Physical assembly receipt ID", "text", False),
    ("assembly_revision_id", "Assembly revision receipt ID", "text", False),
    ("assignment_id", "Tool assignment receipt ID", "text", False),
]
REFERENCE = [
    ("reference_id", "Reference artifact identity", "text", True),
    ("source_session_id", "Source measurement session identity", "text", True),
    ("known_diameter", "Known reference diameter (mm)", "positive", True),
    ("reference_uncertainty_mm", "Reference uncertainty (mm)", "nonnegative", True),
]


class SensorMeasurementsPopup(Popup):
    def __init__(self, machine: MeasurementMachine, **kwargs: Any) -> None:
        self.machine = machine
        self.events: list[dict[str, Any]] = []
        self.read_error: str | None = None
        self.map_options: dict[str, str] = {}
        self.measurement_options: dict[str, str] = {}
        self.receipt_options: dict[str, str] = {}
        self.session_options: dict[str, str] = {}
        self.boundary_no_pending = False
        self.boundary_event = None
        super().__init__(title="Measurement evidence", size_hint=(0.94, 0.94), **kwargs)
        outer = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        tabs = AdaptiveGrid(max_cols=4, min_width=140, row_height=36, spacing=dp(5))
        self.pages: dict[str, BoxLayout] = {}
        for name in ("Setup", "Receipts", "Directional map", "Correct result"):
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
        self.scroll = self.page_scrolls["Setup"]
        outer.add_widget(self.page_manager)
        self.status = wrapped()
        self.status.text = "Local evidence only. Position comes from issued steps; feed comes from the planner."
        self.status.height = dp(42)
        outer.add_widget(self.status)
        controls = AdaptiveGrid(max_cols=2, min_width=140, row_height=36, spacing=dp(5))
        controls.add_widget(Action("Refresh saved evidence", self.refresh))
        controls.add_widget(Action("Close", self.dismiss))
        outer.add_widget(controls)
        self.content = outer
        declarations = getattr(machine, "measurement_declarations", {})
        self.setup = EvidenceForm(SETUP, declarations)
        self.setup_fields = self.setup.fields
        setup_page = self.pages["Setup"]
        setup_page.add_widget(
            self.note(
                "Review this setup before a measurement. Blank fields stay unknown. Changing seating, probe orientation or calibration invalidates comparison with an earlier setup."
            )
        )
        setup_page.add_widget(self.setup)
        self.phase = Choice(
            text=declarations.get("phase") or UNKNOWN, values=(UNKNOWN, "before_cut", "after_cut", "seating_check")
        )
        setup_page.add_widget(label("Measurement purpose", 11, height=26))
        setup_page.add_widget(self.phase)
        self.setup_dimension = Choice(
            text={"x_diameter": "X diameter", "y_diameter": "Y diameter"}.get(
                str(declarations.get("inspected_dimension") or ""), UNKNOWN
            ),
            values=(UNKNOWN, "X diameter", "Y diameter"),
        )
        setup_page.add_widget(label("Diameter axis associated with the recorded approach angle", 11, height=28))
        setup_page.add_widget(self.setup_dimension)
        setup_page.add_widget(Action("Save and use this setup", self.save_context, primary=True))
        self.setup_summary = self.note("")
        setup_page.add_widget(self.setup_summary)

        receipts_page = self.pages["Receipts"]
        self.receipt_choice = Choice(text="Select a saved receipt", values=())
        self.receipt_choice.bind(text=lambda *_a: self.render_receipt())
        receipts_page.add_widget(self.receipt_choice)
        self.receipts = self.note("No saved receipts yet. Submit a measurement from the usual probing controls.")
        receipts_page.add_widget(self.receipts)
        self.raw = Field(readonly=True, multiline=True, size_hint_y=None, height=dp(160))
        receipts_page.add_widget(label("Original received console text (read only)", 11, height=26))
        receipts_page.add_widget(self.raw)
        self.trends = self.note("")
        receipts_page.add_widget(self.trends)
        receipts_page.add_widget(label("Resolve an ambiguous measurement boundary", 13, height=30, bold=True))
        receipts_page.add_widget(
            self.note(
                "Overlapping submitted probe commands leave attribution ambiguous. An END message does not prove which command completed. Preserve an unfinished buffer first, then explicitly declare a completed boundary after checking that no probe commands remain pending. This declaration applies to future sessions; earlier ambiguous measurements remain unchanged."
            )
        )
        self.boundary_form = EvidenceForm([("reason", "Operator boundary explanation", "text", True)])
        self.boundary_form.fields["reason"].bind(text=lambda *_a: self.refresh_boundary())
        receipts_page.add_widget(self.boundary_form)
        self.boundary_check = Action(
            "[ ] I checked that no probe commands remain pending", self.toggle_boundary_pending
        )
        receipts_page.add_widget(self.boundary_check)
        self.boundary_status = self.note("")
        receipts_page.add_widget(self.boundary_status)
        self.close_session_button = Action(
            "Save unfinished buffer as an incomplete receipt", self.close_unfinished_session
        )
        receipts_page.add_widget(self.close_session_button)
        self.boundary_button = Action("Record explicit completed boundary", self.confirm_boundary)
        receipts_page.add_widget(self.boundary_button)

        map_page = self.pages["Directional map"]
        map_page.add_widget(
            self.note(
                "Fit a directional map from raw reference calibration widths, not already compensated feature diameters. Then test a separate held-out session. Saved setup must identify the actual probe, seating, configuration, orientation, approach feed and tip diameter."
            )
        )
        self.map_choice = Choice(text="Select a saved directional map", values=())
        self.map_choice.bind(text=lambda *_a: self.update_actions())
        map_page.add_widget(self.map_choice)
        self.map_summary = self.note("No map selected; correction is unavailable.")
        map_page.add_widget(self.map_summary)
        self.feature = Choice(text="Choose reference geometry", values=("Bore", "Boss"))
        self.feature.bind(text=lambda *_a: self.update_actions())
        map_page.add_widget(label("Reference feature geometry", 11, height=26))
        map_page.add_widget(self.feature)
        self.fit_session_choice = Choice(
            text="Select a recorded source session (or enter an imported identity)", values=()
        )
        self.fit_session_choice.bind(text=lambda *_a: self.select_source_session("fit"))
        map_page.add_widget(self.fit_session_choice)
        self.fit_reference = EvidenceForm(REFERENCE)
        map_page.add_widget(self.fit_reference)
        self.fit_samples = DirectionSamples()
        map_page.add_widget(self.fit_samples)
        self.save_map_button = Action("Save fitted map (unqualified)", self.save_map)
        map_page.add_widget(self.save_map_button)
        self.fit_status = self.note("")
        map_page.add_widget(self.fit_status)
        map_page.add_widget(label("Independent held-out validation", 13, height=30, bold=True))
        self.validation_session_choice = Choice(
            text="Select a held-out recorded session (or enter an imported identity)", values=()
        )
        self.validation_session_choice.bind(text=lambda *_a: self.select_source_session("validate"))
        map_page.add_widget(self.validation_session_choice)
        self.validation_reference = EvidenceForm(
            REFERENCE + [("max_residual_mm", "Allowed residual including reference uncertainty (mm)", "positive", True)]
        )
        map_page.add_widget(self.validation_reference)
        self.validation_samples = DirectionSamples()
        map_page.add_widget(self.validation_samples)
        self.qualify_button = Action("Evaluate held-out measurements", self.qualify)
        map_page.add_widget(self.qualify_button)
        self.validation_status = self.note("")
        map_page.add_widget(self.validation_status)

        correction_page = self.pages["Correct result"]
        correction_page.add_widget(
            self.note(
                "This saves a separate corrected inspection result. It preserves original measurements and does not change firmware offsets or move the machine. A passing held-out check is evidence for the declared setup, not machine accuracy certification."
            )
        )
        self.measurement_choice = Choice(text="Select an inspected bore/boss measurement", values=())
        self.measurement_choice.bind(text=lambda *_a: self.select_measurement())
        correction_page.add_widget(self.measurement_choice)
        self.correction_map_choice = Choice(text="Select a saved directional map", values=())
        self.correction_map_choice.bind(text=lambda *_a: self.update_actions())
        correction_page.add_widget(self.correction_map_choice)
        self.dimension = Choice(text="Choose diameter axis", values=("X diameter", "Y diameter"))
        self.dimension.bind(text=lambda *_a: self.select_direction())
        correction_page.add_widget(self.dimension)
        self.angle = Field(
            hint_text="Recorded actual approach angle in degrees", multiline=False, size_hint_y=None, height=dp(36)
        )
        self.angle.bind(text=lambda *_a: self.update_actions())
        correction_page.add_widget(label("Actual approach angle (degrees; must match original record)", 11, height=28))
        correction_page.add_widget(self.angle)
        self.correction_summary = self.note("")
        correction_page.add_widget(self.correction_summary)
        self.correct_button = Action("Save corrected inspection result", self.correct, primary=True)
        correction_page.add_widget(self.correct_button)
        for form in (self.fit_reference, self.validation_reference):
            for field in form.fields.values():
                field.bind(text=lambda *_a: self.update_actions())
        self.fit_samples.on_change = self.update_actions
        self.validation_samples.on_change = self.update_actions
        self.show_page("Setup")
        self.refresh()
        self.bind(on_dismiss=self.release_focus)
        self.bind(on_open=self.start_boundary_refresh)

    def start_boundary_refresh(self, *_args: Any) -> None:
        if self.boundary_event is None:
            self.boundary_event = Clock.schedule_interval(self.refresh_boundary, 0.3)

    def release_focus(self, *_args: Any) -> None:
        if self.boundary_event is not None:
            self.boundary_event.cancel()
            self.boundary_event = None
        for widget in self.content.walk():
            if hasattr(widget, "focus"):
                widget.focus = False

    @staticmethod
    def note(text: str) -> Any:
        item = wrapped()
        item.text = text
        return item

    def show_page(self, name: str) -> None:
        for widget in self.scroll.walk():
            if hasattr(widget, "focus"):
                widget.focus = False
        self.scroll = self.page_scrolls[name]
        self.page_manager.current = name
        self.scroll.scroll_y = 1
        # Each page retains its viewport and balanced clipping canvas. Update
        # its transform after layout rather than replacing a live viewport.
        Clock.schedule_once(lambda _dt: self.scroll.update_from_scroll(), 0)

    def report_error(self, exc: Exception) -> None:
        self.status.text = f"Not saved: {exc}. Review the fields or recording path; original evidence is preserved."

    def toggle_boundary_pending(self, *_args: Any) -> None:
        self.boundary_no_pending = not self.boundary_no_pending
        self.boundary_check.text = (
            "[x] " if self.boundary_no_pending else "[ ] "
        ) + "I checked that no probe commands remain pending"
        self.refresh_boundary()

    def boundary_readiness(self) -> tuple[str, dict[str, Any]]:
        if self.read_error:
            raise ValueError("Recording unavailable: " + self.read_error)
        reason = self.boundary_form.values()["reason"]
        if not self.boundary_no_pending:
            raise ValueError("Explicitly check that no probe commands remain pending")
        controller = getattr(self.machine, "controller", None)
        if controller is None or getattr(controller, "stream", None) is None:
            raise ValueError("Connected controller and fresh Idle telemetry required")
        context = controller.sensor_context_snapshot()
        age = context.get("arrival_age_s")
        if (
            context.get("state") != "Idle"
            or type(age) not in (int, float)
            or not math.isfinite(age)
            or not 0 <= age <= 0.8
            or getattr(controller, "status_reacquisition_pending", False)
        ):
            raise ValueError("Fresh Idle telemetry required before recording a boundary")
        if any(getattr(controller, name, 0) for name in ("sendNUM", "loadNUM", "pausing")):
            raise ValueError("Controller still has an active or pending program")
        queue_depth = (context.get("motion") or {}).get("queue_depth")
        if (
            isinstance(queue_depth, (int, float))
            and not isinstance(queue_depth, bool)
            and math.isfinite(queue_depth)
            and queue_depth > 0
        ):
            raise ValueError("Firmware reports queued motion; a completed boundary cannot be declared")
        return reason, self.machine.probe_evidence.attribution_status()

    def refresh_boundary(self, *_args: Any) -> None:
        if not hasattr(self, "boundary_button"):
            return
        try:
            reason, state = self.boundary_readiness()
            self.close_session_button.disabled = not state["active_session"]
            self.boundary_button.disabled = state["active_session"]
            self.boundary_status.text = (
                "Active submitted buffer: preserve it as incomplete before declaring a boundary. Attribution is not cleared by this save."
                if state["active_session"]
                else "Ready for explicit operator declaration. Earlier ambiguous measurements are preserved."
            )
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.close_session_button.disabled = self.boundary_button.disabled = True
            self.boundary_status.text = str(exc)

    def close_unfinished_session(self, *_args: Any) -> None:
        def action() -> dict[str, Any]:
            controller = getattr(self.machine, "controller", None)
            if controller is None:
                raise ValueError("Connected controller and fresh Idle telemetry required")
            with controller._adaptive_lock:
                reason, state = self.boundary_readiness()
                if not state["active_session"]:
                    raise ValueError("No active submitted measurement buffer to preserve")
                return self.machine.probe_evidence.capture("incomplete", {"reason": reason})

        self.perform(action, "Unfinished buffer preserved as incomplete; attribution remains ambiguous.")
        self.refresh_boundary()

    def confirm_boundary(self, *_args: Any) -> None:
        def action() -> dict[str, Any]:
            controller = getattr(self.machine, "controller", None)
            if controller is None:
                raise ValueError("Connected controller and fresh Idle telemetry required")
            with controller._adaptive_lock:
                reason, state = self.boundary_readiness()
                if state["active_session"]:
                    raise ValueError("Preserve the active submitted buffer as incomplete first")
                return self.machine.probe_evidence.confirm_completed_boundary(
                    reason, machine_idle=True, pending_commands=0
                )

        result = self.perform(action, "Explicit completed-boundary declaration saved; earlier evidence retained.")
        if result:
            self.boundary_no_pending = False
            self.boundary_check.text = "[ ] I checked that no probe commands remain pending"
        self.refresh_boundary()

    def perform(self, action: Callable[[], dict[str, Any]], message: str) -> dict[str, Any] | None:
        try:
            result = action()
            self.status.text = f"{message} Receipt {result['id'][:8]} · {stamp(result.get('at'))}"
            self.refresh()
            return result
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.report_error(exc)
            return None

    def save_context(self, *_args: Any) -> None:
        def action() -> dict[str, Any]:
            context = dict(getattr(self.machine, "measurement_declarations", {}))
            context.update(self.setup.values())
            context["phase"] = None if self.phase.text == UNKNOWN else self.phase.text
            context["inspected_dimension"] = {"X diameter": "x_diameter", "Y diameter": "y_diameter"}.get(
                self.setup_dimension.text
            )
            receipt = self.machine.probe_evidence.append("measurement_setup", context=context)
            self.machine.measurement_declarations = context
            return receipt

        self.perform(action, "Setup saved for subsequently submitted measurements.")

    def selected(self, choice: Any, options: dict[str, str]) -> dict[str, Any] | None:
        identity = options.get(choice.text)
        return next((event for event in self.events if event["id"] == identity), None)

    def refresh(self, *_args: Any) -> None:
        try:
            store = self.machine.probe_evidence
            self.events = store.events()
            self.read_error = store.error
            self.receipt_options = {
                f"{e['kind'].replace('_', ' ')} · {stamp(e.get('at'))} · {e['id'][:8]}": e["id"]
                for e in self.events[-100:]
            }
            self.map_options = {
                f"{(e.get('context') or {}).get('probe_identity') or 'Probe'} · {stamp(e.get('at'))} · {e['id'][:8]}": e[
                    "id"
                ]
                for e in self.events
                if e["kind"] == "lobing_map"
            }
            self.measurement_options = {
                f"{e['result'].get('kind')} · {stamp(e.get('at'))} · {e['id'][:8]}": e["id"]
                for e in self.events
                if e["kind"] == "measurement"
                and e.get("result_kind") == "probe"
                and e.get("result", {}).get("kind") in ("bore", "boss")
            }
            for choice, options in (
                (self.receipt_choice, self.receipt_options),
                (self.map_choice, self.map_options),
                (self.correction_map_choice, self.map_options),
                (self.measurement_choice, self.measurement_options),
            ):
                choice.values = tuple(options)
            self.session_options = {
                f"{e.get('result_kind', 'measurement')} · {stamp(e.get('at'))} · receipt {e['id'][:8]}": e["id"]
                for e in self.events
                if e["kind"] == "measurement" and e.get("session_id")
            }
            self.fit_session_choice.values = self.validation_session_choice.values = tuple(self.session_options)
            active = getattr(self.machine, "measurement_declarations", {})
            self.setup_summary.text = f"Recording: {store.path}\nCurrent setup: {active.get('probe_identity') or 'unknown probe'}; seating {active.get('seat_revision') or 'unknown'}; reference {active.get('reference_id') or 'unknown'}."
            if self.read_error:
                self.setup_summary.text += "\nRecording error: " + self.read_error
            trends = setter_trends(self.events)
            self.trends.text = "Tool-setter trends: " + (
                "\n".join(
                    f"{t['count']} matching samples; mean change {t['mean_change_mm'] if t['mean_change_mm'] is not None else 'unknown'} mm. {t['interpretation']}"
                    for t in trends
                )
                or "No comparable assembly/seating/settings groups yet."
            )
            self.render_receipt()
            self.update_actions()
            self.refresh_boundary()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.read_error = str(exc)
            self.receipts.text = "Cannot read saved evidence: " + str(exc)
            self.setup_summary.text = f"Recording unavailable at {self.machine.probe_evidence.path}; repair access or select a new destination. Existing evidence is preserved."
            self.update_actions()
            self.refresh_boundary()

    def render_receipt(self) -> None:
        event = self.selected(self.receipt_choice, self.receipt_options)
        if not event:
            self.raw.text = ""
            self.receipts.text = (
                f"{len(self.events)} saved receipts. Select one to inspect original measurements and context."
            )
            return
        context = event.get("context") or {}
        rows = [
            f"Receipt {event['id']} · {stamp(event.get('at'))}",
            f"Type: {event['kind'].replace('_', ' ')}",
            f"Probe: {context.get('probe_identity') or 'unknown'} | reference: {context.get('reference_id') or 'unknown'}",
            f"Raw contacts: {'available' if event.get('raw_hits_available') else 'not established for this receipt'}",
            f"Attribution: {'AMBIGUOUS; not usable for correction' if event.get('attribution_ambiguous') or event.get('session_contaminated') else 'no ambiguity flag recorded'}",
        ]
        result = event.get("result") or event.get("corrected") or {}
        rows.extend(f"{key.replace('_', ' ')}: {value}" for key, value in result.items() if value is not None)
        if event["kind"] == "inspected_correction":
            rows.append(
                "Derived inspection value; original measurement receipt " + event["measurement_id"] + " preserved."
            )
        self.receipts.text = "\n".join(rows)
        raw = event.get("raw_console") or []
        if isinstance(raw, dict):
            raw = [raw]
        self.raw.text = "\n".join(line.get("text", "") for line in raw) or "No raw console transcript in this receipt."
        self.raw.cursor = (0, 0)

    def select_source_session(self, kind: str) -> None:
        choice = self.fit_session_choice if kind == "fit" else self.validation_session_choice
        form = self.fit_reference if kind == "fit" else self.validation_reference
        event = self.selected(choice, self.session_options)
        if event:
            form.fields["source_session_id"].text = event.get("session_id") or ""

    def select_measurement(self) -> None:
        if hasattr(self, "dimension"):
            self.dimension.text = "Choose diameter axis"
            self.angle.text = ""
        self.update_actions()

    @staticmethod
    def recorded_direction(inspected: dict[str, Any] | None, axis: str | None) -> Any:
        context = (inspected or {}).get("context") or {}
        directions = context.get("approach_directions") or {}
        if not isinstance(directions, dict):
            directions = {}
        if axis in directions:
            return directions[axis]
        declared_axis = context.get("inspected_dimension")
        if declared_axis == axis or declared_axis is None and axis == "x_diameter":
            return context.get("approach_direction")
        return None

    def select_direction(self) -> None:
        if not hasattr(self, "angle"):
            return
        inspected = self.selected(self.measurement_choice, self.measurement_options)
        axis = {"X diameter": "x_diameter", "Y diameter": "y_diameter"}.get(self.dimension.text)
        direction = self.recorded_direction(inspected, axis)
        self.angle.text = "" if direction is None else str(direction)
        self.update_actions()

    def qualification(self, map_event: dict[str, Any] | None) -> dict[str, Any] | None:
        if not map_event:
            return None
        found = [e for e in self.events if e["kind"] == "lobing_qualification" and e.get("map_id") == map_event["id"]]
        return found[-1] if found else None

    def update_actions(self) -> None:
        if not hasattr(self, "correct_button"):
            return
        mapping = self.selected(self.map_choice, self.map_options)
        q = self.qualification(mapping)
        self.map_summary.text = (
            "No map selected; correction is unavailable."
            if not mapping
            else f"Map {mapping['id'][:8]}: "
            + (
                "latest held-out validation PASSED"
                if q and q.get("passed")
                else "latest validation FAILED"
                if q
                else "UNQUALIFIED: no held-out validation"
            )
            + ". Original and corrected values remain separate."
        )
        if mapping:
            self.map_summary.text += "\nSource: " + (mapping.get("source_linkage") or {}).get(
                "basis", "original source linkage not established"
            )
        for kind, form, samples, button, status in (
            ("fit", self.fit_reference, self.fit_samples, self.save_map_button, self.fit_status),
            (
                "validate",
                self.validation_reference,
                self.validation_samples,
                self.qualify_button,
                self.validation_status,
            ),
        ):
            try:
                if self.read_error:
                    raise ValueError("Recording unavailable: " + self.read_error)
                if kind == "validate" and mapping is None:
                    raise ValueError("Select a fitted map first")
                context = getattr(self.machine, "measurement_declarations", {})
                for key in MATCH_FIELDS + ("configured_tip_diameter_mm",):
                    if context.get(key) is None or context[key] == "":
                        raise ValueError("Save setup with " + key.replace("_", " "))
                payload = self.reference_payload(form, samples)
                if (
                    kind == "validate"
                    and mapping
                    and payload["context"]["source_session_id"] == mapping["context"].get("source_session_id")
                ):
                    raise ValueError("Use a separate held-out measurement session")
                button.disabled = False
                status.text = (
                    "Ready to save supplied reference observations."
                    if kind == "fit"
                    else "Ready to evaluate this separate held-out session. Passing is not assumed."
                )
            except (ValueError, TypeError, KeyError) as exc:
                button.disabled = True
                status.text = str(exc)
        inspected = self.selected(self.measurement_choice, self.measurement_options)
        correction_map = self.selected(self.correction_map_choice, self.map_options)
        qualification = self.qualification(correction_map)
        missing = []
        if self.read_error:
            missing.append("recording unavailable: " + self.read_error)
        if inspected is None:
            missing.append("select an original bore/boss measurement")
        if correction_map is None:
            missing.append("select a directional map")
        elif not qualification or not qualification.get("passed"):
            missing.append("latest held-out validation must pass")
        axis = {"X diameter": "x_diameter", "Y diameter": "y_diameter"}.get(self.dimension.text)
        if axis is None:
            missing.append("choose a diameter axis")
        elif inspected and (inspected.get("result") or {}).get(axis) is None:
            missing.append("selected axis was not reported")
        elif inspected and self.recorded_direction(inspected, axis) is None:
            missing.append("original approach angle must be attributed to the selected diameter axis")
        try:
            angle = finite(float(self.angle.text))
            recorded_angle = self.recorded_direction(inspected, axis)
            if inspected and (
                recorded_angle is None or not math.isclose(finite(recorded_angle) % 360, angle % 360, abs_tol=1e-9)
            ):
                missing.append("angle must match the original measurement's recorded direction")
        except ValueError:
            missing.append("enter the recorded actual approach angle")
        active = getattr(self.machine, "measurement_declarations", {})
        if inspected and correction_map:
            if (inspected.get("result") or {}).get("kind") != correction_map.get("descriptor", {}).get(
                "feature", "bore"
            ):
                missing.append("measurement and reference feature geometries must match")
            for key in MATCH_FIELDS:
                if (
                    active.get(key) is None
                    or active.get(key) != (inspected.get("context") or {}).get(key)
                    or active.get(key) != (correction_map.get("context") or {}).get(key)
                ):
                    missing.append("review matching setup: " + key.replace("_", " "))
        self.correct_button.disabled = bool(missing)
        self.correction_summary.text = "Before correction: " + "; ".join(missing)
        if not missing and inspected is not None:
            self.correction_summary.text = f"Ready for explicit correction. Original {axis}: {inspected['result'][axis]} mm. A separate derived receipt will be saved."

    def reference_payload(self, form: EvidenceForm, samples: DirectionSamples) -> dict[str, Any]:
        data = form.values()
        context = dict(getattr(self.machine, "measurement_declarations", {}))
        context.update(reference_id=data.pop("reference_id"), source_session_id=data.pop("source_session_id"))
        feature = self.feature.text.lower()
        if form is self.validation_reference:
            mapping = self.selected(self.map_choice, self.map_options)
            feature = (mapping or {}).get("descriptor", {}).get("feature", "")
        if feature not in ("bore", "boss"):
            raise ValueError("Choose the reference feature geometry")
        return dict(data, context=context, feature=feature, samples=samples.values())

    def save_map(self, *_args: Any) -> None:
        result = self.perform(
            lambda: self.machine.probe_evidence.save_map(self.reference_payload(self.fit_reference, self.fit_samples)),
            "Fitted map saved; held-out validation is still required.",
        )
        if result:
            option = next(key for key, value in self.map_options.items() if value == result["id"])
            self.map_choice.text = self.correction_map_choice.text = option
            self.update_actions()

    def qualify(self, *_args: Any) -> None:
        mapping = self.selected(self.map_choice, self.map_options)
        if not mapping:
            self.report_error(ValueError("Select a fitted map first"))
            return
        self.perform(
            lambda: self.machine.probe_evidence.qualify_map(
                mapping["id"], self.reference_payload(self.validation_reference, self.validation_samples)
            ),
            "Held-out evaluation saved. Review PASSED / FAILED above.",
        )

    def correct(self, *_args: Any) -> None:
        inspected = self.selected(self.measurement_choice, self.measurement_options)
        mapping = self.selected(self.correction_map_choice, self.map_options)
        if not inspected or not mapping:
            self.report_error(ValueError("Select the original measurement and map"))
            return

        def action() -> dict[str, Any]:
            context = dict(getattr(self.machine, "measurement_declarations", {}))
            context["inspected_dimension"] = {"X diameter": "x_diameter", "Y diameter": "y_diameter"}.get(
                self.dimension.text
            )
            return self.machine.probe_evidence.apply_correction(
                inspected["id"], mapping["id"], finite(float(self.angle.text)), context
            )

        self.perform(action, "Derived inspection value saved; original measurement retained.")


def open_sensor_measurements(machine: Any) -> SensorMeasurementsPopup:
    popup = SensorMeasurementsPopup(machine)
    popup.open()
    return popup
