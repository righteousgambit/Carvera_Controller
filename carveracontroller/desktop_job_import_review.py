"""Review a prepared portable job before changing the active local preview."""

import copy
import hashlib
import json
import math
import threading
from threading import Event

from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView

from carveracontroller.CNC import CNC
from carveracontroller.desktop_bookmarks import tool_context
from carveracontroller.desktop_components import Action, AdaptiveGrid, Choice, Field, Surface, label
from carveracontroller.machine.job_program_validation import PreviewParserInputs


def import_context(workspace, tool_ids=None):
    """Detached local metadata; no asset reads, camera frames or CNC queries."""
    machine = workspace.machine
    viewer = machine.gcode_viewer
    placement = getattr(viewer, "machine_setup", None)
    camera = getattr(workspace, "camera_registration_panel", None)
    registration = getattr(camera, "registration", None)
    store = getattr(workspace, "profile_store", None)
    profiles = dict(getattr(viewer, "machine_component_profiles", {}))
    if getattr(viewer, "machine_profile", None) is not None:
        profiles["machine"] = viewer.machine_profile
    request = getattr(workspace, "_planning_request", None)
    inventory = store.data.get("tools", []) if store is not None else []
    if tool_ids is not None:
        inventory = [record for record in inventory if record["id"] in tool_ids]
    repeat = getattr(viewer, "repeat_stock_plan", None)
    retained = getattr(getattr(workspace, "restored_job", None), "package", None)
    simulation = getattr(workspace, "simulation_panel", None)
    return copy.deepcopy(
        {
            "preview_parser": PreviewParserInputs.declarations(CNC.vars, inch=CNC.inch, accuracy=CNC.accuracy),
            "connection": getattr(machine.controller, "_connection_generation", None),
            "machine": getattr(workspace, "selected_machine_profile", None),
            "program": (
                getattr(workspace.app, "selected_local_filename", None),
                getattr(workspace.app, "selected_remote_filename", None),
                getattr(machine, "program_preview_generation", 0),
                getattr(getattr(workspace, "operation_panel", None), "generation", 0),
                getattr(viewer, "loaded_program_hash", None),
            ),
            "placement": placement.record() if placement is not None else {},
            "repeat_stock": {
                "plan": repeat.to_dict() if repeat is not None else None,
                "selected_index": getattr(viewer, "repeat_stock_index", None),
                "rest_identity": id(getattr(viewer, "repeat_rest_geometries", None)),
            },
            "workholding": {
                "offset_mm": getattr(viewer, "workholding_offset_mm", (0, 0, 0)),
                "rotation_deg": getattr(viewer, "workholding_rotation_deg", 0),
                "jaw_offset_mm": getattr(viewer, "jaw_offset_mm", 0),
            },
            "components": {
                name: {
                    "cad_path": getattr(profile, "asset_path", None),
                    "geometry_sha256": getattr(profile, "geometry_sha256", None),
                }
                for name, profile in profiles.items()
            },
            "tools": tool_context(getattr(viewer, "library_tool_table_mm", {})),
            "cam_tools": tool_context(getattr(viewer, "tool_table", {}) or {}),
            "toolset": getattr(workspace, "loaded_toolset", None),
            "tool_bindings": getattr(workspace, "loaded_tool_profiles", {}),
            "tool_override": getattr(viewer, "preview_tool_override", None),
            "assembly": getattr(viewer, "assembly_preview_binding", None),
            "inventory": inventory,
            "retained_metadata": {
                name: getattr(retained, name, None) for name in ("material_recipes", "inspection_plan", "photographs")
            },
            "simulation": (
                id(getattr(simulation, "rest_stock", None)),
                getattr(simulation, "rest_identity", None),
                id(getattr(simulation, "report", None)),
            ),
            "render": (getattr(viewer, "move_scale_by_positon", 1), getattr(viewer, "tool_unit_scale", 1)),
            "camera": {
                "registration": registration.to_dict() if registration else None,
                "draft": camera._input_identity() if hasattr(camera, "_input_identity") else None,
                "fit": getattr(camera, "fit_identity", None),
                "stream_url": getattr(getattr(workspace, "camera_client", None), "url", None),
                "stream_generation": getattr(getattr(workspace, "camera_client", None), "generation", None),
                "url_draft": getattr(getattr(workspace, "camera_url_input", None), "text", None),
            },
            "planning_request": id(request) if request is not None else None,
            "restored_job": id(getattr(workspace, "restored_job", None)),
            "historical_preview": id(getattr(workspace, "historical_preview", None)),
        }
    )


