"""Searchable desktop actions. Navigation is distinct from machine execution."""

import heapq
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from itertools import chain
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


def _query_terms(query: str) -> tuple[list[str], dict[str, re.Pattern[str]]]:
    # Quotes bind a phrase while ordinary apostrophes and path backslashes stay
    # literal. An unfinished phrase is searchable as the operator types it.
    tokens = []
    phrases = set()
    for match in re.finditer(r""""[^"]*(?:"|$)|'[^']*(?:'|$)|\S+""", query.casefold()):
        token = match.group()
        if token[0] in ('"', "'"):
            token = token[1:-1] if len(token) > 1 and token[-1] == token[0] else token[1:]
            token = token.strip()
            phrases.add(token)
        if token:
            tokens.append(token)
    exact = {
        token: re.compile(r"(?<!\w)" + re.escape(token) + r"(?!\w)")
        for token in tokens
        if token in phrases
        or re.fullmatch(
            r"(?:t\d+|tool:t\d+|(?:line|operation):\d+|(?:feature|receipt|session):[\w-]+|(?:sequence|connection):\d+)",
            token,
        )
    }
    return tokens, exact


def search_commands(commands: Iterable[Command], query: str, *, cancelled=lambda: False) -> list[Command]:
    tokens, exact = _query_terms(query)
    matches = []
    for command in commands:
        if cancelled():
            return []
        title = command.title.casefold()
        haystack = f"{title} {command.detail} {command.keywords}".casefold()
        if all(exact[token].search(haystack) if token in exact else token in haystack for token in tokens):
            score = sum(3 if token in title else 1 for token in tokens)
            matches.append((-score, command.title.casefold(), command))
    return [entry[2] for entry in sorted(matches, key=lambda entry: entry[:2])]


def search_command_page(commands, query, limit=40, *, cancelled=lambda: False):
    """Count all matches while retaining only the best bounded result page."""
    tokens, exact = _query_terms(query)
    count = 0

    def scored():
        nonlocal count
        for index, command in enumerate(commands):
            if cancelled():
                return
            title = command.title.casefold()
            haystack = f"{title} {command.detail} {command.keywords}".casefold()
            if all(exact[token].search(haystack) if token in exact else token in haystack for token in tokens):
                count += 1
                yield (-sum(3 if token in title else 1 for token in tokens), title, index, command)

    page = [entry[3] for entry in heapq.nsmallest(limit, scored())]
    return ([], 0) if cancelled() else (page, count)


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
                + f" line:{operation.start_line} operation:{index} "
                + ("warning " if warnings else ""),
                available,
            )
        )
    return commands


def iter_tool_commands(workspace, panel, program, library, cam, cancelled=lambda: False, *, cam_scale=1.0):
    """Detached nominal/programmed tools; opening a result never selects a physical tool."""
    viewer = workspace.machine.gcode_viewer
    numbers = set(library) | set(cam)
    if program is not None:
        numbers.update(number for operation in program.operations for number in operation.tool_ids)
    for number in sorted(numbers):
        if cancelled():
            return
        nominal, programmed = library.get(number), cam.get(number)
        description = getattr(nominal, "description", "") or getattr(programmed, "description", "") or "Unnamed tool"
        sources = []
        if nominal is not None:
            sources.append("Library geometry · mm")
        if programmed is not None:
            sources.append("CAM geometry · program units")
        if not sources:
            sources.append("Programmed tool · geometry missing")

        def available(number=number, nominal=nominal, programmed=programmed):
            if (
                workspace.machine.gcode_viewer is not viewer
                or getattr(panel, "program", None) is not program
                or viewer.library_tool_table_mm.get(number) != nominal
                or viewer.tool_table.get(number) != programmed
                or getattr(viewer, "tool_unit_scale", 1.0) != cam_scale
            ):
                return "Tool/job changed · search again"
            return ""

        def open_tool(number=number):
            comparison = workspace.tool_comparison
            comparison.search.text = ""
            comparison.choose(number)
            comparison.focus()

        keywords = " ".join(
            str(getattr(tool, field, ""))
            for tool in (nominal, programmed)
            if tool is not None
            for field in ("vendor", "product_id", "type_name")
        )
        yield Command(
            f"job.tool.{number}",
            f"Tool T{number} · {description}",
            " · ".join(sources) + " · physical identity unverified",
            open_tool,
            f"tool:T{number} cutter calibration assembly {keywords}",
            available,
        )


