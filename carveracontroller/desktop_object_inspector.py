"""Read-only scene selection, related components and local navigation."""

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Surface, label
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.navigation_history import NavigationHistory
from carveracontroller.machine.scene_inspection import COMPONENT_TITLES, EVIDENCE_GROUPS, related_components


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
        row = BoxLayout(size_hint_y=None, height=dp(34), spacing=dp(6))
        self.choice = Choice(text=COMPONENT_TITLES[self.selected], values=tuple(COMPONENT_TITLES.values()))
        self.choice.bind(text=self._choice_changed)
        row.add_widget(self.choice)
        self.back = Action("Back", lambda: self.navigate(-1), size_hint_x=None, width=dp(65), disabled=True)
        self.forward = Action("Forward", lambda: self.navigate(1), size_hint_x=None, width=dp(75), disabled=True)
        row.add_widget(self.back)
        row.add_widget(self.forward)
        self.add_widget(row)
        self.status = content_label("Local selection · placements and physical state unchanged")
        self.add_widget(self.status)
        self.facts = content_label()
        self.add_widget(self.facts)
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
        setup = viewer.machine_setup
        choice = ws.component_choices.get(key)
        lines = [f"{COMPONENT_TITLES[key]} · {'shown' if ws.component_checks[key].active else 'hidden'}"]
        if choice:
            lines.append("Selected asset: " + choice.text)
        if key == "stock":
            lines.extend(
                [
                    "Envelope: " + vector_text(setup.stock_size_mm) if setup.stock_size_mm else "No stock configured",
                    "Minimum corner (program): " + vector_text(setup.stock_origin_mm),
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
            lines.append("Cutter selection links tooling context; mesh highlighting is not yet available")
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