def import_blocker(workspace):
    viewer = workspace.machine.gcode_viewer
    checks = (
        (
            workspace.app.state not in ("Idle", "N/A") or workspace.app.playing,
            "Finish the active run or playback before importing a job.",
        ),
        (getattr(workspace.machine, "loading_file", False), "Wait for the current program preview to finish loading."),
        (getattr(workspace, "_job_apply_active", False), "Wait for the current job publication to finish."),
        (
            any(
                lane["active"]
                for lane in getattr(getattr(workspace, "scene_component_loads", None), "lanes", {}).values()
            ),
            "Wait for fixture, vise or stock preparation to finish.",
        ),
        (
            getattr(workspace, "machine_profile_loading", False) or getattr(viewer, "_default_profile_loading", False),
            "Wait for machine CAD preparation to finish.",
        ),
        (
            getattr(getattr(workspace, "tool_profile_loads", None), "active", False),
            "Wait for cutter geometry preparation to finish.",
        ),
        (
            getattr(getattr(workspace, "camera_registration_panel", None), "running", False),
            "Wait for camera calibration to finish.",
        ),
        (
            getattr(getattr(workspace, "simulation_panel", None), "running", False),
            "Wait for the current simulation to finish.",
        ),
        (
            getattr(workspace, "historical_preview", None) is not None,
            "Restore the current scene before importing another job.",
        ),
    )
    return next((message for blocked, message in checks if blocked), None)


def import_busy(workspace):
    return import_blocker(workspace) is not None