def iter_inspection_commands(workspace, store, features, cancelled=lambda: False):
    """Read-only feature/receipt navigation bound to a retained-store snapshot."""

    def available():
        current = getattr(workspace, "surface_inspection_store", None)
        return (
            "Inspection records changed · search again"
            if current is not store or store.features is not features or store.error
            else ""
        )

    def open_record(feature_id, receipt_id=None):
        from carveracontroller.desktop_surface_inspection import open_surface_inspections

        open_surface_inspections(workspace, feature_id, receipt_id)

    for feature in features:
        if cancelled():
            return
        identity = feature["id"]
        title = f"{feature['part']} · {feature['name']}"
        yield Command(
            f"inspection.feature.{identity}",
            f"Inspection feature · {title}",
            f"{len(feature['samples'])} retained receipts · {identity}",
            partial(open_record, identity),
            f"measurement feature:{identity}",
            available,
        )
        for sample in feature["samples"]:
            if cancelled():
                return
            receipt_id = sample["id"]
            yield Command(
                f"inspection.receipt.{receipt_id}",
                f"Measurement receipt · {sample['source_ref']}",
                f"{title} · {sample['kind']} · {receipt_id}",
                partial(open_record, identity, receipt_id),
                f"receipt:{receipt_id} feature:{identity} {sample['registration_ref']} "
                f"{sample['calibration_ref']} {sample['observed_at']}",
                available,
            )


def inspection_commands(workspace, store, features, cancelled=lambda: False):
    return list(iter_inspection_commands(workspace, store, features, cancelled))


def coordinate_commands(workspace):
    """Search actual snapshot paths; selection refreshes their evidence context."""
    from carveracontroller.desktop_coordinate_review import coordinate_snapshot, open_coordinate_review

    viewer = workspace.machine.gcode_viewer
    setup = getattr(viewer, "machine_setup", None)
    if setup is None:
        return []
    try:
        rows, _identity = coordinate_snapshot(workspace, (0, 0, 0))
    except (ValueError, TypeError):
        return []
    controller = workspace.machine.controller

    def available():
        return (
            "Machine/setup changed · search again"
            if viewer.machine_setup is not setup or workspace.machine.controller is not controller
            else ""
        )

    return [
        Command(
            "coordinate.path." + row.name.casefold().replace(" ", "-"),
            f"Coordinate path · {row.name}",
            row.source + " · opens a fresh snapshot at review point zero",
            partial(open_coordinate_review, workspace, row.name),
            "frame coordinate offset datum " + row.relation,
            available,
        )
        for row in rows
    ]


def iter_alarm_commands(workspace, panel, replay, events, cancelled=lambda: False):
    """Search exact recorded alarm observations, never infer a live alarm."""
    if replay is None:
        return
    session = replay.payload["session_id"]
    for index, event in enumerate(events):
        if cancelled():
            return
        state = event["data"].get("state", "") if event["kind"] == "status" else ""
        if not re.match(r"^alarm(?:$|[:\s])", state, re.IGNORECASE):
            continue

        snapshot = deepcopy(event)

        def available(index=index, event=event, snapshot=snapshot):
            return (
                "Recording changed · search again"
                if getattr(workspace, "run_recording_panel", None) is not panel
                or panel.replay is not replay
                or replay.payload["events"] is not events
                or index >= len(events)
                or events[index] is not event
                or event != snapshot
                or replay.payload["session_id"] != session
                else ""
            )

        sequence, generation = event["sequence"], event["generation"]
        yield Command(
            f"recording.alarm.{session}.{generation}.{sequence}",
            f"Recorded alarm · {state} · event {index + 1}",
            f"Session {session} · sequence {sequence} · connection {generation} · UTC epoch {event['utc_at']:.3f}",
            partial(panel.seek_recorded_event, replay, index),
            f"alarm replay recording session:{session} sequence:{sequence} connection:{generation}",
            available,
        )


