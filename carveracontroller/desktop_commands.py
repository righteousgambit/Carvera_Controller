"""Searchable desktop actions. Navigation is distinct from machine execution."""

import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from threading import Event


@dataclass(frozen=True)
class Command:
    id: str
    title: str
    detail: str
    action: Callable[[], None]
    keywords: str = ""
    availability: Callable[[], str] = lambda: ""

    def invoke(self) -> bool:
        # Check current state at the gesture, not just when the list was drawn.
        if self.availability():
            return False
        self.action()
        return True


def search_commands(commands: Iterable[Command], query: str, *, cancelled=lambda: False) -> list[Command]:
    tokens = query.casefold().split()
    matches = []
    for command in commands:
        if cancelled():
            return []
        title = command.title.casefold()
        haystack = f"{title} {command.detail} {command.keywords}".casefold()
        if all(
            bool(re.search(r"(?<!\w)" + re.escape(token) + r"(?!\w)", haystack))
            if re.fullmatch(r"(?:t\d+|tool:t\d+|line:\d+)", token)
            else token in haystack
            for token in tokens
        ):
            score = sum(3 if token in title else 1 for token in tokens)
            matches.append((-score, command.title.casefold(), command))
    return [entry[2] for entry in sorted(matches, key=lambda entry: entry[:2])]


def job_operation_commands(workspace) -> list[Command]:
    """Exact job entities, bound to the current analysis rather than a row number."""
    panel = getattr(workspace, "operation_panel", None)
    program = getattr(panel, "program", None)
    return _operation_commands(workspace, panel, program)


def _operation_commands(workspace, panel, program, cancelled=lambda: False) -> list[Command]:
    if program is None:
        return []

    def available():
        return "Job changed · search again" if panel.program is not program else ""

    def open_operation(operation):
        workspace.select("Job")
        workspace.program_tasks.choose("Operations")
        panel.select(operation)

    commands = []
    for index, operation in enumerate(program.operations, 1):
        if cancelled():
            return []
        tools = " ".join(f"T{number}" for number in operation.tool_ids) or "No tool"
        warnings = " · ".join(operation.warnings)
        commands.append(
            Command(
                f"job.operation.{program.file_hash}.{operation.id}",
                f"Operation {index:02d} · {operation.name}",
                f"{tools} · lines {operation.start_line}–{operation.end_line}" + (f" · {warnings}" if warnings else ""),
                partial(open_operation, operation),
                f"operation job tool {tools} "
                + " ".join(f"tool:T{number}" for number in operation.tool_ids)
                + f" line:{operation.start_line} "
                + ("warning " if warnings else ""),
                available,
            )
        )
    return commands


