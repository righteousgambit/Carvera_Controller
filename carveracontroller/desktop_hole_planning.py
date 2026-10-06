"""Guided threaded-hole preparation using explicit loaded cutter profiles.

This panel only creates local preview programs. Loading a recipe does not load
physical tools, change offsets, upload a program, or issue machine commands.
"""

import json
import math
import threading
from dataclasses import asdict
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    QuantityField,
    Surface,
    label,
)
from carveracontroller.machine.hole_planning import THREAD_SPECS, Hole, HoleTool, HoleWorkflow, ThreadSpec
from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.tool_process import HOLE_STAGE_SHAPES

_STAGE_SHAPES = HOLE_STAGE_SHAPES
_STAGE_NAMES = {
    "spot": "Spot · optional",
    "drill": "Pilot drill · required",
    "bore": "Bore to pilot size · optional",
    "chamfer": "Chamfer · optional",
    "threadmill": "Thread mill · required",
}
_REQUIRED = {"drill", "threadmill"}


def parse_holes(text):
    """Parse explicit hole locations in work coordinates; reject ambiguous rows."""
    if len(text) > 128 * 1024:
        raise ValueError("Hole list exceeds 128 KB")
    holes = []
    for number, raw in enumerate(text.splitlines(), 1):
        row = raw.partition("#")[0].strip()
        if not row:
            continue
        values = row.split(",") if "," in row else row.split()
        if len(values) not in {3, 4}:
            raise ValueError(f"Hole row {number}: enter X Y hole-depth [thread-depth] in mm")
        try:
            dimensions = [parse_quantity(value, "length") for value in values]
            if any(not math.isfinite(value) for value in dimensions):
                raise ValueError("finite values required")
            holes.append(Hole(*dimensions))
        except ValueError as exc:
            raise ValueError(f"Hole row {number}: {exc}") from exc
        if len(holes) > 1000:
            raise ValueError("Use at most 1,000 holes per plan")
    if not holes:
        raise ValueError("Add at least one hole: X Y hole-depth [thread-depth] in mm")
    return tuple(holes)


def _column(title, control):
    box = BoxLayout(orientation="vertical", spacing=dp(3), size_hint_y=None, height=control.height + dp(24))
    box.add_widget(label(title, 11, MUTED, 21))
    box.add_widget(control)
    return box


class HolePlanningPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.details_open = False
        self.recipe_tools = None
        self.last_plan = None
        self.running = False
        self.generation = 0
        self.tool_labels = {}
        self.header = Action("+  Holes & threads", self.toggle_details, height=dp(34))
        self.add_widget(self.header)
        self.content = BoxLayout(orientation="vertical", spacing=dp(7), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        self.content.add_widget(label("1 · Locate holes and choose the thread", 13, height=26))
        self.content.add_widget(label("Work coordinates · mm · depths are positive below the top face", 11, MUTED, 26))
        self.holes = Field(multiline=True, height=dp(100), hint_text="X Y hole-depth thread-depth\n10 20 8 6")
        self.content.add_widget(self.holes)
        self.thread = Choice(text="1/4-20", values=tuple(THREAD_SPECS))
        self.wcs = Choice(text="G54", values=tuple(f"G{i}" for i in range(54, 60)))
        self.handedness = Choice(text="Right hand", values=("Right hand", "Left hand"))
        self.direction = Choice(text="Climb", values=("Climb", "Conventional"))
        self._grid(
            (
                ("Thread", self.thread),
                ("Work offset", self.wcs),
                ("Handedness", self.handedness),
                ("Cut direction", self.direction),
            )
        )
        self.thread_summary = label("", 11, MUTED, 38)
        self.content.add_widget(self.thread_summary)
        self.thread.bind(text=lambda *_: self.update_thread_summary())
        self.update_thread_summary()
        self.content.add_widget(label("2 · Select loaded cutters", 13, height=26))
        self.content.add_widget(
            label(
                "Profiles must include diameter, flute length and exposed stickout. Optional stages can be skipped.",
                11,
                MUTED,
                42,
            )
        )
        self.tools = {}
        tool_grid = AdaptiveGrid(max_cols=2, min_width=215, row_height=61, spacing=dp(7))
        for kind, title in _STAGE_NAMES.items():
            choice = Choice(text="Select tool" if kind in _REQUIRED else "Skip", values=())
            self.tools[kind] = choice
            tool_grid.add_widget(_column(title, choice))
        tool_grid.add_widget(
            _column("Refresh after loading tool profiles", Action("Refresh tool choices", self.refresh_tools))
        )
        self.content.add_widget(tool_grid)
        self.thread_form = Choice(text="Single form", values=("Single form", "Pitch-specific multi-form"))
        self._grid((("Thread cutter form", self.thread_form),))
        self.cutter_summary = Label(
            text="",
            font_name="Roboto",
            font_size=sp(11),
            color=MUTED,
            size_hint_y=None,
            height=dp(64),
            halign="left",
            valign="middle",
        )
        self.cutter_summary.bind(width=lambda widget, width: setattr(widget, "text_size", (width, None)))
        self.cutter_summary.bind(
            texture_size=lambda widget, size: setattr(widget, "height", max(dp(64), size[1] + dp(12)))
        )
        self.content.add_widget(self.cutter_summary)
        self.content.add_widget(label("3 · Define clearances and cutting conditions", 13, height=26))
        self.content.add_widget(
            label(
                "Use fractions and units, e.g. 1/4 in or 12 ipm. Converted values appear beneath each field.",
                10,
                MUTED,
                42,
            )
        )
        self.inputs = {}
        specifications = (
            ("top_z_mm", "Top face Z · mm", "0"),
            ("floor_z_mm", "Lowest permitted tip Z · mm", "-15"),
            ("clearance_z_mm", "Clearance Z · mm", "5"),
            ("bottom_clearance_mm", "Below thread · mm", "0.5"),
            ("feed_mm_min", "Cutting feed · mm/min", "150"),
            ("plunge_feed_mm_min", "Plunge feed · mm/min", "60"),
            ("rpm", "Spindle · RPM", "10000"),
            ("fit_allowance_mm", "Diametral fit allowance · mm", "0"),
            ("radial_passes", "Thread radial passes", "2"),
            ("bore_stepdown_mm", "Bore stepdown · mm", "0.5"),
            ("chamfer_width_mm", "Chamfer radial width · mm", "0.25"),
            ("drill_angle", "Drill included tip angle · °", "118"),
            ("spot_angle", "Spot included tip angle · °", "120"),
            ("chamfer_angle", "Chamfer included angle · °", "90"),
        )
        fields = []
        for key, title, default in specifications:
            quantity = (
                "angle"
                if key.endswith("_angle")
                else "rpm"
                if key == "rpm"
                else "scalar"
                if key == "radial_passes"
                else "feed"
                if "feed" in key
                else "length"
            )
            field = QuantityField(text=default, kind=quantity, integer=key == "radial_passes")
            self.inputs[key] = field
            fields.append((title, field))
        self._grid(fields)
        self.content.add_widget(
            label(
                "Angles are explicit setup inputs; confirm against the cutter drawing. Feed/RPM are starting inputs, not a qualified recipe.",
                11,
                MUTED,
                42,
            )
        )
        actions = AdaptiveGrid(max_cols=3, min_width=190, row_height=36, spacing=dp(6))
        actions.add_widget(Action("Generate preview", self.generate, primary=True))
        actions.add_widget(Action("Save recipe", self.save))
        actions.add_widget(Action("Load recipe", self.load))
        actions.add_widget(Action("Start a new recipe", self.new_recipe))
        self.content.add_widget(actions)
        self.note = label("Choose loaded tools and add hole locations to prepare a local preview.", 12, MUTED, 64)
        self.content.add_widget(self.note)
        self.thread_form.bind(text=lambda *_: self.update_cutter_summary())
        self.tools["threadmill"].bind(text=lambda *_: self.update_cutter_summary())
        self.refresh_tools()
        self.update_cutter_summary()

    def update_cutter_summary(self):
        try:
            tool = self._tool("threadmill")
            if tool.thread_teeth is None:
                self.cutter_summary.text = "Single form · full thread-depth helix per radial pass. Pitch-specific cutters need the Multi-form choice and complete tooth-stack metadata in Profiles."
            else:
                self.cutter_summary.text = (
                    f"Multi-form · {tool.thread_teeth} complete teeth · pitch {tool.thread_pitch_mm:g} mm\n"
                    f"One {tool.thread_pitch_mm:g} mm axial turn per radial pass · depth coverage up to {tool.thread_teeth * tool.thread_pitch_mm:g} mm\n"
                    f"Tip lies {tool.thread_tip_offset_mm:g} mm below the lowest tooth datum. Review bottom clearance and teeth emerging above the top face. Nominal geometry; thread fit is unqualified."
                )
        except (ValueError, TypeError) as exc:
            self.cutter_summary.text = str(exc) + " · edit the loaded cutter in Profiles or choose a compatible form."

    def _grid(self, fields):
        grid = AdaptiveGrid(max_cols=2, min_width=215, row_height=78, spacing=dp(7))
        for title, control in fields:
            grid.add_widget(_column(title, control))
        self.content.add_widget(grid)
        return grid

    def toggle_details(self):
        self.details_open = not self.details_open
        self.header.text = ("−  " if self.details_open else "+  ") + "Holes & threads"
        if self.details_open:
            self.refresh_tools()
            self.add_widget(self.content)
        elif self.content.parent is self:
            self.remove_widget(self.content)
        Clock.schedule_once(lambda _dt: Clock.schedule_once(self._reveal_heading, 0), 0)

    def _reveal_heading(self, _dt):
        parent = self.parent
        visited = set()
        while parent is not None and id(parent) not in visited:
            visited.add(id(parent))
            if isinstance(parent, ScrollView):
                parent.scroll_to(self.header, padding=dp(8), animate=False)
                return
            parent = parent.parent

    def update_thread_summary(self):
        spec = ThreadSpec.named(self.thread.text)
        self.thread_summary.text = (
            f"{spec.name} · major Ø{spec.major_mm:g} · pitch {spec.pitch_mm:g} · pilot Ø{spec.pilot_mm:g} mm\n"
            "Nominal cutting dimensions; thread fit still requires inspection."
        )

    def refresh_tools(self):
        definitions = self.workspace.machine.gcode_viewer.library_tool_table_mm
        old_numbers = {kind: self.tool_labels.get(choice.text) for kind, choice in self.tools.items()}
        labels = {}
        choices = {kind: [] for kind in self.tools}
        for number, definition in sorted(definitions.items()):
            shape = definition.tool_type.value
            diameter = f"Ø{definition.diameter:g}" if definition.diameter else "diameter missing"
            title = f"T{number} · {definition.description or shape.replace('_', ' ')} · {diameter}"
            labels[title] = number
            for kind, permitted in _STAGE_SHAPES.items():
                if shape in permitted:
                    choices[kind].append(title)
        self.tool_labels = labels
        for kind, choice in self.tools.items():
            placeholder = "Select tool" if kind in _REQUIRED else "Skip"
            choice.values = (placeholder, *choices[kind])
            choice.text = next((title for title in choices[kind] if labels[title] == old_numbers[kind]), placeholder)
        self.update_cutter_summary()

    def _tool(self, kind, *, number=None, angle=None, form=None):
        if number is None:
            selection = self.tools[kind].text
            if selection == "Skip" and kind not in _REQUIRED:
                return None
            number = self.tool_labels.get(selection)
        definitions = self.workspace.machine.gcode_viewer.library_tool_table_mm
        if number is None or number not in definitions:
            raise ValueError(f"{_STAGE_NAMES[kind]}: select a loaded cutter profile")
        definition = definitions[number]
        if definition.tool_type.value not in _STAGE_SHAPES[kind]:
            raise ValueError(f"T{number}: loaded cutter shape changed; refresh tool choices")
        if any(
            value is None or not math.isfinite(value) or value <= 0
            for value in (definition.diameter, definition.flute_length, definition.stickout)
        ):
            raise ValueError(
                f"T{number}: enter positive diameter, flute length and exposed stickout in the tool profile"
            )
        if angle is None:
            angle = self.inputs[kind + "_angle"].text if kind in {"drill", "spot", "chamfer"} else "118"
        if kind in {"spot", "chamfer"} and definition.tool_type.value != "drill" and definition.tip_diameter != 0:
            raise ValueError(
                f"T{number}: this planner requires an explicitly zero tip diameter for spot/chamfer cutters"
            )
        if kind == "threadmill":
            if (form or self.thread_form.text) != "Single form":
                if (
                    definition.thread_pitch is None
                    or definition.thread_teeth is None
                    or definition.thread_tip_offset is None
                ):
                    raise ValueError(
                        f"T{number}: multi-form profile needs pitch, complete teeth and tip-to-lowest-tooth datum"
                    )
            elif definition.thread_pitch is not None or definition.thread_teeth is not None:
                raise ValueError(
                    f"T{number}: pitch-specific profile cannot be treated as single form; use an explicit single-form profile"
                )
        try:
            tip_angle = parse_quantity(str(angle), "angle")
            if not math.isfinite(tip_angle):
                raise ValueError()
        except ValueError as exc:
            raise ValueError(f"T{number}: enter a finite included tip angle for {kind}") from exc
        return HoleTool(
            number,
            kind,
            definition.diameter,
            min(definition.flute_length, definition.stickout),
            definition.stickout,
            tip_angle_deg=tip_angle,
            thread_pitch_mm=definition.thread_pitch,
            thread_teeth=definition.thread_teeth,
            thread_tip_offset_mm=definition.thread_tip_offset or 0,
        )

    def workflow(self):
        holes = parse_holes(self.holes.text)
        tools = {kind: tool for kind in self.tools if (tool := self._tool(kind)) is not None}
        numeric = {}
        for key, field in self.inputs.items():
            if key.endswith("_angle"):
                continue
            try:
                value = field.value()
                if not math.isfinite(value):
                    raise ValueError()
                numeric[key] = value
            except ValueError as exc:
                raise ValueError(
                    f"Enter a finite {'whole number' if key == 'radial_passes' else 'number'} for {key.replace('_', ' ')}"
                ) from exc
        workflow = HoleWorkflow(
            holes=holes,
            tools=tools,
            thread_spec=ThreadSpec.named(self.thread.text),
            wcs=self.wcs.text,
            handedness="right" if self.handedness.text == "Right hand" else "left",
            climb=self.direction.text == "Climb",
            **numeric,
        )
        if self.recipe_tools is not None and {kind: asdict(tool) for kind, tool in tools.items()} != self.recipe_tools:
            raise ValueError(
                "Loaded recipe cutter geometry differs from current tool profiles or angle inputs. Reconcile profiles, or start a new recipe."
            )
        return workflow

    def generate(self):
        if self.running:
            self.note.text = "Hole plan is already calculating; wait for it to finish."
            return
        try:
            snapshot = self.workflow().to_dict()
            workflow = HoleWorkflow.from_dict(snapshot)
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self.generation += 1
        generation = self.generation
        self.note.text = f"Calculating {len(workflow.holes)} threaded holes…"

        def compute():
            try:
                plan = workflow.plan()
                text, error = plan.gcode(), None
            except (ValueError, TypeError, ArithmeticError) as exc:
                plan, text, error = None, None, str(exc)
            Clock.schedule_once(lambda _dt: finish(plan, text, error), 0)

        def finish(plan, text, error):
            from carveracontroller.desktop_planning import stage_program

            self.running = False
            if generation != self.generation:
                return
            if error:
                self.note.text = error
                return
            try:
                if self.workflow().to_dict() != snapshot:
                    self.note.text = "Inputs or cutter profiles changed during calculation; generate a new preview."
                    return
                path = stage_program(self.workspace, text, "holes-and-threads")
                self.last_plan = plan
                stages = " → ".join(f"{stage.name} T{stage.tool_number}" for stage in plan.stages)
                self.note.text = (
                    f"Local preview · {len(workflow.holes)} holes · {workflow.thread_spec.name}\n{stages}\n"
                    f"{Path(path).name} · inspect travel, datum, tools and thread fit before running."
                )
            except (OSError, ValueError, TypeError) as exc:
                self.note.text = str(exc)

        threading.Thread(target=compute, daemon=True, name="hole-plan-preview").start()

    def new_recipe(self):
        self.generation += 1
        self.recipe_tools = None
        self.last_plan = None
        self.note.text = "New recipe · current inputs retained; current loaded cutter profiles will be used."

    def save(self):
        try:
            workflow = self.workflow()
            workflow.plan()
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        data = {"schema": "carvera-hole-recipe", "version": 1, "workflow": workflow.to_dict()}

        def selected(path):
            try:
                payload = json.dumps(data, indent=2, allow_nan=False)
                with Path(path).open("x", encoding="utf-8") as stream:
                    stream.write(payload)
                self.note.text = "Saved hole recipe · " + str(path)
            except (OSError, ValueError) as exc:
                self.note.text = str(exc)

        self.workspace.choose_profile_file(selected, save=True, extension=".cvholes", title="Save hole/thread recipe")

    def load(self):
        self.workspace.choose_profile_file(self.load_path, extension=".cvholes", title="Load hole/thread recipe")

    def load_path(self, path):
        try:
            source = Path(path)
            if source.stat().st_size > 512 * 1024:
                raise ValueError("Hole recipe exceeds 512 KB")
            data = json.loads(source.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Hole recipe must be a JSON object")
            if data.get("schema") != "carvera-hole-recipe" or data.get("version") != 1:
                raise ValueError("Unsupported hole recipe schema")
            workflow = HoleWorkflow.from_dict(data["workflow"])
            self.restore_reviewed_recipe(workflow)
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            self.note.text = "Recipe not ready: " + str(exc)

    def restore_reviewed_recipe(self, workflow):
        """Restore parsed preparation only after every loaded stage matches."""
        workflow.plan()
        thread_key = next((key for key, spec in THREAD_SPECS.items() if spec == workflow.thread_spec), None)
        if thread_key is None:
            raise ValueError("Recipe thread is not in the supported thread library")
        form = "Pitch-specific multi-form" if workflow.tools["threadmill"].thread_teeth is not None else "Single form"
        for kind, tool in workflow.tools.items():
            if kind not in self.tools:
                raise ValueError(f"Unsupported recipe stage: {kind}")
            current = self._tool(kind, number=tool.number, angle=tool.tip_angle_deg, form=form)
            if current != tool:
                raise ValueError(f"T{tool.number}: recipe geometry differs from the current loaded cutter profile")
        self.refresh_tools()
        selected = {}
        for kind, tool in workflow.tools.items():
            selected[kind] = next(
                (title for title in self.tools[kind].values if self.tool_labels.get(title) == tool.number), None
            )
            if selected[kind] is None:
                raise ValueError(f"Load compatible T{tool.number} into the tool library before restoring this recipe")
        self.thread.text = thread_key
        self.holes.text = "\n".join(
            " ".join(
                f"{value:g}"
                for value in (
                    hole.x_mm,
                    hole.y_mm,
                    hole.depth_mm,
                    *(() if hole.thread_depth_mm is None else (hole.thread_depth_mm,)),
                )
            )
            for hole in workflow.holes
        )
        self.wcs.text = workflow.wcs
        self.handedness.text = "Right hand" if workflow.handedness == "right" else "Left hand"
        self.direction.text = "Climb" if workflow.climb else "Conventional"
        self.thread_form.text = form
        for kind, choice in self.tools.items():
            choice.text = selected.get(kind, "Skip")
        for key, field in self.inputs.items():
            if key.endswith("_angle"):
                kind = key.removesuffix("_angle")
                if kind in workflow.tools:
                    field.text = f"{workflow.tools[kind].tip_angle_deg:g}"
            else:
                field.text = f"{getattr(workflow, key):g}"
        self.recipe_tools = {kind: asdict(tool) for kind, tool in workflow.tools.items()}
        self.workflow()
        self.note.text = "Recipe restored and cutter geometry matched · generate a local preview when ready."
