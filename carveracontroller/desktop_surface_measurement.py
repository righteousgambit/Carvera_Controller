"""Responsive local surface measurement review; never dispatches motion."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Field,
    QuantityField,
    label,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.surface_measurement import plan_surface_measurement


class SurfaceMeasurementReview:
    DIRECTIONS = {
        "Surface normal": None,
        "X−": (-1, 0, 0),
        "X+": (1, 0, 0),
        "Y−": (0, -1, 0),
        "Y+": (0, 1, 0),
        "Z−": (0, 0, -1),
        "Z+": (0, 0, 1),
    }

    def __init__(self, interaction):
        self.interaction = interaction
        self.reference = interaction.selected_surface()
        self.plan = None
        self.saving = False
        self.closed = False
        body = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(12))
        scroll = DesktopScrollView(do_scroll_x=False)
        form = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))
        scroll.add_widget(form)
        body.add_widget(scroll)
        form.add_widget(content_label("Nominal CAD measurement plan · ball-center coordinates · no machine commands"))
        self.fields = {}
        grid = AdaptiveGrid(max_cols=2, min_width=200, row_height=76, spacing=dp(8))
        for key, title, default in (
            ("tip", "Effective probe tip diameter", "2 mm"),
            ("clearance", "Approach / retract distance", "5 mm"),
            ("overtravel", "Search beyond nominal contact", "1 mm"),
        ):
            cell = BoxLayout(orientation="vertical")
            cell.add_widget(label(title, 12, height=24))
            field = QuantityField(text=default, kind="length", minimum=0.000001, maximum=1000)
            self.fields[key] = field
            cell.add_widget(field)
            grid.add_widget(cell)
        self.normal = Choice(text="CAD winding", values=("CAD winding", "Reverse winding"))
        self.direction = Choice(text="Surface normal", values=tuple(self.DIRECTIONS))
        for title, control in (("Select outward side", self.normal), ("Probe travel direction", self.direction)):
            cell = BoxLayout(orientation="vertical")
            cell.add_widget(label(title, 12, height=24))
            cell.add_widget(control)
            grid.add_widget(cell)
        form.add_widget(grid)
        self.result = content_label("")
        form.add_widget(self.result)
        form.add_widget(label("Retain an inspection feature", 15, height=30, bold=True))
        self.part = Field(hint_text="Part / specimen identifier")
        self.name = Field(text=f"{self.reference.component} surface", hint_text="Feature name")
        for field in (self.part, self.name):
            field.size_hint_y = None
            field.height = dp(40)
            form.add_widget(field)
        limits = AdaptiveGrid(max_cols=2, min_width=200, row_height=76, spacing=dp(8))
        self.lower = QuantityField(text="", kind="length", optional=True, minimum=-1000, maximum=1000)
        self.upper = QuantityField(text="", kind="length", optional=True, minimum=-1000, maximum=1000)
        for title, field in (
            ("Lower normal deviation (optional)", self.lower),
            ("Upper normal deviation (optional)", self.upper),
        ):
            cell = BoxLayout(orientation="vertical")
            cell.add_widget(label(title, 12, height=24))
            cell.add_widget(field)
            limits.add_widget(cell)
        form.add_widget(limits)
        self.save_note = content_label("")
        form.add_widget(self.save_note)
        form.add_widget(
            content_label(
                "Review physical registration, effective tip calibration, adjacent surfaces, probe body/holder reach and machine limits before execution. CAD winding does not establish the outward side. Search-limit geometry is a planning bound, not a clearance result."
            )
        )
        buttons = AdaptiveGrid(max_cols=3, min_width=140, row_height=38, spacing=dp(8))
        buttons.add_widget(Action("Preview approach", self.preview, primary=True))
        self.save_button = Action("Save inspection feature", self.save_feature)
        buttons.add_widget(self.save_button)
        buttons.add_widget(Action("Close", self.close))
        body.add_widget(buttons)
        self.popup = Popup(title="Surface measurement", content=body, size_hint=(0.72, 0.78))
        self.popup.bind(on_dismiss=lambda *_: setattr(self, "closed", True))
        for field in (*self.fields.values(), self.normal, self.direction):
            field.bind(text=lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        self.plan = None
        try:
            if self.interaction.selected_surface() != self.reference:
                raise ValueError("Surface or setup changed · close and pick again")
            self.plan = plan_surface_measurement(
                self.reference,
                tip_diameter_mm=self.fields["tip"].value(),
                clearance_mm=self.fields["clearance"].value(),
                overtravel_mm=self.fields["overtravel"].value(),
                direction=self.DIRECTIONS[self.direction.text],
                flip=self.normal.text == "Reverse winding",
            )
            lines = [f"{self.reference.component} / {self.reference.group} · triangle {self.reference.triangle_index}"]
            for title, point in (
                ("Nominal surface", self.reference.component_point_mm),
                ("Approach / retract", self.plan.approach_mm),
                ("Expected ball center", self.plan.contact_center_mm),
                ("Search limit", self.plan.search_limit_mm),
            ):
                lines.append(f"{title}: " + ", ".join(f"{v:.3f}" for v in point) + " mm")
            self.result.text = "\n".join(lines)
        except ValueError as exc:
            self.result.text = str(exc)

    def preview(self):
        self.refresh()
        if self.plan is not None:
            self.interaction.preview_measurement(self.plan)
            self.popup.dismiss()

    def close(self):
        self.popup.dismiss()

    def save_feature(self):
        from carveracontroller.desktop_scene import capture_scene_setup
        from carveracontroller.desktop_surface_inspection import open_surface_inspections, run_inspection_job

        if self.saving:
            return
        self.refresh()
        if self.plan is None:
            self.save_note.text = self.result.text
            return
        try:
            workspace = self.interaction.workspace
            plan = self.plan
            arguments = {
                "part": self.part.text,
                "name": self.name.text,
                "limits": (self.lower.value(), self.upper.value()),
                "context": {
                    "setup": capture_scene_setup(workspace),
                    "machine_profile_id": (workspace.selected_machine_profile or {}).get("id"),
                },
            }
        except (ValueError, OSError, TypeError) as exc:
            self.save_note.text = str(exc)
            return
        self.saving = True
        self.save_button.disabled = True
        self.save_note.text = "Saving nominal inspection feature…"

        def saved(identity, error):
            self.saving = False
            self.save_button.disabled = False
            self.save_note.text = error or f"Retained inspection feature {identity}"
            if not error and not self.closed:
                self.popup.dismiss()
                open_surface_inspections(workspace, identity)

        run_inspection_job(workspace, lambda store: store.create(plan, **arguments), saved)

    def open(self):
        self.closed = False
        self.popup.open()