def workspace_commands(workspace) -> list[Command]:
    w = workspace

    def open_inspection_records():
        from carveracontroller.desktop_surface_inspection import open_surface_inspections

        open_surface_inspections(w)

    def idle_community():
        if w.app.state != "Idle":
            return "Connect an idle machine to use this workflow"
        if not w.app.is_community_firmware:
            return "Community firmware is required"
        return ""

    from carveracontroller.desktop_coordinate_review import open_coordinate_review
    from carveracontroller.desktop_layouts import open_layouts

    commands = [
        Command(
            "scene.coordinates",
            "Inspect coordinate chain",
            "Review configured and reported frames without changing machine offsets",
            lambda: open_coordinate_review(w),
            "MCS WCS stock fixture vise jaw tool TLO coordinate transform provenance",
        ),
        Command(
            "workspace.layouts",
            "Workspace layouts",
            "Save and restore pane sizing, camera visibility, view framing and workbench tasks",
            lambda: open_layouts(w),
            "preset arrange layout workspace presentation",
        ),
        Command(
            "inspection.records",
            "Surface inspection records",
            "Review retained nominal features, measurement receipts and pasted tables",
            open_inspection_records,
            "inspection CMM metrology measurements tolerance history batch CSV TSV",
        ),
        Command(
            "tools.compare",
            "Compare tools and calibration",
            "Library, CAM dimensions, reported TLO and raw calibration history",
            lambda: w.tool_comparison.focus(),
            "length offsets diameter measurements history",
        ),
        Command(
            "program.open",
            "Choose program",
            "Inspect a local or machine program",
            w._choose_program,
            "file open cnc gcode",
        ),
        Command(
            "profiles.open",
            "Machine and tool library",
            "Manage machines, cutters and ATC toolsets",
            w._open_profiles,
            "profile cutter mill holder",
        ),
        Command(
            "scene.origin",
            "Set preview origin and stock",
            "Configure local simulation coordinates and stock",
            w._machine_setup,
            "block material setup datum",
        ),
        Command(
            "scene.vise",
            "Position the Mod Vise",
            "Translate, rotate and set the visual jaw opening",
            w._workholding_setup,
            "fixture workholding clamp",
        ),
        Command(
            "view.fit",
            "Fit machine view",
            "Frame the selected machine components",
            w.machine.gcode_viewer.restore_default_view,
            "zoom frame",
        ),
        Command(
            "view.camera",
            "Show or hide camera pane",
            "Keep camera and toolpath together",
            w._toggle_job_camera,
            "webcam ubuntu video",
        ),
        Command(
            "setup.probe",
            "Probe stock and features",
            "Open corner, bore, boss and angle probing",
            w.machine.open_probing_popup,
            "find center datum touch measure",
            idle_community,
        ),
        Command(
            "setup.face",
            "Face a stock surface",
            "Generate facing passes and review the toolpath",
            w.machine.open_facing_popup,
            "skim top flatten hat rough",
            idle_community,
        ),
        Command(
            "setup.inspect",
            "Inspect measured features",
            "Open the CMM measurement workbench",
            w.machine.open_cmm_workbench_popup,
            "bore dimension tolerance metrology",
            idle_community,
        ),
    ]

    from carveracontroller.machine.scene_inspection import COMPONENT_TITLES

    def inspect_component(component):
        # Inspector owns selection history, the Scene transition and scrolling.
        w.object_inspector.select(component)

    for component, title in COMPONENT_TITLES.items():
        commands.append(
            Command(
                f"scene.inspect.{component}",
                f"Inspect {title.casefold()}",
                "Select component geometry, relationships and section controls",
                partial(inspect_component, component),
                "CAD component object assembly section cutaway geometry",
            )
        )

    def inspect_assembly(assembled):
        w.select("Scene")
        w.object_inspector.explode(assembled=assembled)

    commands.extend(
        (
            Command(
                "scene.explode",
                "Explode assembly view",
                "Separate displayed components using the inspector's distance and fit the view",
                partial(inspect_assembly, False),
                "CAD exploded spindle fixture vise stock ATC",
                availability=lambda: (
                    "Choose Preview for exploded inspection; Live and Compare remain assembled"
                    if getattr(w.machine.gcode_viewer, "pose_mode", None) != "Preview"
                    else ""
                ),
            ),
            Command(
                "scene.reassemble",
                "Reassemble component view",
                "Restore assembled display and fit the view; physical placement is unchanged",
                partial(inspect_assembly, True),
                "CAD exploded restore assembly",
            ),
        )
    )

    def open_camera_section(section):
        w.select("Camera")
        w.camera_registration_panel.select_section(section)

    for section, identifier, keywords in (
        ("Source", "source", "ubuntu webcam url connection stream"),
        ("Reference", "reference", "camera capture calibration image points pixels"),
        ("Fit & exchange", "calibration", "camera registration intrinsics fit import export"),
    ):
        commands.append(
            Command(
                f"camera.{identifier}",
                f"Open camera {section.casefold()}",
                "Review camera setup without changing source or machine state",
                partial(open_camera_section, section),
                keywords,
            )
        )

    def open_program_task(task):
        w.select("Job")
        w.program_tasks.choose(task)

    for task, keywords in (
        ("Operations", "operation tree stages tools banks sequence"),
        ("Simulation", "stock removal rest material collision clearance"),
        ("Run record", "recording timeline replay camera receipts history"),
        ("Job package", "portable archive export import transfer setup sheet print tablet handoff"),
        ("View & playback", "toolpath play animation seek"),
    ):
        commands.append(
            Command(
                f"program.task.{task.casefold().replace(' ', '-')}",
                f"Open {task.casefold()}",
                "Review the local job workflow; no machine commands are sent",
                partial(open_program_task, task),
                keywords,
            )
        )
    for mode in ("Live", "Preview", "Compare"):
        commands.append(
            Command(
                f"view.pose.{mode.casefold()}",
                f"Show {mode.casefold()} machine pose",
                "Change visualization only; live pose requires fresh telemetry",
                partial(w.set_pose_mode, mode),
                "position observed simulation overlay",
            )
        )
    for section in ("Signal", "Diagnostics", "Baseline"):

        def open_monitor(section=section):
            w.select("Monitor")
            w.monitor_section_buttons[section].dispatch("on_release")

        commands.append(
            Command(
                f"monitor.{section.casefold()}",
                f"Open spindle {section.casefold()}",
                "Review monitor information; no machine commands are sent",
                open_monitor,
                "rpm telemetry recording quality persistence",
            )
        )
    commands.append(
        Command(
            "monitor.export",
            "Export telemetry diagnostics",
            "Save observed telemetry, recording receipts and UI timing locally",
            w.telemetry_diagnostics.export,
            "spindle recording troubleshooting performance navigation",
            lambda: "A diagnostics export is already pending" if w.telemetry_diagnostics._exporting else "",
        )
    )
    if hasattr(w, "setup_tasks"):

        def open_setup_task(task):
            w.select("Setup")
            w.setup_tasks.show(task)

        for task, keywords in (
            ("Tools", "cutter calibration ATC pockets magazine assembly"),
            ("Datum", "origin probe work offsets coordinate verify inspection"),
            ("Surface", "facing height map surface variation flatness"),
            ("Holes", "drill bore threadmill attachment bolt imperial"),
            ("Repeat", "batch repeated parts placement tool bank"),
        ):
            commands.append(
                Command(
                    "setup.task." + task.casefold(),
                    "Open setup " + task.casefold(),
                    w.setup_tasks.descriptions[task],
                    partial(open_setup_task, task),
                    keywords,
                )
            )
    if hasattr(w, "machine_tasks"):

        def open_machine_task(task):
            w.select("Settings")
            w.machine_tasks.show(task)

        for task, keywords in (
            ("Connect", "network USB Wi-Fi machine connection"),
            ("Health", "response latency UI performance timing stalls diagnostics"),
            ("Kinematics", "joint rotary five-axis TCP candidate trajectory"),
            ("Capabilities", "backend configured observed exercised unsupported"),
            ("Captures", "commissioning historical HAL parameters pins signals before after comparison"),
            ("Preferences", "language maintenance firmware documentation settings"),
        ):
            commands.append(
                Command(
                    "machine.task." + task.casefold(),
                    "Open machine " + task.casefold(),
                    w.machine_tasks.descriptions[task],
                    partial(open_machine_task, task),
                    keywords,
                )
            )
    for section, title in w.section_names.items():
        commands.append(
            Command(
                f"section.{section}",
                title,
                "Open workbench section",
                partial(w.select, section),
                f"navigate workspace {section}",
            )
        )
    return commands


