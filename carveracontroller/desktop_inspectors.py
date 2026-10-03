"""Compact inspector contents; building them never sends machine commands."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.widget import Widget

from carveracontroller.adaptive_popup import Trace
from carveracontroller.CNC import CNC
from carveracontroller.desktop_components import (
    ACCENT,
    AMBER,
    MUTED,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    Surface,
    label,
)
from carveracontroller.Utils import digitize_v


def _card(page, title):
    card = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None)
    card.bind(minimum_height=card.setter("height"))
    card.add_widget(label(title, 13, height=22, bold=True))
    page.add_widget(card)
    return card


def _actions(card, *buttons):
    grid = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
    for button in buttons:
        grid.add_widget(button)
    card.add_widget(grid)
    return grid


class InspectorMetric(Surface):
    def __init__(self, title, detail="", accent=ACCENT):
        super().__init__(orientation="vertical", padding=dp(8), spacing=dp(2), size_hint_y=None, height=dp(78))
        row = BoxLayout(size_hint_y=None, height=dp(30), spacing=dp(8))
        row.add_widget(label(title, 11, MUTED, 30))
        self.value = label("—", 21, accent, 30, halign="right")
        row.add_widget(self.value)
        self.detail = label(detail, 10, MUTED, 28)
        self.add_widget(row)
        self.add_widget(self.detail)


def build_overview(w):
    page = w._page("Overview", scroll=True)
    w.rpm_metric = InspectorMetric("Spindle", "Actual / commanded RPM")
    w.feed_metric = InspectorMetric("Feed", "mm/min • override")
    w.tool_metric = InspectorMetric("Active tool", "Measured length offset")
    position = _card(page, "Position • mm")
    w.position_values, w.machine_values = {}, {}
    for axis, color in (("X", (0.95, 0.55, 0.57, 1)), ("Y", ACCENT), ("Z", (0.42, 0.69, 1, 1))):
        row = BoxLayout(size_hint_y=None, height=dp(32), spacing=dp(6))
        row.add_widget(label(axis, 15, color, 32, size_hint_x=None, width=dp(18)))
        work, machine = label("—", 17, height=32), label("Machine —", 10, MUTED, 32, halign="right")
        w.position_values[axis], w.machine_values[axis] = work, machine
        row.add_widget(work)
        row.add_widget(machine)
        position.add_widget(row)
    w.wcs_label = label("Work coordinate system —", 10, MUTED, 28)
    position.add_widget(w.wcs_label)
    jog = _card(page, "Jog the machine")
    w.jog_help = label("Press an axis to move • mm", 10, MUTED, 30)
    jog.add_widget(w.jog_help)
    steps = GridLayout(cols=2, size_hint_y=None, height=dp(62), spacing=dp(4))
    steps.add_widget(label("XY step • mm", 10, MUTED, 22))
    steps.add_widget(label("Z step • mm", 10, MUTED, 22))
    w.xy_step = Choice(text=w.app.jog_step_xy, values=("10", "1", "0.1", "0.01", "0.005"))
    w.z_step = Choice(text=w.app.jog_step_z, values=("10", "1", "0.1", "0.01", "0.005"))
    w.xy_step.bind(text=lambda _obj, value: w._set_step("xy", value))
    w.z_step.bind(text=lambda _obj, value: w._set_step("z", value))
    steps.add_widget(w.xy_step)
    steps.add_widget(w.z_step)
    jog.add_widget(steps)
    controls = BoxLayout(size_hint_y=None, height=dp(126), spacing=dp(8))
    grid = GridLayout(cols=3, spacing=dp(5))
    w.jog_buttons = []
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
        grid.add_widget(w._jog_button(axis, direction) if axis else Widget())
    controls.add_widget(grid)
    vertical = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_x=None, width=dp(64))
    vertical.add_widget(w._jog_button("Z", 1))
    vertical.add_widget(label("Z AXIS", 9, MUTED, 22, halign="center"))
    vertical.add_widget(w._jog_button("Z", -1))
    controls.add_widget(vertical)
    jog.add_widget(controls)
    w.jog_mode_button = w._guarded(
        "Step jog",
        w.machine.toggle_jog_mode,
        lambda: w.app.is_community_firmware and w.app.fw_version_digitized >= digitize_v("2.0.0"),
    )
    w.keyboard_button = Action("Keyboard off", w.machine.toggle_keyboard_jog_control)
    _actions(jog, w.jog_mode_button, w.keyboard_button)
    for metric in (w.rpm_metric, w.feed_metric, w.tool_metric):
        page.add_widget(metric)
    utilities = _card(page, "Machine utilities")
    w.speed_button = Action("Jog speed", lambda: w.machine.jog_speed_drop_down.open(w.speed_button))
    w.light_button = w._guarded("Light", w._toggle_light, lambda: w.app.state in ("Idle", "Run", "Tool", "Pause"))
    buttons = [w.speed_button, w.light_button, Action("Pendant", w.machine.toggle_pendant_jog_control)]
    for index in (1, 2, 3):
        buttons.append(
            w._guarded(
                f"Macro {index}", lambda i=index: w.machine.run_macro(i), lambda: w.machine._machine_allows_jogging()
            )
        )
    _actions(utilities, *buttons)
    # Refresh retains a fixed visible height for this optional card.
    w.rotary_card = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_y=None, height=dp(146))
    w.rotary_card.add_widget(label("Rotary axis • degrees", 12, height=24))
    w.a_step = Choice(text=w.app.jog_step_a, values=("90", "10", "1", "0.1"))
    w.a_step.bind(text=lambda _obj, value: w._set_step("a", value))
    w.rotary_card.add_widget(w.a_step)
    _actions(w.rotary_card, w._jog_button("A", -1), w._jog_button("A", 1))
    page.add_widget(w.rotary_card)
    w._update_y_placement()


def build_setup(w):
    page = w._page("Setup", scroll=True)
    library = _card(page, "Tool library & machine profiles")
    w.tool_library_summary = label("No tool profile loaded", 11, MUTED, 56)
    library.add_widget(w.tool_library_summary)
    _actions(library, Action("Manage profiles", w._open_profiles), Action("Preview setup", w._machine_setup))
    for title, entries in (
        (
            "Origin & inspection",
            (
                ("Probe stock", w.machine.open_probing_popup, True),
                ("Work offsets", w.machine.wcs_settings_popup.open, False),
                ("Facing wizard", w.machine.open_facing_popup, True),
                ("Inspection", w.machine.open_cmm_workbench_popup, True),
            ),
        ),
        (
            "Physical tool & spindle",
            (
                ("Tool calibration", lambda: w.machine.tool_drop_down.open(w.nav["Setup"]), False),
                ("Spindle / extraction", lambda: w.machine.open_spindle_or_laser_drop_down(w.nav["Setup"]), False),
            ),
        ),
    ):
        card = _card(page, title)
        _actions(
            card,
            *(
                w._guarded(
                    text,
                    callback,
                    lambda community=community: (
                        w.app.state == "Idle" and (not community or w.app.is_community_firmware)
                    ),
                )
                for text, callback, community in entries
            ),
        )
    verify = _card(page, "Position & verify")
    buttons = [
        w._guarded("Home machine", w.machine.controller.home, lambda: w.app.state == "Idle"),
        w._guarded("Set origin…", w.machine.coord_popup.origin_popup.open, lambda: w.app.state == "Idle"),
    ]
    for text, mode in (("Check margins", "Margin"), ("Z probe", "ZProbe"), ("Auto level", "Leveling")):
        buttons.append(
            w._guarded(
                text,
                lambda mode=mode: w._setup_check(mode),
                lambda mode=mode: (
                    w.app.state == "Idle"
                    and bool(w.app.selected_remote_filename)
                    and (mode != "Leveling" or not w.app.has_4axis)
                ),
            )
        )
    _actions(verify, *buttons)
    verify.add_widget(
        label(
            "Profile assignments are local metadata.\nPhysical tool and offsets come from the controller.",
            10,
            AMBER,
            46,
        )
    )


def build_monitor(w):
    page = w._page("Monitor", scroll=True)
    page.add_widget(label("Shadow monitor • proposals never change feed", 11, ACCENT, 40))
    w.monitor_rpm = InspectorMetric("Actual RPM")
    w.monitor_droop = InspectorMetric("Baseline droop", "Filtered against unloaded baseline")
    w.monitor_feed = InspectorMetric("Proposed feed", "Shadow proposal • not applied")
    for metric in (w.monitor_rpm, w.monitor_droop, w.monitor_feed):
        page.add_widget(metric)
    w.monitor_reason = label("Waiting for telemetry", 11, AMBER, 72)
    page.add_widget(w.monitor_reason)
    for title, field in (("Spindle speed • RPM", "rpm"), ("Drive effort • PWM", "pwm")):
        card = _card(page, title)
        trace = Trace(size_hint_y=None, height=dp(112))
        setattr(w, f"trace_{field}", trace)
        card.add_widget(trace)
    baseline = _card(page, "Unloaded baseline")
    baseline.add_widget(label("Capture only while the cutter is clear of stock.", 10, MUTED, 38))
    capture = w._guarded(
        "Capture baseline",
        lambda: w.machine.controller.adaptiveCommand("adaptive baseline"),
        lambda: (
            w.app.state == "Idle"
            and CNC.vars["tarspindle"] > 0
            and CNC.vars["curspindle"] >= CNC.vars["tarspindle"] * 0.9
        ),
    )
    _actions(
        baseline,
        capture,
        *(
            Action(text, lambda cmd=command: w.machine.controller.adaptiveCommand(cmd))
            for text, command in (
                ("Reset baseline", "adaptive reset"),
                ("Shadow on", "adaptive shadow"),
                ("Monitor off", "adaptive off"),
            )
        ),
    )


def build_camera(w):
    page = w._page("Camera", scroll=True)
    card = _card(page, "Camera source")
    card.add_widget(label("Ubuntu JPEG snapshot URL", 10, MUTED, 22))
    w.camera_url_input = Field(text=w.camera_client.url)
    card.add_widget(w.camera_url_input)
    w.camera_settings_note = label("Camera transport is separate from CNC control.", 10, MUTED, 40)
    card.add_widget(w.camera_settings_note)
    w.camera_toggle = Action("Pause viewing", w._toggle_camera)
    _actions(
        card,
        Action("Save source", w._save_camera_url),
        w.camera_toggle,
        Action("Reconnect camera", lambda: w.camera_client.configure(w.camera_client.url)),
    )
    status = label("Connecting…", 11, MUTED, 44)
    w.camera_status_labels.append(status)
    card.add_widget(status)
    from carveracontroller.desktop_camera_registration import CameraRegistrationPanel

    w.camera_registration_panel = CameraRegistrationPanel(w)
    page.add_widget(w.camera_registration_panel)


def build_settings(w):
    page = w._page("Settings", scroll=True)
    card = _card(page, "Machines & connection")
    w.selected_machine_label = label("No machine profile selected", 11, MUTED, 56)
    card.add_widget(w.selected_machine_label)
    w.network_detail = label("", 11, MUTED, 38)
    card.add_widget(w.network_detail)
    _actions(
        card,
        Action("Manage profiles", w._open_profiles),
        w._guarded("Connect profile", w._connect_profile, lambda: not w.connected),
        Action("Network address…", w.machine.manually_input_ip),
        Action("Scan Wi-Fi…", lambda: w.machine.open_wifi_conn_drop_down(w.nav["Settings"])),
        Action("USB device…", lambda: w.machine.open_comports_drop_down(w.nav["Settings"])),
        w._guarded("Disconnect", w.machine.close, lambda: w.connected),
        w._guarded(
            "Reload config", w._retry_configuration, lambda: w.app.state == "Idle" and not w.machine.config_loading
        ),
    )
    preferences = _card(page, "Controller preferences")
    _actions(
        preferences,
        Action("Preferences…", w.machine.config_popup.open),
        w._guarded("Diagnostics", w.machine.diagnose_popup.open, lambda: w.connected),
        Action("Language…", w.machine.language_popup.open),
    )
    advanced = _card(page, "Maintenance & help")
    _actions(
        advanced,
        Action("Machine actions…", lambda: w.machine.func_drop_down.open(w.nav["Settings"])),
        w._guarded("Firmware", w.machine.open_update_popup, lambda: w.app.state == "Idle"),
        Action("Documentation", w.machine.open_online_docs),
    )