def review_sections(current, loaded, setup, prepared, calibration, profile_cad=None, preview_summary=None):
    """Build effective before/after declarations off the UI thread."""
    placement, definitions, profile, components, bank, program_path, residual = prepared
    components_after = dict(current["components"])
    if profile:
        components_after = {k: v for k, v in components_after.items() if k == "machine"}
    if profile_cad is not None:
        components_after["machine"] = {
            "cad_path": profile_cad.asset_path,
            "geometry_sha256": profile_cad.geometry_sha256,
        }
    components_after.update(
        {group: {"cad_path": cad.asset_path, "geometry_sha256": cad.geometry_sha256} for group, cad in components}
    )
    vise = setup["vise"] or (
        {
            "offset_mm": (profile["vise_x"], profile["vise_y"], profile["vise_z"]),
            "rotation_deg": profile["vise_rotation"],
            "jaw_offset_mm": profile["vise_jaw_offset"],
        }
        if profile
        else current["workholding"]
    )
    pairs = {
        "Program": (
            {"path": current["program"][0], "sha256": current["program"][-1]},
            {
                "job_name": loaded.package.name,
                "name": loaded.package.program_name,
                "sha256": hashlib.sha256(loaded.package.program).hexdigest(),
                "bytes": len(loaded.package.program),
            },
        ),
        **(
            {"Preview preparation": ({"inputs": current["preview_parser"]}, preview_summary)}
            if preview_summary is not None
            else {}
        ),
        "Machine profile": (current["machine"], profile or current["machine"]),
        "Stock and work coordinates": (
            {"stock": current["placement"], "repeat_stock": current["repeat_stock"]},
            {"stock": placement.record(), "repeat_stock": "Replaced by the single imported setup"},
        ),
        "Fixture and vise": (
            {"components": current["components"], "placement": current["workholding"]},
            {"components": components_after, "placement": vise},
        ),
        "Preview cutters and toolset": (
            {"tools": current["tools"], "toolset": current["toolset"], "preview_override": current["tool_override"]},
            {"tools": tool_context(definitions), "toolset": bank, "preview_override": "Follow program tools"},
        ),
        "Inventory reconciliation": (
            {
                "saved_inventory": "Retained unchanged",
                "records": [
                    record for record in current["inventory"] if record["id"] in loaded.report.conflicting_inventory
                ],
            },
            {
                "missing_ids": loaded.report.missing_inventory,
                "conflicting_ids": loaded.report.conflicting_inventory,
                "archive_records": [
                    record
                    for record in loaded.package.tools
                    if record["id"] in (*loaded.report.missing_inventory, *loaded.report.conflicting_inventory)
                ],
                "physical_tools": "Not reconciled; archive contains preview declarations",
            },
        ),
        "Camera calibration": (
            current["camera"],
            {
                "registration": calibration[0].to_dict() if calibration else None,
                "draft_inputs": "Replaced by archive calibration; cleared when absent",
            },
        ),
        "Embedded assets": (
            None,
            {
                reference: {"file": path.name, "bytes": len(loaded.asset_bytes.get(reference, b""))}
                for reference, path in loaded.asset_paths.items()
            },
        ),
        "Retained job data": (
            current["retained_metadata"],
            {
                "material_recipes": loaded.package.material_recipes,
                "inspection_plan": loaded.package.inspection_plan,
                "photographs": loaded.package.photographs,
                "residual_stock": (
                    "Retained context; checked after program analysis"
                    if residual is not None and residual.context is not None
                    else "Legacy snapshot; recompute before continuing"
                    if residual is not None
                    else None
                ),
            },
        ),
    }

    def lines(value):
        # Page by both lines and characters, including long geometry paths/drafts.
        text = json.dumps(value, indent=2, sort_keys=True, default=str)
        return [line[start : start + 180] for line in text.splitlines() for start in range(0, max(1, len(line)), 180)]

    return {name: (lines(before), lines(after)) for name, (before, after) in pairs.items()}


def verify_staged_files(loaded, program_path, cancelled=lambda: False):
    """Re-read bytes before Apply; metadata/mtime alone is not content evidence."""
    paths = [(program_path, hashlib.sha256(loaded.package.program).hexdigest())]
    paths.extend((path, reference.removeprefix("asset://")) for reference, path in loaded.asset_paths.items())
    for path, expected in paths:
        if cancelled():
            raise InterruptedError("Import cancelled")
        if path.is_symlink() or not path.is_file():
            raise ValueError("Staged job file is missing or linked; import the archive again")
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            while data := stream.read(512 * 1024):
                if cancelled():
                    raise InterruptedError("Import cancelled")
                size += len(data)
                if size > 64 * 1024 * 1024:
                    raise ValueError("Staged job file exceeds 64 MB")
                digest.update(data)
        if digest.hexdigest() != expected:
            raise ValueError("Staged job bytes changed; import the archive again")


