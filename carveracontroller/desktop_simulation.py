"""Workbench simulation: real stock evolution with explicit approximation limits."""

import json
import threading
from pathlib import Path

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3, simulate
from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Field,
    Surface,
    label,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.geometry_changes import (
    affected_operations,
    asset_problems,
    capture_context,
    context_changes,
    digest_context,
)
from carveracontroller.machine.simulation_preview import (
    scene_from_geometry,
    simulation_segments,
    simulation_tools,
    stock_geometry,
)


class SimulationPanel(Surface):
    def __init__(self, workspace, **kwargs):
        super().__init__(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, **kwargs)
        self.bind(minimum_height=self.setter("height"))
        self.workspace = workspace
        self.cancel_event = threading.Event()
        self.running = False
        self.rest_stock = None
        self.report = None
        self.rest_identity = None
        self.rest_context = None
        self.details_open = False
        self.details_header = Action("+  Material removal & clearance", self.toggle_details, height=dp(34))
        self.add_widget(self.details_header)
        self.content = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        self.content.bind(minimum_height=self.content.setter("height"))
        options = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        self.stock_source = Choice(text="Initial stock", values=("Initial stock", "Continue rest stock"))
        self.resolution = Field(text="2", hint_text="Voxel resolution · mm", size_hint_x=0.35)
        options.add_widget(self.stock_source)
        options.add_widget(self.resolution)
        self.content.add_widget(options)
        actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=34, spacing=dp(6))
        actions.add_widget(Action("Simulate program", lambda: self.start(False)))
        actions.add_widget(Action("Selected operation", lambda: self.start(True)))
        actions.add_widget(Action("Cancel calculation", self.cancel_event.set))
        actions.add_widget(Action("Show initial stock", self.reset_display))
        actions.add_widget(Action("Save rest stock", self.save_stock))
        actions.add_widget(Action("Load rest stock", self.load_stock))
        actions.add_widget(Action("Review change impact", self.review_changes))
        self.content.add_widget(actions)
        self.input_status = content_label(
            "No residual baseline · CAD bytes are checked when calculating, reviewing or saving."
        )
        self.content.add_widget(self.input_status)
        self._input_signature = None
        self.note = label(
            "Stock subtraction uses voxel centers. Clearance uses conservative fixture/vise bounds; holders and machine geometry remain unqualified.",
            11,
            MUTED,
            62,
        )
        self.content.add_widget(self.note)
        self.hits = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None)
        self.hits.bind(minimum_height=self.hits.setter("height"))
        self.content.add_widget(self.hits)

    def toggle_details(self):
        self.details_open = not self.details_open
        self.details_header.text = ("−  " if self.details_open else "+  ") + "Material removal & clearance"
        if self.details_open:
            self.add_widget(self.content)
        elif self.content.parent is self:
            self.remove_widget(self.content)

    def _identity(self):
        context = self._context()
        return context["program"], digest_context(context)

    def _context(self):
        return capture_context(self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program)

    def refresh_inputs(self):
        # No disk I/O in the telemetry refresh loop. Explicit actions rehash CAD.
        current = capture_context(
            self.workspace.machine.gcode_viewer, self.workspace.operation_panel.program, verify_assets=False
        )
        signature = (digest_context(current), self.rest_identity)
        if signature == self._input_signature:
            return
        self._input_signature = signature
        if self.rest_context is None:
            self.input_status.text = (
                "No residual baseline · CAD bytes are checked when calculating, reviewing or saving."
            )
        elif signature[0] != digest_context(self.rest_context):
            self.input_status.text = (
                "Setup or tool inputs changed · previous residual is hidden. Review change impact and recompute."
            )
            self.workspace.machine.gcode_viewer.set_rest_stock_geometry(None)
        else:
            self.input_status.text = (
                "Residual matches loaded definitions · CAD bytes are rechecked on calculation, review, save or export."
            )

    def review_changes(self):
        current = self._context()
        changes = context_changes(self.rest_context, current) if self.rest_context else ()
        program = self.workspace.operation_panel.program
        operations = affected_operations(changes, program.operations if program else ())
        problems = asset_problems(current)
        if changes or problems:
            self.workspace.machine.gcode_viewer.set_rest_stock_geometry(None)
            self.note.text = "Residual preview is older; review the changed inputs and recompute."
        content = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
        popup = Popup(title="Geometry change impact", content=content, size_hint=(0.88, 0.85))
        content.add_widget(
            content_label(
                f"{len(changes)} changed inputs · {len(operations)} affected operations\n"
                + (
                    "Residual result is older; recompute before continuing or exporting."
                    if changes
                    else "No changed inputs against the residual result."
                    if self.rest_context
                    else "No residual baseline yet. Calculate material removal to establish one."
                )
            )
        )
        scroll = DesktopScrollView(do_scroll_x=False)
        rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
        rows.bind(minimum_height=rows.setter("height"))
        scroll.add_widget(rows)
        content.add_widget(scroll)
        rows.add_widget(
            content_label(
                f"Program: {current['program'] or 'none'}\nStock: {current['stock']['size_mm']} mm · origin {current['stock']['origin_mm']} mm\n{len(current['tools'])} program tools · {len(current['components'])} CAD component selections"
            )
        )
        if problems:
            rows.add_widget(content_label("CAD requires attention\n" + "\n".join(problems)))
        for change in changes:
            rows.add_widget(content_label(f"{change.title}\nPrevious: {change.before}\nCurrent: {change.after}"))
        if self.rest_context:
            rows.add_widget(
                content_label(
                    "Previous context: "
                    + digest_context(self.rest_context)
                    + "\nCurrent context: "
                    + digest_context(current)
                )
            )
        for operation in operations:

            def inspect(operation=operation):
                popup.dismiss()
                self.workspace.operation_panel.select(operation)
                self.workspace.select("Program")

            rows.add_widget(
                Action(
                    f"Inspect {operation.name} · lines {operation.start_line}–{operation.end_line}",
                    inspect,
                    height=dp(36),
                )
            )
        rows.add_widget(
            content_label(
                "Dependencies identify affected operations, not collision regions. Stock subtraction remains approximate; holder/machine clearance and physical offsets are unqualified."
            )
        )
        content.add_widget(Action("Close", popup.dismiss, height=dp(36)))
        popup.open()
        return popup

    def start(self, selected):
        if self.running:
            self.note.text = "Calculation is already running. Cancel it before starting another."
            return
        try:
            program = self.workspace.operation_panel.program
            if program is None:
                raise ValueError("Choose a parsed local program first")
            operation = self.workspace.operation_panel.selected_operation if selected else None
            if selected and operation is None:
                raise ValueError("Select an operation in the operation list first")
            segments = simulation_segments(
                program, operation.start_line if operation else None, operation.end_line if operation else None
            )
            viewer = self.workspace.machine.gcode_viewer
            tools = simulation_tools(viewer.library_tool_table_mm, {s.tool_id for s in segments})
            setup = viewer.machine_setup
            if setup.stock_size_mm is None:
                raise ValueError("Set stock size and placement in Scene first")
            bounds = AABB(
                Vec3(*setup.stock_origin_mm), Vec3(*(a + b for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm)))
            )
            context = self._context()
            problems = asset_problems(context)
            if problems:
                raise ValueError("\n".join(problems))
            identity = (context["program"], digest_context(context))
            if self.stock_source.text == "Continue rest stock":
                if self.rest_stock is None or self.rest_identity != identity:
                    raise ValueError(
                        "Rest stock belongs to another program/setup/tool selection; start from initial stock or load a matching snapshot"
                    )
                stock = self.rest_stock.clone()
            else:
                stock = StockVolume(bounds, float(self.resolution.text), max_voxels=2_000_000)
            scene = scene_from_geometry(viewer._machine_scene(), setup, bounds)
            unresolved = tuple(
                line
                for line in program.unresolved_motion_lines
                if operation is None or operation.start_line <= line <= operation.end_line
            )
        except (ValueError, TypeError) as exc:
            self.note.text = str(exc)
            return
        self.running = True
        self.cancel_event.clear()
        self.hits.clear_widgets()
        self.note.text = f"Calculating {len(segments):,} resolved segments · {stock.resolution_mm:g} mm voxels…"

        def run():
            try:
                report = simulate(segments, tools, stock, scene, cancelled=self.cancel_event.is_set)
                geometry = stock_geometry(stock)
                error = None
            except (ValueError, ArithmeticError) as exc:
                report, geometry, error = None, None, str(exc)
            Clock.schedule_once(lambda _dt: finish(report, geometry, error), 0)

        def finish(report, geometry, error):
            self.running = False
            if error:
                self.note.text = "Simulation failed: " + error
                return
            if identity != self._identity():
                self.note.text = "Calculation finished for an older setup; result was not applied."
                return
            self.rest_stock, self.report, self.rest_identity = stock, report, identity
            self.rest_context = context
            viewer.set_rest_stock_geometry(geometry)
            self.note.text = (
                f"{'Cancelled · partial result' if report.cancelled else 'Computed preview'} · "
                f"removed {report.removed_volume_mm3:,.1f} mm³ · remaining {report.remaining_volume_mm3:,.1f} mm³\n"
                f"{len(report.candidates)} conservative clearance candidates · physical clearance unqualified"
            )
            model_notes = tuple(
                dict.fromkeys(tool.stock_model_note for tool in tools.values() if tool.stock_model_note)
            )
            if model_notes:
                self.note.text += "\n" + "; ".join(model_notes)
            if unresolved:
                self.note.text += f"\n{len(unresolved)} unresolved travel/motion lines were excluded: " + ", ".join(
                    map(str, unresolved[:8])
                )
            self.note.height = dp(82 if unresolved else 62)
            candidates = tuple(dict.fromkeys(report.candidates))
            for line, component, obstacle in candidates[:12]:
                self.hits.add_widget(
                    Action(
                        f"Line {line} · {component} ↔ {obstacle}",
                        lambda line=line: viewer.set_distance_by_lineidx(line, 0),
                        height=dp(30),
                    )
                )
            if len(candidates) > 12:
                self.hits.add_widget(
                    label(
                        f"{len(candidates) - 12} additional candidates; isolate an operation to inspect.", 10, MUTED, 34
                    )
                )

        threading.Thread(target=run, daemon=True).start()

    def reset_display(self):
        self.workspace.machine.gcode_viewer.set_rest_stock_geometry(None)

    def save_stock(self):
        if self.rest_stock is None:
            self.note.text = "Calculate material removal before saving rest stock."
            return
        if self.rest_identity != self._identity() or not self.rest_context:
            self.note.text = (
                "Residual result is older or lacks its context; review change impact and recompute before saving."
            )
            return

        def save(path):
            try:
                if self.rest_identity != self._identity():
                    raise ValueError("Setup changed while choosing a file; recompute before saving")
                data = {
                    "schema": 2,
                    "program_sha256": self.rest_identity[0],
                    "context": self.rest_context,
                    "context_sha256": self.rest_identity[1],
                    "stock": self.rest_stock.snapshot(),
                }
                Path(path).write_text(json.dumps(data))
                self.note.text = "Saved rest stock · " + path
            except (OSError, ValueError) as exc:
                self.note.text = str(exc)

        self.workspace.choose_profile_file(save, save=True, extension=".cvstock", title="Save residual stock")

    def load_stock(self):
        def load(path):
            try:
                source = Path(path)
                if source.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError("Rest-stock snapshot exceeds 16 MB")
                data = json.loads(source.read_text())
                if not isinstance(data, dict):
                    raise ValueError("Rest-stock snapshot must be an object")
                identity = self._identity()
                if data.get("schema") != 2:
                    raise ValueError("Legacy snapshot has no tool/setup identity; recompute from initial stock")
                context = data["context"]
                if digest_context(context) != data.get("context_sha256"):
                    raise ValueError("Snapshot context digest differs from its recorded inputs")
                if data.get("program_sha256") != identity[0] or data["context_sha256"] != identity[1]:
                    raise ValueError("Snapshot does not match current program, stock, tools, workholding or CAD bytes")
                problems = asset_problems(context)
                if problems:
                    raise ValueError("\n".join(problems))
                stock = StockVolume.from_snapshot(data["stock"])
                setup = self.workspace.machine.gcode_viewer.machine_setup
                expected = AABB(
                    Vec3(*setup.stock_origin_mm),
                    Vec3(*(a + b for a, b in zip(setup.stock_origin_mm, setup.stock_size_mm))),
                )
                if stock.bounds != expected:
                    raise ValueError("Snapshot stock placement differs from current setup")
                self.workspace.machine.gcode_viewer.set_rest_stock_geometry(stock_geometry(stock))
                self.rest_stock, self.rest_identity = stock, identity
                self.rest_context = context
                self.stock_source.text = "Continue rest stock"
                self.note.text = (
                    f"Loaded rest stock · {stock.remaining_volume_mm3:,.1f} mm³ · physical setup unverified"
                )
            except (OSError, ValueError, TypeError, KeyError) as exc:
                self.note.text = "Snapshot not applied: " + str(exc)

        self.workspace.choose_asset_file(load, suffixes=(".cvstock",))
