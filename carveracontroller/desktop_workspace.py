"""Desktop workflow shell over the existing controller and preflight actions.

Navigation and telemetry are read-only. Machine actions use the same guarded
controller paths as the original UI; adaptive control remains shadow-only.
"""

import time

from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.graphics import Color, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.splitter import Splitter
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from carveracontroller.adaptive_popup import Trace
from carveracontroller.CNC import CNC
from carveracontroller.machine.webcam import DEFAULT_CAMERA_URL, WebcamClient
from carveracontroller.Utils import digitize_v
from carveracontroller.webcam_view import WebcamTexture

BG = (0.055, 0.071, 0.098, 1)
PANEL = (0.083, 0.106, 0.141, 1)
RAISED = (0.118, 0.149, 0.192, 1)
TEXT = (0.91, 0.94, 0.98, 1)
MUTED = (0.57, 0.65, 0.75, 1)
ACCENT = (0.27, 0.80, 0.73, 1)
DANGER = (0.77, 0.22, 0.29, 1)
AMBER = (0.98, 0.72, 0.32, 1)


class Surface(BoxLayout):
    def __init__(self, color=PANEL, radius=12, **kwargs):
        super().__init__(**kwargs)
        with self.canvas.before:
            self._color = Color(*color)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(radius)])
        self.bind(pos=self._update_shape, size=self._update_shape)

    def _update_shape(self, *_args):
        self._shape.pos, self._shape.size = self.pos, self.size


def label(text, size=14, color=TEXT, height=26, **kwargs):
    kwargs.setdefault("halign", "left")
    item = Label(
        text=text,
        font_name="Roboto",
        font_size=sp(size),
        color=color,
        size_hint_y=None,
        height=dp(height),
        valign="middle",
        **kwargs,
    )
    item.bind(size=lambda obj, value: setattr(obj, "text_size", value))
    return item


class Action(Button):
    hovered = BooleanProperty(False)

    def __init__(self, text, action=None, primary=False, danger=False, **kwargs):
        self.base_color = DANGER if danger else ACCENT if primary else RAISED
        kwargs.setdefault("height", dp(40))
        super().__init__(
            text=text,
            font_name="Roboto",
            font_size=sp(13),
            background_normal="",
            background_down="",
            background_disabled_normal="",
            background_color=(0, 0, 0, 0),
            color=BG if primary else TEXT,
            disabled_color=MUTED,
            size_hint_y=None,
            **kwargs,
        )
        with self.canvas.before:
            self._fill = Color(*self.base_color)
            self._shape = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(7)])
        self.bind(pos=self._paint, size=self._paint, state=self._paint, disabled=self._paint, hovered=self._paint)
        if action:
            self.bind(on_release=lambda _button: action())

    def _paint(self, *_args):
        factor = 0.55 if self.disabled else 0.8 if self.state == "down" else 1.16 if self.hovered else 1
        self._fill.rgba = tuple(c * factor for c in self.base_color[:3]) + (1,)
        self._shape.pos, self._shape.size = self.pos, self.size


class Metric(Surface):
    def __init__(self, title, value="—", detail="", accent=TEXT, **kwargs):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(3), **kwargs)
        self.add_widget(label(title.upper(), 10, MUTED, 18))
        self.value = label(value, 25, accent, 34)
        self.detail = label(detail, 11, MUTED, 18)
        self.add_widget(self.value)
        self.add_widget(self.detail)


