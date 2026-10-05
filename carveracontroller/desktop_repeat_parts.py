"""Repeat-part planning with explicit declared frames and local preview only."""

import threading
from dataclasses import replace

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import MUTED, Action, AdaptiveGrid, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_planning import PlanningCard, planning_choice, planning_field
from carveracontroller.machine.geometry_changes import capture_context, digest_context
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.repeat_archive import load_repeat_result, save_repeat_result, verify_assets
from carveracontroller.machine.repeat_parts import WCS_NAMES, RepeatPartPlan, RepeatPartStore
from carveracontroller.machine.repeat_playback import prepare_repeat_playback
from carveracontroller.machine.repeat_simulation import simulate_repeat_parts


class RepeatPartsPanel(PlanningCard):
    def __init__(self, workspace, **kwargs):
        super().__init__("Repeat parts & work offsets", **kwargs)
        self.workspace = workspace
        self.store = RepeatPartStore()
        self.plan = None
        self.owner = None
        self.closed = False
        self.calculating = False
        self.cancel_event = threading.Event()
        self.result = None
        self.result_archive_context = None
        self.page = "Layout"
        self.tabs = AdaptiveGrid(max_cols=3, min_width=120, row_height=34, spacing=dp(6))
        self.tabs.add_widget(Action("Array layout", lambda: self.show_page("Layout")))
        self.tabs.add_widget(Action("Review & simulate", lambda: self.show_page("Review")))
        self.tabs.add_widget(Action("Results & files", lambda: self.show_page("Results")))
        self.content.add_widget(self.tabs)
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
        self.layout_body.add_widget(fields)
        vectors = AdaptiveGrid(max_cols=3, min_width=145, row_height=62, spacing=dp(6))
        self.offset = planning_field(vectors, "First datum · machine XYZ", "-180, -120, -110")
        self.origin = planning_field(vectors, "Stock origin · local XYZ", "0, 0, -10")
        self.stock_size_field = planning_field(vectors, "Each stock size · XYZ", "40, 40, 10")
        self.layout_body.add_widget(vectors)
        actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        for title, callback in (
            ("Use current scene dimensions", self.seed),
            ("Build declared array", self.generate),
            ("Save machine plan", self.save),
            ("Restore machine plan", self.restore),
        ):
            actions.add_widget(Action(title, callback))
        self.layout_body.add_widget(actions)
        self.summary = content_label("No repeat-part plan loaded.")
        self.results_body.add_widget(self.summary)
        self.choice = planning_choice(self.review_body, "Selected part", ("Build or restore a plan",))
        view_actions = AdaptiveGrid(max_cols=2, min_width=180, row_height=36, spacing=dp(6))
        view_actions.add_widget(Action("Preview selected part", self.preview))
        view_actions.add_widget(Action("Hide other stocks", self.hide_others))
        self.review_body.add_widget(view_actions)
        simulation = AdaptiveGrid(max_cols=3, min_width=145, row_height=62, spacing=dp(6))
        self.resolution = planning_field(
            simulation, "Voxel size · mm", "1", quantity="length", minimum=0.05, maximum=10
        )
        self.calculate_action = Action("Simulate all stocks", self.simulate)
        self.cancel_action = Action("Cancel calculation", self.cancel_event.set, disabled=True)
        simulation.add_widget(self.calculate_action)
        simulation.add_widget(self.cancel_action)
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
        self.show_page("Layout")

    def draft_changed(self, *_):
        if self.plan is not None:
            self.cancel_event.set()
            self.result = None
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
        if self.calculating:
            self.cancel_event.set()
        self.workspace.machine.gcode_viewer.clear_repeat_stock()
        self.result = None
        self.plan, self.owner = plan, owner
        self.choice.values = tuple(f"{p.name} · {p.wcs}" for p in plan.parts)
        self.choice.text = self.choice.values[0]
        self.show_page("Review")
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
            self.check_preview_state()
            index = self.choice.values.index(self.choice.text)
            part = plan.parts[index]
            preserved = (
                self.result.geometries
                if (self.result is not None and self.result_context == self.result_signature())
                else None
            )
            ws.set_pose_mode("Preview")
            ws.machine.gcode_viewer.configure_machine(
                work_offset_mm=part.work_offset_mm,
                stock_origin_mm=part.stock_origin_mm,
                stock_size_mm=part.stock_size_mm,
                alignment_confirmed=False,
                repeat_plan=plan,
                repeat_index=index,
                repeat_rest_geometries=preserved,
            )
            if preserved is None:
                self.result = None
                self.summary.text = "\n".join(
                    f"{p.name} · {p.wcs} · datum " + ", ".join(f"{v:g}" for v in p.work_offset_mm) for p in plan.parts
                )
            ws.simulation_geometry = {
                "offset": part.work_offset_mm,
                "origin": part.stock_origin_mm,
                "size": part.stock_size_mm,
                "rotation_deg": 0,
            }
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
                error = None
            except (OSError, ValueError, TypeError, KeyError, ArithmeticError, InterruptedError) as exc:
                restored, error = None, str(exc)
            Clock.schedule_once(lambda _dt: finish(restored, error), 0)

        def finish(restored, error):
            self.calculating = False
            if self.closed:
                return
            self.calculate_action.disabled, self.cancel_action.disabled = False, True
            try:
                if error:
                    raise ValueError(error)
                if identity != self.calculation_identity() or self.cancel_event.is_set():
                    raise ValueError(
                        "Context changed or cancelled; displayed results retained"
                        + (". File contains the captured inputs." if saving else "")
                    )
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
        except (ValueError, TypeError, OSError) as exc:
            self.simulation_note.text = str(exc)
            return
        self.cancel_event.clear()
        self.calculating = True
        self.calculate_action.disabled, self.cancel_action.disabled = True, False
        self.simulation_note.text = "Resolving declared WCS and calculating all stocks…"

        def run():
            try:
                verify_assets(archive_context)
                result = simulate_repeat_parts(
                    program, plan, definitions, geometry, resolution, cancelled=self.cancel_event.is_set
                )
                error = None
            except (ValueError, ArithmeticError, OSError, InterruptedError) as exc:
                result, error = None, str(exc)
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
