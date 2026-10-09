"""Repeat-part planning with explicit declared frames and local preview only."""

import threading
from dataclasses import replace

from kivy.clock import Clock
from kivy.logger import Logger
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import ACCENT, BG, MUTED, RAISED, TEXT, Action, AdaptiveGrid, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.geometry_changes import capture_context, digest_context
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.repeat_archive import load_repeat_result, save_repeat_result, verify_assets
from carveracontroller.machine.repeat_display import RepeatStockDisplay
from carveracontroller.machine.repeat_parts import (
    WCS_NAMES,
    RepeatPartPlan,
    RepeatPartStore,
    StockInstance,
    StockSource,
    frame_review,
    grid_draft,
    plan_revision,
    replace_part,
)
from carveracontroller.machine.repeat_playback import prepare_repeat_playback
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts


class RepeatPartsPanel(PlanningCard):
    def __init__(self, workspace, **kwargs):
        super().__init__("Repeat parts & work offsets", **kwargs)
        self.workspace = workspace
        self.store = RepeatPartStore()
        self.plan = None
        self.array_stock_source = None
        self.owner = None
        self.saved_revisions = {}
        self.io_busy = False
        self.io_generation = 0
        self.draft_generation = 0
        self.plan_io_receipt = None
        self.plan_io_label = ""
        self._plan_status_signature = None
        self._frame_signature = None
        self.syncing_layout = False
        self.syncing_editor = False
        self.part_drafts = {}
        self.part_edit_context = None
        self.closed = False
        self.calculating = False
        self.cancel_event = threading.Event()
        self.result = None
        self.result_archive_context = None
        self.page = "Layout"
        self.tabs = AdaptiveGrid(max_cols=3, min_width=120, row_height=34, spacing=dp(6))
        self.tab_actions = {}
        for title, page in (
            ("Array layout", "Layout"),
            ("Review & simulate", "Review"),
            ("Results & files", "Results"),
        ):
            action = Action(title, lambda page=page: self.show_page(page), height=dp(34))
            self.tab_actions[page] = action
            self.tabs.add_widget(action)
        self.content.add_widget(self.tabs)
        self.plan_toolbar = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.save_plan_action = Action("Save machine plan", self.save)
        self.restore_plan_action = Action("Restore machine plan", self.restore)
        self.plan_toolbar.add_widget(self.save_plan_action)
        self.plan_toolbar.add_widget(self.restore_plan_action)
        self.content.add_widget(self.plan_toolbar)
        self.persistence_status = content_label("Array draft · build or restore a reviewed plan.")
        self.content.add_widget(self.persistence_status)
        self.layout_body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.review_body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.results_body = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        for body in (self.layout_body, self.review_body, self.results_body):
            body.bind(minimum_height=body.setter("height"))
        self.content.add_widget(self.layout_body)
        self.content.add_widget(label("Declared G54–G59 frames · full-array preview · mm", 12, height=28))
        fields = AdaptiveGrid(max_cols=3, min_width=145, row_height=78, spacing=dp(6))
        self.rows = planning_field(fields, "Rows", "1", quantity="scalar", integer=True, minimum=1, maximum=6)
        self.columns = planning_field(fields, "Columns", "2", quantity="scalar", integer=True, minimum=1, maximum=6)
        self.pitch_x = planning_field(fields, "Column pitch", "60", quantity="length")
        self.pitch_y = planning_field(fields, "Row pitch", "60", quantity="length")
        self.first_wcs = planning_choice(fields, "First declared frame", WCS_NAMES)
        self.stock_shape = planning_choice(fields, "Stock shape", ("Rectangular block", "Current scene solid"))
        self.stock_shape.bind(text=self.choose_stock_shape)
        self.layout_body.add_widget(fields)
        vectors = AdaptiveGrid(max_cols=3, min_width=145, row_height=62, spacing=dp(6))
        self.offset = planning_field(vectors, "First datum · machine XYZ", "-180, -120, -110")
        self.origin = planning_field(vectors, "Stock origin · local XYZ", "0, 0, -10")
        self.stock_size_field = planning_field(vectors, "Each stock size · XYZ", "40, 40, 10")
        self.stock_angles = planning_field(vectors, "Stock angles · XYZ (°)", "0, 0, 0")
        self.layout_body.add_widget(vectors)
        self.layout_note = content_label(
            "Array fields create a regular row-major layout. Stock angles use fixed X, then Y, then Z about each center; declared WCS is translation only."
        )
        self.layout_body.add_widget(self.layout_note)
        self.layout_body.add_widget(Action("Start a new array draft", self.new_array))
        actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        for title, callback in (
            ("Use current scene stock", self.seed),
            ("Build declared array", self.generate),
        ):
            action = Action(title, callback)
            actions.add_widget(action)
        self.layout_body.add_widget(actions)
        self.summary = content_label("No repeat-part plan loaded.")
        self.results_body.add_widget(self.summary)
        self.choice = planning_choice(self.review_body, "Selected part", ("Build or restore a plan",))
        self.choice.bind(text=lambda *_: self.refresh_frame_review())
        self.frame_detail = content_label("Build or restore an array to review its declared frame.")
        self.review_body.add_widget(self.frame_detail)
        self.part_editor = PlanningCard("Edit selected part")
        edit_fields = AdaptiveGrid(max_cols=2, min_width=145, row_height=78, spacing=dp(6))
        self.part_name = planning_field(self.part_editor.content, "Part name")
        self.part_wcs = planning_choice(edit_fields, "Declared frame", WCS_NAMES)
        self.part_offset = planning_field(edit_fields, "Datum · machine XYZ")
        self.part_origin = planning_field(edit_fields, "Stock origin · local XYZ")
        self.part_size = planning_field(edit_fields, "Stock size · XYZ")
        self.part_orientation = planning_field(edit_fields, "Stock angles · XYZ (°)")
        self.part_editor.content.add_widget(edit_fields)
        edit_actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        edit_actions.add_widget(Action("Apply part draft", self.apply_part))
        edit_actions.add_widget(Action("Discard part draft", self.discard_part_draft))
        edit_actions.add_widget(Action("Apply all part drafts", self.apply_all_parts))
        edit_actions.add_widget(Action("Discard all part drafts", self.discard_all_parts))
        self.part_editor.content.add_widget(edit_actions)
        self.part_editor.content.add_widget(self.part_editor.note)
        self.review_body.add_widget(self.part_editor)
        for control in self.part_fields:
            control.bind(text=self.part_draft_changed)
        view_actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        view_actions.add_widget(Action("Preview selected part", self.preview))
        view_actions.add_widget(Action("Hide other stocks", self.hide_others))
        self.cancel_stock_preparation = Action("Cancel stock preparation", self.cancel_event.set, disabled=True)
        view_actions.add_widget(self.cancel_stock_preparation)
        self.review_body.add_widget(view_actions)
        simulation = AdaptiveGrid(max_cols=2, min_width=220, row_height=78, spacing=dp(6))
        self.resolution = planning_field(
            simulation, "Voxel size · mm", "1", quantity="length", minimum=0.05, maximum=10
        )
        self.calculate_action = Action("Simulate all stocks", self.simulate)
        self.cancel_action = Action("Cancel calculation", self.cancel_event.set, disabled=True)
        simulation_actions = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(78), spacing=dp(6))
        simulation_actions.add_widget(self.calculate_action)
        simulation_actions.add_widget(self.cancel_action)
        simulation.add_widget(simulation_actions)
        self.review_body.add_widget(simulation)
        playback = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        playback.add_widget(Action("Use declared-WCS playback", self.prepare_playback))
        playback.add_widget(Action("Restore original file playback", self.restore_playback))
        self.review_body.add_widget(playback)
        self.simulation_note = content_label(
            "Uses each program WCS; does not duplicate paths. Declared offsets remain unmeasured."
        )
        self.review_body.add_widget(self.simulation_note)
        file_actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        file_actions.add_widget(Action("Save all rest stocks", self.save_result))
        file_actions.add_widget(Action("Load matching rest stocks", self.load_result))
        self.results_body.add_widget(file_actions)
        self.artifact_status = content_label(
            "Saved results retain occupancy and conservative candidates; detailed contacts are not archived."
        )
        self.results_body.add_widget(self.artifact_status)
        self.note = content_label(self.note.text)
        self.content.add_widget(self.note)
        self.layout_controls = (
            self.rows,
            self.columns,
            self.pitch_x,
            self.pitch_y,
            self.first_wcs,
            self.stock_shape,
            self.offset,
            self.origin,
            self.stock_angles,
        )
        for control in (*self.layout_controls, self.stock_size_field):
            control.bind(text=self.draft_changed)
        self.note.bind(text=lambda *_: self.refresh_plan_status())
        self.show_page("Layout")
        self.refresh_plan_status()

    def draft_changed(self, *_):
        if self.syncing_layout:
            return
        if self.part_drafts and self.plan is not None:
            self.sync_array_fields(self.plan)
            self.refresh_draft_note(self.choice.values.index(self.choice.text))
            self.note.text = "Apply or discard pending part drafts before changing the array layout"
            return
        self.draft_generation += 1
        if self.plan is not None:
            self.cancel_event.set()
            self.result = None
            self.workspace.machine.gcode_viewer.clear_repeat_stock()
            self.plan = None
            self.owner = None
            self.choice.values = ("Build or restore a plan",)
            self.choice.text = self.choice.values[0]
            self.summary.text = "Inputs changed. Build the declared array again before saving or previewing."
            self.refresh_frame_review()
            self.fill_part_editor()

    def refresh_frame_review(self):
        if not hasattr(self, "frame_detail"):
            return
        profile = self.workspace.selected_machine_profile
        signature = (id(self.plan), self.owner, profile.get("id") if profile else None, self.choice.text)
        if signature == self._frame_signature:
            return
        self._frame_signature = signature
        self.fill_part_editor()
        self.refresh_plan_status()
        try:
            plan = self.current_plan()
            index = self.choice.values.index(self.choice.text)
            review = frame_review(plan, index)
        except (ValueError, AttributeError):
            self.frame_detail.text = "Build or restore a plan for the selected machine to review declared frames."
            return

        def xyz(values):
            return ", ".join(f"{value:g}" for value in values)

        low, high = review["bounds_mm"]
        gap = review["nearest_stock_gap_mm"]
        self.frame_detail.text = (
            f"{review['name']} · {review['wcs']} · declared machine XYZ (mm)\n"
            f"Datum: {xyz(review['datum_mm'])}\n"
            f"Stock envelope lower: {xyz(low)}\nStock envelope upper: {xyz(high)}\n"
            f"Stock X/Y/Z angles: {xyz(plan.parts[index].stock_orientation_deg)}° · about center\n"
            + (f"Bounding-envelope gap: {gap:g} mm" if gap is not None else "Single stock · no neighboring part")
            + (
                f"\nImported solid · SHA {plan.parts[index].stock_source.reference['source_sha256'][:12]} · source dimensions locked"
                if plan.parts[index].stock_source is not None
                else "\nRectangular stock"
            )
            + "\nStock separation does not establish cutter/fixture clearance or measured work offsets."
        )

    def sync_array_fields(self, plan):
        draft = grid_draft(plan)
        self.syncing_layout = True
        try:
            for control in self.layout_controls:
                control.disabled = draft is None
            if draft is None:
                self.stock_size_field.disabled = True
                self.layout_note.text = (
                    "Custom frame table · edit individual parts in Review, or explicitly start a new array draft."
                )
                return
            self.array_stock_source = plan.parts[0].stock_source
            self.stock_shape.text = (
                "Current scene solid" if self.array_stock_source is not None else "Rectangular block"
            )
            self.stock_size_field.disabled = self.array_stock_source is not None
            self.rows.text, self.columns.text = str(draft.rows), str(draft.columns)
            self.pitch_x.text, self.pitch_y.text = repr(draft.pitch_mm[0]), repr(draft.pitch_mm[1])
            self.first_wcs.text = draft.first_wcs
            for field, values in (
                (self.offset, draft.work_offset_mm),
                (self.origin, draft.stock_origin_mm),
                (self.stock_size_field, draft.stock_size_mm),
                (self.stock_angles, draft.stock_orientation_deg),
            ):
                field.text = ", ".join(repr(value) for value in values)
            self.layout_note.text = "Array fields describe the loaded geometry. Unused pitch axes default to 60 mm; saved positions are retained."
        finally:
            self.syncing_layout = False

    def new_array(self):
        if self.part_drafts:
            self.note.text = "Apply or discard pending part drafts before starting a new array"
            return
        self.draft_generation += 1
        for control in self.layout_controls:
            control.disabled = False
        self.layout_note.text = (
            "New regular array draft · Build replaces the current declaration with new part names and frames."
        )
        self.array_stock_source = None
        self.stock_shape.text = "Rectangular block"
        self.stock_size_field.disabled = False
        self.show_page("Layout")

    @property
    def part_fields(self):
        return (
            self.part_name,
            self.part_wcs,
            self.part_offset,
            self.part_origin,
            self.part_size,
            self.part_orientation,
        )

    @staticmethod
    def part_text(part):
        return (
            part.name,
            part.wcs,
            *(
                ", ".join(repr(value) for value in values)
                for values in (
                    part.work_offset_mm,
                    part.stock_origin_mm,
                    part.stock_size_mm,
                    part.stock_orientation_deg,
                )
            ),
        )

    def editor_context(self):
        plan = self.current_plan()
        return (id(plan), self.owner, self.profile_id())

    def part_draft_changed(self, *_):
        if self.syncing_editor:
            return
        self.draft_generation += 1
        try:
            context = self.editor_context()
            index = self.choice.values.index(self.choice.text)
        except (ValueError, AttributeError):
            return
        if context != self.part_edit_context:
            return
        values = tuple(field.text for field in self.part_fields)
        if values == self.part_text(self.plan.parts[index]):
            self.part_drafts.pop(index, None)
        else:
            self.part_drafts[index] = values
        self.refresh_draft_note(index)

    def refresh_draft_note(self, index):
        count = len(self.part_drafts)
        self.refresh_plan_status()
        if hasattr(self, "layout_controls"):
            for control in self.layout_controls:
                control.disabled = bool(count) or grid_draft(self.plan) is None
            self.stock_size_field.disabled = (
                bool(count) or grid_draft(self.plan) is None or self.array_stock_source is not None
            )
        self.part_editor.note.text = (
            f"{count} unapplied part draft(s) · "
            + ("this part has pending edits. " if index in self.part_drafts else "this part is reviewed. ")
            + "Drafts stay while selecting parts. Apply validates the declaration; Save retains reviewed values."
            if count
            else "Local declaration only · machine offsets remain untouched. Edits stay while selecting parts."
        )

    def fill_part_editor(self):
        if not hasattr(self, "part_editor"):
            return
        try:
            plan = self.current_plan()
            context = self.editor_context()
            index = self.choice.values.index(self.choice.text)
            part = plan.parts[index]
        except (ValueError, AttributeError):
            self.part_drafts.clear()
            self.part_edit_context = None
            self.part_editor.note.text = "Build or restore a plan for this machine before editing a part."
            self.part_editor.disabled = True
            self.syncing_editor = True
            try:
                for field in self.part_fields:
                    field.text = ""
            finally:
                self.syncing_editor = False
            return
        if context != self.part_edit_context:
            self.part_drafts.clear()
            self.part_edit_context = context
        self.part_editor.disabled = False
        self.part_size.disabled = part.stock_source is not None
        self.syncing_editor = True
        try:
            values = self.part_drafts.get(index, self.part_text(part))
            for field, value in zip(self.part_fields, values):
                field.text = value
            self.refresh_draft_note(index)
        finally:
            self.syncing_editor = False

    def discard_part_draft(self):
        def discard():
            self.current_plan()
            index = self.choice.values.index(self.choice.text)
            self.part_drafts.pop(index, None)
            self.draft_generation += 1
            self.fill_part_editor()

        self.run(discard)

    def discard_all_parts(self):
        def discard():
            self.current_plan()
            self.part_drafts.clear()
            self.draft_generation += 1
            self.fill_part_editor()

        self.run(discard)

    @staticmethod
    def draft_part(values, source=None):
        def vector(text, quantity="length"):
            components = text.split(",")
            if len(components) != 3:
                raise ValueError("Enter three comma-separated coordinates")
            return tuple(parse_quantity(value.strip(), quantity) for value in components)

        name, wcs, offset, origin, size, orientation = values
        return StockInstance(
            name, wcs, vector(offset), vector(origin), vector(size), source, vector(orientation, "angle")
        )

    def publish_part_edits(self, updated, index, pending):
        owner = self.owner
        self.show_plan(updated, owner)
        self.part_edit_context = self.editor_context()
        self.part_drafts = pending
        self.choice.text = self.choice.values[index]
        self.fill_part_editor()
        self.note.text = "Part drafts applied locally; save to retain the reviewed plan for this machine."

    def apply_part(self):
        def apply():
            plan = self.current_plan()
            index = self.choice.values.index(self.choice.text)
            updated = replace_part(
                plan,
                index,
                self.draft_part(tuple(field.text for field in self.part_fields), plan.parts[index].stock_source),
            )
            pending = {key: values for key, values in self.part_drafts.items() if key != index}
            self.publish_part_edits(updated, index, pending)

        self.run(apply)

    def apply_all_parts(self):
        def apply():
            plan = self.current_plan()
            if self.part_edit_context != self.editor_context():
                raise ValueError("Review drafts for the current machine plan first")
            if not self.part_drafts:
                raise ValueError("No unapplied part drafts")
            updated = RepeatPartPlan(
                tuple(
                    self.draft_part(self.part_drafts[index], part.stock_source) if index in self.part_drafts else part
                    for index, part in enumerate(plan.parts)
                )
            )
            index = self.choice.values.index(self.choice.text)
            self.publish_part_edits(updated, index, {})

        self.run(apply)

    def profile_id(self):
        profile = self.workspace.selected_machine_profile
        if not profile or not isinstance(profile.get("id"), str) or not profile["id"].strip():
            raise ValueError("Choose a saved machine profile first")
        return profile["id"]

    def refresh_plan_status(self):
        if not hasattr(self, "persistence_status"):
            return
        profile = self.workspace.selected_machine_profile
        owner = profile.get("id") if profile else None
        receipt = self.plan_io_receipt or {}
        signature = (
            id(self.plan),
            self.owner,
            owner,
            self.io_busy,
            self.plan_io_label,
            len(self.part_drafts),
            self.saved_revisions.get(owner),
            receipt.get("state"),
            receipt.get("owner"),
        )
        if signature == self._plan_status_signature:
            return
        self._plan_status_signature = signature
        current = profile and self.plan is not None and self.owner == owner
        self.save_plan_action.disabled = self.io_busy or not current or bool(self.part_drafts)
        self.restore_plan_action.disabled = self.io_busy or not profile or bool(self.part_drafts)
        if not profile:
            text = "Choose a saved machine profile to retain repeat plans."
        elif self.plan is None or self.owner != owner:
            text = "Array draft · build or restore a reviewed plan for this machine."
        else:
            revision = self.saved_revisions.get(owner)
            saved = revision == plan_revision(self.plan)
            state = (
                "matches last saved/read plan"
                if saved
                else "reviewed changes not saved"
                if revision
                else "not compared with saved file"
            )
            text = f"{len(self.plan.parts)} declared parts · {state}."
            if self.part_drafts:
                text += f" {len(self.part_drafts)} pending edit(s): apply or discard before Save."
        if self.io_busy:
            text += f" {self.plan_io_label} in background; navigation remains available."
        elif receipt.get("state") == "failed":
            text += " Last file operation failed; details below."
        elif receipt.get("state") == "not applied":
            text += " Last restore was not applied because its context changed."
        self.persistence_status.text = text

    @staticmethod
    def triple(field, quantity="length"):
        values = field.text.split(",")
        if len(values) != 3:
            raise ValueError("Enter three comma-separated coordinates")
        return tuple(parse_quantity(value.strip(), quantity) for value in values)

    def run(self, action):
        try:
            action()
        except (ValueError, OSError, TypeError, KeyError) as exc:
            self.note.text = str(exc)

    def choose_stock_shape(self, *_):
        if self.syncing_layout:
            return
        if self.part_drafts:
            self.sync_array_fields(self.current_plan())
            self.note.text = "Apply or discard pending part drafts before changing stock shape"
            return
        if self.stock_shape.text == "Rectangular block":
            self.array_stock_source = None
            self.stock_size_field.disabled = False
            return
        model = self.workspace.machine.gcode_viewer.machine_setup.stock_model
        if model is None:
            self.syncing_layout = True
            self.stock_shape.text = "Rectangular block"
            self.syncing_layout = False
            self.note.text = "Import a solid in Scene first, then choose Current scene solid"
            return
        self.array_stock_source = StockSource.from_model(model)
        self.stock_size_field.text = ", ".join(repr(v) for v in model.size_mm)
        self.stock_size_field.disabled = True
        self.note.text = f"Exact source {model.source_sha256[:12]} · {model.source_units}; source dimensions locked"

    def seed(self):
        def apply():
            self.require_array_draft()
            setup = self.workspace.machine.gcode_viewer.machine_setup
            if setup.stock_size_mm is None:
                raise ValueError("Declare stock dimensions in Scene first")
            for field, values in (
                (self.offset, setup.work_offset_mm),
                (self.origin, setup.stock_origin_mm),
                (self.stock_size_field, setup.stock_size_mm),
                (self.stock_angles, setup.stock_orientation.degrees),
            ):
                field.text = ", ".join(repr(value) for value in values)
            self.stock_shape.text = "Current scene solid" if setup.stock_model is not None else "Rectangular block"
            self.choose_stock_shape()
            self.note.text = "Copied scene stock source and dimensions. Build the array to review declared frames."

        self.run(apply)

    def show_plan(self, plan, owner):
        self.draft_generation += 1
        if self.calculating:
            self.cancel_event.set()
        self.workspace.machine.gcode_viewer.clear_repeat_stock()
        self.result = None
        self.part_drafts.clear()
        self.part_edit_context = None
        self.plan, self.owner = plan, owner
        self.sync_array_fields(plan)
        self.choice.values = tuple(f"{p.name} · {p.wcs}" for p in plan.parts)
        self.choice.text = self.choice.values[0]
        self.show_page("Review")
        self.refresh_frame_review()
        self.summary.text = "\n".join(
            f"{p.name} · {p.wcs} · datum " + ", ".join(f"{v:g}" for v in p.work_offset_mm) for p in plan.parts
        )

    def require_array_draft(self):
        if self.part_drafts:
            raise ValueError("Apply or discard pending part drafts before replacing the reviewed array")
        if any(control.disabled for control in self.layout_controls):
            raise ValueError("Custom frame table retained. Start a new array draft before rebuilding it.")

    def generate(self):
        def apply():
            self.require_array_draft()
            owner = self.profile_id()
            plan = RepeatPartPlan.grid(
                int(self.rows.value()),
                int(self.columns.value()),
                (self.pitch_x.value(), self.pitch_y.value(), 0),
                self.triple(self.offset),
                self.triple(self.origin),
                self.triple(self.stock_size_field),
                self.first_wcs.text,
                self.array_stock_source,
                self.triple(self.stock_angles, "angle"),
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

    def plan_io(self, owner, work, apply, operation_label="Working with plan file"):
        if self.io_busy:
            self.note.text = "A plan-file operation is already running; navigation remains available."
            return
        self.io_busy = True
        self.plan_io_label = operation_label
        self.io_generation += 1
        operation = self.io_generation
        generation = self.draft_generation
        self.save_plan_action.disabled = self.restore_plan_action.disabled = True
        self.note.text = f"{operation_label} in the background…"

        def finish(value, error):
            if self.closed or operation != self.io_generation:
                return
            self.io_busy = False
            self.cancel_stock_preparation.disabled = True
            self.save_plan_action.disabled = self.restore_plan_action.disabled = False
            self.plan_io_receipt = {
                "owner": owner,
                "operation": operation,
                "error": error,
                "state": "failed" if error else "completed",
            }
            if error:
                self.note.text = error
                return
            apply(value, generation)
            self.refresh_plan_status()

        def worker():
            try:
                value, error = work(), None
            except Exception as exc:
                value, error = None, f"Plan-file operation failed: {exc}"
            Clock.schedule_once(lambda _dt: finish(value, error), 0)

        try:
            threading.Thread(target=worker, name="repeat-plan-file", daemon=True).start()
        except RuntimeError as exc:
            finish(None, str(exc))

    def save(self):
        try:
            owner = self.profile_id()
            plan = self.current_plan()
            if self.part_drafts:
                raise ValueError("Apply or discard pending part drafts before saving the reviewed plan")
            revision = self.saved_revisions.get(owner)
            store = self.store
        except (ValueError, OSError) as exc:
            self.note.text = str(exc)
            return

        def complete(saved_revision, _generation):
            self.saved_revisions[owner] = saved_revision
            self.plan_io_receipt.update(state="saved", revision=saved_revision)
            # The authorized snapshot was saved for its original owner, even if
            # the operator changed their current viewing context meanwhile.
            profile = self.workspace.selected_machine_profile
            if profile and profile.get("id") == owner and self.plan == plan:
                self.note.text = "Saved declared stock instances for this machine. No machine offsets were written."
            else:
                self.note.text = "Plan snapshot saved for its original machine; current draft was retained."

        self.plan_io(owner, lambda: store.save(owner, plan, revision), complete, "Saving plan")

    def restore(self):
        try:
            owner = self.profile_id()
            if self.part_drafts:
                raise ValueError("Apply or discard pending part drafts before restoring another plan")
            store = self.store
        except ValueError as exc:
            self.note.text = str(exc)
            return

        def read():
            plan = store.load(owner)
            if plan is None:
                raise ValueError("This machine has no saved repeat-part plan")
            return plan

        def complete(plan, generation):
            profile = self.workspace.selected_machine_profile
            if not profile or profile.get("id") != owner or self.draft_generation != generation:
                self.plan_io_receipt.update(state="not applied", reason="Machine or draft changed during restore")
                self.note.text = "Saved plan read but not applied: machine or draft changed. Restore again when ready."
                return
            self.saved_revisions[owner] = plan_revision(plan)
            self.show_plan(plan, owner)
            self.plan_io_receipt.update(state="restored", revision=self.saved_revisions[owner])
            self.note.text = "Restored declared plan. Select a part for local preview."

        self.plan_io(owner, read, complete, "Reading saved plan")

    def preview(self):
        def apply():
            plan = self.current_plan()
            if any(p.stock_source is not None for p in plan.parts) or (
                self.result is not None and self.result_context == self.result_signature()
            ):
                self.prepare_stock_preview(plan)
                return
            self.publish_stock_preview(plan)

        self.run(apply)

    def prepare_stock_preview(self, plan):
        if self.io_busy:
            self.note.text = "Stock or plan-file preparation is already running; navigation remains available"
            return
        self.check_preview_state()
        owner = self.profile_id()
        index = self.choice.values.index(self.choice.text)
        selection = self.choice.text
        self.cancel_event.clear()
        self.cancel_stock_preparation.disabled = False
        viewer = self.workspace.machine.gcode_viewer
        original_setup = viewer.machine_setup
        scale = viewer.move_scale_by_positon or 1
        result = self.result if self.result is not None and self.result_context == self.result_signature() else None

        def prepare():
            prepared = plan.prepared(scale=scale, selected_index=index, cancelled=self.cancel_event.is_set)
            display = (
                RepeatStockDisplay.prepare(
                    prepared, index, result.geometries, scale, cancelled=self.cancel_event.is_set
                )
                if result is not None
                else None
            )
            return prepared, display

        def complete(prepared, generation):
            if (
                (self.workspace.selected_machine_profile or {}).get("id") != owner
                or self.plan != plan
                or self.draft_generation != generation
                or self.choice.text != selection
                or viewer.machine_setup != original_setup
                or (viewer.move_scale_by_positon or 1) != scale
                or (result is not None and self.result is not result)
            ):
                self.note.text = "Stock preparation completed for an older selection; previous scene retained"
                return
            self.publish_stock_preview(prepared[0], prepared[1])

        self.plan_io(
            owner,
            prepare,
            complete,
            "Preparing array stock display",
        )

    def publish_stock_preview(self, plan, prepared_display=None):
        def apply():
            ws = self.workspace
            self.check_preview_state()
            index = self.choice.values.index(self.choice.text)
            part = plan.parts[index]
            preserved = (
                (prepared_display if prepared_display is not None else self.result.geometries)
                if (self.result is not None and self.result_context == self.result_signature())
                else None
            )
            ws.set_pose_mode("Preview")
            ws.machine.gcode_viewer.configure_machine(
                work_offset_mm=part.work_offset_mm,
                stock_origin_mm=part.stock_origin_mm,
                stock_size_mm=part.stock_size_mm,
                stock_rotation_deg=part.stock_orientation_deg[2],
                stock_tilt_deg=part.stock_orientation_deg[:2],
                stock_model=plan.setup(part).stock_model,
                alignment_confirmed=False,
                repeat_plan=plan,
                repeat_index=index,
                repeat_rest_geometries=preserved,
            )
            if preserved is not None:
                self.result = replace(self.result, geometries=preserved)
            if preserved is None:
                self.result = None
                self.summary.text = "\n".join(
                    f"{p.name} · {p.wcs} · datum " + ", ".join(f"{v:g}" for v in p.work_offset_mm) for p in plan.parts
                )
            ws.simulation_geometry = {
                "offset": part.work_offset_mm,
                "origin": part.stock_origin_mm,
                "size": part.stock_size_mm,
                "rotation_deg": part.stock_orientation_deg[2],
                "tilt_deg": part.stock_orientation_deg[:2],
            }
            if part.stock_source is not None:
                ws.simulation_geometry["stock_source"] = part.stock_source.reference
            self.refresh_preview_note(preserved is not None)

        self.run(apply)

    def refresh_preview_note(self, computed=None):
        viewer = self.workspace.machine.gcode_viewer
        plan = viewer.repeat_stock_plan
        if plan is None:
            return
        part = plan.parts[viewer.repeat_stock_index]
        if computed is None:
            computed = self.result is not None and self.result_context == self.result_signature()
        self.note.text = (
            f"Computed rest stocks retained; {part.name} · {part.wcs} is active. " + self.playback_status()
            if computed
            else f"{len(plan.parts)} declared stocks shown. {part.name} · {part.wcs} is active (gold); "
            "other stocks are nominal (blue). Use Simulate all stocks for declared-WCS removal. "
            + self.playback_status()
            + " Standard simulation applies only to the active stock."
        )

    def hide_others(self):
        self.workspace.machine.gcode_viewer.clear_repeat_stock()
        self.note.text = "Other instances hidden. Active stock and its simulation remain unchanged."

    def show_page(self, name):
        self.page = name
        for page, action in self.tab_actions.items():
            action.base_color = ACCENT if page == name else RAISED
            action.color = BG if page == name else TEXT
            action._paint()
        for body in (self.layout_body, self.review_body, self.results_body):
            if body.parent is self.content:
                self.content.remove_widget(body)
        self.content.add_widget(
            {"Layout": self.layout_body, "Review": self.review_body, "Results": self.results_body}[name], index=1
        )
        if self.expanded:
            Clock.schedule_once(lambda _dt: Clock.schedule_once(self.reveal_review, 0), 0)

    def reveal_review(self, *_):
        if self.workspace.active_section == "Setup" and self.expanded:
            self._reveal_heading(0)

    def check_preview_state(self):
        if self.calculating:
            raise ValueError("Finish or cancel the array calculation before changing preview setup")
        if self.io_busy:
            raise ValueError("Finish or cancel array stock preparation before changing preview setup")
        ws = self.workspace
        if ws.app.playing or ws.app.state not in ("Idle", "N/A"):
            raise ValueError("Stop playback and wait for an idle machine before changing preview setup")
        record = ws.run_recording_panel
        if record.busy or record.previous_scene is not None or ws.machine_profile_loading:
            raise ValueError("Return from recorded setup and finish profile loading before changing preview")
        if ws.simulation_panel.running:
            raise ValueError("Finish the active-stock calculation before changing the array preview")

    def result_signature(self):
        # Selected active instance does not alter the machine-space calculation.
        return tuple(value for index, value in enumerate(self.calculation_identity()) if index not in (4, 5, 6))

    def archive_context(self):
        context = capture_context(
            self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program, verify_assets=False
        )
        plan = self.current_plan()
        # Active-part selection is a viewing choice, not a different machine-space result.
        context.pop("stock")
        context.pop("work_offset_mm")
        context.update(
            repeat_plan=plan.to_dict(), machine_profile_id=self.profile_id(), resolution_mm=self.resolution.value()
        )
        return context

    def save_result(self):
        if self.result is None or self.result_context != self.result_signature() or not self.result_archive_context:
            self.artifact_status.text = "Calculate current array results before saving."
            return
        self.workspace.choose_profile_file(
            lambda path: self.exchange_result(path, True),
            save=True,
            extension=".cvstocks",
            title="Save all rest stocks",
        )

    def load_result(self):
        self.workspace.choose_asset_file(lambda path: self.exchange_result(path, False), suffixes=(".cvstocks",))

    def exchange_result(self, path, saving):
        try:
            self.check_preview_state()
            context = self.archive_context()
            viewer = self.workspace.machine.gcode_viewer
            plan = viewer.repeat_stock_plan
            selected_index = viewer.repeat_stock_index
            scale = viewer.move_scale_by_positon or 1
            if viewer.repeat_stock_plan != self.current_plan():
                raise ValueError("Preview this array before exchanging its results")
            identity = self.calculation_identity()
            program = self.workspace.operation_panel.program
            if program is None:
                raise ValueError("Choose a parsed local program first")
            result = self.result
            if saving and (
                result is None
                or self.result_context != self.result_signature()
                or digest_context(context) != digest_context(self.result_archive_context)
            ):
                raise ValueError("Result inputs changed; recompute before saving")
        except (ValueError, TypeError, OSError) as exc:
            self.artifact_status.text = str(exc)
            return
        self.cancel_event.clear()
        self.calculating = True
        self.calculate_action.disabled, self.cancel_action.disabled = True, False
        self.artifact_status.text = "Saving all rest stocks…" if saving else "Validating all rest stocks…"

        def worker():
            try:
                if saving:
                    save_repeat_result(path, result, context, cancelled=self.cancel_event.is_set)
                    restored = None
                else:
                    restored = load_repeat_result(path, program, context, cancelled=self.cancel_event.is_set)
                    restored = replace(
                        restored,
                        geometries=RepeatStockDisplay.prepare(
                            plan, selected_index, restored.geometries, scale, cancelled=self.cancel_event.is_set
                        ),
                    )
                error = None
            except (OSError, ValueError, TypeError, KeyError, ArithmeticError, InterruptedError) as exc:
                restored, error = None, str(exc)
            except Exception as exc:
                Logger.exception("RepeatParts: Unexpected array exchange failure")
                restored, error = None, f"Array exchange failed: {exc}"
            Clock.schedule_once(lambda _dt: finish(restored, error), 0)

        def finish(restored, error):
            self.calculating = False
            if self.closed:
                return
            self.calculate_action.disabled, self.cancel_action.disabled = False, True
            try:
                if identity != self.calculation_identity() or self.cancel_event.is_set():
                    raise ValueError(
                        "Context changed or cancelled; displayed results retained"
                        + (". File contains the captured inputs." if saving and error is None else "")
                    )
                if error:
                    raise ValueError(error)
                self.check_preview_state()
                if not saving:
                    viewer.set_repeat_rest_geometries(restored.plan, restored.geometries)
                    self.result, self.result_context = restored, self.result_signature()
                    self.result_archive_context = context
                    self.summary.text = "\n".join(
                        f"{part.name} · {part.wcs}: {report.remaining_volume_mm3:g} mm³ left · {report.removed_volume_mm3:g} mm³ removed\n{len(report.candidates)} retained conservative collision candidates; detailed contacts unavailable"
                        for part, report in zip(restored.plan.parts, restored.reports)
                    )
                    self.refresh_preview_note(True)
                self.artifact_status.text = (
                    ("Saved" if saving else "Loaded")
                    + " all rest stocks · "
                    + str(path)
                    + " · physical setup unqualified"
                )
            except (ValueError, TypeError, OSError) as exc:
                self.artifact_status.text = str(exc)

        threading.Thread(target=worker, daemon=True).start()

    def calculation_identity(self):
        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        program = ws.operation_panel.program
        return (
            id(program),
            program.file_hash if program else None,
            self.profile_id(),
            self.plan,
            viewer.repeat_stock_plan,
            viewer.repeat_stock_index,
            viewer.machine_setup,
            id(viewer.machine_profile),
            tuple((key, id(value)) for key, value in viewer.machine_component_profiles.items()),
            viewer.workholding_offset_mm,
            viewer.workholding_rotation_deg,
            viewer.jaw_offset_mm,
            tuple((key, repr(value)) for key, value in sorted(viewer.library_tool_table_mm.items())),
            self.resolution.text,
            viewer.move_scale_by_positon,
        )

    def restore_playback(self):
        def apply():
            self.check_preview_state()
            self.workspace.machine.gcode_viewer.restore_file_playback()
            self.workspace.operation_panel.refresh_path_highlight()
            self.refresh_preview_note()
            self.simulation_note.text = "Original loaded-file playback restored; stock results retained."

        self.run(apply)

    def playback_status(self):
        return (
            "Declared-WCS playback is active."
            if self.workspace.machine.gcode_viewer.declared_playback is not None
            else "Toolpath playback still uses a single frame."
        )

    def prepare_playback(self):
        try:
            self.check_preview_state()
            plan = self.current_plan()
            ws = self.workspace
            viewer = ws.machine.gcode_viewer
            program = ws.operation_panel.program
            if program is None or program.file_hash != viewer.loaded_program_hash:
                raise ValueError("Wait for the same local program to finish loading")
            if viewer.repeat_stock_plan != plan:
                raise ValueError("Preview this array before preparing playback")
            identity = self.calculation_identity()
        except (ValueError, TypeError, OSError) as exc:
            self.simulation_note.text = str(exc)
            return
        self.cancel_event.clear()
        self.calculating = True
        self.calculate_action.disabled, self.cancel_action.disabled = True, False
        self.simulation_note.text = "Preparing declared-frame toolpath playback…"

        def worker():
            try:
                playback, error = prepare_repeat_playback(program, plan, cancelled=self.cancel_event.is_set), None
            except (ValueError, ArithmeticError, InterruptedError) as exc:
                playback, error = None, str(exc)
            except Exception as exc:
                Logger.exception("RepeatParts: Unexpected array playback failure")
                playback, error = None, f"Array playback failed: {exc}"
            Clock.schedule_once(lambda _dt: finish(playback, error), 0)

        def finish(playback, error):
            self.calculating = False
            if self.closed:
                return
            self.calculate_action.disabled, self.cancel_action.disabled = False, True
            try:
                if error:
                    raise ValueError(error)
                if self.cancel_event.is_set() or identity != self.calculation_identity():
                    raise ValueError("Playback cancelled or context changed; previous path retained")
                self.check_preview_state()
                ws.set_pose_mode("Preview")
                viewer.set_declared_playback(playback)
                ws.machine.gcode_viewer_distance = viewer.get_total_distance()
                ws.operation_panel.refresh_path_highlight()
                self.refresh_preview_note()
                self.simulation_note.text = (
                    f"Declared-WCS path and cutter playback active · {len(playback.unresolved_lines)} "
                    "unresolved source lines excluded. Offsets are local declarations, not measurements."
                )
            except (ValueError, TypeError, OSError) as exc:
                self.simulation_note.text = str(exc)

        threading.Thread(target=worker, daemon=True).start()

    def simulate(self):
        if self.calculating:
            self.simulation_note.text = "Array calculation is already running."
            return
        try:
            plan = self.current_plan()
            self.check_preview_state()
            viewer = self.workspace.machine.gcode_viewer
            if viewer.repeat_stock_plan != plan:
                raise ValueError("Preview this array before calculating stock removal")
            program = self.workspace.operation_panel.program
            if program is None:
                raise ValueError("Choose a parsed local program first")
            resolution = self.resolution.value()
            definitions = {key: replace(value) for key, value in viewer.library_tool_table_mm.items()}
            geometry = viewer._machine_scene()
            identity = self.calculation_identity()
            archive_context = self.archive_context()
            selected_index = viewer.repeat_stock_index
            scale = viewer.move_scale_by_positon or 1
        except (ValueError, TypeError, OSError) as exc:
            self.simulation_note.text = str(exc)
            return
        self.cancel_event.clear()
        self.calculating = True
        self.calculate_action.disabled, self.cancel_action.disabled = True, False
        self.simulation_note.text = "Resolving declared WCS and calculating all stocks…"

        def run():
            try:
                verify_assets(archive_context, cancelled=self.cancel_event.is_set)
                result = simulate_repeat_parts(
                    program, plan, definitions, geometry, resolution, cancelled=self.cancel_event.is_set
                )
                result = replace(
                    result,
                    geometries=RepeatStockDisplay.prepare(
                        plan, selected_index, result.geometries, scale, cancelled=self.cancel_event.is_set
                    ),
                )
                error = None
            except (ValueError, ArithmeticError, OSError, InterruptedError) as exc:
                result, error = None, str(exc)
            except Exception as exc:
                Logger.exception("RepeatParts: Unexpected array calculation failure")
                result, error = None, f"Array calculation failed: {exc}"
            Clock.schedule_once(lambda _dt: finish(result, error), 0)

        def finish(result, error):
            self.calculating = False
            if self.closed:
                return
            self.calculate_action.disabled, self.cancel_action.disabled = False, True
            try:
                if error:
                    raise ValueError(error)
                if self.cancel_event.is_set():
                    raise ValueError("Array calculation cancelled; previous scene retained")
                if self.calculation_identity() != identity or viewer.parent is None:
                    raise ValueError("Setup/program/tools changed; array result was not applied")
                self.check_preview_state()
                viewer.set_repeat_rest_geometries(plan, result.geometries)
                self.result = result
                self.result_context = self.result_signature()
                self.result_archive_context = archive_context
                lines = []
                for part, report in zip(plan.parts, result.reports):
                    contacts = sorted({line for line, *_ in report.candidates})
                    contact_summary = (
                        f"{len(report.candidates)} collision candidates · lines "
                        + ", ".join(str(line) for line in contacts[:6])
                        + ("…" if len(contacts) > 6 else "")
                        if contacts
                        else "No conservative collision candidates; clearance remains unqualified"
                    )
                    lines.append(
                        f"{part.name} · {part.wcs}: removed {report.removed_volume_mm3:g} mm³ / "
                        f"{report.remaining_volume_mm3:g} mm³ left\n{contact_summary}"
                    )
                self.summary.text = "\n".join(lines)
                excluded = ", ".join(str(line) for line in result.unresolved_lines[:12])
                if len(result.unresolved_lines) > 12:
                    excluded += "…"
                self.simulation_note.text = (
                    f"Computed declared-frame preview · {len(result.segments)} segments · "
                    f"{len(result.unresolved_lines)} unresolved lines excluded"
                    + (f" ({excluded})" if excluded else "")
                    + ". Approximate voxels; physical registration/clearance unqualified. "
                    + self.playback_status()
                )
                self.refresh_preview_note(True)
                if self.workspace.active_section == "Setup" and self.page == "Review":
                    self.show_page("Results")
            except (ValueError, TypeError, OSError) as exc:
                self.simulation_note.text = str(exc)
            Clock.schedule_once(self.reveal_review, 0)

        threading.Thread(target=run, daemon=True).start()
