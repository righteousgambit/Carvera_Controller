"""Read-only scene selection, related components and local navigation."""

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, QuantityField, Surface, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_view_state import capture_view, restore_view
from carveracontroller.machine.navigation_history import NavigationHistory
from carveracontroller.machine.scene_inspection import (
    COMPONENT_TITLES,
    EVIDENCE_GROUPS,
    GEOMETRY_GROUPS,
    related_components,
)


def vector_text(values):
    return " · ".join(f"{axis} {value:.3f}" for axis, value in zip("XYZ", values)) + " mm"


def dimension_text(value, scale=1.0):
    return "unknown" if value is None else f"{value * scale:g} mm"


class SceneObjectInspector(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.selected = "stock"
        self.history = workspace.navigation.history if hasattr(workspace, "navigation") else NavigationHistory()
        self.add_widget(label("Inspect component", 15, height=26, bold=True))
        self.choice = Choice(text=COMPONENT_TITLES[self.selected], values=tuple(COMPONENT_TITLES.values()))
        self.choice.bind(text=self._choice_changed)
        self.add_widget(self.choice)
        row = AdaptiveGrid(max_cols=2, min_width=80, row_height=34, spacing=dp(6))
        self.back = Action("Back", lambda: self.navigate(-1), disabled=True)
        self.forward = Action("Forward", lambda: self.navigate(1), disabled=True)
        row.add_widget(self.back)
        row.add_widget(self.forward)
        self.add_widget(row)
        self.add_widget(label("Inspection separation · mm", 11, height=22))
        self.explode_distance = QuantityField(
            text="25", hint_text="Separation · 0–100 mm", kind="length", minimum=0, maximum=100
        )
        self.add_widget(self.explode_distance)
        separation = AdaptiveGrid(max_cols=2, min_width=120, row_height=34, spacing=dp(6))
        separation.add_widget(Action("Explode & fit", self.explode))
        separation.add_widget(Action("Reassemble", lambda: self.explode(assembled=True)))
        self.add_widget(separation)
        self.isolation = None
        self._isolation_frame_request = 0
        isolation = AdaptiveGrid(max_cols=2, min_width=120, row_height=34, spacing=dp(6))
        self.isolate_button = Action("Isolate selected", self.isolate)
        self.restore_visibility_button = Action("Restore previous view", self.restore_visibility, disabled=True)
        isolation.add_widget(self.isolate_button)
        isolation.add_widget(self.restore_visibility_button)
        self.add_widget(isolation)
        self.status = content_label("Local selection · placements and physical state unchanged")
        self.add_widget(self.status)
        self.facts = content_label()
        self.add_widget(self.facts)
        self.cutter_drawing = None
        self.cutter_drawing_definition = None
        self.cutter_drawing_card = Surface(orientation="vertical", size_hint_y=None, height=dp(214))
        self.cutter_drawing_card.bind(minimum_height=self.cutter_drawing_card.setter("height"))
        self.cutter_drawing_status = content_label()
        self.relations = AdaptiveGrid(max_cols=2, min_width=170, row_height=34, spacing=dp(4))
        self.relationship_details = content_label()
        self.add_widget(self.relationship_details)
        self.add_widget(self.relations)
        self.actions = AdaptiveGrid(max_cols=2, min_width=170, row_height=34, spacing=dp(4))
        self.add_widget(self.actions)
        from carveracontroller.desktop_section_view import SectionPanel

        self.section_panel = SectionPanel(self, content_label)
        self.add_widget(self.section_panel)
        self.refresh_trigger = Clock.create_trigger(self.refresh, 0)

    def _machine_identity(self):
        profile = self.workspace.selected_machine_profile
        return profile["id"] if profile else None

    def _clear_scene_selection(self):
        interaction = self.workspace.scene_interaction
        interaction.request += 1
        interaction.surface_selection = None
        interaction._clear_candidates()
        interaction.clear_measurement()
        interaction.refresh_handle()

    def _refresh_visibility_controls(self):
        previous = getattr(self.workspace, "_syncing_scene_controls", False)
        self.workspace._syncing_scene_controls = True
        try:
            self.workspace.scene_scope.text = (
                "Full machine" if self.workspace.machine.gcode_viewer.machine_view_scope == "machine" else "Work area"
            )
            viewer = self.workspace.machine.gcode_viewer
            for key, check in self.workspace.component_checks.items():
                check.active = (
                    viewer.cutter_visible
                    if key == "cutter"
                    else viewer.machine_group_visibility["fixed" if key == "outer" else key]
                )
        finally:
            self.workspace._syncing_scene_controls = previous
        self.refresh()

    def isolate(self):
        viewer = self.workspace.machine.gcode_viewer
        key = self.selected
        groups = GEOMETRY_GROUPS.get(key, ())
        available = (
            viewer.inspection_cutter_snapshot() is not None
            if key == "cutter"
            else any(
                geometry is not None and bool(geometry.indices)
                for geometry in (viewer._inspection_geometry.get(group) for group in groups)
            )
        )
        if not available:
            self.status.text = "Selected component geometry is unavailable · visibility unchanged"
            return
        previous = self.isolation
        baseline = (
            previous
            if previous and previous["machine_id"] == self._machine_identity()
            else {
                "machine_id": self._machine_identity(),
                "groups": dict(viewer.machine_group_visibility),
                "cutter_visible": viewer.cutter_visible,
                "machine_visible": viewer.machine_visible,
                "view_scope": viewer.machine_view_scope,
                "view": capture_view(viewer),
                "saved_camera": viewer._machine_camera_saved,
            }
        )
        try:
            viewer.set_scene_component_visibility(
                {group: group in groups for group in viewer.machine_group_visibility},
                cutter_visible=key == "cutter",
                machine_visible=True,
                view_scope="machine" if key == "outer" else "workarea",
            )
        except ValueError as exc:
            self.status.text = str(exc)
            return
        self.isolation = baseline
        self.restore_visibility_button.disabled = False
        self._clear_scene_selection()
        self._refresh_visibility_controls()
        self._isolation_frame_request += 1
        request = self._isolation_frame_request
        if key == "cutter":
            # Visibility changes schedule projection/layout updates. Capture the
            # framing context after those updates, not in the isolation gesture.
            def frame_when_settled(_dt):
                if (
                    request == self._isolation_frame_request
                    and self.isolation is baseline
                    and self.selected == key
                    and self._machine_identity() == baseline["machine_id"]
                    and self.workspace.active_section == "Scene"
                ):
                    self.workspace.scene_interaction.frame_selected()

            # Kivy may dispatch a projection/layout trigger after this frame's
            # ordinary callbacks. Defer capture into the following frame too.
            Clock.schedule_once(lambda _dt: Clock.schedule_once(frame_when_settled, 0), 0)
        self.status.text = "Isolated " + COMPONENT_TITLES[key] + " · Restore previous view retains original framing"

    def restore_visibility(self):
        self._isolation_frame_request += 1
        if self.isolation is None:
            return
        baseline = self.isolation
        if baseline["machine_id"] != self._machine_identity():
            self.isolation = None
            self.restore_visibility_button.disabled = True
            self.status.text = "Machine profile changed · previous view was not applied"
            return
        viewer = self.workspace.machine.gcode_viewer
        try:
            viewer.set_scene_component_visibility(
                baseline["groups"],
                cutter_visible=baseline["cutter_visible"],
                machine_visible=baseline["machine_visible"],
                view_scope=baseline["view_scope"],
            )
            restore_view(viewer, baseline["view"])
            viewer._machine_camera_saved = baseline["saved_camera"]
        except ValueError as exc:
            self.status.text = str(exc)
            return
        self.isolation = None
        self.restore_visibility_button.disabled = True
        self._clear_scene_selection()
        self._refresh_visibility_controls()
        self.status.text = "Previous component visibility and camera framing restored"

    def explode(self, assembled=False):
        viewer = self.workspace.machine.gcode_viewer
        try:
            viewer.set_explosion(0 if assembled else self.explode_distance.value())
            viewer._fit_machine_view()
            self.workspace.scene_interaction.surface_selection = None
            self.workspace.scene_interaction.clear_measurement()
            self.workspace.scene_interaction.refresh_handle()
            self.refresh()
            self.status.text = (
                "Exploded inspection · nominal geometry and setup unchanged"
                if viewer.explosion_mm
                else "Assembled view restored"
            )
            self.workspace.model_caption.text = (
                "Machine & toolpath · " + viewer.pose_mode + (" · exploded inspection" if viewer.explosion_mm else "")
            )
        except (ValueError, TypeError) as exc:
            self.status.text = str(exc)

    def _choice_changed(self, _choice, title):
        key = next(key for key, value in COMPONENT_TITLES.items() if value == title)
        if key != self.selected:
            self.select(key)

    def select(self, key, *, record=True, reveal=True):
        if key not in COMPONENT_TITLES:
            raise ValueError("Unknown scene component")
        shared = getattr(self.workspace, "navigation", None)
        if record and shared:
            shared.depart()
        elif record and not self.history.items:
            self.history.record(self.selected)
        self.selected = key
        self.choice.text = COMPONENT_TITLES[key]
        self.workspace.machine.gcode_viewer.set_inspected_component(key)
        if record and not shared:
            self.history.record(key)
        self.back.disabled, self.forward.disabled = not self.history.can_back, not self.history.can_forward
        self.status.text = "Local selection · placements and physical state unchanged"
        self.refresh()
        if reveal:
            self.workspace.select("Scene", record_navigation=False)
            Clock.schedule_once(lambda _dt: self._reveal(), 0)
        if record and shared:
            shared.arrive("scene", key)

    def navigate(self, direction):
        if hasattr(self.workspace, "navigation"):
            self.workspace.navigation.navigate(direction)
            return
        candidate = self.history.candidate(direction)
        if candidate:
            index, key = candidate
            self.select(key, record=False)
            self.history.commit(index)
            self.back.disabled, self.forward.disabled = not self.history.can_back, not self.history.can_forward

    def _reveal(self):
        parent = self.parent
        while parent:
            if isinstance(parent, ScrollView):
                parent.scroll_to(self.choice, padding=dp(12), animate=False)
                return
            parent = parent.parent

    def refresh(self, *_):
        ws = self.workspace
        viewer = ws.machine.gcode_viewer
        key = self.selected
        drawing_tool, drawing_scale, drawing_source = None, 1.0, ""
        setup = viewer.machine_setup
        choice = ws.component_choices.get(key)
        if viewer.explosion_mm and viewer.pose_mode == "Preview":
            self.status.text = "Exploded inspection · display separation only, not physical placement"
        elif self.status.text.startswith("Exploded inspection"):
            self.status.text = "Assembled view · placements and physical state unchanged"
        lines = [f"{COMPONENT_TITLES[key]} · {'shown' if ws.component_checks[key].active else 'hidden'}"]
        if choice:
            lines.append("Selected asset: " + choice.text)
        if key == "stock":
            lines.extend(
                [
                    "Envelope: " + vector_text(setup.stock_size_mm) if setup.stock_size_mm else "No stock configured",
                    "Unrotated corner (program): " + vector_text(setup.stock_origin_mm),
                    f"Stock Z rotation {setup.stock_rotation_deg:g}° about stock center",
                    "Preview work offset: " + vector_text(setup.work_offset_mm),
                    "Computed residual shown"
                    if getattr(viewer, "_rest_stock_geometry", None)
                    else "Declared stock envelope",
                ]
            )
        elif key == "workholding":
            lines.extend(
                [
                    "Draft placement: " + vector_text(viewer.workholding_offset_mm),
                    f"Rotation {viewer.workholding_rotation_deg:g}° · jaw shift {viewer.jaw_offset_mm:g} mm",
                    "Jaw shift is a CAD displacement; measured opening and clamping are unverified",
                ]
            )
        elif key == "cutter":
            requested = viewer._tool_number_at_index(int(getattr(viewer, "cur_line_index", 0)))
            number = viewer._active_tool_number
            number = number if type(number) is int else None
            tool = viewer.library_tool_table_mm.get(number)
            scale = 1.0
            source = "Local tool profile"
            if tool is None:
                tool = viewer.tool_table.get(number)
                scale = viewer.tool_unit_scale
                source = "CAM tool metadata"
            mode = "Reported" if viewer.pose_mode == "Live" else "Preview"
            lines.append(
                f"Displayed {mode.lower()} T{number}" if number is not None else "Displayed cutter identity unavailable"
            )
            if requested != number:
                lines.append(
                    f"Requested T{requested} · displayed geometry has not updated"
                    if requested is not None
                    else "Requested tool identity unavailable"
                )
            binding = viewer.assembly_preview_binding
            if binding and binding["number"] == number:
                lines.append(f"Physical assembly preview: {binding['name']} · definition {binding['revision_id'][:8]}")
                from carveracontroller.machine.assembly_preview import design_fingerprint

                assembly = ws.machine.tool_custody.assembly(binding["assembly_id"])
                profile = (
                    next((p for p in ws.profile_store.data["tools"] if p["id"] == binding["profile_id"]), None)
                    if ws.profile_store
                    else None
                )
                current = (
                    assembly is not None
                    and assembly["revision_id"] == binding["revision_id"]
                    and profile is not None
                    and design_fingerprint(profile) == binding["design_fingerprint"]
                )
                lines.append(
                    "Current declared definition"
                    if current
                    else "OLDER assembly or cutter design; preview again to update"
                )
                lines.append("Operator-declared geometry; preview binding does not verify physical installation")
            if tool:
                drawing_tool, drawing_scale, drawing_source = tool, scale, source
                lines.extend(
                    [
                        source,
                        f"Diameter {dimension_text(tool.diameter, scale)} · cutting length {dimension_text(tool.flute_length, scale)}",
                        f"Overall length {dimension_text(tool.length, scale)} · shank {dimension_text(tool.shank_diameter, scale)}",
                        f"Stickout {dimension_text(tool.stickout, scale)}",
                        "Declared visualization dimensions · physical seating not established",
                    ]
                )
            else:
                lines.append("No dimensioned tool profile or CAM metadata available")
            lines.append(
                "Selected cutter highlighted in teal · nominal displayed geometry"
                if viewer.inspection_cutter_snapshot() is not None
                else "Cutter selection retained · no drawable cutter geometry"
            )
        profile = viewer.machine_component_profiles.get(key) or viewer.machine_profile
        if profile and key != "stock" and key != "cutter":
            lines.extend(
                [
                    "CAD: " + profile.model,
                    "Source revision: " + profile.source_revision,
                    "Source SHA-256: " + profile.source_sha256,
                ]
            )
            if key == "fixture":
                lines.append("Mounting: " + (profile.fixture_registration or "unqualified"))
            if key == "atc":
                lines.append("CAD rack only · physical occupancy and calibration unverified")
        elif key not in ("stock", "cutter"):
            lines.append("Schematic geometry · no manufacturer CAD loaded")
        bounds = viewer.inspected_component_bounds(key)
        if bounds:
            lines.append("Rendered bounds size: " + vector_text(tuple(b - a for a, b in zip(*bounds))))
            lines.append("Bounds are component-local envelope dimensions, not measured clearance")
        self.facts.text = "\n".join(lines)
        self._refresh_cutter_drawing(drawing_tool, drawing_scale, drawing_source)
        self.relations.clear_widgets()
        self.relationship_details.text = "\n".join(relation for _other, relation in related_components(key))
        for other, relation in related_components(key):
            button = Action("Inspect " + COMPONENT_TITLES[other], lambda other=other: self.select(other))
            self.relations.add_widget(button)
        self.actions.clear_widgets()
        if key in ("stock", "fixture", "table"):
            self.actions.add_widget(Action("Edit origin & stock…", ws._machine_setup))
        if key == "workholding":
            self.actions.add_widget(Action("Edit vise placement…", ws._workholding_setup))
        if key in ("cutter", "atc", "spindle"):
            self.actions.add_widget(Action("Tool profiles…", ws._open_profiles))
        self.actions.add_widget(Action("Setup evidence", lambda: ws.readiness.open()))
        evidence = getattr(getattr(ws, "readiness", None), "items", ())
        details = [f"{item.title}: {item.state}" for item in evidence if item.key in EVIDENCE_GROUPS[key]]
        if details:
            self.facts.text += "\n" + " · ".join(details)
        self.section_panel.refresh()

    def _refresh_cutter_drawing(self, tool, scale, source):
        from carveracontroller.addons.tool_visualization.dimension_drawing import drawing_definition_mm

        card = self.cutter_drawing_card
        if tool is None:
            self._clear_cutter_drawing()
            return
        try:
            definition = drawing_definition_mm(tool, scale)
            if definition != self.cutter_drawing_definition:
                from carveracontroller.desktop_tool_drawing import ToolDrawing

                if self.cutter_drawing is None:
                    self.cutter_drawing = ToolDrawing(definition, compact=True, size_hint_y=None, height=dp(180))
                    card.add_widget(self.cutter_drawing)
                else:
                    self.cutter_drawing.update_definition(definition)
                self.cutter_drawing_definition = definition
            self.cutter_drawing_status.text = source + " · nominal schematic, not CAD or measured seating"
        except (ValueError, TypeError, OverflowError) as exc:
            self._clear_cutter_drawing()
            self.cutter_drawing_status.text = "Dimensioned schematic unavailable: " + str(exc)
        if not self.cutter_drawing_status.parent:
            card.add_widget(self.cutter_drawing_status)
        if not card.parent:
            self.add_widget(card, index=self.children.index(self.facts))

    def _clear_cutter_drawing(self):
        if self.cutter_drawing:
            self.cutter_drawing.dispose()
        self.cutter_drawing = self.cutter_drawing_definition = None
        self.cutter_drawing_card.clear_widgets()
        if self.cutter_drawing_card.parent:
            self.remove_widget(self.cutter_drawing_card)

    def dispose(self):
        self._clear_cutter_drawing()
        self.refresh_trigger.cancel()
