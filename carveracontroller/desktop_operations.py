"""Program operations and bank review. Selection changes preview only."""

import math
import threading
from pathlib import Path

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.widget import Widget

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    DANGER,
    MUTED,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
from carveracontroller.machine.inverse_time import MappedJointMotion, analyze_inverse_time
from carveracontroller.machine.move_inspection import MoveInspector
from carveracontroller.machine.navigation_history import NavigationHistory
from carveracontroller.machine.operation_facts import format_operation_facts, operation_facts
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
        self.operation_card = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None)
        self.operation_card.bind(minimum_height=self.operation_card.setter("height"))
        self.operation_heading = content_label()
        self.operation_heading.color = TEXT
        self.operation_card.add_widget(self.operation_heading)
        self.path_highlight_enabled = True
        self.path_highlight_action = Action("Operation highlight: on", self.toggle_path_highlight, height=dp(32))
        self.operation_card.add_widget(self.path_highlight_action)
        self.path_highlight_note = content_label()
        self.operation_card.add_widget(self.path_highlight_note)
        self.operation_metrics = GridLayout(cols=2, spacing=dp(6), size_hint_y=None)
        self.operation_metrics.bind(minimum_height=self.operation_metrics.setter("height"))
        self.operation_card.bind(
            width=lambda obj, width: setattr(self.operation_metrics, "cols", 1 if width < dp(420) else 2)
        )
        self.operation_values = {}
        self.operation_metric_cells = []
        for key, title in (
            ("path", "Resolved path"),
            ("motion", "Motion lines"),
            ("frames", "Work frames"),
            ("tools", "Program tools"),
        ):
            cell = Surface(orientation="vertical", padding=dp(8), spacing=dp(2), size_hint_y=None)
            self.operation_metric_cells.append(cell)
            cell.bind(minimum_height=self._size_operation_metrics)
            cell.add_widget(label(title, 10, MUTED, 20))
            value = content_label()
            value.color = TEXT
            cell.add_widget(value)
            cell.add_widget(Widget())
            self.operation_values[key] = value
            self.operation_metrics.add_widget(cell)
        self.operation_card.add_widget(self.operation_metrics)
        self.operation_tool_actions = AdaptiveGrid(max_cols=3, min_width=120, row_height=32, spacing=dp(6))
        self.operation_card.add_widget(self.operation_tool_actions)
        self.detail = content_label()
        self.operation_details_open = False
        self.operation_details_action = Action(
            "Process, bounds & warnings", self.toggle_operation_details, height=dp(32)
        )
        self.operation_card.add_widget(self.operation_details_action)
        self.inspection_tools = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.inspection_tools.bind(minimum_height=self.inspection_tools.setter("height"))
        navigation = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(38))
        self.line_field = Field(hint_text="Line", input_filter="int", size_hint_x=0.3)
        self.line_field.bind(on_text_validate=lambda *_: self.inspect_entry())
        navigation.add_widget(self.line_field)
        navigation.add_widget(Action("Inspect", self.inspect_entry))
        navigation.add_widget(Action("Previous move", lambda: self.step(-1)))
        navigation.add_widget(Action("Next move", lambda: self.step(1)))
        self.inspection_tools.add_widget(navigation)
        self.search_field = Field(hint_text="Search: cutting tool:T1, rapid, unresolved, or source text")
        self.search_field.bind(on_text_validate=lambda *_: self.search())
        self.inspection_tools.add_widget(self.search_field)
        self.search_action = Action("Find source lines", self.search)
        self.inspection_tools.add_widget(self.search_action)
        self.results = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.results.bind(minimum_height=self.results.setter("height"))
        result_scroll = DesktopScrollView(size_hint_y=None, height=0, do_scroll_x=False)
        self.results.bind(minimum_height=lambda obj, height: setattr(result_scroll, "height", min(dp(180), height)))
        result_scroll.add_widget(self.results)
        self.inspection_tools.add_widget(result_scroll)
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
        from carveracontroller.desktop_joint_feedback import JointFeedbackPanel

        self.motion_feedback = JointFeedbackPanel()
        from carveracontroller.desktop_declared_path import DeclaredPathPanel

        self.motion_path = DeclaredPathPanel()
        self.motion_demand_details = content_label()
        self.motion_corner_page = 0
        self.motion_corner_identity = None
        self.motion_corner_navigation = AdaptiveGrid(max_cols=2, min_width=110, row_height=30, spacing=dp(5))
        self.motion_corner_previous = Action("Previous corners", lambda: self.step_motion_corners(-1), disabled=True)
        self.motion_corner_next = Action("Next corners", lambda: self.step_motion_corners(1), disabled=True)
        self.motion_corner_navigation.add_widget(self.motion_corner_previous)
        self.motion_corner_navigation.add_widget(self.motion_corner_next)
        self.motion_demand_details_open = False
        self.motion_demand_details_action = Action("Model & sources", self.toggle_motion_details, height=dp(30))
        self.motion_demand.add_widget(self.motion_demand_details_action)
        from carveracontroller.desktop_joint_study import JointStudyImport

        self.joint_study_import = JointStudyImport(self)
        self.motion_demand.add_widget(self.joint_study_import)
        self.move_card = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None)
        self.move_card.bind(minimum_height=self.move_card.setter("height"))
        self.move_title = content_label("Select an operation or inspect a source line. Preview only.")
        self.move_title.color = TEXT
        self.move_card.add_widget(self.move_title)
        self.move_facts = GridLayout(cols=2, spacing=dp(8), size_hint_y=None)
        self.move_facts.bind(minimum_height=self.move_facts.setter("height"))
        self.move_card.bind(width=lambda obj, width: setattr(self.move_facts, "cols", 1 if width < dp(420) else 2))
        self.move_values = {}
        for key, title in (
            ("tool", "Tool & motion"),
            ("frame", "Program frame"),
            ("feed", "Programmed feed"),
            ("spindle", "Programmed spindle"),
        ):
            cell = Surface(orientation="vertical", padding=dp(8), spacing=dp(2), size_hint_y=None)
            cell.bind(minimum_height=cell.setter("height"))
            cell.add_widget(label(title, 10, MUTED, 20))
            value = content_label()
            value.color = TEXT
            cell.add_widget(value)
            self.move_values[key] = value
            self.move_facts.add_widget(cell)
        self.move_geometry = content_label()
        self.move_tool_context = content_label()
        self.move_tool_action = Action("Review tool context", self.review_tool_context, height=dp(32), disabled=True)
        self.move_tool_number = None
        self.move_valid = False
        self.move_issues = content_label()
        self.move_issues.color = DANGER
        self.move_card.add_widget(self.move_geometry)
        self.move_card.add_widget(self.move_tool_context)
        self.move_card.add_widget(self.move_tool_action)
        self.move_card.add_widget(self.move_issues)
        self.move_details_open = False
        self.move_details_action = Action(
            "Source & modal details", self.toggle_move_details, height=dp(32), disabled=True
        )
        self.move_card.add_widget(self.move_details_action)
        self.explanation = content_label("Select an operation or inspect a source line. Preview only.")
        from carveracontroller.desktop_modal_inspector import ModalInspectorPanel

        self.modal_inspector = ModalInspectorPanel(content_label, self.queue_reveal)
        self.inspection.add_widget(self.move_card)
        self.reset_move_card(self.explanation.text)
        self.inspection_tools.add_widget(self.inspection)
        self.banks = content_label()
        from carveracontroller.desktop_tool_banks import ToolBankPanel

        self.bank_workbench = ToolBankPanel(self)
        self.bank_toggle = Action("+ Prepare tool banks", self.toggle_banks, disabled=True)
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
        self.joint_study_import.cancel(clear=True)
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
        if self.inspection_tools.parent:
            self.remove_widget(self.inspection_tools)
        if self.bank_workbench.parent:
            self.remove_widget(self.bank_workbench)
        self.bank_toggle.text = "+ Prepare tool banks"
        self.bank_toggle.disabled = True
        self.program = None
        self.inspector = None
        self.selected_line = None
        self.joint_motion_reviews.clear()
        self.selected_operation = None
        self.refresh_path_highlight()
        if self.operation_card.parent:
            self.remove_widget(self.operation_card)
        self.operation_details_open = False
        self.operation_details_action.text = "Process, bounds & warnings"
        if self.detail.parent:
            self.operation_card.remove_widget(self.detail)
        self.operation_tool_actions.clear_widgets()
        self.rows = []
        self.results.clear_widgets()
        self.search_action.text = "Find source lines"
        self.line_field.text = ""
        self.explanation.text = "Select an operation or inspect a source line. Preview only."
        self.reset_move_card(self.explanation.text)
        if self.motion_demand.parent:
            self.inspection.remove_widget(self.motion_demand)
        self.motion_demand_details_open = False
        self.motion_demand_details_action.text = "Model & sources"
        self.motion_corner_page = 0
        self.motion_corner_identity = None
        self.motion_feedback.show(None, None)
        self.motion_path.show(None, None)
        if self.motion_feedback.parent:
            self.motion_demand.remove_widget(self.motion_feedback)
        if self.motion_corner_navigation.parent:
            self.motion_demand.remove_widget(self.motion_corner_navigation)
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
        if not self.inspection_tools.parent:
            self.add_widget(self.inspection_tools, index=self.children.index(self.bank_toggle) + 1)
        self.bank_toggle.disabled = not bool(program.operations)
        self.note.text = f"{len(program.operations)} operations · select to inspect and seek preview"
        for index, operation in enumerate(program.operations, 1):
            tools = ", ".join(f"T{n}" for n in operation.tool_ids) or "No tool selected"
            duration = (
                f"{operation.estimated_seconds / 60:.1f} min nominal"
                if operation.estimated_seconds is not None
                else "Time unknown"
            )
            row = Action(
                f"{index:02d}  {operation.name}\n{tools} · {duration} · lines {operation.start_line}–{operation.end_line}"
                + (
                    f" · {len(operation.warnings)} warning{'s' if len(operation.warnings) != 1 else ''}"
                    if operation.warnings
                    else ""
                ),
                lambda op=operation: self.select(op),
                height=dp(66),
                halign="left",
                valign="middle",
                padding=(dp(10), 0),
            )
            row.bind(width=lambda obj, width: setattr(obj, "text_size", (max(dp(40), width - dp(20)), None)))
            row.bind(texture_size=lambda obj, size: setattr(obj, "height", max(dp(66), size[1] + dp(16))))
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
        self.inspect_line(operation.start_line, seek=True, reveal=self.operation_card)

    def _select_details(self, operation):
        self.selected_operation = operation
        self.refresh_path_highlight()
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
        report = operation_facts(self.program, operation)
        facts = format_operation_facts(report)
        self.operation_heading.text = f"{operation.name} · lines {operation.start_line}–{operation.end_line}"
        self.operation_values[
            "path"
        ].text = f"Feed {report.feed_path_mm:.1f} mm · rapid {report.rapid_mm:.1f} mm\nArcs approximated · contact unverified"
        self.operation_values[
            "motion"
        ].text = f"{report.resolved_moves} resolved · {len(report.unresolved_lines)} unresolved"
        self.operation_values["frames"].text = ", ".join(report.frames) or "Unknown"
        self.operation_values["tools"].text = ", ".join(f"T{number}" for number in operation.tool_ids) or "Unknown"
        self.operation_tool_actions.clear_widgets()
        for number in operation.tool_ids:
            self.operation_tool_actions.add_widget(
                Action(f"Review T{number}", lambda tool=number: self.review_operation_tool(tool), height=dp(32))
            )
        self.operation_details_action.text = (
            "Hide process details" if self.operation_details_open else "Process, bounds & warnings"
        ) + (f" · {len(operation.warnings)} warnings" if operation.warnings else "")
        if not self.inspection_tools.parent:
            self.add_widget(self.inspection_tools, index=self.children.index(self.bank_toggle) + 1)
        if not self.operation_card.parent:
            self.add_widget(self.operation_card, index=self.children.index(self.inspection_tools) + 1)
        self.detail.text = (
            f"{operation.name} · lines {operation.start_line}–{operation.end_line}\n" + facts + bounds + warnings
        )

    def toggle_path_highlight(self):
        self.path_highlight_enabled = not self.path_highlight_enabled
        self.refresh_path_highlight()

    def refresh_path_highlight(self):
        viewer = self.workspace.machine.gcode_viewer
        operation = self.selected_operation
        active = False
        if self.path_highlight_enabled and self.program is not None and operation is not None:
            active = viewer.set_operation_highlight(self.program.file_hash, operation.start_line, operation.end_line)
        else:
            viewer.set_operation_highlight(None)
        self.path_highlight_action.text = "Operation highlight: " + ("on" if self.path_highlight_enabled else "off")
        self.path_highlight_note.text = (
            "Complete selected operation in teal · other paths dimmed · preview marker only"
            if active
            else "Operation highlight paused in Live view."
            if self.path_highlight_enabled and operation is not None and viewer.pose_mode == "Live"
            else "Highlight awaits matching loaded preview geometry."
            if self.path_highlight_enabled and operation is not None
            else ""
        )

    def _size_operation_metrics(self, *_):
        height = max((cell.minimum_height for cell in self.operation_metric_cells), default=0)
        for cell in self.operation_metric_cells:
            cell.height = height

    def toggle_operation_details(self):
        self.operation_details_open = not self.operation_details_open
        if self.operation_details_open:
            self.operation_card.add_widget(self.detail)
            self.queue_reveal(self.operation_details_action)
        elif self.detail.parent:
            self.operation_card.remove_widget(self.detail)
        self.operation_details_action.text = (
            "Hide process details" if self.operation_details_open else "Process, bounds & warnings"
        )
        if self.selected_operation and self.selected_operation.warnings:
            self.operation_details_action.text += f" · {len(self.selected_operation.warnings)} warnings"

    def review_operation_tool(self, number):
        if self.selected_operation is None or number not in self.selected_operation.tool_ids:
            return
        comparison = self.workspace.tool_comparison
        comparison.search.text = ""
        comparison.focus()
        comparison.choose(number)

    def inspect_entry(self):
        try:
            number = int(self.line_field.text)
            self.inspect_line(number, seek=True)
        except ValueError:
            self.explanation.text = "Choose a source line within the loaded program."
            self.reset_move_card(self.explanation.text)

    def inspect_line(self, number, seek=False, *, reveal=None):
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
        self.joint_study_import.refresh()
        self.line_field.text = str(number)
        state = move.after
        self.modal_inspector.inspect(move)
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
            self.motion_path.show(mapped, (move.program_hash, number))
            if mapped and mapped.path_points and self.motion_path.parent is None:
                self.motion_demand.add_widget(
                    self.motion_path, index=self.motion_demand.children.index(self.motion_demand_summary)
                )
            elif (not mapped or not mapped.path_points) and self.motion_path.parent:
                self.motion_demand.remove_widget(self.motion_path)
            feedback = mapped.feedback if mapped else None
            self.motion_feedback.show(feedback, (move.program_hash, number))
            if feedback and self.motion_feedback.parent is None:
                self.motion_demand.add_widget(
                    self.motion_feedback, index=self.motion_demand.children.index(self.motion_demand_summary)
                )
            elif not feedback and self.motion_feedback.parent:
                self.motion_demand.remove_widget(self.motion_feedback)
            previous_corner_identity = self.motion_corner_identity
            if (
                previous_corner_identity is None
                or previous_corner_identity[:2] != (move.program_hash, number)
                or previous_corner_identity[2] is not mapped
            ):
                self.motion_corner_identity = (move.program_hash, number, mapped)
                self.motion_corner_page = 0
            corner_count = len(mapped.joint_transitions) if mapped else 0
            self.motion_corner_previous.disabled = self.motion_corner_page == 0
            self.motion_corner_next.disabled = (self.motion_corner_page + 1) * 64 >= corner_count
            if self.motion_demand_details_open and corner_count > 64:
                if self.motion_corner_navigation.parent is None:
                    index = (
                        self.motion_demand.children.index(self.motion_demand_details) + 1
                        if self.motion_demand_details.parent is self.motion_demand
                        else 0
                    )
                    self.motion_demand.add_widget(self.motion_corner_navigation, index=index)
            elif self.motion_corner_navigation.parent is not None:
                self.motion_demand.remove_widget(self.motion_corner_navigation)
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
                    else "No sampled position/velocity exceedance found in this declared study"
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
                transitions = mapped.joint_transitions
                joint_text += (
                    f"\nInterior velocity changes: {len(transitions)} · reversals: {sum(t.reverses for t in transitions)}"
                    + (" · blending/dynamics review required" if transitions else " · endpoints remain unmodeled")
                )
                joint_model = (
                    f"Model: {mapped.model_source}\nTrajectory: {mapped.trajectory_source}\n"
                    + "\n".join(f"{joint.name} limit source: {joint.limit_source}" for joint in mapped.joint_demands)
                    + f"\nSampling: ≤{mapped.rotary_step_degrees:g} deg rotary / ≤{mapped.linear_step_mm:g} mm linear joint increments; Cartesian error is not bounded."
                )
                feedback = mapped.feedback
                if feedback:
                    joint_text += (
                        f"\nSupplied feedback · {feedback.samples} samples · duration {feedback.duration_seconds:.6g} s "
                        f"(requested {mapped.seconds:g} s; difference {feedback.duration_seconds - mapped.seconds:+.6g} s)"
                        f" · maximum gap {feedback.maximum_gap_seconds:.6g} s"
                    )
                    for observed in feedback.demands:
                        unit = "mm" if observed.kind == "linear" else "deg"
                        acceleration = (
                            f"{observed.maximum_acceleration:.6g} {unit}/s²"
                            if observed.maximum_acceleration is not None
                            else "unknown (needs ≥3 samples)"
                        )
                        jerk = (
                            f"{observed.maximum_jerk:.6g} {unit}/s³"
                            if observed.maximum_jerk is not None
                            else "unknown (needs ≥4 samples)"
                        )
                        following = (
                            f"{observed.maximum_following_error:.6g} {unit}"
                            if observed.maximum_following_error is not None
                            else "unknown (command samples absent)"
                        )
                        joint_text += (
                            f"\n{observed.name} sampled feedback: velocity {observed.maximum_velocity:.6g} {unit}/s; "
                            f"acceleration {acceleration}; jerk {jerk}; reversals {observed.reversals}; "
                            f"command/reported error {following}"
                        )
                    joint_model += (
                        f"\nFeedback: {feedback.source}\nFeedback timing: {feedback.timing_source}"
                        "\nVelocity uses position secants at interval midpoints; acceleration/jerk recursively difference those secants. "
                        "Nonuniform intervals are retained. Between-sample peaks, timestamp alignment, filtering and backend following-error semantics remain unqualified. "
                        "Command/reported error uses paired samples only; feedback does not replace declared kinematic geometry."
                    )
                if transitions:
                    joint_model += "\nDeclared waypoint corners (unwrapped joints; no acceleration inferred):\n"
                    start = self.motion_corner_page * 64
                    joint_model += f"Corners {start + 1}–{min(start + 64, len(transitions))} of {len(transitions)}\n"
                    joint_model += "\n".join(
                        f"{corner.name} at {100 * corner.fraction:.5g}% ({mapped.seconds * corner.fraction:.5g} s): "
                        f"{corner.before_per_second:.6g} → {corner.after_per_second:.6g} "
                        f"{'mm/s' if corner.kind == 'linear' else 'deg/s'} · "
                        + ("REVERSAL" if corner.reverses else "velocity change")
                        for corner in transitions[start : start + 64]
                    )
                    if len(transitions) > 64:
                        joint_model += (
                            f"\nShowing first 64 of {len(transitions)} changes; the study retains all changes."
                        )
                    joint_model += "\nCorner rate tolerance: relative 1e-9 / absolute 1e-12. Endpoint approach/exit and backend blending are unknown."
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
            self.motion_feedback.show(None, None)
            self.motion_path.show(None, None)
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
                    "cutter_compensation",
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
        self.move_title.text = f"{title} · line {number} · program preview"
        self.move_values[
            "tool"
        ].text = f"{tool} · {'G' + str(state.motion) if state.motion is not None else 'motion unknown'}"
        self.move_values["frame"].text = f"{state.wcs or 'unknown'} · {modal}"
        self.move_values["feed"].text = move.feed_description
        spindle_speed = f"{state.spindle_speed:g}" if state.spindle_speed is not None else "unknown"
        self.move_values["spindle"].text = f"{state.spindle or 'unknown'} · {spindle_speed} RPM"
        self.move_geometry.text = (
            geometry + "\nMachine pose unavailable: measured frame transform and tool offset are not applied here."
        )
        self.move_issues.text = "\n".join(move.warnings)
        if not self.move_facts.parent:
            self.move_card.add_widget(self.move_facts, index=len(self.move_card.children) - 1)
        self.move_details_action.disabled = False
        self.move_valid = True
        self.move_tool_number = state.tool
        self.refresh_tool_context()
        if seek:
            self._seeking = True
            try:
                self.workspace.enter_preview()
                self.workspace.machine.gcode_viewer.set_distance_by_lineidx(number, 0)
                self.refresh_path_highlight()
            finally:
                self._seeking = False
            self.queue_reveal(reveal or self.inspection, align_top=reveal is not None)
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

    def step_motion_corners(self, offset):
        if self.program is None or self.selected_line is None:
            return
        report = self.joint_motion_reviews.get((self.program.file_hash, self.selected_line))
        if report is None:
            return
        self.motion_corner_page = min(
            max(0, (len(report.joint_transitions) - 1) // 64), max(0, self.motion_corner_page + offset)
        )
        self.inspect_line(self.selected_line, seek=False, reveal=False)

    def toggle_motion_details(self):
        self.motion_demand_details_open = not self.motion_demand_details_open
        self.motion_demand_details_action.text = (
            "Hide model & sources" if self.motion_demand_details_open else "Model & sources"
        )
        if self.motion_demand_details_open:
            if not self.motion_corner_previous.disabled or not self.motion_corner_next.disabled:
                self.motion_demand.add_widget(self.motion_corner_navigation)
            self.motion_demand.add_widget(self.motion_demand_details)
            self.queue_reveal(self.motion_demand_details_action)
        elif self.motion_demand_details.parent:
            self.motion_demand.remove_widget(self.motion_demand_details)
            if self.motion_corner_navigation.parent:
                self.motion_demand.remove_widget(self.motion_corner_navigation)

    def reset_move_card(self, message):
        self.motion_path.show(None, None)
        if self.motion_demand.parent:
            self.inspection.remove_widget(self.motion_demand)
        self.move_title.text = message
        self.move_valid = False
        self.move_tool_number = None
        self.move_tool_context.text = ""
        self.move_tool_action.disabled = True
        self.move_geometry.text = self.move_issues.text = ""
        for value in self.move_values.values():
            value.text = ""
        if self.move_facts.parent:
            self.move_card.remove_widget(self.move_facts)
        if self.explanation.parent:
            self.move_card.remove_widget(self.explanation)
        if self.modal_inspector.parent:
            self.move_card.remove_widget(self.modal_inspector)
        self.modal_inspector.inspect(None)
        self.move_details_open = False
        self.move_details_action.text = "Source & modal details"
        self.move_details_action.disabled = True

    def toggle_move_details(self):
        if self.move_details_action.disabled:
            return
        self.move_details_open = not self.move_details_open
        self.move_details_action.text = (
            "Hide source & modal details" if self.move_details_open else "Source & modal details"
        )
        if self.move_details_open:
            self.move_card.add_widget(self.modal_inspector)
            self.move_card.add_widget(self.explanation)
            self.queue_reveal(self.move_details_action)
        else:
            for item in (self.modal_inspector, self.explanation):
                if item.parent:
                    self.move_card.remove_widget(item)

    def refresh_tool_context(self):
        if not self.move_valid:
            return
        comparison = getattr(self.workspace, "tool_comparison", None)
        number = self.move_tool_number
        self.move_tool_action.disabled = comparison is None or number is None
        self.move_tool_action.text = f"Review programmed T{number}" if number is not None else "Tool selection unknown"
        row = next((item for item in comparison.rows if item.number == number), None) if comparison else None
        if row is None:
            self.move_tool_context.text = (
                "Tool geometry unavailable for this programmed selection. Physical assembly identity is unverified."
            )
            self.move_tool_context.color = MUTED
            return
        dimension = lambda value: "unknown" if value is None else f"{value:g} mm"
        self.move_tool_context.text = (
            f"Loaded tooling · {row.name}\n"
            f"Declared library Ø {dimension(row.library_diameter_mm)} · CAM Ø {dimension(row.cam_diameter_mm)} · stickout {dimension(row.stickout_mm)}\n"
            f"Current reported TLO {dimension(row.observed_tlo_mm)} ({row.report_state}; reported active tool only). Physical assembly identity is unverified."
            + ("\nDiameter discrepancy: reconcile library and CAM geometry." if row.diameter_conflict else "")
        )
        self.move_tool_context.color = DANGER if row.diameter_conflict else MUTED

    def review_tool_context(self):
        comparison = getattr(self.workspace, "tool_comparison", None)
        if self.move_valid and comparison is not None and self.move_tool_number is not None:
            comparison.search.text = ""
            comparison.focus()
            comparison.choose(self.move_tool_number)

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
            if not self._route_task(tasks, widget):
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
            if not self._route_task(tasks, widget):
                return
            self.workspace.select("Job", record_navigation=False)
        # A changed explanation schedules texture and nested layout work. Wait
        # for those actual triggers, rather than revealing its previous height.
        # Wrapped descendants can resize their containers a frame after the
        # ancestor layout has settled. Include their pending texture/layout
        # work so a review is aligned using its final content height.
        pending = list(widget.walk(restrict=True))
        current = widget.parent
        while current is not None and not isinstance(current, ScrollView):
            pending.append(current)
            current = current.parent
        if any(
            getattr(item, name, None) is not None and getattr(item, name).is_triggered
            for item in pending
            for name in ("_trigger_texture", "_trigger_layout")
        ):
            self.queue_reveal(widget, align_top=align_top)
            return
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
                if target is self.history_row and widget is self.inspection:
                    align_top = True
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

    def _route_task(self, tasks, widget):
        if tasks.show_for(widget):
            return True
        # Source controls are retained while no program is loaded. Their
        # logical owner remains Operations even when the inspector is detached.
        current, visited = widget, set()
        while current is not None and id(current) not in visited:
            if current is self.inspection_tools:
                return tasks.show_for(self)
            visited.add(id(current))
            current = current.parent
        return False

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
