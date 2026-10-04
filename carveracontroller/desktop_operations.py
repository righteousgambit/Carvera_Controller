"""Program operations and bank review. Selection changes preview only."""

import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import (
    ACCENT,
    BG,
    MUTED,
    RAISED,
    TEXT,
    Action,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
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
        self.explanation = content_label("Select an operation or inspect a source line. Preview only.")
        self.inspection.add_widget(self.explanation)
        self.add_widget(self.inspection)
        self.banks = content_label()
        self.add_widget(self.banks)
        from carveracontroller.desktop_bookmarks import BookmarkPanel

        self.bookmarks = BookmarkPanel(self)
        self.add_widget(self.bookmarks)

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
        self.selected_operation = None
        self.rows = []
        self.results.clear_widgets()
        self.search_action.text = "Find source lines"
        self.line_field.text = ""
        self.explanation.text = "Select an operation or inspect a source line. Preview only."
        self.detail.text, self.detail.height = "", 0
        self.banks.text, self.banks.height = "", 0
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
            Clock.schedule_once(lambda _dt: self._reveal(self.inspection), 0)
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
            Clock.schedule_once(lambda _dt: self._reveal(self.history_note), 0)
        finally:
            self._history_restoring = False

    def _reveal(self, widget):
        # A changed explanation schedules texture and nested layout work. Wait
        # for those actual triggers, rather than revealing its previous height.
        current = widget
        while current is not None and not isinstance(current, ScrollView):
            if any(
                getattr(current, name, None) is not None and getattr(current, name).is_triggered
                for name in ("_trigger_texture", "_trigger_layout")
            ):
                Clock.schedule_once(lambda _dt: self._reveal(widget), 0)
                return
            current = current.parent
        parent = self.parent
        while parent is not None:
            if isinstance(parent, ScrollView):
                # Long wrapped explanations may exceed a small workbench.
                # Keep navigation at their beginning reachable in that case.
                target = (
                    self.history_row if widget is self.inspection and widget.height > parent.height - dp(24) else widget
                )
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
