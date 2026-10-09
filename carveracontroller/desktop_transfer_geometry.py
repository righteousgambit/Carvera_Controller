"""Dimensioned nominal spindle transfer review, isolated from live machine state."""

from __future__ import annotations

from dataclasses import asdict

from kivy.core.text import Label as CoreLabel
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.slider import Slider
from kivy.uix.widget import Widget

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import (
    ACCENT,
    DANGER,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    release_screen_focus,
)
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.mill_turn_plan import Review, ScheduledStep, dump_plan, plan_from_record, plan_record
from carveracontroller.machine.transfer_geometry import (
    TransferGeometry,
    TransferStudy,
    example_geometry,
    geometry_from_record,
    geometry_record,
    receiver_face,
)


class TransferSection(Widget):
    """True-proportion axial/radial cross-section of declared coaxial solids."""

    def __init__(self, **kwargs):
        super().__init__(size_hint_y=None, height=dp(200), **kwargs)
        self.study: TransferStudy | None = None
        self.fraction = 1.0
        self.primitives = []
        self.bind(size=self.draw, pos=self.draw)

    def show(self, study, fraction=1.0):
        self.study, self.fraction = study, fraction
        self.draw()

    def draw(self, *_):
        self.canvas.clear()
        self.primitives = []
        if self.study is None:
            return
        study, g = self.study, self.study.geometry
        face = receiver_face(g, self.fraction)
        z0 = min(g.stock_start_z_mm, g.source_face_z_mm - g.source.body_length_mm, g.receiver_end_z_mm)
        z1 = max(g.stock_end_z_mm, g.receiver_start_z_mm + g.receiver.body_length_mm)
        radius = max(g.stock_diameter_mm, g.source.outer_diameter_mm, g.receiver.outer_diameter_mm) / 2
        scale = max(0.001, min(max(1, self.width - dp(24)) / (z1 - z0), max(1, self.height - dp(54)) / (2 * radius)))
        offset = self.x + (self.width - (z1 - z0) * scale) / 2
        middle = self.y + dp(26) + (self.height - dp(54)) / 2

        def point(z, r):
            return offset + (z - z0) * scale, middle + r * scale

        def solid(name, a, b, lower, upper, color):
            x, y = point(a, lower)
            size = ((b - a) * scale, (upper - lower) * scale)
            self.primitives.append((name, (a, b, lower, upper), (x, y), size))
            Color(*color)
            Rectangle(pos=(x, y), size=size)

        def chuck(name, spec, face, direction):
            end, bottom = face + direction * spec.body_length_mm, face + direction * spec.bore_depth_mm
            a, b = sorted((face, end))
            outer, bore = spec.outer_diameter_mm / 2, spec.bore_diameter_mm / 2
            solid(name + " upper wall", a, b, bore, outer, RAISED)
            solid(name + " lower wall", a, b, -outer, -bore, RAISED)
            bottom_start, bottom_end = sorted((bottom, end))
            solid(name + " blind end", bottom_start, bottom_end, -bore, bore, MUTED)
            Color(*TEXT)
            Line(rectangle=(*point(a, -outer), (b - a) * scale, outer * 2 * scale), width=dp(1))

        def caption(text, x, y):
            label = CoreLabel(text=text, font_name="Roboto", font_size=sp(10))
            label.refresh()
            Color(*TEXT)
            Rectangle(
                texture=label.texture,
                pos=(min(self.right - label.texture.width - dp(4), max(self.x + dp(4), x)), y),
                size=label.texture.size,
            )

        with self.canvas:
            Color(*MUTED)
            Line(points=[self.x + dp(6), middle, self.right - dp(6), middle], dash_length=dp(4), dash_offset=dp(4))
            chuck("source", g.source, g.source_face_z_mm, -1)
            chuck("receiver", g.receiver, face, 1)
            solid(
                "stock", g.stock_start_z_mm, g.stock_end_z_mm, -g.stock_diameter_mm / 2, g.stock_diameter_mm / 2, ACCENT
            )
            caption("SOURCE", point(g.source_face_z_mm - g.source.body_length_mm, 0)[0], self.top - dp(22))
            caption("RECEIVER", point(face, 0)[0], self.top - dp(22))
            caption(
                f"Stock Ø{g.stock_diameter_mm:g} × {g.stock_end_z_mm - g.stock_start_z_mm:g} mm",
                self.x + dp(6),
                self.y + dp(3),
            )
            for contact in study.contacts:
                Color(*DANGER)
                x = point(contact.receiver_face_z_mm, 0)[0]
                Line(
                    points=[x, self.y + dp(22), x, self.top - dp(24)], dash_length=dp(3), dash_offset=dp(3), width=dp(1)
                )


