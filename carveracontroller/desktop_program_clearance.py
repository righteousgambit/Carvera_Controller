"""Detached, cancellable source-linked program machine-clearance workbench."""

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice
from carveracontroller.machine.joint_clearance import bodies_from_record
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource, review_program_clearance
from carveracontroller.machine.repeat_parts import WCS_NAMES


class ProgramClearanceControls(PlanningCard):
    def __init__(self, card, plot_factory):
        super().__init__("Program machine clearance")
        self.card = card
        self.result = None
        self.selected = None
        self.page = 0
        self.frame = planning_choice(self.content, "Single-scene WCS datum", WCS_NAMES)
        self.frame.bind(text=lambda *_: self.card.owner._invalidate())
        self.content.add_widget(
            flowing_text(
                "Review all resolved XYZ polylines using each loaded tool's geometry. Repeat-part setups use their named datums. Curves, unresolved blocks and automatic tool-change travel retain explicit coverage gaps. Initial stock remains occupied; intended cutting can produce contact.",
                70,
            )
        )
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=40, spacing=dp(6))
        self.whole = Action("Review loaded program", lambda: self.review(False))
        self.operation = Action("Review selected operation", lambda: self.review(True))
        for action in (self.whole, self.operation):
            action.bind(width=lambda button, width: setattr(button, "text_size", (max(10, width - dp(12)), None)))
            actions.add_widget(action)
        self.content.add_widget(actions)
        self.note = flowing_text("Load a program, explicit tool profiles and C1 scene geometry before review.", 50)
        self.content.add_widget(self.note)
        self.contact = planning_choice(self.content, "Contact · line / tool", ("No review",))
        self.contact.bind(text=lambda *_: self.select_contact())
        self.source_action = Action("Inspect source", self.inspect_source, disabled=True)
        self.content.add_widget(self.source_action)
        pages = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.previous = Action("Previous contacts", lambda: self.change_page(-1), disabled=True)
        self.next = Action("Next contacts", lambda: self.change_page(1), disabled=True)
        pages.add_widget(self.previous)
        pages.add_widget(self.next)
        self.content.add_widget(pages)
        self.plot = plot_factory()
        self.plot.height = 0
        self.content.add_widget(self.plot)
        self.details = flowing_text("", 0)
        self.content.add_widget(self.details)

    def clear_result(self):
        self.result = self.selected = None
        self.source_action.disabled = True
        self.previous.disabled = self.next.disabled = True
        self.page = 0
        self.contact.values = ("No review",)
        self.contact.text = "No review"
        self.plot.geometry = ()
        self.plot.draw()
        self.plot.height = 0
        self.details.text = ""
        self.note.text = "Inputs changed · review the current scene and source again."

    def inputs(self, selected):
        owner = self.card.owner
        panel = owner.workspace.operation_panel
        program = panel.program
        if program is None:
            raise ValueError("Load a program first")
        operation = panel.selected_operation if selected else None
        if selected and operation is None:
            raise ValueError("Select a program operation first")
        start, end = (operation.start_line, operation.end_line) if operation else (1, len(program.lines))
        tools = program.motion_tool_ids(start, end)
        if not tools or None in tools or len(tools) > 32:
            raise ValueError("Resolved motion needs explicit loaded profiles for every tool (at most 32)")
        captures = {tool: self.card.scene_capture.inputs(tool) for tool in tools}
        first = next(iter(captures.values()))
        offsets = (
            {part.wcs: part.work_offset_mm for part in first.repeat_plan.parts}
            if first.repeat_plan is not None
            else {self.frame.text: first.setup.work_offset_mm}
        )
        return ProgramClearanceSource.capture(program), captures, offsets, start, end

    def review(self, selected):
        owner = self.card.owner
        if owner.running:
            return
        try:
            source, captures, offsets, start, end = self.inputs(selected)
            tolerance = self.card.tolerance.value()
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = str(exc)
            return
        self.clear_result()
        self.note.text = f"Reviewing every resolved segment in lines {start}–{end}…"

        def completed(result):
            try:
                current = self.inputs(selected)
                same = (
                    current[0].file_hash == source.file_hash
                    and current[3:] == (start, end)
                    and current[2] == offsets
                    and {t: c.digest for t, c in current[1].items()} == {t: c.digest for t, c in captures.items()}
                )
            except (ValueError, TypeError, ArithmeticError):
                same = False
            if not same:
                self.note.text = "Program, operation or scene changed during review; result withheld."
                return
            self.show_result(result)

        owner._start(
            lambda cancelled: review_program_clearance(
                source,
                captures,
                offsets,
                start_line=start,
                end_line=end,
                tolerance_mm=tolerance,
                cancelled=cancelled,
            ),
            completed,
            error_target=self.note,
        )

    def show_result(self, result):
        self.result = result
        self.note.text = (
            f"{result.status.replace('_', ' ')} · {len(result.segments)} resolved segments · "
            f"{len(result.contacts)} possible contact intervals\n"
            f"Source {result.program_hash[:12]} · lines {result.start_line}–{result.end_line} · "
            f"{result.tested_pairs} pair/segments · {result.intervals} bounded intervals\n"
            f"Uncovered blocks: {len(result.uncovered_lines)} · curved blocks: {len(result.curved_lines)} · "
            f"tool-change blocks: {len(result.tool_change_lines)}\n"
            + "Coverage gap lines (first 32 per category): "
            + "; ".join(
                f"{name}: " + (", ".join(map(str, rows[:32])) or "none")
                for name, rows in (
                    ("uncovered", result.uncovered_lines),
                    ("curved", result.curved_lines),
                    ("tool change", result.tool_change_lines),
                )
            )
            + "\n"
            + result.qualification
        )
        self.page = 0
        self.refresh_page()

    def change_page(self, delta):
        if self.result is not None:
            self.page = max(0, min((len(self.result.contacts) - 1) // 64, self.page + delta))
            self.refresh_page()

    def refresh_page(self):
        result = self.result
        if result is None:
            return
        first = self.page * 64
        self.contact.values = tuple(
            f"{index + first + 1} · line {c.line} · T{c.tool} · {c.contact.first} / {c.contact.second}"
            for index, c in enumerate(result.contacts[first : first + 64])
        ) or ("No contact in resolved polylines",)
        self.previous.disabled = self.page == 0
        self.next.disabled = first + 64 >= len(result.contacts)
        self.contact.text = self.contact.values[0]
        self.select_contact()

    def select_contact(self):
        if self.result is None or not self.result.contacts or self.contact.text not in self.contact.values:
            return
        selected = self.result.contacts[self.page * 64 + self.contact.values.index(self.contact.text)]
        segment = self.result.segments[selected.segment_index]
        fraction = selected.contact.witness_fraction
        if fraction is None:
            fraction = (selected.contact.lower_fraction + selected.contact.upper_fraction) / 2
        point = segment.start + (segment.end - segment.start).scaled(fraction)
        machine = machine_from_record(self.result.records[selected.tool])
        bodies, _excluded = bodies_from_record(self.result.records[selected.tool], machine)
        self.plot.show(
            machine, bodies, dict(zip(("X", "Y", "Z"), point.tuple)), (selected.contact.first, selected.contact.second)
        )
        self.plot.height = dp(200)
        self.details.text = (
            f"Detached declared-body pose · XY left / XZ right\nLine {selected.line} · T{selected.tool} · "
            f"source path fraction [{selected.source_lower_ratio:.6g}, {selected.source_upper_ratio:.6g}]\n"
            + (
                "Envelope overlap at interval midpoint."
                if selected.contact.witness_fraction is not None
                else "Possible contact interval; no midpoint overlap witness."
            )
        )
        self.selected = selected
        self.source_action.disabled = False

    def inspect_source(self):
        if self.result is None or self.selected is None:
            return
        panel = self.card.owner.workspace.operation_panel
        if panel.program is None or panel.program.file_hash != self.result.program_hash:
            self.note.text = "Loaded source differs from this detached review; source navigation withheld."
            return
        panel.inspect_line(self.selected.line, seek=True)
