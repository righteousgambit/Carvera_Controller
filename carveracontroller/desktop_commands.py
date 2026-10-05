"""Searchable desktop actions. Navigation is distinct from machine execution."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass


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


def search_commands(commands: Iterable[Command], query: str) -> list[Command]:
    tokens = query.casefold().split()
    matches = []
    for command in commands:
        title = command.title.casefold()
        haystack = f"{title} {command.detail} {command.keywords}".casefold()
        if all(token in haystack for token in tokens):
            score = sum(3 if token in title else 1 for token in tokens)
            matches.append((-score, command.title.casefold(), command))
    return [entry[2] for entry in sorted(matches, key=lambda entry: entry[:2])]


def workspace_commands(workspace) -> list[Command]:
    w = workspace

    def idle_community():
        if w.app.state != "Idle":
            return "Connect an idle machine to use this workflow"
        if not w.app.is_community_firmware:
            return "Community firmware is required"
        return ""

    commands = [
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

    def open_program_task(task):
        w.select("Job")
        w.program_tasks.choose(task)

    for task, keywords in (
        ("Operations", "operation tree stages tools banks sequence"),
        ("Simulation", "stock removal rest material collision clearance"),
        ("Run record", "recording timeline replay camera receipts history"),
        ("Job package", "portable archive export import transfer"),
        ("View & playback", "toolpath play animation seek"),
    ):
        commands.append(
            Command(
                f"program.task.{task.casefold().replace(' ', '-')}",
                f"Open {task.casefold()}",
                "Review the local job workflow; no machine commands are sent",
                lambda task=task: open_program_task(task),
                keywords,
            )
        )
    for mode in ("Live", "Preview", "Compare"):
        commands.append(
            Command(
                f"view.pose.{mode.casefold()}",
                f"Show {mode.casefold()} machine pose",
                "Change visualization only; live pose requires fresh telemetry",
                lambda mode=mode: w.set_pose_mode(mode),
                "position observed simulation overlay",
            )
        )
    for section, title in w.section_names.items():
        commands.append(
            Command(
                f"section.{section}",
                title,
                "Open workbench section",
                lambda section=section: w.select(section),
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
        self.popup = ModalView(size_hint=(0.72, 0.68), auto_dismiss=True)
        body = Surface(orientation="vertical", padding=dp(16), spacing=dp(10))
        heading = BoxLayout(size_hint_y=None, height=dp(30))
        heading.add_widget(label("Find an action", 18, bold=True, height=30))
        heading.add_widget(Action("Close · Esc", self.popup.dismiss, size_hint_x=None, width=dp(110), height=dp(30)))
        body.add_widget(heading)
        self.input = Field(hint_text="Search actions, tools, probing or workbench sections…")
        body.add_widget(self.input)
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
        self.popup.bind(on_dismiss=lambda *_: Window.unbind(on_key_down=self.keydown))
        Window.bind(on_key_down=self.keydown)
        self.refresh()
        self.popup.open()
        Clock.schedule_once(lambda _: setattr(self.input, "focus", True), 0)

    def refresh(self, preserve=False):
        from kivy.metrics import dp

        from carveracontroller.desktop_components import ACCENT, BG, MUTED, RAISED, TEXT, Action, label

        self.matches = search_commands(self.commands, self.input.text)
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
            row.disabled = bool(reason)
            row.base_color = ACCENT if index == self.selected else RAISED
            row.color = BG if index == self.selected else TEXT
            row._paint()
            self.list.add_widget(row)
            self.rows.append(row)
        if not self.matches:
            self.list.add_widget(label("No actions match. Try ‘probe’, ‘stock’, ‘camera’ or ‘tool’.", 12, MUTED, 48))

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
            self.refresh(preserve=True)
            from kivy.clock import Clock

            Clock.schedule_once(lambda _dt: Clock.schedule_once(self._reveal_selected, 0), 0)
            return True
        if key in (13, 271):
            if self.matches:
                self.execute(self.matches[self.selected])
            return True
        return False