class CommandPalette:
    def __init__(self, workspace):
        self.workspace = workspace
        self.commands = workspace_commands(workspace)
        self.popup = None
        self.selected = 0
        self._entity_program = None
        self._entity_commands = []
        self.search_generation = 0
        self.search_pending = False
        self._cancel_search = Event()
        self._search_future = None

    def open(self):
        from kivy.clock import Clock
        from kivy.core.window import Window
        from kivy.metrics import dp
        from kivy.uix.boxlayout import BoxLayout
        from kivy.uix.modalview import ModalView

        from carveracontroller.desktop_components import MUTED, Action, DesktopScrollView, Field, Surface, label

        self.workspace.machine.toggle_keyboard_jog_control(disable=True)
        if self.popup is not None and self.popup.parent:
            self.input.focus = True
            return
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="workspace-search")
        self.popup = ModalView(size_hint=(0.72, 0.68), auto_dismiss=True)
        body = Surface(orientation="vertical", padding=dp(16), spacing=dp(10))
        heading = BoxLayout(size_hint_y=None, height=dp(30))
        heading.add_widget(label("Find in workspace", 18, bold=True, height=30))
        heading.add_widget(Action("Close · Esc", self.popup.dismiss, size_hint_x=None, width=dp(110), height=dp(30)))
        body.add_widget(heading)
        self.input = Field(hint_text="Search actions or job operations: name, T1, warning, line:24…")
        body.add_widget(self.input)
        self.result_note = label("", 11, MUTED, 28)
        body.add_widget(self.result_note)
        self.list = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
        self.list.bind(minimum_height=self.list.setter("height"))
        self.scroll = DesktopScrollView(do_scroll_x=False, bar_width=dp(9))
        self.scroll.add_widget(self.list)
        body.add_widget(self.scroll)
        body.add_widget(
            label(
                "Up/Down Select    Enter Open    Esc Close · machine state is checked again when selected",
                10,
                MUTED,
                30,
            )
        )
        self.popup.add_widget(body)
        self.input.bind(text=lambda *_: self.refresh())
        self.popup.bind(on_dismiss=self._dismissed)
        Window.bind(on_key_down=self.keydown)
        self.popup.open()
        self.refresh()
        Clock.schedule_once(lambda _: setattr(self.input, "focus", True), 0)

    def _dismissed(self, *_):
        from kivy.core.window import Window

        self.search_generation += 1
        self._cancel_search.set()
        self.search_pending = False
        self._executor.shutdown(wait=False, cancel_futures=True)
        Window.unbind(on_key_down=self.keydown)

    def refresh(self, preserve=False):
        from kivy.clock import Clock

        self._cancel_search.set()
        if self._search_future is not None:
            self._search_future.cancel()
        self._cancel_search = cancel = Event()
        self.search_generation += 1
        generation = self.search_generation
        panel = getattr(self.workspace, "operation_panel", None)
        program = getattr(panel, "program", None)
        query = self.input.text
        cached = self._entity_commands if program is self._entity_program else None
        actions = tuple(self.commands)
        # Publish cheap action matches immediately; expensive job work has one
        # owner and at most one queued successor. No widgets are touched there.
        self.matches = search_commands(actions, query)[:40]
        self.search_pending = True
        self.result_note.text = "Searching current job… · actions available below"
        self._render(preserve)

        def work():
            try:
                entries = (
                    cached if cached is not None else _operation_commands(self.workspace, panel, program, cancel.is_set)
                )
                if cancel.is_set():
                    return
                matches = search_commands((*actions, *entries), query, cancelled=cancel.is_set)
                if not cancel.is_set():
                    Clock.schedule_once(lambda _dt: deliver(entries, matches), 0)
            except Exception as exc:
                # Keep local actions usable and expose a failed search rather
                # than leaving an orphaned "Searching" state indefinitely.
                message = f"Job search unavailable: {type(exc).__name__} · actions remain available"
                Clock.schedule_once(lambda _dt: failed(message), 0)

        def failed(message):
            if generation == self.search_generation and self.popup.parent:
                if getattr(panel, "program", None) is not program:
                    self.refresh()
                    return
                self.search_pending = False
                self.result_note.text = message

        def deliver(entries, matches):
            if generation != self.search_generation or not self.popup.parent:
                return
            if getattr(panel, "program", None) is not program:
                self.refresh()
                return
            selected_id = self.matches[self.selected].id if self.matches else None
            self._entity_program, self._entity_commands = program, entries
            self.matches = matches[:40]
            self.selected = next((i for i, item in enumerate(self.matches) if item.id == selected_id), 0)
            self.search_pending = False
            self.result_note.text = (
                f"{len(matches)} matches · first 40 shown; refine your search"
                if len(matches) > 40
                else f"{len(matches)} matches · actions and current job operations"
            )
            self._render(preserve=True)

        self._search_future = self._executor.submit(work)

    def _render(self, preserve=False):
        from kivy.metrics import dp

        from carveracontroller.desktop_components import ACCENT, BG, MUTED, RAISED, TEXT, Action, label

        self.selected = min(self.selected, max(0, len(self.matches) - 1)) if preserve else 0
        self.list.clear_widgets()
        self.rows = []
        if not preserve:
            self.scroll.scroll_y = 1
        for index, command in enumerate(self.matches):
            reason = command.availability()
            text = f"{command.title}\n{reason or command.detail}"
            row = Action(text, lambda command=command: self.execute(command), height=dp(58), halign="left")
            row.text_size = (max(1, row.width - dp(20)), None)
            row.bind(width=lambda row, width: setattr(row, "text_size", (width - dp(20), None)))
            row.bind(texture_size=lambda row, size: setattr(row, "height", max(dp(58), size[1] + dp(16))))
            row.disabled = bool(reason)
            row.base_color = ACCENT if index == self.selected else RAISED
            row.color = BG if index == self.selected else TEXT
            row._paint()
            self.list.add_widget(row)
            self.rows.append(row)
        if not self.matches:
            self.list.add_widget(label("No matches. Try an operation name, ‘T1’, ‘camera’ or ‘stock’.", 12, MUTED, 48))

    def execute(self, command):
        if command.availability():
            self.refresh(preserve=True)
            return False
        self.popup.dismiss()
        return command.invoke()

    def _reveal_selected(self, _dt):
        if not self.popup or not self.popup.parent or not self.rows:
            return
        if self.list.height <= self.scroll.height:
            self.scroll.scroll_y = 1
        else:
            self.scroll.scroll_to(self.rows[self.selected], animate=False)

    def keydown(self, _window, key, _scancode, _text, _modifiers):
        if not self.popup or not self.popup.parent:
            return False
        if key == 27:
            self.popup.dismiss()
            return True
        if key in (273, 274) and self.matches:
            self.selected = (self.selected + (-1 if key == 273 else 1)) % len(self.matches)
            self._render(preserve=True)
            from kivy.clock import Clock

            Clock.schedule_once(lambda _dt: Clock.schedule_once(self._reveal_selected, 0), 0)
            return True
        if key in (13, 271):
            if self.matches:
                self.execute(self.matches[self.selected])
            return True
        return False
