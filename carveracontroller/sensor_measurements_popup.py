"""Local measurement receipt review, map import and explicit qualification.

All actions affect local evidence only. A scrolling layout remains usable on
short displays; raw receipts and corrected inspected values stay separate.
"""

from __future__ import annotations

import json

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action, AdaptiveGrid, DesktopScrollView, Field, label
from carveracontroller.desktop_tool_custody import wrapped
from carveracontroller.machine.probe_evidence import CONTEXT_FIELDS, finite, setter_trends

MAP_EXAMPLE = {
    "known_diameter": None,
    "reference_uncertainty_mm": None,
    "feature": "bore",
    "context": dict.fromkeys(
        (
            "probe_identity",
            "seat_revision",
            "configuration_id",
            "orientation_deg",
            "approach_feed_mm_min",
            "reference_id",
            "source_session_id",
            "configured_tip_diameter_mm",
        )
    ),
    "samples": [{"angle_degrees": None, "measured_diameter": None}],
}
VALIDATION_EXAMPLE = {
    "known_diameter": None,
    "reference_uncertainty_mm": None,
    "max_residual_mm": None,
    "context": MAP_EXAMPLE["context"],
    "samples": MAP_EXAMPLE["samples"],
}


class SensorMeasurementsPopup(Popup):
    def __init__(self, machine, **kwargs):
        self.machine = machine
        super().__init__(title="Measurement evidence", size_hint=(0.94, 0.92), **kwargs)
        outer = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        scroll = DesktopScrollView(do_scroll_x=False)
        body = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        scroll.add_widget(body)
        outer.add_widget(scroll)
        self.notice = wrapped()
        self.notice.text = (
            "Position: issued steps. Feed: commanded/planner. Neither is independent physical feedback.\n"
            "Receipts retain raw values; declarations are operator context, not physical readback. "
            "Missing values remain unknown. These actions send no machine commands.\n"
            "Declare phase as before_cut, after_cut or seating_check. Keep seating/configuration identity stable "
            "only while physically unchanged. Raw contact hits may be unavailable in legacy firmware output."
        )
        body.add_widget(self.notice)
        body.add_widget(label("Measurement setup — used for subsequently submitted measurements", 12, height=36))
        declarations = dict.fromkeys(CONTEXT_FIELDS)
        declarations.update(getattr(machine, "measurement_declarations", {}))
        self.setup_fields = {}
        setup = (
            ("probe_identity", "Physical probe identity"),
            ("seat_revision", "Seating identity / revision"),
            ("configuration_id", "Reviewed probe configuration identity"),
            ("reference_id", "Reference artifact identity"),
            ("phase", "Measurement purpose: before_cut / after_cut / seating_check"),
            ("orientation_deg", "Actual probe orientation, degrees"),
            ("approach_direction", "Actual diameter approach direction, degrees"),
            ("approach_feed_mm_min", "Probe approach feed, mm/min"),
            ("configured_tip_diameter_mm", "Configured effective tip diameter, mm"),
            ("assembly_id", "Declared physical tool assembly ID (optional)"),
            ("assembly_revision_id", "Declared assembly revision ID (optional)"),
            ("assignment_id", "Declared assignment receipt ID (optional)"),
        )
        for key, description in setup:
            field = Field(
                hint_text=description,
                text="" if declarations[key] is None else str(declarations[key]),
                size_hint_y=None,
                height=dp(38),
            )
            self.setup_fields[key] = field
            body.add_widget(label(description, 11, height=24))
            body.add_widget(field)
        self.context = Field(text=json.dumps(declarations, indent=2), multiline=True, size_hint_y=None, height=dp(160))
        self.context.cursor = (0, 0)
        body.add_widget(label("Additional context (optional JSON; unknown values remain null)", 11, height=28))
        body.add_widget(self.context)
        body.add_widget(Action("Use this measurement setup", self.save_context))
        body.add_widget(label("Saved receipts and tool-setter trends", 12, height=28))
        self.receipts = Field(readonly=True, multiline=True, size_hint_y=None, height=dp(220))
        body.add_widget(self.receipts)
        body.add_widget(Action("Refresh saved evidence", self.refresh))
        body.add_widget(label("Directional map JSON — raw reference calibration diameters", 12, height=32))
        self.map_data = Field(text=json.dumps(MAP_EXAMPLE, indent=2), multiline=True, size_hint_y=None, height=dp(250))
        body.add_widget(self.map_data)
        body.add_widget(Action("Save directional map locally", self.save_map))
        self.map_id = Field(hint_text="Saved directional map receipt ID", size_hint_y=None, height=dp(38))
        body.add_widget(self.map_id)
        body.add_widget(label("Held-out validation JSON — separate measured session and reference", 12, height=36))
        self.validation = Field(
            text=json.dumps(VALIDATION_EXAMPLE, indent=2), multiline=True, size_hint_y=None, height=dp(250)
        )
        body.add_widget(self.validation)
        body.add_widget(Action("Evaluate and save held-out qualification", self.qualify))
        self.measurement_id = Field(hint_text="Inspected measurement receipt ID", size_hint_y=None, height=dp(38))
        body.add_widget(self.measurement_id)
        self.angle = Field(hint_text="Recorded actual approach angle in degrees", size_hint_y=None, height=dp(38))
        body.add_widget(self.angle)
        self.dimension = Field(hint_text="Inspected axis: x_diameter or y_diameter", size_hint_y=None, height=dp(38))
        body.add_widget(self.dimension)
        body.add_widget(Action("Save corrected inspected diameter (raw retained)", self.correct))
        self.status = wrapped()
        body.add_widget(self.status)
        buttons = AdaptiveGrid(max_cols=2, row_height=36)
        buttons.add_widget(Action("Close", self.dismiss))
        outer.add_widget(buttons)
        self.content = outer
        self.refresh()

    def perform(self, action):
        try:
            result = action()
            self.status.text = json.dumps(result, indent=2)
            self.refresh()
            return result
        except (ValueError, OSError, KeyError, TypeError) as exc:
            self.status.text = "Evidence action refused: " + str(exc)
            return None

    def save_context(self, *_args):
        def action():
            context = json.loads(self.context.text)
            if not isinstance(context, dict):
                raise ValueError("Context must be an object")
            for key, field in self.setup_fields.items():
                value = field.text.strip()
                if key in (
                    "orientation_deg",
                    "approach_direction",
                    "approach_feed_mm_min",
                    "configured_tip_diameter_mm",
                ):
                    context[key] = (
                        None
                        if not value
                        else finite(float(value), key in ("approach_feed_mm_min", "configured_tip_diameter_mm"))
                    )
                else:
                    context[key] = value or None
            self.machine.measurement_declarations = context
            return {"saved_for_next_measurement": context}

        self.perform(action)

    def refresh(self, *_args):
        try:
            store = self.machine.probe_evidence
            events = store.events()
            summaries = [
                {
                    key: event.get(key)
                    for key in ("id", "kind", "at", "result_kind", "context", "result", "passed", "corrected")
                }
                for event in events[-30:]
            ]
            self.receipts.text = json.dumps(
                {
                    "path": str(store.path),
                    "capture_error": store.error,
                    "recent_receipts": summaries,
                    "setter_trends": setter_trends(events),
                },
                indent=2,
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self.receipts.text = "Unable to read evidence; original preserved: " + str(exc)

    def save_map(self, *_args):
        result = self.perform(lambda: self.machine.probe_evidence.save_map(json.loads(self.map_data.text)))
        if result:
            self.map_id.text = result["id"]

    def qualify(self, *_args):
        self.perform(
            lambda: self.machine.probe_evidence.qualify_map(self.map_id.text.strip(), json.loads(self.validation.text))
        )

    def correct(self, *_args):
        def action():
            context = dict(getattr(self.machine, "measurement_declarations", {}))
            context["inspected_dimension"] = self.dimension.text.strip()
            return self.machine.probe_evidence.apply_correction(
                self.measurement_id.text.strip(), self.map_id.text.strip(), float(self.angle.text), context
            )

        self.perform(action)


def open_sensor_measurements(machine):
    popup = SensorMeasurementsPopup(machine)
    popup.open()
    return popup