class TransferGeometryCard(PlanningCard):
    def __init__(self, panel):
        super().__init__("Coaxial transfer geometry")
        self.panel = panel
        self.item: ScheduledStep | None = None
        self.digest = None
        self.drafts = {}
        self.draft_geometries = {}
        self.poses = {}
        self.axis_drafts = {}
        self.local_geometry: TransferGeometry | None = None
        self.message = flowing_text("Select a grip step to review declared stock/chuck geometry.", 30)
        self.content.add_widget(self.message)
        self.preview = TransferSection()
        self.content.add_widget(self.preview)
        controls = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.slider = Slider(min=0, max=1, value=1)
        self.start_action = Action("Start", lambda: setattr(self.slider, "value", 0), size_hint_x=None, width=dp(62))
        controls.add_widget(self.start_action)
        controls.add_widget(self.slider)
        self.contact_action = Action("First contact", self.seek_contact, size_hint_x=None, width=dp(108), disabled=True)
        controls.add_widget(self.contact_action)
        self.content.add_widget(controls)
        self.position = flowing_text("", 24)
        self.content.add_widget(self.position)
        self.slider.bind(value=self.update_pose)
        self.form = AdaptiveGrid(max_cols=2, min_width=150, row_height=78, spacing=dp(6))
        self.dimensions = PlanningCard("Stock & chuck dimensions")
        self.axis = planning_choice(self.dimensions.content, "Declared approach axis", ("Z-shared",))
        self.fields = {}
        labels = {
            "stock_start_z_mm": "Stock source end · Z",
            "stock_end_z_mm": "Stock receiver end · Z",
            "stock_diameter_mm": "Stock diameter",
            "source_face_z_mm": "Source chuck face · Z",
            "receiver_start_z_mm": "Receiver start face · Z",
            "receiver_end_z_mm": "Receiver target face · Z",
            "clearance_mm": "Required dimensional clearance",
            "body_length_mm": "Body length",
            "outer_diameter_mm": "Outer diameter",
            "bore_diameter_mm": "Open bore diameter",
            "bore_depth_mm": "Blind bore depth",
        }
        for key in (
            "stock_start_z_mm",
            "stock_end_z_mm",
            "stock_diameter_mm",
            "source_face_z_mm",
            "receiver_start_z_mm",
            "receiver_end_z_mm",
            "clearance_mm",
        ):
            self.fields[key] = planning_field(self.form, labels[key], quantity="length")
        for owner in ("source", "receiver"):
            for key in ("body_length_mm", "outer_diameter_mm", "bore_diameter_mm", "bore_depth_mm"):
                self.fields[owner + "." + key] = planning_field(
                    self.form, owner.capitalize() + " " + labels[key].lower(), quantity="length"
                )
        self.dimensions.content.add_widget(self.form)
        self.content.add_widget(self.dimensions)
        self.add_action = Action("Add nominal geometry draft", self.add_geometry)
        self.apply_action = Action("Apply dimensions and review", self.apply, primary=True)
        self.content.add_widget(self.add_action)
        self.content.add_widget(self.apply_action)
        self.content.add_widget(
            flowing_text(
                "Opposing coaxial annular bodies and blind bores · millimetres. Apply dimensions to update the reviewed cross-section. Jaws, tools, noncoaxial CAD, compliance and encoder phase are outside this model.",
                50,
            )
        )
        self.show(None, None)

    def capture(self):
        if self.item is not None and self.local_geometry is not None:
            self.drafts[self.item.step.id] = {key: field.text for key, field in self.fields.items()}
            self.draft_geometries[self.item.step.id] = self.local_geometry
            self.poses[self.item.step.id] = self.slider.value
            self.axis_drafts[self.item.step.id] = self.axis.text

    def show(self, item: ScheduledStep | None, review: Review | None):
        if self.item is item and self.digest == (review.digest if review else None):
            return
        self.capture()
        release_screen_focus(self.form)
        if self.digest != (review.digest if review else None):
            self.drafts = {}
            self.draft_geometries = {}
            self.poses = {}
            self.axis_drafts = {}
        self.digest = review.digest if review else None
        self.item = item
        study = item.geometry if item else None
        self.local_geometry = study.geometry if study else self.draft_geometries.get(item.step.id) if item else None
        self.preview.show(study)
        self.slider.value = self.poses.get(item.step.id, 1) if item else 1
        self._fill()
        self._controls()
        if study:
            first = study.contacts[0] if study.contacts else None
            self.message.text = (
                (
                    "CONTACT · " + first.surface_a + " / " + first.surface_b
                    if first
                    else "Declared geometry accepted"
                    if study.accepted
                    else "Insufficient declared engagement"
                )
                + f"\nSource {study.source_engagement_mm:g}/{study.source_required_engagement_mm:g} · receiver {study.receiver_engagement_mm:g}/{study.required_engagement_mm:g} mm actual/required\nTarget minimum dimensional margin {study.minimum_clearance_mm:g} mm · requirement {study.geometry.clearance_mm:g} mm"
            )
        else:
            self.message.text = (
                "Grip geometry absent · add explicit nominal dimensions to review."
                if item and item.step.action == "grip"
                else "Select a grip step to review declared stock/chuck geometry."
            )
        self.update_pose()

    def _fill(self):
        if self.local_geometry is None or self.item is None:
            return
        record = geometry_record(self.local_geometry)
        self.axis.values = tuple(
            resource.id for resource in self.panel.review.plan.resources if resource.kind == "axis"
        )
        self.axis.text = self.axis_drafts.get(self.item.step.id, self.local_geometry.axis)
        draft = self.drafts.get(self.item.step.id, {})
        for key, field in self.fields.items():
            owner, _, name = key.partition(".")
            value = record[owner]
            if name:
                assert isinstance(value, dict)
                value = value[name]
            field.text = draft.get(key, str(value))

    def _controls(self):
        allowed = self.item is not None and self.item.step.action == "grip"
        self.add_action.disabled = not allowed or self.local_geometry is not None
        self.apply_action.disabled = not allowed or self.local_geometry is None
        if self.local_geometry is None and self.dimensions.parent is self.content:
            self.content.remove_widget(self.dimensions)
        elif self.local_geometry is not None and self.dimensions.parent is None:
            self.content.add_widget(self.dimensions, index=3)
        self.preview.height = dp(200) if self.preview.study else 0
        self.slider.disabled = self.preview.study is None
        self.start_action.disabled = self.preview.study is None
        self.contact_action.disabled = not self.preview.study or not self.preview.study.contacts

    def add_geometry(self):
        if self.item is None or self.item.step.action != "grip" or self.panel.review is None:
            return
        axes = [resource.id for resource in self.panel.review.plan.resources if resource.kind == "axis"]
        if not axes:
            self.message.text = "Declare an approach axis in the plan before adding geometry."
            return
        self.local_geometry = example_geometry(self.item.step.id, axes[0])
        self._fill()
        self._controls()
        self.dimensions.set_expanded(True)
        self.message.text = "Nominal draft only · replace every dimension with your intended setup and apply to review."

    def update_pose(self, *_):
        if self.preview.study and self.item is not None:
            self.preview.show(self.preview.study, self.slider.value)
            face = receiver_face(self.preview.study.geometry, self.slider.value)
            seconds = self.item.start_s + self.slider.value * self.item.step.duration_s
            self.position.text = f"{self.slider.value:.1%} approach · receiver Z {face:g} mm · {seconds:g} s nominal · {self.preview.study.geometry.axis} reserved"
        else:
            self.position.text = ""

    def seek_contact(self):
        if self.preview.study and self.preview.study.contacts:
            self.slider.value = self.preview.study.contacts[0].fraction

    def apply(self):
        panel = self.panel
        if (
            panel.closed
            or panel.review is None
            or self.digest != panel.review.digest
            or self.item is None
            or self.item.step.id != panel.selected_id
            or self.local_geometry is None
        ):
            return
        record = geometry_record(self.local_geometry)
        record["axis"] = self.axis.text
        try:
            for key, field in self.fields.items():
                value = field.value()
                owner, _, name = key.partition(".")
                if name:
                    nested = record[owner]
                    assert isinstance(nested, dict)
                    nested[name] = value
                else:
                    record[owner] = value
            geometry = geometry_from_record(record)
            plan = plan_record(panel.review.plan)
            declared = plan.get("transfer_geometry", [])
            assert isinstance(declared, list)
            rows = [row for row in declared if row["step"] != geometry.step]
            plan["transfer_geometry"] = [*rows, asdict(geometry)]
            text = dump_plan(plan_from_record(plan))
        except ValueError as error:
            self.message.text = "Dimensions not admitted; reviewed geometry retained: " + str(error)
            return
        selected = panel.selected_id
        panel.source.text = text
        panel.preferred_id = selected
        panel.request_review()