def recording_workflow_commands(workspace):
    """Local archive actions retain the recording selection shown in search."""
    panel = getattr(workspace, "run_recording_panel", None)
    if panel is None:
        return []
    replay = panel.replay
    buffer = workspace.machine.controller.run_recording
    archive = panel.camera_archive

    def available(camera=False):
        if workspace.run_recording_panel is not panel or panel.busy:
            return "Recording task changed or busy · search again"
        if panel.replay is not replay or workspace.machine.controller.run_recording is not buffer:
            return "Recording selection changed · search again"
        if camera and (
            archive is None
            or panel.camera_archive is not archive
            or replay is None
            or archive.header["recording_session_id"] != replay.payload["session_id"]
        ):
            return "Select the matching recorded camera part first"
        return ""

    def open_action(action, camera=False):
        workspace.select("Job")
        workspace.program_tasks.choose("Run record")
        if camera and not panel.camera_section.expanded:
            panel.camera_section.toggle.dispatch("on_release")
        getattr(panel, action)()

    return [
        Command(
            "recording." + action,
            title,
            "Local recording files · opens Run record; no machine commands",
            partial(open_action, action, camera),
            keywords,
            partial(available, camera),
        )
        for action, title, keywords, camera in (
            ("export", "Export run recording", "export recording save status archive cvrun", False),
            ("import_recording", "Open run recording", "import recording status archive cvrun", False),
            ("export_camera", "Export recorded camera bundle", "export camera frames jpeg cvcamera", True),
        )
    ]


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
            "program.close_local",
            "Close local preview",
            "Clear desktop program context while retaining live monitoring",
            w.close_local_preview,
            "file close clear unload program preview",
            availability=lambda: "" if w.can_close_local_preview() else "No idle local-only preview available",
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
    for section in ("Signal", "Decision", "Diagnostics", "Baseline"):

        def open_monitor(section=section):
            w.select("Monitor")
            w.monitor_section_buttons[section].dispatch("on_release")

        commands.append(
            Command(
                f"monitor.{section.casefold()}",
                f"Open spindle {section.casefold()}",
                "Review monitor information; no machine commands are sent",
                open_monitor,
                "rpm telemetry recording quality persistence adaptive limiting factor response explanation",
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
            ("Channels", "mill turn dual spindle shared axis turret barrier sync chuck grip cutoff transfer datum"),
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
    commands.extend(recording_workflow_commands(w))
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
        self.input = Field(hint_text='Search: name, "exact phrase", T1, operation:12, line:20, receipt:ID…')
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
        viewer = self.workspace.machine.gcode_viewer
        # Capture membership cheaply here; detach scalar tool geometry on the
        # search worker. Each result checks its detached values at activation.
        library = dict(viewer.library_tool_table_mm)
        cam = dict(viewer.tool_table)
        cam_scale = viewer.tool_unit_scale
        cached = self._entity_commands if program is self._entity_program else None
        store = getattr(self.workspace, "surface_inspection_store", None)
        features = store.features if store is not None else None
        recording_panel = getattr(self.workspace, "run_recording_panel", None)
        replay = getattr(recording_panel, "replay", None)
        events = replay.payload["events"] if replay is not None else ()
        actions = (
            *(command for command in self.commands if not command.id.startswith("recording.")),
            *recording_workflow_commands(self.workspace),
            *coordinate_commands(self.workspace),
        )
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
                # First file read stays on the worker. Loaded stores replace their
                # feature list on save, so the captured list is a stable snapshot.
                from carveracontroller.machine.surface_inspection import SurfaceInspectionStore

                record_store = store if store is not None else SurfaceInspectionStore()
                record_features = features if features is not None else record_store.features
                records = iter_inspection_commands(self.workspace, record_store, record_features, cancel.is_set)
                tools = iter_tool_commands(
                    self.workspace, panel, program, deepcopy(library), deepcopy(cam), cancel.is_set, cam_scale=cam_scale
                )
                alarms = iter_alarm_commands(self.workspace, recording_panel, replay, events, cancel.is_set)
                matches, count = search_command_page(
                    chain(actions, entries, tools, records, alarms), query, cancelled=cancel.is_set
                )
                if not cancel.is_set():
                    Clock.schedule_once(lambda _dt: deliver(entries, matches, count, record_store, record_features), 0)
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

        def deliver(entries, matches, count, record_store, record_features):
            if generation != self.search_generation or not self.popup.parent:
                return
            if getattr(panel, "program", None) is not program:
                self.refresh()
                return
            if getattr(recording_panel, "replay", None) is not replay:
                self.refresh()
                return
            current_store = getattr(self.workspace, "surface_inspection_store", None)
            if current_store is None:
                if getattr(self.workspace, "inspection_busy", False):
                    self.search_pending = False
                    self.result_note.text = "Inspection records loading elsewhere · search again when ready"
                    return
                self.workspace.surface_inspection_store = record_store
            elif current_store is not record_store or record_store.features is not record_features:
                self.refresh()
                return
            selected_id = self.matches[self.selected].id if self.matches else None
            self._entity_program, self._entity_commands = program, entries
            self.matches = matches[:40]
            self.selected = next((i for i, item in enumerate(self.matches) if item.id == selected_id), 0)
            self.search_pending = False
            self.result_note.text = (
                f"{count} matches · first 40 shown; refine your search"
                if count > 40
                else f"{count} matches · actions, job, tools, frames, measurements, recorded alarms"
            ) + (" · inspection file unavailable" if record_store.error else "")
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
        from kivy.core.window import Window
        from kivy.uix.modalview import ModalView

        if not self.popup or not self.popup.parent or self.popup not in Window.children:
            return False
        if any(isinstance(child, ModalView) for child in Window.children[: Window.children.index(self.popup)]):
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
