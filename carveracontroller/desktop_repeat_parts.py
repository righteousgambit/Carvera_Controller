"""Repeat-part planning with explicit declared frames and local preview only."""

from kivy.metrics import dp

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, label
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.repeat_parts import WCS_NAMES, RepeatPartPlan, RepeatPartStore


class RepeatPartsPanel(PlanningCard):
    def __init__(self, workspace, **kwargs):
        super().__init__("Repeat parts & work offsets", **kwargs)
        self.workspace = workspace
        self.store = RepeatPartStore()
        self.plan = None
        self.owner = None
        self.content.add_widget(label("Declared G54–G59 frames · full-array preview · mm", 12, height=28))
        fields = AdaptiveGrid(max_cols=2, min_width=200, row_height=78, spacing=dp(6))
        self.rows = planning_field(fields, "Rows", "1", quantity="scalar", integer=True, minimum=1, maximum=6)
        self.columns = planning_field(fields, "Columns", "2", quantity="scalar", integer=True, minimum=1, maximum=6)
        self.pitch_x = planning_field(fields, "Column pitch", "60", quantity="length")
        self.pitch_y = planning_field(fields, "Row pitch", "60", quantity="length")
        self.first_wcs = planning_choice(fields, "First declared frame", WCS_NAMES)
        self.content.add_widget(fields)
        vectors = AdaptiveGrid(max_cols=1, min_width=200, row_height=62, spacing=dp(6))
        self.offset = planning_field(vectors, "First datum in machine XYZ · comma-separated", "-180, -120, -110")
        self.origin = planning_field(vectors, "Stock lower corner relative to datum XYZ", "0, 0, -10")
        self.stock_size_field = planning_field(vectors, "Each stock size XYZ", "40, 40, 10")
        self.content.add_widget(vectors)
        actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        for title, callback in (
            ("Use current scene dimensions", self.seed),
            ("Build declared array", self.generate),
            ("Save machine plan", self.save),
            ("Restore machine plan", self.restore),
        ):
            actions.add_widget(Action(title, callback))
        self.content.add_widget(actions)
        self.choice = planning_choice(self.content, "Selected part", ("Build or restore a plan",))
        self.content.add_widget(Action("Preview array with selected part active", self.preview))
        self.content.add_widget(Action("Hide other stock instances", self.hide_others))
        self.summary = label("No repeat-part plan loaded.", 11, MUTED, 150)
        self.content.add_widget(self.summary)
        self.content.add_widget(self.note)
        for control in (
            self.rows,
            self.columns,
            self.pitch_x,
            self.pitch_y,
            self.first_wcs,
            self.offset,
            self.origin,
            self.stock_size_field,
        ):
            control.bind(text=self.draft_changed)

    def draft_changed(self, *_):
        if self.plan is not None:
            self.workspace.machine.gcode_viewer.clear_repeat_stock()
            self.plan = None
            self.owner = None
            self.choice.values = ("Build or restore a plan",)
            self.choice.text = self.choice.values[0]
            self.summary.text = "Inputs changed. Build the declared array again before saving or previewing."

    def profile_id(self):
        profile = self.workspace.selected_machine_profile
        if not profile:
            raise ValueError("Choose a saved machine profile first")
        return profile["id"]

    @staticmethod
    def triple(field):
        values = field.text.split(",")
        if len(values) != 3:
            raise ValueError("Enter three comma-separated coordinates")
        return tuple(parse_quantity(value.strip(), "length") for value in values)

    def run(self, action):
        try:
            action()
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.note.text = str(exc)

    def seed(self):
        def apply():
            setup = self.workspace.machine.gcode_viewer.machine_setup
            if setup.stock_size_mm is None:
                raise ValueError("Declare stock dimensions in Scene first")
            for field, values in (
                (self.offset, setup.work_offset_mm),
                (self.origin, setup.stock_origin_mm),
                (self.stock_size_field, setup.stock_size_mm),
            ):
                field.text = ", ".join(f"{value:g}" for value in values)
            self.note.text = "Copied scene dimensions. Build the array to review declared frames."

        self.run(apply)

    def show_plan(self, plan, owner):
        self.workspace.machine.gcode_viewer.clear_repeat_stock()
        self.plan, self.owner = plan, owner
        self.choice.values = tuple(f"{p.name} · {p.wcs}" for p in plan.parts)
        self.choice.text = self.choice.values[0]
        self.summary.text = "\n".join(
            f"{p.name} · {p.wcs} · datum " + ", ".join(f"{v:g}" for v in p.work_offset_mm) for p in plan.parts
        )

    def generate(self):
        def apply():
            owner = self.profile_id()
            plan = RepeatPartPlan.grid(
                int(self.rows.value()),
                int(self.columns.value()),
                (self.pitch_x.value(), self.pitch_y.value(), 0),
                self.triple(self.offset),
                self.triple(self.origin),
                self.triple(self.stock_size_field),
                self.first_wcs.text,
            )
            self.show_plan(plan, owner)
            self.note.text = (
                "Declared array reviewed for stock overlap. Machine travel, fixtures and offsets remain unverified."
            )

        self.run(apply)

    def current_plan(self):
        if self.plan is None or self.owner != self.profile_id():
            raise ValueError("Build or restore a plan for the currently selected machine")
        return self.plan

    def save(self):
        def apply():
            self.store.save(self.profile_id(), self.current_plan())
            self.note.text = "Saved declared stock instances for this machine. No machine offsets were written."

        self.run(apply)

    def restore(self):
        def apply():
            owner = self.profile_id()
            plan = self.store.load(owner)
            if plan is None:
                raise ValueError("This machine has no saved repeat-part plan")
            self.show_plan(plan, owner)
            self.note.text = "Restored declared plan. Select a part for local preview."

        self.run(apply)

    def preview(self):
        def apply():
            plan = self.current_plan()
            ws = self.workspace
            if ws.app.playing or ws.app.state not in ("Idle", "N/A"):
                raise ValueError("Stop playback and wait for an idle machine before changing preview setup")
            record = ws.run_recording_panel
            if record.busy or record.previous_scene is not None or ws.machine_profile_loading:
                raise ValueError("Return from recorded setup and finish profile loading before changing preview")
            index = self.choice.values.index(self.choice.text)
            part = plan.parts[index]
            ws.set_pose_mode("Preview")
            ws.machine.gcode_viewer.configure_machine(
                work_offset_mm=part.work_offset_mm,
                stock_origin_mm=part.stock_origin_mm,
                stock_size_mm=part.stock_size_mm,
                alignment_confirmed=False,
                repeat_plan=plan,
                repeat_index=index,
            )
            ws.simulation_geometry = {
                "offset": part.work_offset_mm,
                "origin": part.stock_origin_mm,
                "size": part.stock_size_mm,
                "rotation_deg": 0,
            }
            self.note.text = (
                f"{len(plan.parts)} declared stocks shown. {part.name} · {part.wcs} is active (gold); "
                "other stocks are nominal (blue). Program WCS is not remapped; simulation applies only to the active stock."
            )

        self.run(apply)

    def hide_others(self):
        self.workspace.machine.gcode_viewer.clear_repeat_stock()
        self.note.text = "Other instances hidden. Active stock and its simulation remain unchanged."
