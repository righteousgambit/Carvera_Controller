"""Explicit source capture for the declared articulated-clearance workbench."""

from kivy.metrics import dp

from carveracontroller.desktop_capabilities import flowing_text
from carveracontroller.desktop_components import Action, AdaptiveGrid
from carveracontroller.desktop_planning import PlanningCard, planning_choice
from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.scene_joint_clearance import build_scene_clearance, capture_scene_clearance


class SceneClearanceControls(PlanningCard):
    def __init__(self, card):
        super().__init__("Capture workspace geometry")
        self.card = card
        self.tool_names = {}
        self.tool = planning_choice(self.content, "Loaded tool profile", ("Choose a loaded tool",))
        actions = AdaptiveGrid(max_cols=2, min_width=145, row_height=36, spacing=dp(6))
        for caption, callback in (
            ("Refresh tool choices", self.refresh_tools),
            ("Capture current C1 scene", self.capture),
            ("Check capture source", self.check_source),
        ):
            action = Action(caption, callback)
            action.bind(width=lambda button, width: setattr(button, "text_size", (max(10, width - dp(12)), None)))
            actions.add_widget(action)
        self.content.add_widget(actions)
        self.note = flowing_text(
            "Capture selected CAD, vise placement, initial stock and an explicit tool profile. Hidden components remain included. This replaces the local declaration only; no machine commands.",
            60,
        )
        self.content.add_widget(self.note)
        self.refresh_tools()

    def refresh_tools(self):
        viewer = self.card.owner.workspace.machine.gcode_viewer
        self.tool_names = {
            f"T{number} · {definition.description[:65] or definition.tool_type.value.replace('_', ' ').title()}": number
            for number, definition in sorted(viewer.library_tool_table_mm.items(), key=lambda row: str(row[0]))
            if type(number) is int
        }
        self.tool.values = tuple(self.tool_names) or ("Choose a loaded tool",)
        selected = getattr(viewer, "preview_tool_override", None)
        if self.tool.text not in self.tool.values:
            self.tool.text = next(
                (name for name, number in self.tool_names.items() if number == selected), self.tool.values[0]
            )

    def source_changed(self):
        source = self.card.owner.record.get("scene_source")
        if source is None:
            self.note.text = "No workspace source on this declaration. Capture selected CAD, initial stock and an explicit tool profile to replace it locally. Hidden components remain included; no machine commands."
        else:
            self.note.text = (
                f"Detached capture · T{source['tool_number']} · source {source['scene_digest'][:12]}\n"
                "Source identity records the original capture; local body edits remain separate declarations.\n"
                + "\n".join(source["notes"])
            )

    def inputs(self, number=None):
        viewer = self.card.owner.workspace.machine.gcode_viewer
        if number is None:
            number = self.tool_names.get(self.tool.text)
        if type(number) is not int or number not in viewer.library_tool_table_mm:
            raise ValueError("Load and choose an explicit tool profile first")
        return capture_scene_clearance(
            viewer.machine_profile,
            dict(viewer.machine_component_profiles),
            viewer.machine_setup,
            (tuple(viewer.workholding_offset_mm), viewer.workholding_rotation_deg, viewer.jaw_offset_mm),
            viewer.library_tool_table_mm[number],
            number,
            viewer.repeat_stock_plan,
            capture_context(viewer, None, verify_assets=False),
        )

    def capture(self):
        owner = self.card.owner
        if owner.running:
            return
        if self.card.body_drafts:
            self.note.text = "Apply or discard retained body drafts before replacing the declaration."
            return
        try:
            captured = self.inputs()
            viewer = owner.workspace.machine.gcode_viewer
            point = captured.setup.machine_point(viewer._preview_program_point)
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = str(exc)
            return
        self.note.text = "Verifying selected assets and preparing component envelopes…"

        def completed(record):
            try:
                if self.inputs(captured.number).digest != captured.digest:
                    self.note.text = (
                        "Workspace geometry changed during capture; previous declaration retained. Capture again."
                    )
                    return
            except (ValueError, TypeError, ArithmeticError):
                self.note.text = "Workspace selection changed during capture; previous declaration retained."
                return
            owner._invalidate()
            owner.record = record
            owner.topology.text = "Imported geometry"
            owner._show_profile("Captured nominal workspace geometry; detached snapshot")
            owner.length_field.text = "0"
            for field, value in zip(owner.target_fields, point):
                field.text = format(value, ".12g")
            owner.axis_field.text = "0 0 1"
            row = " ".join(format(point[i], ".12g") for i in (0, 2, 1))
            owner.seeds.text = row + "\n" + row
            self.note.text = (
                f"Captured {len(record['collision_bodies'])} bodies · T{captured.number} · source {captured.digest[:12]}\n"
                "Route starts at the preview XYZ in machine coordinates (X/Z/Y order); edit it to review motion. Tool-chain origin is the tip.\n"
                + "\n".join(record["scene_source"]["notes"])
            )
            self.card.note.text = (
                "Captured detached nominal scene. Enter ordered joint waypoints and review declared clearance."
            )

        owner._start(
            lambda cancelled: build_scene_clearance(captured, cancelled=cancelled), completed, error_target=self.note
        )

    def check_source(self):
        source = self.card.owner.record.get("scene_source")
        if source is None:
            self.note.text = "This declaration has no workspace capture source."
            return
        try:
            current = self.inputs(source["tool_number"])
        except (ValueError, TypeError, ArithmeticError) as exc:
            self.note.text = "Capture source unavailable: " + str(exc)
            return
        self.note.text = (
            "Original capture inputs match the current workspace declaration. Local body edits and disk asset changes require separate review; this is not live or physical qualification."
            if current.digest == source["scene_digest"]
            else "Workspace geometry differs from the original capture. The displayed declaration is detached; capture again to update it."
        )