class DesktopWorkspace(Surface):
    pages = (
        ("Overview", "Overview"),
        ("Setup", "Setup & tools"),
        ("Job", "Job workspace"),
        ("Monitor", "Spindle monitor"),
        ("Console", "Command console"),
        ("Camera", "Ubuntu camera"),
        ("Settings", "Settings"),
    )
    descriptions = {
        "Camera": ("Ubuntu camera", "Live view from the Insta360 Link 2 • independent of CNC control."),
        "Overview": ("Machine overview", "Your machine, position and next step in one place."),
        "Setup": ("Setup & tools", "Establish the work coordinate system before reviewing a job."),
        "Job": ("Job workspace", "Inspect the toolpath, select a program and review setup before starting."),
        "Monitor": ("Spindle monitor", "Live RPM and drive effort with experimental feed proposals."),
        "Console": (
            "Command console",
            "Inspect responses and send individual commands. Control + M opens this workspace.",
        ),
        "Settings": ("Settings & connection", "Connection options, controller preferences and machine diagnostics."),
    }

    def __init__(self, root, app, **kwargs):
        super().__init__(color=BG, radius=0, orientation="vertical", **kwargs)
        self.machine, self.app = root, app
        camera_url = Config.get("carvera", "webcam_snapshot_url", fallback=DEFAULT_CAMERA_URL)
        try:
            self.camera_client = WebcamClient(camera_url)
        except ValueError:
            self.camera_client = WebcamClient(DEFAULT_CAMERA_URL)
        self.camera_texture = WebcamTexture()
        self.camera_status_labels = []
        self.guards = []
        self.nav = {}
        self._build_header()
        body = BoxLayout(spacing=dp(24), padding=(dp(16), dp(20), dp(24), dp(16)))
        rail = self._build_rail()
        body.add_widget(rail)
        main = BoxLayout(orientation="vertical", spacing=dp(18))
        heading = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66))
        self.heading = label("Machine overview", 26, height=38)
        self.description = label("", 13, MUTED, 26)
        heading.add_widget(self.heading)
        heading.add_widget(self.description)
        main.add_widget(heading)
        self.workspaces = ScreenManager(transition=NoTransition())
        main.add_widget(self.workspaces)
        body.add_widget(main)
        self.add_widget(body)
        self._build_overview()
        self._build_setup()
        self._build_job()
        self._build_monitor()
        self._build_console()
        self._build_camera()
        self._build_settings()
        self._build_footer()
        # Existing menu/file callbacks still change the original screen manager.
        root.content.bind(current=self._legacy_navigation)
        app.bind(state=self._state_changed, playing=self._state_changed)
        app.bind(selected_local_filename=self._program_changed, selected_remote_filename=self._program_changed)
        app.bind(invert_y_axis_jogging=self._update_y_placement)
        self.select("Overview")
        self.event = Clock.schedule_interval(self.refresh, 0.2)
        Window.bind(mouse_pos=self._hover, on_focus=self._window_focus)
        self.refresh(0)

    def _state_changed(self, *_args):
        self.refresh(0)

    def _hover(self, _window, position):
        for item in self.walk():
            if isinstance(item, Action):
                x, y = item.to_widget(*position)
                item.hovered = not item.disabled and 0 <= x - item.x <= item.width and 0 <= y - item.y <= item.height

    def _window_focus(self, _window, focused):
        if not focused and self.machine.keyboard_jog_control:
            self.machine.toggle_keyboard_jog_control(disable=True)

    def dispose(self):
        self.event.cancel()
        self.camera_client.stop()
        self.machine.content.unbind(current=self._legacy_navigation)
        self.app.unbind(
            state=self._state_changed,
            playing=self._state_changed,
            selected_local_filename=self._program_changed,
            selected_remote_filename=self._program_changed,
            invert_y_axis_jogging=self._update_y_placement,
        )
        Window.unbind(mouse_pos=self._hover, on_focus=self._window_focus)

    def _guarded(self, text, callback, guard, **kwargs):
        button = Action(text, lambda: callback() if callback and guard() else None, **kwargs)
        self.guards.append((button, guard))
        return button

    def _build_header(self):
        header = Surface(radius=0, padding=(dp(24), dp(12)), spacing=dp(20), size_hint_y=None, height=dp(76))
        brand = BoxLayout(orientation="vertical", size_hint_x=None, width=dp(174))
        brand.add_widget(label("CARVERA", 19, height=28, bold=True))
        brand.add_widget(label("DESKTOP WORKSPACE", 9, MUTED, 18))
        header.add_widget(brand)
        status = BoxLayout(orientation="vertical")
        self.state_label = label("Disconnected", 16, ACCENT, 26, bold=True)
        self.connection_label = label("Connect a machine to begin", 11, MUTED, 20)
        status.add_widget(self.state_label)
        status.add_widget(self.connection_label)
        header.add_widget(status)
        self.connect_button = Action("Connection", self._connection_menu, size_hint_x=None, width=dp(112))
        header.add_widget(self.connect_button)
        self.hold_button = self._guarded(
            "Feed hold",
            self._feed_hold,
            lambda: self.app.state in ("Run", "Idle", "Hold"),
            size_hint_x=None,
            width=dp(120),
        )
        header.add_widget(self.hold_button)
        header.add_widget(
            self._guarded(
                "STOP",
                self.machine.controller.estopCommand,
                lambda: self.connected,
                danger=True,
                size_hint_x=None,
                width=dp(94),
            )
        )
        self.add_widget(header)

    @property
    def connected(self):
        return self.app.state not in ("N/A", "", "Disconnected")

    def _connection_menu(self):
        self.machine.status_drop_down.open(self.connect_button)

    def _feed_hold(self):
        self.machine.controller.toggleFeedholdCommand(self.app.state == "Hold")

    def _build_rail(self):
        rail = BoxLayout(orientation="vertical", spacing=dp(7), size_hint_x=None, width=dp(174))
        rail.add_widget(label("WORKSPACE", 10, MUTED, 26))
        for key, text in self.pages:
            button = Action(text, lambda key=key: self.select(key))
            button.halign = "left"
            button.padding = (dp(14), 0)
            button.valign = "middle"
            button.bind(size=lambda item, size: setattr(item, "text_size", (size[0] - dp(28), size[1])))
            self.nav[key] = button
            rail.add_widget(button)
        rail.add_widget(Widget())
        self.rail_note = label("SPINDLE MONITOR\nShadow only", 11, MUTED, 48)
        rail.add_widget(self.rail_note)
        rail.add_widget(label("Community Controller", 11, MUTED, 24))
        return rail

    def _page(self, name, scroll=False):
        content = BoxLayout(orientation="vertical", spacing=dp(18))
        screen = Screen(name=name)
        if scroll:
            content.size_hint_y = None
            content.bind(minimum_height=content.setter("height"))
            view = ScrollView(do_scroll_x=False, bar_width=dp(5))
            view.add_widget(content)
            screen.add_widget(view)
        else:
            screen.add_widget(content)
        self.workspaces.add_widget(screen)
        return content

    def _section(self, title, subtitle, height=None):
        section = Surface(orientation="vertical", padding=dp(18), spacing=dp(8))
        if height:
            section.size_hint_y, section.height = None, dp(height)
        section.add_widget(label(title, 17, height=28, bold=True))
        if subtitle:
            section.add_widget(label(subtitle, 12, MUTED, 28))
        return section

    def _build_overview(self):
        page = self._page("Overview", scroll=True)
        metrics = GridLayout(cols=3, spacing=dp(14), size_hint_y=None, height=dp(100))
        self.rpm_metric = Metric("Spindle", detail="Actual / commanded RPM", accent=ACCENT)
        self.feed_metric = Metric("Feed", detail="mm/min • override")
        self.tool_metric = Metric("Active tool", detail="Tool length offset")
        for tile in (self.rpm_metric, self.feed_metric, self.tool_metric):
            metrics.add_widget(tile)
        page.add_widget(metrics)
        row = BoxLayout(spacing=dp(18), size_hint_y=None, height=dp(280))
        position = self._section("Position", "Work / machine coordinates • mm")
        position.padding, position.spacing = dp(14), dp(6)
        self.position_values = {}
        self.machine_values = {}
        for axis, color in (("X", (0.95, 0.55, 0.57, 1)), ("Y", ACCENT), ("Z", (0.42, 0.69, 1, 1))):
            line = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(12))
            line.add_widget(label(axis, 19, color, 36, size_hint_x=None, width=dp(28)))
            work = label("—", 23, height=36)
            machine = label("Machine —", 12, MUTED, 36, halign="right")
            self.position_values[axis], self.machine_values[axis] = work, machine
            line.add_widget(work)
            line.add_widget(machine)
            position.add_widget(line)
        self.wcs_label = label("Work coordinate system —", 12, MUTED, 24)
        position.add_widget(self.wcs_label)
        row.add_widget(position)
        jog = self._section("Move the machine", "Press an axis to move")
        jog.padding, jog.spacing = dp(14), dp(6)
        self.jog_help = jog.children[0]
        steps = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(28))
        steps.add_widget(label("XY step", 11, MUTED, 28))
        self.xy_step = Spinner(
            text=self.app.jog_step_xy,
            values=("10", "1", "0.1", "0.01", "0.005"),
            font_name="Roboto",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(28),
        )
        self.xy_step.bind(text=lambda _w, value: self._set_step("xy", value))
        steps.add_widget(self.xy_step)
        steps.add_widget(label("Z step", 11, MUTED, 28))
        self.z_step = Spinner(
            text=self.app.jog_step_z,
            values=("10", "1", "0.1", "0.01", "0.005"),
            font_name="Roboto",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(28),
        )
        self.z_step.bind(text=lambda _w, value: self._set_step("z", value))
        steps.add_widget(self.z_step)
        jog.add_widget(steps)
        controls = BoxLayout(spacing=dp(16), size_hint_y=None, height=dp(108))
        grid = GridLayout(cols=3, spacing=dp(6))
        self.jog_buttons = []
        for axis, direction in (
            (None, 0),
            ("Y", -1),
            (None, 0),
            ("X", -1),
            (None, 0),
            ("X", 1),
            (None, 0),
            ("Y", 1),
            (None, 0),
        ):
            if axis:
                button = self._jog_button(axis, direction)
                grid.add_widget(button)
            else:
                grid.add_widget(Widget())
        controls.add_widget(grid)
        vertical = BoxLayout(orientation="vertical", spacing=dp(8), size_hint_x=0.35)
        vertical.add_widget(self._jog_button("Z", 1))
        vertical.add_widget(label("Z AXIS", 10, MUTED, 20, halign="center"))
        vertical.add_widget(self._jog_button("Z", -1))
        controls.add_widget(vertical)
        jog.add_widget(controls)
        modes = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(32))
        self.jog_mode_button = self._guarded(
            "Step jog",
            self.machine.toggle_jog_mode,
            lambda: self.app.is_community_firmware and self.app.fw_version_digitized >= digitize_v("2.0.0"),
        )
        self.jog_mode_button.height = dp(32)
        modes.add_widget(self.jog_mode_button)
        self.keyboard_button = Action("Keyboard off", self.machine.toggle_keyboard_jog_control)
        self.keyboard_button.height = dp(32)
        modes.add_widget(self.keyboard_button)
        jog.add_widget(modes)
        row.add_widget(jog)
        page.add_widget(row)
        next_step = self._section(
            "Continue your workflow", "Set up your stock, review the program, then follow the run.", 140
        )
        actions = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        actions.add_widget(Action("Set up machine", lambda: self.select("Setup")))
        actions.add_widget(Action("Review a job", lambda: self.select("Job"), primary=True))
        actions.add_widget(Action("View live spindle", lambda: self.select("Monitor")))
        next_step.add_widget(actions)
        page.add_widget(next_step)
        machine_tools = self._section("Machine utilities", "Jog speed, lighting and configured shortcuts", 148)
        utilities = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(40))
        self.speed_button = Action("Jog speed", lambda: self.machine.jog_speed_drop_down.open(self.speed_button))
        utilities.add_widget(self.speed_button)
        self.light_button = self._guarded(
            "Light", self._toggle_light, lambda: self.app.state in ("Idle", "Run", "Tool", "Pause")
        )
        utilities.add_widget(self.light_button)
        utilities.add_widget(Action("Pendant", self.machine.toggle_pendant_jog_control))
        for index in (1, 2, 3):
            utilities.add_widget(
                self._guarded(
                    f"Macro {index}",
                    lambda i=index: self.machine.run_macro(i),
                    lambda: self.machine._machine_allows_jogging(),
                )
            )
        machine_tools.add_widget(utilities)
        page.add_widget(machine_tools)
        self.rotary_card = self._section("Rotary axis", "A axis • step in degrees", 146)
        rotary = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        self.a_step = Spinner(
            text=self.app.jog_step_a, values=("90", "10", "1", "0.1"), size_hint_y=None, height=dp(40)
        )
        self.a_step.bind(text=lambda _w, value: self._set_step("a", value))
        rotary.add_widget(self._jog_button("A", -1))
        rotary.add_widget(self.a_step)
        rotary.add_widget(self._jog_button("A", 1))
        self.rotary_card.add_widget(rotary)
        page.add_widget(self.rotary_card)
        self._update_y_placement()

    def _toggle_light(self):
        self.machine.controller.setLightSwitch(not bool(CNC.vars.get("sw_light", 0)))

    def _jog_button(self, axis, direction):
        button = self._guarded(
            f"{axis}{'+' if direction > 0 else '−'}", None, lambda: self.machine._machine_allows_jogging()
        )
        button.bind(
            on_press=lambda _b, a=axis, d=direction: self._jog(a, d),
            on_release=lambda _b: self.machine.controller.stopContinuousJog(),
        )
        self.jog_buttons.append(button)
        return button

    def _set_step(self, axis, value):
        setattr(self.app, f"jog_step_{axis}", value)
        getattr(self.machine, f"step_{axis}").text = value

    def _jog(self, axis, direction):
        if not self.machine.is_jogging_enabled():
            return
        # Labels explicitly name the commanded axis direction; inversion only
        # changes the physical up/down placement, not the labeled command.
        amount = self.a_step.text if axis == "A" else self.z_step.text if axis == "Z" else self.xy_step.text
        self.machine.controller.jog(f"{axis}{'-' if direction < 0 else ''}{amount}")

    def _build_setup(self):
        page = self._page("Setup", scroll=True)
        steps = (
            (
                "01  Establish your origin",
                "Probe the stock or review work offsets before machining.",
                (
                    ("Probing workspace", self.machine.open_probing_popup),
                    ("Work offsets", self.machine.wcs_settings_popup.open),
                ),
            ),
            (
                "02  Prepare the surface",
                "Plan a facing operation and inspect stock clearance.",
                (
                    ("Facing wizard", self.machine.open_facing_popup),
                    ("Inspection workbench", self.machine.open_cmm_workbench_popup),
                ),
            ),
            (
                "03  Review the cutting tool",
                "Inspect the loaded tool, length calibration and spindle controls.",
                (
                    ("Tool & calibration", lambda: self.machine.tool_drop_down.open(self.nav["Setup"])),
                    ("Spindle & extraction", lambda: self.machine.open_spindle_or_laser_drop_down(self.nav["Setup"])),
                ),
            ),
        )
        for title, subtitle, entries in steps:
            card = self._section(title, subtitle, 154)
            row = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
            for text, callback in entries:
                needs_community = text in ("Probing workspace", "Facing wizard", "Inspection workbench")
                row.add_widget(
                    self._guarded(
                        text,
                        callback,
                        lambda community=needs_community: (
                            self.app.state == "Idle" and (not community or self.app.is_community_firmware)
                        ),
                    )
                )
            card.add_widget(row)
            page.add_widget(card)
        positioning = self._section(
            "Position & verify", "Home, establish an origin, and check the selected program footprint.", 148
        )
        row = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(40))
        row.add_widget(self._guarded("Home machine", self.machine.controller.home, lambda: self.app.state == "Idle"))
        row.add_widget(
            self._guarded("Set origin…", self.machine.coord_popup.origin_popup.open, lambda: self.app.state == "Idle")
        )
        for text, mode in (("Check margins…", "Margin"), ("Z probe…", "ZProbe"), ("Auto level…", "Leveling")):
            row.add_widget(
                self._guarded(
                    text,
                    lambda mode=mode: self._setup_check(mode),
                    lambda mode=mode: (
                        self.app.state == "Idle"
                        and bool(self.app.selected_remote_filename)
                        and (mode != "Leveling" or not self.app.has_4axis)
                    ),
                )
            )
        positioning.add_widget(row)
        page.add_widget(positioning)
        page.add_widget(Action("Continue to job review", lambda: self.select("Job"), primary=True))

    def _setup_check(self, mode):
        popup = self.machine.coord_popup
        popup.mode = mode
        for feature, selected in (("margin", "Margin"), ("zprobe", "ZProbe"), ("leveling", "Leveling")):
            popup.set_config(feature, "active", mode == selected)
        popup.load_config()
        popup.open()

    def _build_job(self):
        page = self._page("Job")
        toolbar = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(42))
        toolbar.add_widget(
            self._guarded(
                "Choose program",
                self._choose_program,
                lambda: self.app.state in ("Idle", "N/A") or self.app.playing,
                size_hint_x=None,
                width=dp(152),
            )
        )
        self.program_label = label("No program selected", 13, MUTED, 42)
        toolbar.add_widget(self.program_label)
        toolbar.add_widget(
            self._guarded(
                "Review & start",
                self._review_start,
                lambda: (
                    (
                        self.app.state == "Idle"
                        and self.machine.config_loaded
                        and bool(self.app.selected_remote_filename)
                        and not self.app.playing
                    )
                    or self.app.state == "Pause"
                ),
                primary=True,
                size_hint_x=None,
                width=dp(148),
            )
        )
        page.add_widget(toolbar)
        view_controls = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(36))
        preview_guard = lambda: bool(self.app.selected_remote_filename or self.app.selected_local_filename)
        for text, callback in (
            ("Fit view", self.machine.gcode_viewer.restore_default_view),
            ("Orbit", lambda: self.machine.gcode_viewer.set_orbit(True)),
            ("Pan", lambda: self.machine.gcode_viewer.set_orbit(False)),
            ("Zoom +", self.machine.gcode_viewer.zoom_in),
            ("Zoom −", self.machine.gcode_viewer.zoom_out),
            ("Simulate toolpath", self.machine.gcode_play_toggle),
        ):
            guard = (
                (lambda: preview_guard() and self.app.state in ("Idle", "N/A"))
                if text == "Simulate toolpath"
                else preview_guard
            )
            view_controls.add_widget(self._guarded(text, callback, guard, height=dp(36)))
        page.add_widget(view_controls)
        # Reuse the actual preview, controls and toolpath renderer, not a rendition.
        self.machine.float_layout.parent.remove_widget(self.machine.float_layout)
        self.preview_row = BoxLayout(spacing=dp(8))
        self.machine.float_layout.size_hint_x = 0.58
        self.preview_row.add_widget(self.machine.float_layout)
        self.job_camera_splitter = Splitter(
            sizable_from="left",
            size_hint_x=0.42,
            min_size=dp(220),
            max_size=dp(900),
            strip_size=dp(8),
            keep_within_parent=True,
            rescale_with_parent=True,
        )
        self.job_camera_splitter.add_widget(self._camera_surface(compact=True))
        self.preview_row.add_widget(self.job_camera_splitter)
        page.add_widget(self.preview_row)
        display_controls = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(12))
        self.camera_pane_button = Action("Camera: shown", self._toggle_job_camera, height=dp(36))
        display_controls.add_widget(self.camera_pane_button)
        self.machine_view_button = Action("Machine view: off", self._toggle_machine_view, height=dp(36))
        display_controls.add_widget(self.machine_view_button)
        display_controls.add_widget(Action("Simulation setup…", self._machine_setup, height=dp(36)))
        page.add_widget(display_controls)
        self.machine_preview_note = label("Toolpath preview • simulation does not send machine commands", 11, MUTED, 32)
        page.add_widget(self.machine_preview_note)
        self.empty_preview = label(
            "Choose a program to preview its toolpath.\nLocal files can be inspected before uploading to the machine.",
            14,
            MUTED,
            90,
            halign="center",
        )
        page.add_widget(self.empty_preview)
        actions = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        actions.add_widget(Action("Program lines & console", lambda: self.select("Console")))
        actions.add_widget(
            self._guarded(
                "Pause at safe opportunity",
                self.machine.controller.suspendCommand,
                lambda: self.app.state == "Run" and self.app.playing,
            )
        )
        actions.add_widget(
            self._guarded(
                "Abort program",
                self.machine.controller.abortCommand,
                lambda: self.app.state in ("Run", "Pause") and self.app.playing,
            )
        )
        page.add_widget(actions)

    def _toggle_job_camera(self):
        if self.job_camera_splitter.parent:
            self.preview_row.remove_widget(self.job_camera_splitter)
            self.camera_pane_button.text = "Camera: hidden"
        else:
            self.preview_row.add_widget(self.job_camera_splitter)
            self.camera_pane_button.text = "Camera: shown"

    def _toggle_machine_view(self):
        viewer = self.machine.gcode_viewer
        if not hasattr(viewer, "set_machine_visible"):
            self.machine_preview_note.text = "Machine scene is being integrated."
            return
        enabled = not getattr(viewer, "machine_visible", False)
        enabled = viewer.set_machine_visible(enabled)
        self.machine_view_button.text = "Machine view: on" if enabled else "Machine view: off"
        self.machine_preview_note.text = (
            "Nominal machine kinematics • set program origin and stock in Simulation setup"
            if enabled
            else "Toolpath preview • simulation does not send machine commands"
        )

    def _machine_setup(self):
        from kivy.uix.popup import Popup

        layout = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
        layout.add_widget(
            label(
                "Schematic preview • coordinates are in a nominal tool-tip frame.\nEnter stock size and its minimum corner in program coordinates (mm).",
                13,
                MUTED,
                60,
            )
        )
        fields = GridLayout(cols=3, spacing=dp(12), size_hint_y=None, height=dp(190))
        entries = {}
        saved = getattr(self, "simulation_geometry", {})
        for group, titles, defaults in (
            ("size", ("Stock X size", "Stock Y size", "Stock Z size"), (127, 69.4182, 50.8762)),
            ("origin", ("Stock minimum X", "Stock minimum Y", "Stock minimum Z"), (-63.5, -34.7091, -50.8762)),
            (
                "offset",
                ("Program origin X", "Program origin Y", "Program origin Z"),
                (-180, -120, -89.1238),
            ),
        ):
            for index, title in enumerate(titles):
                cell = BoxLayout(orientation="vertical", spacing=dp(4))
                cell.add_widget(label(title, 11, MUTED, 22))
                value = saved.get(group, defaults)[index]
                entry = TextInput(text=f"{value:g}", multiline=False, font_size=sp(13), size_hint_y=None, height=dp(36))
                cell.add_widget(entry)
                entries[group, index] = entry
                fields.add_widget(cell)
        layout.add_widget(fields)
        note = label(
            "Starting stock values are a draft; confirm your actual stock and origin.\nThis schematic does not qualify collisions or stock removal.",
            12,
            AMBER,
            56,
        )
        layout.add_widget(note)
        actions = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        popup = Popup(title="Machine simulation setup", content=layout, size_hint=(0.8, None), height=dp(460))

        def apply():
            import math

            try:
                values = {
                    group: tuple(float(entries[group, i].text) for i in range(3))
                    for group in ("size", "origin", "offset")
                }
                if not all(math.isfinite(v) for group in values.values() for v in group) or any(
                    v <= 0 for v in values["size"]
                ):
                    raise ValueError()
            except ValueError:
                note.text = "Enter finite numbers; stock sizes must be greater than zero."
                return
            viewer = self.machine.gcode_viewer
            if hasattr(viewer, "configure_machine"):
                viewer.configure_machine(
                    work_offset_mm=values["offset"], stock_size_mm=values["size"], stock_origin_mm=values["origin"]
                )
                self.simulation_geometry = values
                note.text = "Simulation geometry updated."
                popup.dismiss()

        actions.add_widget(Action("Apply to preview", apply, primary=True))
        actions.add_widget(Action("Cancel", popup.dismiss))
        layout.add_widget(actions)
        popup.open()

    def _choose_program(self):
        root = self.machine
        root.file_popup.firmware_mode = False
        root.file_popup.popup_manager.transition.duration = 0
        root.file_popup.popup_manager.current = "remote_page" if self.connected else "local_page"
        root.file_popup.open()
        if self.app.state == "Idle":
            root.file_popup.load_remote_root()

    def _review_start(self):
        if self.app.state == "Pause":
            self.machine.controller.resumeCommand()
        else:
            self.machine.coord_popup.mode = "Run"
            self.machine.coord_popup.load_config()
            self.machine.coord_popup.open()

    def _build_monitor(self):
        page = self._page("Monitor", scroll=True)
        banner = Surface(padding=dp(10), size_hint_y=None, height=dp(48))
        banner.add_widget(label("SHADOW ONLY   •   Records proposals; does not change machine feed", 13, ACCENT, 32))
        page.add_widget(banner)
        metrics = GridLayout(cols=3, spacing=dp(14), size_hint_y=None, height=dp(100))
        self.monitor_rpm = Metric("Actual RPM", accent=ACCENT)
        self.monitor_droop = Metric("Baseline droop", detail="Filtered against unloaded baseline")
        self.monitor_feed = Metric("Proposed feed", detail="Shadow proposal • not applied")
        for item in (self.monitor_rpm, self.monitor_droop, self.monitor_feed):
            metrics.add_widget(item)
        page.add_widget(metrics)
        self.monitor_reason = label("Waiting for telemetry", 13, AMBER, 48)
        page.add_widget(self.monitor_reason)
        baseline = self._section(
            "Unloaded baseline", "Confirm the cutter is clear of the stock before capturing a baseline.", 148
        )
        row = BoxLayout(spacing=dp(10), size_hint_y=None, height=dp(40))
        for text, command in (
            ("Capture baseline", "adaptive baseline"),
            ("Reset baseline", "adaptive reset"),
            ("Shadow on", "adaptive shadow"),
            ("Monitor off", "adaptive off"),
        ):
            if command == "adaptive baseline":
                row.add_widget(
                    self._guarded(
                        text,
                        lambda: self.machine.controller.adaptiveCommand("adaptive baseline"),
                        lambda: (
                            self.app.state == "Idle"
                            and CNC.vars["tarspindle"] > 0
                            and CNC.vars["curspindle"] >= CNC.vars["tarspindle"] * 0.9
                        ),
                    )
                )
            else:
                row.add_widget(Action(text, lambda cmd=command: self.machine.controller.adaptiveCommand(cmd)))
        baseline.add_widget(row)
        page.add_widget(baseline)
        graphs = GridLayout(cols=2, spacing=dp(14), size_hint_y=None, height=dp(180))

        def layout_graphs(_grid, width):
            graphs.cols = 2 if width >= dp(900) else 1
            graphs.height = dp(180) if graphs.cols == 2 else dp(374)

        graphs.bind(width=layout_graphs)
        for title, field, maximum, color in (
            ("Spindle speed • 0–15,000 RPM", "rpm", 15000, ACCENT),
            ("Drive effort • 0–100% PWM", "pwm", 1, (0.42, 0.69, 1, 1)),
        ):
            card = self._section(title, "Last 60 seconds • gaps indicate unavailable samples", 180)
            trace = Trace()
            card.add_widget(trace)
            setattr(self, f"trace_{field}", trace)
            graphs.add_widget(card)
        page.add_widget(graphs)

    def _build_console(self):
        page = self._page("Console")
        row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(10))
        row.add_widget(
            Action("Machine responses", lambda: setattr(self.machine.cmd_manager, "current", "manual_cmd_page"))
        )
        row.add_widget(Action("Program lines", lambda: setattr(self.machine.cmd_manager, "current", "gcode_cmd_page")))
        page.add_widget(row)
        self.machine.cmd_manager.parent.remove_widget(self.machine.cmd_manager)
        page.add_widget(self.machine.cmd_manager)
        self.machine.manual_cmd.font_name = "Roboto"
        self.machine.manual_cmd.font_size = sp(14)
        self.machine.manual_cmd.background_color = RAISED
        self.machine.manual_cmd.foreground_color = TEXT
        self.machine.manual_cmd.cursor_color = ACCENT
        self.machine.manual_cmd.hint_text = "Enter a command • Control + Enter to send"
        page.add_widget(
            label("Commands act on the connected machine. Review each command before sending.", 12, MUTED, 26)
        )

    def _camera_surface(self, compact=False):
        card = Surface(orientation="vertical", padding=dp(14), spacing=dp(8))
        card.add_widget(label("Ubuntu camera", 14, height=24, bold=True))
        card.add_widget(self.camera_texture.new_view())
        status = label("Connecting…", 11, MUTED, 40 if compact else 26)
        self.camera_status_labels.append(status)
        card.add_widget(status)
        return card

    def _build_camera(self):
        page = self._page("Camera")
        row = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        self.camera_toggle = Action("Pause viewing", self._toggle_camera, size_hint_x=None, width=dp(144))
        row.add_widget(self.camera_toggle)
        row.add_widget(
            Action(
                "Reconnect camera",
                lambda: self.camera_client.configure(self.camera_client.url),
                size_hint_x=None,
                width=dp(156),
            )
        )
        row.add_widget(Action("Camera settings", lambda: self.select("Settings"), size_hint_x=None, width=dp(148)))
        row.add_widget(Widget())
        page.add_widget(row)
        page.add_widget(self._camera_surface())
        page.add_widget(
            label("Viewing only • camera status does not indicate machine clearance or cutting depth.", 12, MUTED, 26)
        )

    def _toggle_camera(self):
        enabled, _frame, _error = self.camera_client.snapshot()
        self.camera_client.set_enabled(not enabled)

    def _save_camera_url(self):
        try:
            self.camera_client.configure(self.camera_url_input.text)
        except ValueError as exc:
            self.camera_settings_note.text = str(exc)
            return
        Config.set("carvera", "webcam_snapshot_url", self.camera_client.url)
        Config.write()
        self.camera_settings_note.text = "Saved. Camera connection restarted."

    def _refresh_camera(self):
        enabled, frame, error = self.camera_client.snapshot()
        age = frame.age() if frame else None
        if not enabled:
            text, color = "Paused • last image frozen", MUTED
        elif error:
            text, color = error, AMBER
        elif age is None:
            text, color = "Frame received • capture time unavailable", AMBER
        elif age > 2:
            text, color = f"Stale image • captured {age:.1f}s ago", AMBER
        else:
            text, color = f"Live • captured {age:.1f}s ago", ACCENT
        for item in self.camera_status_labels:
            item.text, item.color = text, color
        self.camera_toggle.text = "Pause viewing" if enabled else "Resume viewing"
        if self.workspaces.current in ("Camera", "Job"):
            self.camera_texture.update(frame)

    def _retry_configuration(self):
        if self.app.state != "Idle" or self.machine.config_loading:
            return
        self.machine._config_download_failures = 0
        self.machine._config_apply_failed = False
        self.machine.config_loading = True
        self.machine.download_config_file()

    def _build_settings(self):
        page = self._page("Settings", scroll=True)
        card = self._section(
            "Connect your machine", "Use a direct network connection or USB. Camera viewing remains separate.", 196
        )
        self.network_detail = label("", 13, MUTED, 26)
        card.add_widget(self.network_detail)
        row = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        row.add_widget(Action("Network address…", self.machine.manually_input_ip))
        row.add_widget(Action("Scan Wi-Fi…", lambda: self.machine.open_wifi_conn_drop_down(self.nav["Settings"])))
        row.add_widget(Action("USB device…", lambda: self.machine.open_comports_drop_down(self.nav["Settings"])))
        row.add_widget(self._guarded("Disconnect", self.machine.close, lambda: self.connected))
        card.add_widget(row)
        card.add_widget(
            self._guarded(
                "Reload machine configuration",
                self._retry_configuration,
                lambda: self.app.state == "Idle" and not self.machine.config_loading,
            )
        )
        card.height = dp(240)
        page.add_widget(card)
        camera = self._section(
            "Ubuntu webcam", "JPEG snapshot endpoint • video transport stays separate from CNC control.", 206
        )
        self.camera_url_input = TextInput(
            text=self.camera_client.url, multiline=False, font_size=sp(13), size_hint_y=None, height=dp(40)
        )
        camera.add_widget(self.camera_url_input)
        camera.add_widget(Action("Save & reconnect camera", self._save_camera_url))
        self.camera_settings_note = label("Current feed uses the existing Ubuntu camera forward.", 11, MUTED, 24)
        camera.add_widget(self.camera_settings_note)
        page.add_widget(camera)
        card = self._section(
            "Controller preferences", "Configure keyboard jogging, units, display and connection behavior.", 150
        )
        row = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        row.add_widget(Action("Preferences…", self.machine.config_popup.open))
        row.add_widget(self._guarded("Machine diagnostics", self.machine.diagnose_popup.open, lambda: self.connected))
        row.add_widget(Action("Language…", self.machine.language_popup.open))
        card.add_widget(row)
        page.add_widget(card)
        card = self._section(
            "Advanced tools", "Existing machine maintenance and recovery actions are available here.", 150
        )
        row = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        row.add_widget(Action("Machine actions…", lambda: self.machine.func_drop_down.open(self.nav["Settings"])))
        row.add_widget(
            self._guarded("Firmware & controller", self.machine.open_update_popup, lambda: self.app.state == "Idle")
        )
        row.add_widget(Action("Documentation", self.machine.open_online_docs))
        card.add_widget(row)
        page.add_widget(card)

    def _build_footer(self):
        footer = Surface(radius=0, padding=(dp(24), dp(5)), size_hint_y=None, height=dp(34))
        self.footer_status = label("", 11, MUTED, 24)
        footer.add_widget(self.footer_status)
        self.progress = label("", 11, MUTED, 24, halign="right")
        footer.add_widget(self.progress)
        self.add_widget(footer)

    def select(self, page):
        self.workspaces.current = page
        self.app.show_gcode_ctl_bar = page == "Job"
        self.heading.text, self.description.text = self.descriptions[page]
        for key, button in self.nav.items():
            button.base_color = (0.14, 0.29, 0.30, 1) if key == page else BG
            button.color = ACCENT if key == page else MUTED
            button._paint()
        if page == "Console":
            self.machine.cmd_manager.current = "manual_cmd_page"
        else:
            self.machine.manual_cmd.focus = False
        # Keyboard jogging is an explicit opt-in and never retained in an
        # editor/telemetry workspace where arrow keys must navigate text.
        if page != "Overview" and self.machine.keyboard_jog_control:
            self.machine.toggle_keyboard_jog_control(disable=True)

    def _program_changed(self, _app, filename):
        if filename:
            self.select("Job")

    def _update_y_placement(self, *_args):
        # Rebuild button placement by swapping the Y controls' positions in
        # their common grid; each button retains its labeled command.
        y_buttons = [b for b in self.jog_buttons if b.text.startswith("Y")]
        grid = y_buttons[0].parent
        order = sorted(y_buttons, key=lambda b: b.y, reverse=True)
        desired = "Y+" if self.app.invert_y_axis_jogging else "Y−"
        if order[0].text != desired:
            children = list(grid.children)
            first, second = (children.index(b) for b in y_buttons)
            children[first], children[second] = children[second], children[first]
            grid.clear_widgets()
            for child in reversed(children):
                grid.add_widget(child)

    def _legacy_navigation(self, _manager, name):
        if name == "File":
            self.select("Job")
        elif name == "Control":
            self.select("Overview")

    def refresh(self, _dt):
        for button, guard in self.guards:
            button.disabled = not guard()
        connected = self.connected
        data = CNC.vars
        self.hold_button.text = "Resume motion" if self.app.state == "Hold" else "Feed hold"
        self.state_label.text = "Disconnected" if not connected else self.app.state
        self.state_label.color = MUTED if not connected else ACCENT if self.app.state == "Idle" else AMBER
        address = getattr(self.machine, "past_machine_addr", "")
        self.connection_label.text = (
            f"{self.app.model or 'Carvera'}  •  {address or 'USB'}" if connected else "Choose a connection to begin"
        )
        self.connect_button.text = "Connection" if connected else "Connect…"
        self.network_detail.text = f"Last network address: {address or 'Not configured'}"
        self.rpm_metric.value.text = f"{data['curspindle']:,.0f}" if connected else "—"
        self.rpm_metric.detail.text = (
            f"/ {data['tarspindle']:,.0f} commanded RPM" if connected else "Actual / commanded RPM"
        )
        self.feed_metric.value.text = f"{data['curfeed']:,.0f}" if connected else "—"
        self.feed_metric.detail.text = (
            f"mm/min  •  {data['OvFeed']:.0f}% override" if connected else "mm/min • override"
        )
        self.tool_metric.value.text = f"T{self.app.tool}" if connected and self.app.tool >= 0 else "—"
        self.tool_metric.detail.text = f"Length offset {data['tlo']:.3f} mm" if connected else "Tool length offset"
        for axis in self.position_values:
            self.position_values[axis].text = f"{data['w' + axis.lower()]:.3f}" if connected else "—"
            self.machine_values[axis].text = f"Machine {data['m' + axis.lower()]:.3f}" if connected else "Machine —"
        self.wcs_label.text = (
            f"{self.machine.coord_system_data_view.main_text}  •  Work coordinate system"
            if connected
            else "Work coordinate system —"
        )
        step_mode = self.machine.controller.jog_mode == self.machine.controller.JOG_MODE_STEP
        for spinner in (self.xy_step, self.z_step, self.a_step):
            spinner.disabled = not step_mode or not self.machine._machine_allows_jogging()
        self.jog_help.text = "Press an axis to move • mm" if step_mode else "Hold an axis to move • release to stop"
        self.rotary_card.height = dp(146) if self.app.has_4axis else 0
        self.rotary_card.opacity = 1 if self.app.has_4axis else 0
        self.rotary_card.disabled = not self.app.has_4axis
        self.light_button.text = "Light on" if CNC.vars.get("sw_light", 0) else "Light off"
        self.speed_button.text = self.app.jog_speed_text.replace("Jog Speed:", "Speed: ")
        self.keyboard_button.text = "Keyboard on" if self.machine.keyboard_jog_control else "Keyboard off"
        self.jog_mode_button.text = self.app.jog_mode_text.replace("Jog Mode:", "") + " jog"
        filename = self.app.selected_remote_filename or self.app.selected_local_filename
        self.program_label.text = filename.rsplit("/", 1)[-1] if filename else "No program selected"
        viewer = self.machine.gcode_viewer
        if hasattr(viewer, "get_machine_simulation_info"):
            info = viewer.get_machine_simulation_info()
            self.machine_view_button.text = "Machine view: on" if info["visible"] else "Machine view: off"
            if info["visible"]:
                placement = (
                    "origin configured"
                    if info.get("alignment_configured", info.get("alignment_confirmed"))
                    else "illustrative origin"
                )
                self.machine_preview_note.text = (
                    f"C1 schematic • {placement} • collision / stock-removal checks unavailable"
                )
            elif getattr(viewer, "_machine_has_rotary_motion", False):
                self.machine_preview_note.text = (
                    "Rotary toolpath • full-machine scene is available for 3-axis previews only"
                )
        self.empty_preview.height = 0 if filename else dp(90)
        self.empty_preview.opacity = 0 if filename else 1
        self.progress.text = self.machine.progress_info or "No program running"
        self._refresh_monitor(connected)
        if connected and not self.machine.config_loaded:
            self.footer_status.text += " • " + (
                "Loading machine configuration" if self.machine.config_loading else "Machine configuration unavailable"
            )
        self._refresh_camera()

    def _refresh_monitor(self, connected):
        with self.machine.controller._adaptive_lock:
            state = self.machine.controller.adaptive_monitor.snapshot()
            samples = list(self.machine.controller.adaptive_monitor.history)
        sample = state["sample"]
        age = time.monotonic() - sample["timestamp"] if sample else None
        fresh = connected and age is not None and age <= 0.8
        self.footer_status.text = (
            f"Telemetry {age:.2f}s ago  •  Shadow monitor"
            if fresh
            else "Telemetry unavailable"
            if not connected
            else "Telemetry stale • inspect connection"
        )
        self.monitor_rpm.value.text = f"{sample['rpm']:,.0f}" if fresh else "—"
        self.monitor_rpm.detail.text = (
            f"/ {sample['commanded_rpm']:,.0f} commanded • {age:.2f}s ago"
            if fresh
            else "Waiting for fresh spindle telemetry"
        )
        baseline = state.get("baseline")
        self.monitor_droop.value.text = f"{state['filtered_droop'] * 100:.2f}%" if fresh and baseline else "—"
        self.monitor_feed.value.text = f"{state['proposed_override']:.0f}%" if fresh and baseline else "—"
        self.monitor_reason.text = (
            state["reason"].replace(
                "baseline required (adaptive baseline); no feed proposal",
                "Capture an unloaded baseline before using feed proposals.",
            )
            if connected
            else "Connect a machine to receive live telemetry."
        )
        self.rail_note.text = f"SPINDLE MONITOR\n{state['mode'].capitalize()} • proposals only"
        if self.workspaces.current == "Monitor":
            self.trace_rpm.draw(samples, "rpm", 15000, ACCENT)
            self.trace_pwm.draw(samples, "pwm", 1, (0.42, 0.69, 1, 1))


def install_desktop_workspace(root, app):
    """Keep the original widgets alive for controller bindings, replace the shell."""
    old_widgets = list(root.children)
    workspace = DesktopWorkspace(root, app)
    root.clear_widgets()
    root._original_layout = old_widgets
    root.desktop_workspace = workspace
    root.add_widget(workspace)
    return workspace
