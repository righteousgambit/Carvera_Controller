"""Program operations and bank review. Selection changes preview only."""

import math
import threading
from pathlib import Path

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    DANGER,
    MUTED,
    RAISED,
    TEXT,
    Action,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
from carveracontroller.machine.inverse_time import MappedJointMotion, analyze_inverse_time
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.navigation_history import NavigationHistory
from carveracontroller.machine.program_operations import ProgramOperations


def content_label(text=""):
    item = Label(
        text=text,
        font_name="Roboto",
        font_size=sp(11),
        color=MUTED,
        halign="left",
        valign="top",
        size_hint_y=None,
        height=0,
    )
    item.bind(width=lambda obj, width: setattr(obj, "text_size", (max(dp(80), width), None)))
    item.bind(texture_size=lambda obj, size: setattr(obj, "height", size[1] + dp(12) if obj.text else 0))
    return item


class OperationPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.generation = 0
        self.program = None
        self.selected_operation = None
        self.inspector = None
        self.selected_line = None
        self.joint_motion_reviews = {}
        self.rows = []
        self.search_generation = 0
        self._seeking = False
        self.history = workspace.navigation.history if hasattr(workspace, "navigation") else NavigationHistory()
        self._history_restoring = False
        self.add_widget(label("Operations", 15, height=26, bold=True))
        self.note = label("Choose a local program to inspect operations and tool banks.", 11, MUTED, 28)
        self.add_widget(self.note)
        self.history_row = history_row = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(34))
        self.back_action = Action("Back", lambda: self.navigate_history(-1), disabled=True)
        self.forward_action = Action("Forward", lambda: self.navigate_history(1), disabled=True)
        history_row.add_widget(self.back_action)
        history_row.add_widget(self.forward_action)
        self.history_note = content_label()
        self.items = BoxLayout(orientation="vertical", spacing=dp(5), size_hint_y=None, height=0)
        self.items.bind(minimum_height=self.items.setter("height"))
        operation_scroll = DesktopScrollView(size_hint_y=None, height=0, do_scroll_x=False)
        self.items.bind(minimum_height=lambda obj, height: setattr(operation_scroll, "height", min(dp(240), height)))
        operation_scroll.add_widget(self.items)
        self.add_widget(operation_scroll)
        self.detail = content_label()
        self.add_widget(self.detail)
        navigation = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(38))
        self.line_field = Field(hint_text="Line", input_filter="int", size_hint_x=0.3)
        self.line_field.bind(on_text_validate=lambda *_: self.inspect_entry())
        navigation.add_widget(self.line_field)
        navigation.add_widget(Action("Inspect", self.inspect_entry))
        navigation.add_widget(Action("Previous move", lambda: self.step(-1)))
        navigation.add_widget(Action("Next move", lambda: self.step(1)))
        self.add_widget(navigation)
        self.search_field = Field(hint_text="Search: cutting tool:T1, rapid, unresolved, or source text")
        self.search_field.bind(on_text_validate=lambda *_: self.search())
        self.add_widget(self.search_field)
        self.search_action = Action("Find source lines", self.search)
        self.add_widget(self.search_action)
        self.results = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.results.bind(minimum_height=self.results.setter("height"))
        result_scroll = DesktopScrollView(size_hint_y=None, height=0, do_scroll_x=False)
        self.results.bind(minimum_height=lambda obj, height: setattr(result_scroll, "height", min(dp(180), height)))
        result_scroll.add_widget(self.results)
        self.add_widget(result_scroll)
        self.inspection = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.inspection.bind(minimum_height=self.inspection.setter("height"))
        history_row.add_widget(Action("Operations", lambda: self._reveal(self.items)))
        self.inspection.add_widget(history_row)
        self.inspection.add_widget(self.history_note)
        self.motion_demand = Surface(orientation="vertical", padding=dp(10), spacing=dp(4), size_hint_y=None)
        self.motion_demand.bind(minimum_height=self.motion_demand.setter("height"))
        self.motion_demand.add_widget(label("Inverse-time motion", 13, height=24, bold=True))
        self.motion_demand_status = content_label()
        self.motion_demand.add_widget(self.motion_demand_status)
        self.motion_demand_summary = content_label()
        self.motion_demand.add_widget(self.motion_demand_summary)
        self.motion_demand_details = content_label()
        self.motion_demand_details_open = False
        self.motion_demand_details_action = Action("Model & sources", self.toggle_motion_details, height=dp(30))
        self.motion_demand.add_widget(self.motion_demand_details_action)
        self.explanation = content_label("Select an operation or inspect a source line. Preview only.")
        self.inspection.add_widget(self.explanation)
        self.add_widget(self.inspection)
        self.banks = content_label()
        from carveracontroller.desktop_tool_banks import ToolBankPanel

        self.bank_workbench = ToolBankPanel(self)
        self.bank_toggle = Action("+ Prepare tool banks", self.toggle_banks)
        self.add_widget(self.bank_toggle)
        from carveracontroller.desktop_bookmarks import BookmarkPanel

        self.bookmarks = BookmarkPanel(self)
        self.add_widget(self.bookmarks)

    def toggle_banks(self):
        if self.bank_workbench.parent:
            self.remove_widget(self.bank_workbench)
            self.bank_toggle.text = "+ Prepare tool banks"
        else:
            self.add_widget(self.bank_workbench, index=self.children.index(self.bank_toggle))
            self.bank_toggle.text = "− Prepare tool banks"
            self.bank_workbench.refresh()
            self._reveal(self.bank_workbench.heading)

    def load(self, filename):
        if hasattr(self.workspace, "navigation"):
            self.workspace.navigation.reset()
        else:
            self.history.clear()
        self._refresh_history()
        self.history_note.text = ""
        self.search_generation += 1
        self.generation += 1
        generation = self.generation
        self.items.clear_widgets()
        self.program = None
        self.inspector = None
        self.selected_line = None
        self.joint_motion_reviews.clear()
        self.selected_operation = None
        self.rows = []
        self.results.clear_widgets()
        self.search_action.text = "Find source lines"
        self.line_field.text = ""
        self.explanation.text = "Select an operation or inspect a source line. Preview only."
        if self.motion_demand.parent:
            self.inspection.remove_widget(self.motion_demand)
        self.motion_demand_details_open = False
        self.motion_demand_details_action.text = "Model & sources"
        if self.motion_demand_details.parent:
            self.motion_demand.remove_widget(self.motion_demand_details)
        self.detail.text, self.detail.height = "", 0
        self.banks.text, self.banks.height = "", 0
        self.bank_workbench.load(None)
        self.bookmarks.refresh()
        if not filename:
            self.note.text = "Choose a local program to inspect operations and tool banks."
            return
        self.note.text = "Reading program operations…"

        def parse():
            try:
                path = Path(filename)
                if path.stat().st_size > 64 * 1024 * 1024:
                    raise ValueError("Operation analysis limit is 64 MB")
                program = ProgramOperations.from_text(path.read_text(encoding="utf-8", errors="strict"))
                error = None
            except (OSError, ValueError, UnicodeError) as exc:
                program, error = None, str(exc)
            Clock.schedule_once(lambda _dt: self._loaded(generation, program, error), 0)

        threading.Thread(target=parse, daemon=True).start()

    def _loaded(self, generation, program, error):
        if generation != self.generation:
            return
        self.program = program
        if error:
            self.note.text = "Operations unavailable: " + error
            return
        self.inspector = MoveInspector(program)
        self.note.text = f"{len(program.operations)} operations · select to inspect and seek preview"
        for operation in program.operations:
            tools = ", ".join(f"T{n}" for n in operation.tool_ids) or "No tool selected"
            duration = (
                f"{operation.estimated_seconds / 60:.1f} min nominal"
                if operation.estimated_seconds is not None
                else "Time unknown"
            )
            row = Action(
                f"{operation.name} · {tools} · {duration}",
                lambda op=operation: self.select(op),
                height=dp(48),
                halign="left",
                valign="middle",
                padding=(dp(10), 0),
            )
            row.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0] - dp(16), size[1])))
            self.rows.append((operation, row))
            self.items.add_widget(row)
        banks = program.plan_tool_banks()
        text = []
        for bank in banks:
            assignments = " · ".join(f"Slot {slot} -> T{tool}" for slot, tool in bank.slots)
            text.append(f"Bank {bank.index}: lines {bank.start_line}–{bank.end_line}\n{assignments}")
            if bank.reload_required:
                text.append("Reload required · review and reconcile physical tools before continuing")
        self.banks.text = "\n".join(text)
        self.bank_workbench.load(program)
        self.bookmarks.refresh()

    def select(self, operation):
        self.inspect_line(operation.start_line, seek=True)

    def _select_details(self, operation):
        self.selected_operation = operation
        for item, row in self.rows:
            row.base_color = ACCENT if item.id == operation.id else RAISED
            row.color = BG if item.id == operation.id else TEXT
            row._paint()
        if operation.bounds_mm:
            lower, upper = operation.bounds_mm
            bounds = "\nProgram bounds (mm): " + " · ".join(
                f"{axis} {lo:.3f}…{hi:.3f}" for axis, lo, hi in zip("XYZ", lower, upper)
            )
        else:
            bounds = "\nBounds unavailable"
        warnings = "\n" + "\n".join(operation.warnings) if operation.warnings else ""
        self.detail.text = f"{operation.name} · lines {operation.start_line}–{operation.end_line}" + bounds + warnings

    def inspect_entry(self):
        try:
            number = int(self.line_field.text)
            self.inspect_line(number, seek=True)
        except ValueError:
            self.explanation.text = "Choose a source line within the loaded program."

    def inspect_line(self, number, seek=False):
        if self.inspector is None:
            return
        move = self.inspector.explain(number)
        recording = seek and not self._history_restoring
        shared = getattr(self.workspace, "navigation", None)
        if recording and shared:
            shared.depart()
        elif recording and self.selected_line is not None:
            self.history.update_current(self._history_point())
        if move.operation and move.operation != self.selected_operation:
            self._select_details(move.operation)
        self.selected_line = number
        self.line_field.text = str(number)
        state = move.after
        demand = analyze_inverse_time(move)
        if demand.applicable:
            duration = (
                f"{demand.seconds:.6g} s requested for the entire block"
                if demand.seconds is not None
                else "Requested duration unknown"
            )
            path = (
                f"{demand.sampled_length_mm:.6g} mm sampled program path"
                if demand.sampled_length_mm is not None
                else "Program path length unknown"
            )
            rate = (
                f" · {demand.average_path_mm_min:.6g} mm/min average" if demand.average_path_mm_min is not None else ""
            )
            mapped = self.joint_motion_reviews.get((move.program_hash, number))
            self.motion_demand_status.text = (
                "Duration unknown · " + (demand.issues[0] if demand.issues else "Block requires interpretation")
                if demand.seconds is None
                else ""
            )
            self.motion_demand_status.color = DANGER
            issues = demand.issues
            joint_model = ""
            joint_text = "Joint demand unknown: mapped joint trajectory and machine velocity limits are not supplied. Program XYZ is not machine-joint or TCP motion."
            if mapped:
                exceeded = sorted(
                    set(mapped.position_limit_violations)
                    | {joint.name for joint in mapped.joint_demands if joint.exceeds_limit}
                )
                self.motion_demand_status.text = (
                    "Declared limits exceeded: " + ", ".join(exceeded)
                    if exceeded
                    else "No declared-limit exceedance found in this sampled study"
                )
                self.motion_demand_status.color = DANGER if exceeded else MUTED
                issues = tuple(
                    "Program geometry unresolved; supplied joint study is a declaration, not interpreted controller motion."
                    if issue == "Program geometry unresolved; path and joint demand unknown"
                    else issue
                    for issue in issues
                )
                joint_text = (
                    f"Declared joint study · {mapped.pose_samples} poses · tool length {mapped.tool_length_mm:g} mm\n"
                    f"World tip path {mapped.world_tip_length_mm:.6g} mm · work-frame tip path {mapped.work_tip_length_mm:.6g} mm\n"
                    f"Maximum sampled work-frame tip rate {mapped.maximum_sampled_work_tip_mm_s:.6g} mm/s\n"
                    + "\n".join(
                        f"{joint.name}: {joint.maximum_sampled_per_second:.6g} {'mm/s' if joint.kind == 'linear' else 'deg/s'} / declared {joint.limit_per_second:g} · {'EXCEEDS LIMIT' if joint.exceeds_limit else 'within sampled velocity limit'}"
                        for joint in mapped.joint_demands
                    )
                    + f"\nPosition limits exceeded: {', '.join(mapped.position_limit_violations) or 'none in sampled poses'}"
                    + "\nDeclared study only: actual machine mapping, limits, compensation and execution remain unverified."
                )
                joint_model = (
                    f"Model: {mapped.model_source}\nTrajectory: {mapped.trajectory_source}\n"
                    + "\n".join(f"{joint.name} limit source: {joint.limit_source}" for joint in mapped.joint_demands)
                    + f"\nSampling: ≤{mapped.rotary_step_degrees:g} deg rotary / ≤{mapped.linear_step_mm:g} mm linear joint increments; Cartesian error is not bounded."
                )
            self.motion_demand_summary.text = f"Line {number} · {duration}\n{path}{rate}\n" + joint_text
            self.motion_demand_details.text = (
                ("\n".join(issues) + "\n" if issues else "")
                + "Nominal inverse-minute model; arc length uses parser chords. Acceleration and backend timing are not modeled.\n"
                + joint_model
            )
            if not self.motion_demand.parent:
                self.inspection.add_widget(self.motion_demand, index=len(self.inspection.children) - 2)
        elif self.motion_demand.parent:
            self.inspection.remove_widget(self.motion_demand)
        changes = (
            " · ".join(
                f"{name}: {getattr(move.before, name) if getattr(move.before, name) is not None else 'unknown'} -> {getattr(state, name) if getattr(state, name) is not None else 'unknown'}"
                for name in (
                    "units",
                    "distance",
                    "plane",
                    "arc_distance",
                    "feed_mode",
                    "motion",
                    "wcs",
                    "tool",
                    "pending_tool",
                    "tool_length_command",
                    "feed",
                    "spindle_speed",
                    "spindle",
                    "coolant",
                )
                if getattr(move.before, name) != getattr(state, name)
            )
            or "Modal state unchanged"
        )
        tool = f"T{state.tool}" if state.tool is not None else "Unknown tool"
        title = move.operation.name if move.operation else "Source"
        geometry = "Unresolved motion" if move.unresolved else "No resolved motion on this line"
        if move.segments:
            start, end = move.segments[0].start_mm, move.segments[-1].end_mm
            xyz = lambda point: " · ".join(f"{axis} {value:.3f}" for axis, value in zip("XYZ", point))
            geometry = f"Program start: {xyz(start)} mm\nProgram end: {xyz(end)} mm"
        modal = " · ".join(
            value or "Unknown" for value in (state.units, state.distance, state.plane, state.arc_distance)
        )
        context = "\n".join(f"{'>' if n == number else ' '} {n}: {source}" for n, source in move.context)
        warnings = "\n" + "\n".join(move.warnings) if move.warnings else ""
        self.explanation.text = (
            f"{title} · line {number} · {tool}\n"
            f"Frame: {state.wcs or 'unknown'} · {modal}\n"
            f"Motion: {'G' + str(state.motion) if state.motion is not None else 'unknown'} · pending tool: {state.pending_tool if state.pending_tool is not None else 'unknown'}\n"
            f"Changes: {changes}\n"
            f"{geometry}\n{move.feed_description}\n"
            f"Spindle: {state.spindle or 'unknown'} · {state.spindle_speed if state.spindle_speed is not None else 'unknown'} RPM\n"
            f"Coolant: {state.coolant or 'unknown'} · length compensation: {state.tool_length_command or 'unknown'}\n"
            "Machine pose unavailable: measured frame transform and tool offset are not applied here.\n"
            f"\n{context}{warnings}"
        )
        if seek:
            self._seeking = True
            try:
                self.workspace.machine.gcode_viewer.set_distance_by_lineidx(number, 0)
            finally:
                self._seeking = False
            self.queue_reveal(self.inspection)
        if recording and shared:
            self.workspace.machine.gcode_viewer.set_inspected_component(None)
            self.workspace.select("Job", record_navigation=False)
            shared.arrive("program", number)
            self.history_note.text = ""
        elif recording:
            point = self._history_point()
            if not self.history.items or self.history.items[self.history.index]["line"] != number:
                self.history.record(point)
            else:
                self.history.update_current(point)
            self._refresh_history()
            self.history_note.text = ""

        if hasattr(self.workspace, "simulation_panel"):
            self.workspace.simulation_panel.operation_selected(number)

    def review_joint_motion(self, program_hash, line, report: MappedJointMotion):
        """Read-only handoff for a declared study, bound to a parsed source block."""
        if not isinstance(report, MappedJointMotion):
            raise ValueError("A mapped joint-motion report is required")
        if self.program is None or self.inspector is None or self.program.file_hash != program_hash:
            raise ValueError("Joint review belongs to a different or unavailable program")
        block = analyze_inverse_time(self.inspector.explain(line))
        if block.seconds is None or not math.isclose(block.seconds, report.seconds, rel_tol=1e-9, abs_tol=1e-12):
            raise ValueError("Joint study duration does not match the inverse-time block")
        self.joint_motion_reviews[(program_hash, line)] = report
        self.inspect_line(line, seek=False)

    def toggle_motion_details(self):
        self.motion_demand_details_open = not self.motion_demand_details_open
        self.motion_demand_details_action.text = (
            "Hide model & sources" if self.motion_demand_details_open else "Model & sources"
        )
        if self.motion_demand_details_open:
            self.motion_demand.add_widget(self.motion_demand_details)
            self.queue_reveal(self.motion_demand_details_action)
        elif self.motion_demand_details.parent:
            self.motion_demand.remove_widget(self.motion_demand_details)

    def _history_point(self):
        from carveracontroller.desktop_bookmarks import capture_bookmark_context
        from carveracontroller.desktop_view_state import capture_view

        point = {"line": self.selected_line, "program": self.program.file_hash, "context": None, "view": None}
        try:
            point["context"] = capture_bookmark_context(self.workspace)
            point["view"] = capture_view(self.workspace.machine.gcode_viewer)
        except (ValueError, AttributeError, TypeError):
            # Source navigation remains useful without a saved profile or a
            # complete model, but such an entry cannot restore view geometry.
            point["context"] = point["view"] = None
        return point

    def _refresh_history(self):
        self.back_action.disabled = not self.history.can_back
        self.forward_action.disabled = not self.history.can_forward

    def navigate_history(self, direction):
        if hasattr(self.workspace, "navigation"):
            self.workspace.navigation.navigate(direction)
            return
        from carveracontroller.desktop_view_state import restore_view

        if not self.program or self.selected_line is None:
            return
        self.history.update_current(self._history_point())
        candidate = self.history.candidate(direction)
        if candidate is None:
            return
        index, point = candidate
        try:
            current = self._history_point()
            if point["program"] != self.program.file_hash:
                raise ValueError("Program revision changed")
            if point["context"] is not None and point["context"] != current["context"]:
                raise ValueError("Machine profile or setup changed; restore the matching setup to revisit this view")
            self._history_restoring = True
            self.inspect_line(point["line"], seek=True)
            if point["view"] is not None:
                restore_view(self.workspace.machine.gcode_viewer, point["view"])
            self.history.commit(index)
            self._refresh_history()
            self.history_note.text = f"Revisited line {point['line']} · local preview only"
        except (ValueError, AttributeError, TypeError) as exc:
            self.history_note.text = "Navigation unavailable: " + str(exc)
            self.queue_reveal(self.history_note)
        finally:
            self._history_restoring = False

    def queue_reveal(self, widget, *, align_top=False):
        """Enter the requested task now; discard a reveal after a later task choice."""
        tasks = getattr(self.workspace, "program_tasks", None)
        if tasks is not None:
            if not tasks.show_for(widget):
                return
            self.workspace.select("Job", record_navigation=False)
        if tasks is not None and widget is tasks.tabs:
            # The selector is fixed outside the report viewport; revealing it
            # must not change the operator's scroll destination.
            return
        generation = tasks.generation if tasks is not None else None

        def reveal(_dt):
            if tasks is None or (tasks.generation == generation and self.workspace.active_section == "Job"):
                self._reveal(widget, align_top=align_top) if align_top else self._reveal(widget)

        Clock.schedule_once(reveal, 0)

    def _reveal(self, widget, *, align_top=False):
        tasks = getattr(self.workspace, "program_tasks", None)
        if tasks is not None:
            if not tasks.show_for(widget):
                return
            self.workspace.select("Job", record_navigation=False)
        # A changed explanation schedules texture and nested layout work. Wait
        # for those actual triggers, rather than revealing its previous height.
        current = widget
        while current is not None and not isinstance(current, ScrollView):
            if any(
                getattr(current, name, None) is not None and getattr(current, name).is_triggered
                for name in ("_trigger_texture", "_trigger_layout")
            ):
                self.queue_reveal(widget, align_top=align_top)
                return
            current = current.parent
        parent = self.workspace.program_tools.parent if tasks is not None else self.parent
        while parent is not None:
            if isinstance(parent, ScrollView):
                # A pending focus/scroll animation must not overwrite an
                # explicit source or review navigation destination.
                Animation.cancel_all(parent, "scroll_x", "scroll_y")
                if parent.effect_y is not None:
                    parent.effect_y.velocity = 0
                # Long wrapped explanations may exceed a small workbench.
                # Keep navigation at their beginning reachable in that case.
                target = (
                    self.history_row if widget is self.inspection and widget.height > parent.height - dp(24) else widget
                )
                if align_top and parent._viewport is not None:
                    viewport = parent._viewport
                    travel = viewport.height - parent.height
                    if travel > 0:
                        # BoxLayout children share their parent's coordinates.
                        # A relative conversion through every nested layout
                        # subtracts those positions repeatedly; compare the
                        # two window coordinates instead.
                        top = target.to_window(target.x, target.top)[1] - viewport.to_window(viewport.x, viewport.y)[1]
                        parent.scroll_y = min(1, max(0, (top - parent.height + dp(12)) / travel))
                        if parent.effect_y is not None:
                            parent.effect_y.reset(-travel * parent.scroll_y)
                        return
                parent.scroll_to(target, padding=dp(12), animate=False)
                return
            parent = parent.parent

    def observe_preview_line(self, number):
        if (
            self._seeking
            or self._history_restoring
            or self.program is None
            or self.line_field.focus
            or getattr(self.workspace, "active_section", None) not in ("Job", "Preview")
        ):
            return
        if isinstance(number, (int, float)) and number == int(number) and 1 <= number <= len(self.program.lines):
            number = int(number)
            if number != self.selected_line:
                self.inspect_line(number)

    def step(self, direction):
        if self.inspector:
            number = self.inspector.adjacent_motion(self.selected_line or 0, direction)
            if number is not None:
                self.inspect_line(number, seek=True)

    def search(self):
        self.results.clear_widgets()
        if not self.inspector:
            return
        self.search_generation += 1
        generation = self.search_generation
        inspector = self.inspector
        query = self.search_field.text
        self.search_action.text = "Searching…"

        def find():
            matches = inspector.search(query, limit=21)
            Clock.schedule_once(lambda _dt: self._search_loaded(generation, inspector, matches), 0)

        threading.Thread(target=find, daemon=True).start()

    def _search_loaded(self, generation, inspector, matches):
        if generation != self.search_generation or inspector is not self.inspector:
            return
        self.search_action.text = "Find source lines"
        self.results.clear_widgets()
        for number in matches[:20]:
            source = self.program.lines[number - 1]
            row = Action(f"Line {number} · {source[:100]}", lambda n=number: self.inspect_line(n, seek=True))
            row.shorten = True
            row.shorten_from = "right"
            row.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0] - dp(16), size[1])))
            self.results.add_widget(row)
        self.results.add_widget(
            label(
                "First 20 matches · refine search" if len(matches) > 20 else f"{len(matches)} matching source lines",
                11,
                MUTED,
                28,
            )
        )
