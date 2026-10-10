"""Detached, cancellable source-linked program machine-clearance workbench."""

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice
from carveracontroller.desktop_program_surfaces import SurfaceClearanceControls
from carveracontroller.machine.joint_clearance import bodies_from_record
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource, review_program_clearance
from carveracontroller.machine.program_surface_clearance import review_program_surfaces
from carveracontroller.machine.repeat_parts import WCS_NAMES


class ProgramClearanceControls(PlanningCard):
    def __init__(self, card, plot_factory):
        super().__init__("Program machine clearance")
        self.card = card
        self.result = None
        self.retained_inputs = None
        self.selected = None
        self.page = 0
        self.frame = planning_choice(self.content, "Single-scene WCS datum", WCS_NAMES)
        self.frame.bind(text=lambda *_: self.card.owner._invalidate())
        self.content.add_widget(
            flowing_text(
                "Review resolved XYZ motion and bounded curve interiors using each loaded tool's geometry. Repeat-part setups use their named datums. Missing curve bounds, unresolved blocks and automatic tool-change travel remain gaps. Initial stock remains occupied; intended cutting can produce contact.",
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
        files = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        self.save_action = Action("Save body review…", self.save_review, disabled=True)
        self.load_action = Action("Open review…", self.load_review)
        files.add_widget(self.save_action)
        files.add_widget(self.load_action)
        self.content.add_widget(files)
        self.exchange_status = flowing_text("Reopen reviews as detached declarations; current setup is preserved.", 30)
        self.content.add_widget(self.exchange_status)
        self.note = flowing_text("Load a program, explicit tool profiles and C1 scene geometry before review.", 50)
        self.content.add_widget(self.note)
        self.scope = PlanningCard("Coverage & limits")
        self.scope_note = flowing_text("Review a program or open a retained review for its declared scope.", 35)
        self.scope.content.add_widget(self.scope_note)
        self.content.add_widget(self.scope)
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
        self.surfaces = SurfaceClearanceControls(self)
        self.content.add_widget(self.surfaces)

    def clear_result(self):
        self.surfaces.clear()
        self.result = self.selected = None
        self.retained_inputs = None
        self.save_action.disabled = True
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
        self.scope_note.text = "Previous scope cleared; review the current inputs again."

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

    def review(self, selected, *, surfaces=False):
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
                    and current[0].parse_settings == source.parse_settings
                    and current[0].motion is source.motion
                    and current[0].curve_enclosures is source.curve_enclosures
                    and current[3:] == (start, end)
                    and current[2] == offsets
                    and {t: c.digest for t, c in current[1].items()} == {t: c.digest for t, c in captures.items()}
                )
            except (ValueError, TypeError, ArithmeticError):
                same = False
            if not same:
                self.note.text = "Program, operation or scene changed during review; result withheld."
                return
            self.retained_inputs = (source, dict(offsets))
            self.show_result(result.body_review if surfaces else result)
            if surfaces:
                self.surfaces.show(result)

        reviewer = review_program_surfaces if surfaces else review_program_clearance
        owner._start(
            lambda cancelled: reviewer(
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
        self.surfaces.clear()
        self.result = result
        self.save_action.disabled = self.retained_inputs is None

        def gaps(limit):
            return "; ".join(
                f"{name}: " + (", ".join(map(str, rows[:limit])) or "none")
                for name, rows in (
                    ("uncovered", result.uncovered_lines),
                    ("curved", result.curved_lines),
                    ("tool change", result.tool_change_lines),
                )
            )

        bounds = "; ".join(
            f"L{line} {command} ≤{bound:.6g} mm" for line, command, bound in result.curve_enclosures[:32]
        )
        self.note.text = (
            f"{result.status.replace('_', ' ')} · {len(result.segments)} resolved segments · "
            f"{len(result.contacts)} possible contact intervals\n"
            f"Source {result.program_hash[:12]} · lines {result.start_line}–{result.end_line}\n"
            f"Bounded curves: {len(result.curve_enclosures)} · curve gaps: {len(result.curved_lines)} · "
            f"uncovered: {len(result.uncovered_lines)} · tool changes: {len(result.tool_change_lines)}\n"
            f"Coverage gap lines (first8): {gaps(8)}\n"
            "Declared geometry; backend execution and physical clearance unqualified."
        )
        self.scope_note.text = (
            f"{result.tested_pairs} body pair/segments · {result.intervals} bounded intervals\n"
            f"Coverage gap lines (first32 per category): {gaps(32)}\n"
            + (f"Curve position bounds (first32): {bounds}\n" if bounds else "")
            + result.qualification
        )
        self.page = 0
        self.refresh_page()
        # Publish a settled compact result height. Texture updates otherwise
        # lag worker completion and make the next disclosure appear to grow.
        self.note.texture_update()
        self.details.texture_update()
        self.content.do_layout()
        self.do_layout()

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
            f"source {'curve parameter' if any(line == selected.line for line, _command, _bound in self.result.curve_enclosures) else 'path fraction'} [{selected.source_lower_ratio:.6g}, {selected.source_upper_ratio:.6g}]\n"
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

    def save_review(self):
        owner = self.card.owner
        if owner.running or self.result is None or self.retained_inputs is None:
            return
        from carveracontroller.machine.program_clearance_archive import save_program_review

        result, inputs, generation = self.result, self.retained_inputs, owner.generation

        def chosen(path):
            if owner.closed or owner.generation != generation or self.result is not result:
                self.exchange_status.text = "Review changed while choosing a file; save the current result again."
                return
            owner._start(
                lambda cancelled: save_program_review(path, inputs[0], inputs[1], result, cancelled=cancelled),
                lambda digest: setattr(
                    self.exchange_status,
                    "text",
                    f"Saved and recomputed detached program review · SHA256 {digest[:12]}\nExact UTF-8 parser input, settings, declared geometry and coverage gaps retained. No controller or setup change.",
                ),
                error_target=self.exchange_status,
            )

        owner.workspace.choose_profile_file(
            chosen,
            save=True,
            extension=".cvprogramclearance",
            title="Save program machine-clearance review",
        )

    def load_review(self):
        owner = self.card.owner
        if owner.running:
            return
        from carveracontroller.machine.program_clearance_archive import load_program_review

        generation = owner.generation

        def chosen(path):
            if owner.closed or owner.generation != generation:
                self.exchange_status.text = "Inputs changed while choosing a review; choose again."
                return

            def loaded(archive):
                self.retained_inputs = (archive.source, dict(archive.work_offsets))
                self.show_result(archive.report)
                self.note.text = (
                    f"Opened and recomputed detached review · SHA256 {archive.sha256[:12]}\n"
                    "Current program, scene, tool library and work datums were not replaced. Source navigation requires a matching loaded program.\n"
                    + self.note.text
                )

            owner._start(
                lambda cancelled: load_program_review(path, cancelled=cancelled),
                loaded,
                error_target=self.exchange_status,
            )

        owner.workspace.choose_asset_file(chosen, suffixes=(".cvprogramclearance",))