class JobImportReview:
    PAGE_LINES = 60

    def __init__(self, workspace, generation, context, loaded, prepared, sections, publish):
        self.workspace, self.generation, self.context = workspace, generation, context
        self.loaded, self.prepared, self.sections, self.publish = loaded, prepared, sections, publish
        self.tool_ids = {record["id"] for record in loaded.package.tools}
        self.closed = self.checking = self.publication_failed = False
        self.cancel_event = Event()
        self.page = 0
        self.popup = ModalView(size_hint=(None, None))
        self.popup.title = "Review job import"
        body = self.body = Surface(orientation="vertical", padding=dp(14), spacing=dp(8))
        self.heading = label("Review imported job · " + loaded.package.name[:70], 17, height=30, bold=True)
        body.add_widget(self.heading)
        profile = prepared[2] or context["machine"] or {}
        size = prepared[0].stock_size_mm
        stock_summary = " × ".join(f"{value:g}" for value in size) + " mm" if size else "No stock dimensions"
        self.summary = label(
            f"{loaded.package.program_name} · {len(loaded.package.program):,} bytes · {profile.get('name', 'Current machine')}\n"
            f"{stock_summary} · {len(prepared[1])} preview cutters · {len(loaded.report.missing_inventory)} missing / {len(loaded.report.conflicting_inventory)} conflicting library records",
            12,
            height=56,
        )
        body.add_widget(self.summary)
        self.section = Choice(text=next(iter(sections)), values=tuple(sections))
        selectors = self.selectors = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(6))
        selectors.add_widget(self.section)
        self.view_mode = Choice(text="Compare", values=("Compare", "Current", "Imported"), size_hint_x=0.4)
        selectors.add_widget(self.view_mode)
        body.add_widget(selectors)
        search = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.query = Field(hint_text="Find a value in this section", size_hint_x=1)
        self.query.bind(on_text_validate=lambda *_: self.find())
        search.add_widget(self.query)
        search.add_widget(Action("Find next", self.find, size_hint_x=None, width=dp(110)))
        body.add_widget(search)
        self.section.bind(text=lambda *_: self.show_page(0))
        self.panes = BoxLayout(spacing=dp(8))
        self.current = Field(multiline=True, readonly=True, size_hint_y=1, font_size=dp(11))
        self.incoming = Field(multiline=True, readonly=True, size_hint_y=1, font_size=dp(11))
        self.pane_widgets = []
        for title, field in (("Current local preview", self.current), ("Imported proposal", self.incoming)):
            column = BoxLayout(orientation="vertical", spacing=dp(4))
            column.add_widget(label(title, 12, height=24, bold=True))
            column.add_widget(field)
            self.pane_widgets.append(column)
            self.panes.add_widget(column)
        body.add_widget(self.panes)
        self.panes.bind(width=self._layout_panes)
        self.view_mode.bind(text=self._layout_panes)
        nav = AdaptiveGrid(max_cols=3, min_width=100, row_height=32, spacing=dp(6))
        self.previous = Action("Previous page", lambda: self.show_page(self.page - 1), height=dp(32))
        self.page_note = label("", 11, height=32)
        self.next = Action("Next page", lambda: self.show_page(self.page + 1), height=dp(32))
        for item in (self.previous, self.page_note, self.next):
            nav.add_widget(item)
        body.add_widget(nav)
        self.note = label(
            "Apply replaces only local preview declarations. Saved tool inventory and CNC state remain unchanged.",
            11,
            height=58,
        )
        body.add_widget(self.note)
        actions = AdaptiveGrid(max_cols=2, min_width=140, row_height=36, spacing=dp(6))
        self.cancel_button = Action("Cancel import", self.cancel)
        self.apply_button = Action("Apply local preview", self.apply, primary=True)
        actions.add_widget(self.cancel_button)
        actions.add_widget(self.apply_button)
        body.add_widget(actions)
        self.popup.add_widget(body)
        self.popup.bind(on_dismiss=self._dismissed)
        self.resize_trigger = Clock.create_trigger(self._resize, 0)
        Window.bind(on_resize=self.resize_trigger)
        self.popup.bind(on_open=self.resize_trigger)
        self._resize()
        self.show_page(0)
        workspace._job_import_review = self
        workspace.package_note.text = "Job prepared · review changes before applying."
        self.popup.open()

    def _resize(self, *_):
        self.popup.size = min(dp(1000), Window.width * 0.94), Window.height * 0.9
        short = Window.height < dp(550)
        self.body.spacing = dp(6 if short else 8)
        self.heading.height = dp(26 if short else 30)
        self.selectors.height = dp(34 if short else 38)
        self.note.height = dp(38 if short else 58)
        self.summary.height = 0 if short else dp(56)
        self.summary.opacity = 0 if self.summary.height == 0 else 1
        self._layout_panes()

    def _layout_panes(self, *_):
        compact = self.popup.height < dp(640) and self.panes.width < dp(620)
        self.view_mode.values = ("Current", "Imported") if compact else ("Compare", "Current", "Imported")
        if self.view_mode.text not in self.view_mode.values:
            self.view_mode.text = "Imported"
        self.panes.orientation = "vertical" if self.panes.width < dp(620) else "horizontal"
        wanted = (
            self.pane_widgets
            if self.view_mode.text == "Compare"
            else [self.pane_widgets[0 if self.view_mode.text == "Current" else 1]]
        )
        if tuple(reversed(self.panes.children)) != tuple(wanted):
            self.panes.clear_widgets()
            for pane in wanted:
                self.panes.add_widget(pane)

    def show_page(self, page):
        before, after = self.sections[self.section.text]
        count = max(1, math.ceil(max(len(before), len(after)) / self.PAGE_LINES))
        self.page = max(0, min(page, count - 1))
        start = self.page * self.PAGE_LINES
        self.current.text = "\n".join(before[start : start + self.PAGE_LINES])
        self.incoming.text = "\n".join(after[start : start + self.PAGE_LINES])
        self.previous.disabled, self.next.disabled = self.page == 0, self.page + 1 == count
        self.page_note.text = f"Page {self.page + 1} / {count}"

    def find(self):
        query = self.query.text.strip().casefold()
        if not query:
            return
        before, after = self.sections[self.section.text]
        length = max(len(before), len(after))
        start = getattr(self, "_last_match", -1) + 1
        for step in range(length):
            index = (start + step) % length
            if any(query in rows[index].casefold() for rows in (before, after) if index < len(rows)):
                self._last_match = index
                self.show_page(index // self.PAGE_LINES)
                self.page_note.text += f" · match line {index + 1}"
                return
        self.page_note.text = "No matching value in this section"

    def _release(self):
        self.closed = True
        self.cancel_event.set()
        Window.unbind(on_resize=self.resize_trigger)
        self.resize_trigger.cancel()
        if getattr(self.workspace, "_job_import_review", None) is self:
            self.workspace._job_import_review = None

    def _close(self):
        self._release()
        self.popup.dismiss(animation=False)

    def _dismissed(self, *_):
        if not self.closed:
            self._release()
            self.workspace.package_note.text = self._closing_message()

    def cancel(self):
        if self.closed:
            return
        self._close()
        self.workspace.package_note.text = self._closing_message()

    def _closing_message(self):
        if self.publication_failed:
            if getattr(self.workspace, "_job_import_recovery", None) == (self.generation, True):
                return "Import not applied · previous local preview restored; staged assets retained."
            return "Import publication failed · local preview may be partially updated; staged assets retained."
        return "Import cancelled · current preview retained; staged assets kept locally."

    def current_context(self):
        return (
            self.workspace._job_import_generation == self.generation
            and not import_busy(self.workspace)
            and import_context(self.workspace, self.tool_ids) == self.context
        )

    def apply(self):
        if self.closed or self.checking:
            return
        if not self.current_context():
            self.note.text = "Program, setup, tooling, calibration or connection changed. Cancel and import again to review current context."
            self.apply_button.disabled = True
            return
        self.checking = True
        self.apply_button.disabled = True
        self.note.text = "Checking staged file contents…"

        def verify():
            try:
                verify_staged_files(self.loaded, self.prepared[5], self.cancel_event.is_set)
                error = None
            except Exception as exc:
                error = str(exc) or type(exc).__name__
            Clock.schedule_once(lambda _dt: finish(error), 0)

        def finish(error):
            self.checking = False
            if self.closed:
                return
            if error:
                self.note.text = "Import not applied: " + error
                return
            if not self.current_context():
                self.note.text = "Context changed during verification. Cancel and import again."
                return
            published = self.publish()
            if self.closed or self.workspace._job_import_generation != self.generation:
                return
            if published:
                self._close()
            else:
                self.publication_failed = True
                self.cancel_button.text = "Close review"
                self.note.text = self.workspace.package_note.text

        try:
            threading.Thread(target=verify, daemon=True, name="job-import-verify").start()
        except RuntimeError as exc:
            self.checking = False
            self.apply_button.disabled = False
            self.note.text = f"Could not start verification: {exc}. Try Apply again."
