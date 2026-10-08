"""Workbench simulation: real stock evolution with explicit approximation limits."""

import threading
from dataclasses import replace

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3, simulate
from carveracontroller.addons.manufacturing_simulation.clearance import analyze_clearance
from carveracontroller.desktop_clearance import ClearanceCandidates, ClearanceCard
from carveracontroller.desktop_clearance_navigation import ClearanceNavigation
from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.geometry_changes import (
    affected_operations,
    asset_problems,
    capture_context,
    context_changes,
    digest_context,
    verify_context_assets,
)
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.simulation_preview import (
    collision_geometry,
    scene_from_geometry,
    simulation_segments,
    simulation_tool_issues,
    simulation_tools,
    stock_geometry,
    stock_path_review,
)


class SimulationPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.cancel_event = threading.Event()
        self.cancel_requests = 0
        self.running = False
        self.rest_stock = None
        self.report = None
        self.rest_identity = None
        self.rest_context = None
        self.clearance_inputs = None
        self.clearance_identity = None
        self.clearance_context = None
        self.clearance_stale = False
        self.details_open = False
        self.clearance_inspector = None
        self.clearance_remedies = None
        self.clearance_return = None
        self.clearance_motion_action = None
        self.change_review = None
        self.artifact_transfer = None
        self.clearance_navigation = ClearanceNavigation(self)
        self.details_header = Action("+  Material removal & clearance", self.toggle_details, height=dp(34))
        header = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        header.add_widget(self.details_header)
        self.cancel_action = Action("Cancel", self.cancel_calculation, size_hint_x=None, width=dp(72), disabled=True)
        header.add_widget(self.cancel_action)
        self.add_widget(header)
        self.content = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.tool_readiness = content_label()
        self.content.add_widget(self.tool_readiness)
        self.tool_remedies = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.tool_remedies.bind(minimum_height=self.tool_remedies.setter("height"))
        self.content.add_widget(self.tool_remedies)
        self._tool_issue_signature = None
        self._tool_readiness_key = None
        self._tool_issues = ()
        self._alignment_key = None
        self.alignment_status = content_label()
        self.content.add_widget(self.alignment_status)
        self.review_stock_action = Action(
            "Review stock placement & work offset", lambda: self.workspace._machine_setup(), height=dp(32)
        )
        self.content.add_widget(self.review_stock_action)
        options = AdaptiveGrid(max_cols=3, min_width=150, row_height=60, spacing=dp(6))
        self.stock_source = Choice(text="Initial stock", values=("Initial stock", "Continue rest stock"))
        self.resolution = Field(text="2", hint_text="Voxel resolution · mm")
        self.clearance_tolerance = Field(text="0.05", hint_text="Maximum numerical error · mm")
        for title, control in (
            ("Stock basis", self.stock_source),
            ("Stock grid · mm", self.resolution),
            ("Numerical error · mm", self.clearance_tolerance),
        ):
            field = BoxLayout(orientation="vertical", spacing=dp(3))
            field.add_widget(label(title, 11, MUTED, 20))
            field.add_widget(control)
            options.add_widget(field)
        self.content.add_widget(options)
        self.toolbar = AdaptiveGrid(max_cols=4, min_width=115, row_height=34, spacing=dp(6))
        self.scope = Choice(text="Whole program", values=("Whole program", "Selected operation"))
        self.scope.bind(text=lambda *_: self.refresh_controls())
        self.simulate_action = Action(
            "Simulate", lambda: self.start(self.scope.text == "Selected operation"), primary=True
        )
        self.clearance_action = Action("Clearance plot", self.review_clearance)
        self.menu_actions = {
            "Review change impact": self.review_changes,
            "Review clearance inputs": lambda: self.review_changes("clearance"),
            "Show initial stock": self.reset_display,
            "Save rest stock": self.save_stock,
            "Load rest stock": self.load_stock,
        }
        self.more = Choice(text="More actions…", values=tuple(self.menu_actions))
        self.more.bind(text=self._menu_selected)
        for control in (self.scope, self.simulate_action, self.clearance_action, self.more):
            self.toolbar.add_widget(control)
        self.content.add_widget(self.toolbar)
        self.selection_note = content_label("Whole program · choose a program to calculate.")
        self.content.add_widget(self.selection_note)
        self.input_status = content_label(
            "No residual baseline · CAD bytes are checked when calculating, reviewing or saving."
        )
        self.content.add_widget(self.input_status)
        self._input_signature = None
        self.note = content_label(
            "Body clearance uses remaining-stock cell boxes before each motion cuts. Removal classifies voxel centers; stock-grid error is separate from numerical clearance error. Fixture/vise bounds and physical geometry remain unqualified.",
        )
        self.content.add_widget(self.note)
        self.artifact_status = content_label()
        self.content.add_widget(self.artifact_status)
        self.clearance_card = ClearanceCard(
            self.seek_clearance, on_selected=self.select_clearance, on_source=self.reveal_clearance_source
        )
        navigation = BoxLayout(size_hint_y=None, spacing=dp(6))
        navigation.bind(minimum_height=navigation.setter("height"))
        self.navigation_status = content_label()
        self.navigation_cancel = Action(
            "Cancel check",
            self.clearance_navigation.cancel,
            size_hint_x=None,
            width=dp(110),
            height=dp(36),
            disabled=True,
        )
        navigation.add_widget(self.navigation_status)
        navigation.add_widget(self.navigation_cancel)
        self.content.add_widget(navigation)
        self.hits = ClearanceCandidates(self.inspect_clearance)
        self.refresh_controls()

    def _menu_selected(self, _widget, value):
        action = self.menu_actions.get(value)
        if action:
            self.more.text = "More actions…"
            if not self.running:
                action()

    def cancel_calculation(self):
        self.cancel_requests += 1
        self.cancel_event.set()

    def _definition_identity(self):
        context = capture_context(
            self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program, verify_assets=False
        )
        return context["program"], digest_context(context)

    def refresh_controls(self):
        program = self.workspace.operation_panel.program
        operation = self.workspace.operation_panel.selected_operation
        selected = self.scope.text == "Selected operation"
        busy = self.running or (self.artifact_transfer is not None and self.artifact_transfer.active)
        self.simulate_action.disabled = busy or program is None or (selected and operation is None)
        self.clearance_action.disabled = busy or self.clearance_inputs is None or self.clearance_stale
        self.cancel_action.disabled = not self.running
        self.more.disabled = self.scope.disabled = busy
        self.simulate_action.text = "Calculating…" if self.running else "Simulate"
        self.selection_note.text = (
            (
                f"Selected: {operation.name} · lines {operation.start_line}–{operation.end_line}"
                if operation
                else "No operation selected · select one in Operations."
            )
            if selected
            else (
                f"Whole program · {len(program.operations)} operations"
                if program
                else "Whole program · choose a program to calculate."
            )
        )
        issues = self.refresh_tool_readiness(program, operation if selected else None)
        self.simulate_action.disabled = self.simulate_action.disabled or bool(issues)
        self.refresh_stock_alignment(program, operation if selected else None, issues)
        point = self.clearance_card.plot.selected if hasattr(self, "clearance_card") else None
        if point and not self.running:
            self.selection_note.text += (
                f"\nClearance: line {point.line} · T{point.tool_id} · {point.component} near {point.obstacle}"
            )

    def refresh_tool_readiness(self, program, operation=None):
        definitions = self.workspace.machine.gcode_viewer.library_tool_table_mm
        key = (
            id(program),
            (operation.start_line, operation.end_line) if operation else None,
            tuple((number, repr(definition)) for number, definition in sorted(definitions.items())),
        )
        if key == self._tool_readiness_key:
            return self._tool_issues
        if program is None:
            required = set()
        else:
            required = {
                str(tool)
                for tool in program.motion_tool_ids(
                    operation.start_line if operation else None, operation.end_line if operation else None
                )
            }
        issues = simulation_tool_issues(definitions, required)
        self._tool_readiness_key, self._tool_issues = key, issues
        self.tool_readiness.text = (
            f"Cutter geometry needs attention · {len(issues)} profiles\n" + "\n".join(reason for _, reason in issues)
            if issues
            else (
                f"Cutting dimensions ready · {len(required)} profiles\nCAD checked on calculation · physical installation unverified"
                if required
                else "Choose resolved program motion to review cutter geometry."
            )
        )
        if issues != self._tool_issue_signature:
            self._tool_issue_signature = issues
            self.tool_remedies.clear_widgets()
            for identifier, _reason in issues:
                if identifier != "None":
                    self.tool_remedies.add_widget(
                        Action(
                            f"Review T{identifier} geometry",
                            lambda number=int(identifier): self.review_simulation_tool(number),
                            height=dp(32),
                        )
                    )
        return issues

    def refresh_stock_alignment(self, program, operation, issues):
        viewer = self.workspace.machine.gcode_viewer
        setup = viewer.machine_setup
        key = (
            self._tool_readiness_key,
            setup.stock_origin_mm,
            setup.stock_size_mm,
            setup.stock_rotation_deg,
            bool(issues),
        )
        if key == self._alignment_key:
            return
        self._alignment_key = key
        if program is None:
            self.alignment_status.text = "Choose a program to compare cutting motion with declared stock."
            return
        if setup.stock_size_mm is None:
            self.alignment_status.text = "Stock is undefined · set dimensions and placement in Scene."
            return
        if issues:
            self.alignment_status.text = "Stock/path alignment awaits the required cutter dimensions."
            return
        definitions = {number: replace(value) for number, value in viewer.library_tool_table_mm.items()}
        self.alignment_status.text = "Reviewing cutting motion against declared stock…"

        def review():
            try:
                segments = simulation_segments(
                    program,
                    operation.start_line if operation else None,
                    operation.end_line if operation else None,
                    cancelled=lambda: key != self._alignment_key,
                )
                tools = simulation_tools(definitions, {s.tool_id for s in segments}, validate_assets=False)
                bounds = AABB(
                    Vec3(*setup.stock_origin_mm),
                    Vec3(*(a + b for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm))),
                )
                bounds = StockVolume(bounds, max(setup.stock_size_mm), rotation_deg=setup.stock_rotation_deg).bounds
                result = stock_path_review(segments, tools, bounds, cancelled=lambda: key != self._alignment_key)
                if result is None:
                    return
                count, total = result["possible_overlap_segments"], result["cutting_segments"]
                message = (
                    f"Possible stock engagement · {count:,} of {total:,} cutting segments"
                    if count
                    else (
                        "Cutting motion misses declared stock · check stock placement and program work offset"
                        if total
                        else "No resolved cutting motion in this selection"
                    )
                )
                extent = " to ".join(
                    "(" + ", ".join(f"{value:g}" for value in point) + ")"
                    for point in (bounds.minimum.tuple, bounds.maximum.tuple)
                )
                message = (
                    f"{message}\nStock bounds in program mm: {extent}\n"
                    "Conservative +Z cutter envelopes; overlap does not prove removal, clearance or physical alignment."
                )
            except InterruptedError:
                return
            except (ValueError, TypeError, ArithmeticError) as exc:
                message = f"Stock/path review unavailable: {exc}"
            Clock.schedule_once(lambda _dt: apply(message), 0)

        def apply(message):
            if key == self._alignment_key:
                self.alignment_status.text = message

        try:
            threading.Thread(target=review, daemon=True, name="stock-path-review").start()
        except (RuntimeError, OSError):
            self.alignment_status.text = "Stock/path review worker could not start; change selection to review again."

    def review_simulation_tool(self, number):
        comparison = self.workspace.tool_comparison
        comparison.search.text = ""
        comparison.focus()
        comparison.choose(number)

    def operation_selected(self, number):
        point = self.clearance_card.plot.selected
        if point and point.line != number:
            self.clearance_card.plot.selected = None
            self.clearance_card.plot.paint()
            self.clearance_card.inspect.disabled = True
            self.clearance_card.source_action.disabled = True
            self.clearance_card.details.text = (
                f"Source selection changed to line {number}. Select a clearance interval to inspect its geometry."
            )
        self.clearance_card.refresh_navigation()
        self.refresh_controls()

    def _navigate_clearance(self, action, owner_current=lambda: True):
        self.clearance_navigation.submit(action, owner_current)

    def select_clearance(self, point):
        def select():
            self.workspace.operation_panel.inspect_line(point.line, seek=False)
            self.refresh_controls()

        self._navigate_clearance(select, lambda: self.clearance_card.plot.selected is point)

    def reveal_clearance_source(self):
        point = self.clearance_card.plot.selected
        if point is None:
            return

        def reveal():
            self.workspace.operation_panel.inspect_line(point.line, seek=False)
            self.workspace.operation_panel._reveal(self.workspace.operation_panel.inspection)
            self.refresh_controls()

        self._navigate_clearance(reveal, lambda: self.clearance_card.plot.selected is point)

    def _invalidate_clearance(self):
        """Retain captured results, but separate them from current-path inspection."""
        self.clearance_navigation.cancel()
        self.clearance_stale = True
        message = "Inputs changed · captured clearance is historical. Recompute material removal before plotting or inspecting the current path."
        self.clearance_card.summary.text = message
        self.clearance_card.headline.text = message
        self.clearance_card.inspect.disabled = True
        self.clearance_card.source_action.disabled = True
        if self.clearance_motion_action is not None:
            self.clearance_motion_action.disabled = True
        self.clearance_card.plot.selected = None
        self.clearance_card.plot.paint()
        self.clearance_card.refresh_navigation()
        self.refresh_controls()

    def toggle_details(self):
        self.details_open = not self.details_open
        self.details_header.text = ("−  " if self.details_open else "+  ") + "Material removal & clearance"
        if self.details_open:
            self.add_widget(self.content)
            self.workspace.operation_panel.queue_reveal(self.details_header)
        elif self.content.parent is self:
            self.remove_widget(self.content)

    def _identity(self):
        context = self._context()
        return context["program"], digest_context(context)

    def _context(self):
        return capture_context(self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program)

    def hide_single_residual(self):
        """Invalidating this panel's baseline must not clear an array-owned result."""
        viewer = self.workspace.machine.gcode_viewer
        if viewer.repeat_rest_geometries is None:
            viewer.set_rest_stock_geometry(None)

    def refresh_inputs(self):
        self.refresh_controls()
        # No disk I/O in the telemetry refresh loop. Explicit actions rehash CAD.
        current = capture_context(
            self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program, verify_assets=False
        )
        signature = (digest_context(current), self.rest_identity, self.clearance_identity)
        if signature == self._input_signature:
            return
        self._input_signature = signature
        if self.clearance_inputs is not None and (current["program"], signature[0]) != self.clearance_identity:
            self._invalidate_clearance()
        if self.rest_context is None:
            self.input_status.text = (
                "Captured clearance inputs changed · recompute material removal to capture the current setup."
                if self.clearance_stale
                else "No residual baseline · CAD bytes are checked when calculating, reviewing or saving."
            )
        elif signature[0] != digest_context(self.rest_context):
            self.input_status.text = (
                "Setup or tool inputs changed · previous residual is hidden. Review change impact and recompute."
            )
            self.hide_single_residual()
            if self.clearance_card.parent and not self.clearance_stale:
                self.clearance_card.summary.text = "Inputs changed · this captured clearance plot is older. Recompute before seeking into the current path."
                self.clearance_card.headline.text = self.clearance_card.summary.text
        else:
            self.input_status.text = (
                "Residual matches loaded definitions · CAD bytes are rechecked on calculation, review, save or export."
            )

    def review_changes(self, result=None):
        if result not in (None, "residual", "clearance"):
            raise ValueError("Choose residual or clearance inputs to review")
        from carveracontroller.desktop_geometry_review import GeometryChangeReview

        previous = getattr(self, "change_review", None)
        if previous is not None:
            previous.dismiss()
        self.change_review = GeometryChangeReview(self, result)
        return self.change_review

    def start(self, selected):
        if self.artifact_transfer is not None and self.artifact_transfer.active:
            self.note.text = "Finish or cancel the snapshot transfer first."
            return
        if self.workspace.repeat_parts_panel.calculating:
            self.note.text = "Finish or cancel the array calculation first."
            return
        if self.running:
            self.note.text = "Calculation is already running. Cancel it before starting another."
            return
        try:
            program = self.workspace.operation_panel.program
            if program is None:
                raise ValueError("Choose a parsed local program first")
            operation = self.workspace.operation_panel.selected_operation if selected else None
            if selected and operation is None:
                raise ValueError("Select an operation in the operation list first")
            start_line = operation.start_line if operation else None
            end_line = operation.end_line if operation else None
            viewer = self.workspace.machine.gcode_viewer
            definitions = {number: replace(definition) for number, definition in viewer.library_tool_table_mm.items()}
            setup = viewer.machine_setup
            if setup.stock_size_mm is None:
                raise ValueError("Set stock size and placement in Scene first")
            bounds = AABB(
                Vec3(*setup.stock_origin_mm), Vec3(*(a + b for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm)))
            )
            context = capture_context(viewer, program, verify_assets=False)
            identity = (context["program"], digest_context(context))
            baseline = None
            if self.stock_source.text == "Continue rest stock":
                if self.rest_stock is None or self.rest_identity != identity:
                    raise ValueError(
                        "Rest stock belongs to another program/setup/tool selection; start from initial stock or load a matching snapshot"
                    )
                baseline = self.rest_stock
            resolution = float(self.resolution.text) if baseline is None else baseline.resolution_mm
            collision_profiles = {
                group: viewer.machine_component_profiles.get(group, viewer.machine_profile)
                for group in ("fixture", "workholding")
            }
            placement = (
                tuple(viewer.workholding_offset_mm),
                viewer.workholding_rotation_deg,
                viewer.jaw_offset_mm,
            )
            unresolved = tuple(
                line
                for line in program.unresolved_motion_lines
                if operation is None or operation.start_line <= line <= operation.end_line
            )
        except (ValueError, TypeError, OSError) as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self.refresh_controls()
        self.cancel_event.clear()
        self.note.text = f"Preparing CAD, stock and motion · {resolution:g} mm voxels…"
        tasks = getattr(self.workspace, "program_tasks", None)
        task_generation = tasks.generation if tasks is not None else None

        def motion_ready(count):
            current = capture_context(viewer, self.workspace.operation_panel.program, verify_assets=False)
            if self.running and identity == (current["program"], digest_context(current)):
                self.note.text = f"Calculating {count:,} resolved segments · {resolution:g} mm voxels…"

        def acceptance_ready(partial=False):
            if self.running and identity == self._definition_identity():
                self.note.text = (
                    "Cancelled partial result · rechecking CAD bytes before acceptance…"
                    if partial
                    else "Calculation complete · rechecking CAD bytes before acceptance…"
                )

        def run():
            tools = {}
            segments = ()
            preparation_cancelled = False
            stock = scene = clearance_stock = None
            verified_identity = acceptance_cancel_requests = None
            accept_cancelled_result = False
            preparation_phase = "CAD asset"
            try:
                problems = asset_problems(verify_context_assets(context, cancelled=self.cancel_event.is_set))
                if problems:
                    raise ValueError("\n".join(problems))
                preparation_phase = "Stock"
                stock = (
                    baseline.clone(cancelled=self.cancel_event.is_set)
                    if baseline is not None
                    else StockVolume(
                        bounds,
                        resolution,
                        max_voxels=2_000_000,
                        rotation_deg=setup.stock_rotation_deg,
                        cancelled=self.cancel_event.is_set,
                    )
                )
                clearance_stock = stock.clone(cancelled=self.cancel_event.is_set)
                preparation_phase = "Collision scene"
                scene_geometry = collision_geometry(collision_profiles, *placement, cancelled=self.cancel_event.is_set)
                scene = scene_from_geometry(scene_geometry, setup, stock.bounds, cancelled=self.cancel_event.is_set)
                preparation_phase = "Motion"
                segments = simulation_segments(program, start_line, end_line, cancelled=self.cancel_event.is_set)
                Clock.schedule_once(lambda _dt: motion_ready(len(segments)), 0)
                tools = simulation_tools(definitions, {s.tool_id for s in segments})
                report = simulate(segments, tools, stock, scene, cancelled=self.cancel_event.is_set)
                try:
                    geometry = stock_geometry(stock, cancelled=self.cancel_event.is_set)
                except InterruptedError:
                    geometry = None
                preparation_phase = "Result CAD acceptance"
                # Cancelling only viewport preparation retains completed stock,
                # just as cancelling the solver retains its complete segments.
                accept_cancelled_result = report.cancelled or geometry is None
                Clock.schedule_once(lambda _dt, partial=accept_cancelled_result: acceptance_ready(partial), 0)
                acceptance_cancel_requests = self.cancel_requests
                accepted = verify_context_assets(
                    context,
                    cancelled=lambda: self.cancel_requests != acceptance_cancel_requests
                    or (not accept_cancelled_result and self.cancel_event.is_set()),
                )
                verified_identity = (accepted["program"], digest_context(accepted))
                error = None
            except InterruptedError:
                report, geometry, error = (
                    None,
                    None,
                    f"{preparation_phase} preparation cancelled; previous results preserved.",
                )
                preparation_cancelled = True
            except (ValueError, ArithmeticError, OSError) as exc:
                report, geometry, error = None, None, str(exc)
            Clock.schedule_once(
                lambda _dt: finish(
                    report,
                    geometry,
                    error,
                    tools,
                    segments,
                    preparation_cancelled,
                    stock,
                    scene,
                    clearance_stock,
                    verified_identity,
                    acceptance_cancel_requests,
                    accept_cancelled_result,
                ),
                0,
            )

        def finish(
            report,
            geometry,
            error,
            tools,
            segments,
            preparation_cancelled,
            stock,
            scene,
            clearance_stock,
            verified_identity,
            acceptance_cancel_requests,
            accept_cancelled_result,
        ):
            self.running = False
            self.refresh_controls()
            if error:
                self.note.text = error if preparation_cancelled else "Simulation failed: " + error
                return
            if self.cancel_requests != acceptance_cancel_requests or (
                self.cancel_event.is_set() and not accept_cancelled_result
            ):
                self.note.text = "Result CAD acceptance preparation cancelled; previous results preserved."
                return
            if identity != verified_identity or identity != self._definition_identity():
                self.note.text = "Calculation finished for an older setup; result was not applied."
                return
            self.rest_stock, self.report, self.rest_identity = stock, report, identity
            self.artifact_status.text = ""
            self.rest_context = context
            self.clearance_inputs = (segments, tools, scene, clearance_stock)
            self.clearance_identity = identity
            self.clearance_context = context
            self.clearance_stale = False
            self.refresh_controls()
            if self.clearance_card.parent:
                self.content.remove_widget(self.clearance_card)
            viewer.set_rest_stock_geometry(geometry)
            self.note.text = (
                f"{'Cancelled · partial result' if report.cancelled else 'Computed preview'} · "
                f"removed {report.removed_volume_mm3:,.1f} mm³ · remaining {report.remaining_volume_mm3:,.1f} mm³\n"
                f"{len(report.candidates)} conservative clearance candidates · physical clearance unqualified"
            )
            if geometry is None:
                self.note.text += (
                    "\nStock visualization cancelled; completed stock results retained. Run again to rebuild the view."
                )
            model_notes = tuple(
                dict.fromkeys(
                    note for tool in tools.values() for note in (tool.stock_model_note, *tool.clearance_notes) if note
                )
            )
            if model_notes:
                self.note.text += "\n" + "; ".join(model_notes)
            if unresolved:
                self.note.text += f"\n{len(unresolved)} unresolved travel/motion lines were excluded: " + ", ".join(
                    map(str, unresolved[:8])
                )
            if self.hits.parent:
                self.content.remove_widget(self.hits)
            self.hits.set_candidates(
                report.candidates,
                contacts=report.clearance_details,
                segments=segments,
                operations=program.operations,
            )
            if report.candidates:
                self.content.add_widget(self.hits)
            if self.workspace.active_section == "Job" and (tasks is None or tasks.generation == task_generation):
                self.workspace.operation_panel.queue_reveal(self.note, align_top=True)

        self._launch_calculation(run)

    def _launch_calculation(self, run):
        """Restore local controls when no calculation thread can be launched."""
        try:
            threading.Thread(target=run, daemon=True, name="local-simulation").start()
        except (RuntimeError, OSError):
            self.running = False
            self.refresh_controls()
            self.note.text = "Calculation worker could not start; previous results preserved."
            return False
        return True

    def review_clearance(self):
        if self.artifact_transfer is not None and self.artifact_transfer.active:
            self.note.text = "Finish or cancel the snapshot transfer first."
            return
        if self.running:
            self.note.text = "A calculation is running. Cancel it before reviewing clearances."
            return
        if not self.clearance_inputs:
            self.note.text = "Calculate material removal first to capture the path, assembly geometry and obstacle bounds for clearance review."
            return
        identity = self.clearance_identity
        context = capture_context(
            self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program, verify_assets=False
        )
        if self.clearance_stale or identity != (context["program"], digest_context(context)):
            self._invalidate_clearance()
            self.note.text = "Clearance inputs are older. Review change impact and recompute before plotting."
            return
        segments, tools, scene, clearance_stock = self.clearance_inputs
        try:
            tolerance = parse_quantity(self.clearance_tolerance.text, "length")
            if tolerance <= 0:
                raise ValueError("Clearance accuracy must be positive")
        except ValueError as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self.refresh_controls()
        self.cancel_event.clear()
        self.note.text = "Verifying CAD and calculating clearance intervals · bounded numerical error, physical geometry unqualified…"

        def run():
            stale = cancelled = False
            verified_identity = None
            try:
                verified = verify_context_assets(context, cancelled=self.cancel_event.is_set)
                if identity != (verified["program"], digest_context(verified)):
                    Clock.schedule_once(lambda _dt: finish(None, None, True, False, None), 0)
                    return
                report = analyze_clearance(
                    segments,
                    tools,
                    scene,
                    stock=clearance_stock,
                    tolerance_mm=tolerance,
                    cancelled=self.cancel_event.is_set,
                )
                accepted = verify_context_assets(context, cancelled=self.cancel_event.is_set)
                verified_identity = (accepted["program"], digest_context(accepted))
                error = None
            except InterruptedError:
                report, error, cancelled = None, None, True
            except (ValueError, ArithmeticError) as exc:
                report, error = None, str(exc)
            Clock.schedule_once(lambda _dt: finish(report, error, stale, cancelled, verified_identity), 0)

        def finish(report, error, stale, cancelled, verified_identity):
            self.running = False
            self.refresh_controls()
            if cancelled or self.cancel_event.is_set():
                self.note.text = "Clearance review cancelled; previous results preserved."
                return
            if stale:
                self._invalidate_clearance()
                self.note.text = "Clearance inputs are older. Review change impact and recompute before plotting."
                return
            if error:
                self.note.text = "Clearance calculation failed: " + error
                return
            if identity != verified_identity or identity != self._definition_identity():
                self.note.text = "Clearance calculation finished for older inputs; result was not applied."
                return
            self.clearance_card.set_report(report)
            if not self.clearance_card.parent:
                self.content.add_widget(self.clearance_card, index=1)
            self.note.text = (
                "Clearance plot is ready. Select an interval to inspect its geometry, then inspect the source motion."
            )
            if self.details_open:
                Clock.schedule_once(lambda _dt: self.workspace.operation_panel._reveal(self.clearance_card.title), 0)

        self._launch_calculation(run)

    def seek_clearance(self, point):
        if point is None:
            self.clearance_card.details.text = "Select a plotted motion first."
            return

        def seek():
            operation = next(
                (
                    op
                    for op in self.workspace.operation_panel.program.operations
                    if op.start_line <= point.line <= op.end_line
                ),
                None,
            )
            if operation:
                self.workspace.operation_panel.inspect_line(point.line, seek=False)
                self.clearance_card.details.text += "\nOperation: " + operation.name
            self.workspace.machine.gcode_viewer.set_distance_by_lineidx(point.line, point.source_ratio)

        self._navigate_clearance(seek, lambda: self.clearance_card.plot.selected is point)

    def inspect_clearance(self, line, component, obstacle):
        """Inspect the captured result, never substitute today's mutable CAD."""
        if self.report is None:
            return None
        current = not self.clearance_stale and self.clearance_identity == self._definition_identity()
        contacts = [
            contact
            for number, contact in self.report.clearance_details
            if number == line and contact.component == component and contact.obstacle == obstacle
        ]
        self.close_clearance_inspector()
        body = Surface(orientation="vertical", spacing=dp(8), padding=dp(10), size_hint_y=None)
        body.bind(minimum_height=body.setter("height"))
        heading = label("Clearance review", 14, bold=True, height=28)
        body.add_widget(heading)
        content = body
        content.add_widget(
            content_label(
                f"Line {line} · {component} near {obstacle}\n"
                + (
                    "Loaded definitions match; CAD bytes are rechecked before navigation. "
                    if current
                    else "Historical captured inputs; recompute before navigating. "
                )
                + "Potential contact in the calculated preview; physical clearance remains unqualified."
            )
        )
        content.add_widget(
            content_label(
                "Conservative geometry · physical registration unverified. Missing holder or machine geometry remains unresolved."
            )
        )
        geometry = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        geometry.bind(minimum_height=geometry.setter("height"))
        captured_contacts = set()
        for contact in contacts:
            bounds = contact.obstacle_bounds
            signature = (contact.method, bounds.minimum.tuple, bounds.maximum.tuple, contact.sections)
            if signature in captured_contacts:
                continue
            captured_contacts.add(signature)

            def coordinate(point):
                return "(" + ", ".join(f"{value:.3f}" for value in point.tuple) + ")"

            description = f"Method: {contact.method}\nObstacle box (program mm): {coordinate(bounds.minimum)} to {coordinate(bounds.maximum)}"
            geometry.add_widget(content_label(description))
            for section in contact.sections:
                description = f"Tip-relative height {section.low_mm:.3f}–{section.high_mm:.3f} mm · radial envelope {section.radius_mm:.3f} mm\n{section.source}"
                geometry.add_widget(content_label(description))
        geometry.add_widget(
            content_label(
                "Boxes include empty space within fixtures. Rotating envelopes fill concavities. Stock checks use remaining occupied cells before each motion; voxel-center removal and within-motion timing remain approximate. Missing machine structures, registration and holder geometry remain unresolved."
            )
        )

        def toggle_geometry():
            if geometry.parent is content:
                content.remove_widget(geometry)
                geometry_action.text = "+  Captured geometry details"
            else:
                content.add_widget(geometry, index=content.children.index(geometry_action))
                geometry_action.text = "−  Captured geometry details"

        geometry_action = Action("+  Captured geometry details", toggle_geometry, height=dp(34))
        content.add_widget(geometry_action)
        from carveracontroller.desktop_remedies import RemedyPanel

        remedies = RemedyPanel(self, line, component, obstacle)
        content.add_widget(remedies)
        self.clearance_inspector, self.clearance_remedies = body, remedies
        self.clearance_return = Action("Return to clearance review", self.reveal_clearance_inspector)
        self.workspace.operation_panel.inspection.add_widget(
            self.clearance_return, index=len(self.workspace.operation_panel.inspection.children)
        )
        actions = AdaptiveGrid(max_cols=2, min_width=150, row_height=36, spacing=dp(8))

        def inspect_motion():
            if self.clearance_stale or self.clearance_identity != self._definition_identity():
                preview_action.disabled = True
                content.add_widget(
                    content_label(
                        "Inputs changed since this calculation. Recompute before inspecting this result against the current path."
                    )
                )
                return
            self._navigate_clearance(
                lambda: self.workspace.operation_panel.inspect_line(line, seek=True),
                lambda: self.clearance_inspector is body,
            )

        preview_action = Action("Show motion in preview", inspect_motion, disabled=not current)
        self.clearance_motion_action = preview_action
        actions.add_widget(preview_action)
        actions.add_widget(Action("Close review", self.close_clearance_inspector))
        body.add_widget(actions, index=len(body.children) - 2)
        self.content.add_widget(body)
        if not self.details_open:
            self.toggle_details()
        self.reveal_clearance_inspector()
        return body

    def reveal_clearance_inspector(self):
        if self.clearance_inspector is not None:
            if not self.details_open:
                self.toggle_details()
            heading = self.clearance_inspector.children[-1]
            inspector = self.clearance_inspector

            if inspector.parent is not None:
                self.workspace.operation_panel.queue_reveal(heading, align_top=True)

    def close_clearance_inspector(self):
        """Cancel its worker and remove the review without changing captured results."""
        self.clearance_navigation.cancel()
        if self.clearance_remedies is not None:
            self.clearance_remedies.close()
        for widget in (self.clearance_inspector, self.clearance_return):
            if widget is not None and widget.parent is not None:
                widget.parent.remove_widget(widget)
        self.clearance_inspector = self.clearance_remedies = self.clearance_return = self.clearance_motion_action = None

    def reset_display(self):
        self.workspace.machine.gcode_viewer.set_rest_stock_geometry(None)

    def _start_stock_transfer(self, path, *, save):
        if self.running or self.workspace.repeat_parts_panel.calculating:
            self.artifact_status.text = "Finish or cancel the calculation before transferring rest stock."
            return None
        previous = self.artifact_transfer
        if previous is not None:
            if previous.active:
                self.artifact_status.text = "Finish or cancel the current snapshot transfer first."
                return None
            previous.dismiss()
        from carveracontroller.desktop_stock_transfer import StockTransfer

        return StockTransfer(self, path, save=save)

    def save_stock(self):
        if self.rest_stock is None:
            self.artifact_status.text = "Calculate material removal before saving rest stock."
            return
        if self.rest_identity != self._definition_identity() or not self.rest_context:
            self.artifact_status.text = (
                "Residual result is older or lacks its context; review change impact and recompute before saving."
            )
            return
        self.workspace.choose_profile_file(
            lambda path: self._start_stock_transfer(path, save=True),
            save=True,
            extension=".cvstock",
            title="Save residual stock",
        )

    def load_stock(self):
        self.workspace.choose_asset_file(
            lambda path: self._start_stock_transfer(path, save=False), suffixes=(".cvstock",)
        )
