"""Desktop workflow shell over the existing controller and preflight actions.

Navigation and telemetry are read-only. Machine actions use the same guarded
controller paths as the original UI; adaptive control remains shadow-only.
"""

import threading
import time
from copy import deepcopy
from pathlib import Path

from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.behaviors import FocusBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.widget import Widget

from carveracontroller.CNC import CNC
from carveracontroller.desktop_components import (
    ACCENT,
    AMBER,
    BG,
    DANGER,
    MUTED,
    PANEL,
    RAISED,
    TEXT,
    Action,
    AdaptiveGrid,
    Choice,
    Field,
    QuantityField,
    Surface,
    displayed_control,
    label,
)
from carveracontroller.desktop_components import DesktopScrollView as ScrollView
from carveracontroller.machine.webcam import DEFAULT_CAMERA_URL, WebcamClient
from carveracontroller.webcam_view import WebcamTexture


class DesktopWorkspace(Surface):
    desktop_focus_scope = True
    pages = (
        ("Overview", "Overview"),
        ("Setup", "Setup & tools"),
        ("Job", "Job workspace"),
        ("Monitor", "Spindle"),
        ("Console", "Console"),
        ("Camera", "Camera"),
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
        self._profile_load_generation = 0
        self._profile_load_active = False
        self._profile_load_pending = None
        self._profile_load_closed = False
        self.machine_profile_loading = False
        from carveracontroller.machine.ui_timing import NavigationTimings

        self.navigation_timings = NavigationTimings()
        self.refresh_timings = NavigationTimings(limit=60)
        self._timing_clock_event = None
        self._timing_pending_flip = None
        Window.bind(on_flip=self._navigation_flip)
        from carveracontroller.desktop_navigation import SelectionNavigation

        self.navigation = SelectionNavigation(self)
        self.selected_machine_profile = None
        self.loaded_toolset = None
        self.profile_error = None
        from carveracontroller.machine.desktop_profiles import ProfileError, ProfileStore

        try:
            self.profile_store = ProfileStore()
        except (ProfileError, OSError) as exc:
            self.profile_store = None
            self.profile_error = str(exc)
        camera_url = Config.get("carvera", "webcam_snapshot_url", fallback=DEFAULT_CAMERA_URL)
        try:
            self.camera_client = WebcamClient(camera_url)
        except ValueError:
            self.camera_client = WebcamClient(DEFAULT_CAMERA_URL)
        self.camera_texture = WebcamTexture()
        self.camera_status_labels = []
        self.guards = []
        self.nav = {}
        body = BoxLayout(spacing=dp(14), padding=(dp(12), dp(12), dp(16), dp(12)))
        self.body = body
        main = BoxLayout(orientation="vertical", spacing=dp(10), size_hint_x=0.5)
        self.media_column = main
        heading = BoxLayout(orientation="vertical", size_hint_y=None, height=dp(66))
        self.heading_area = heading
        self.heading = label("Machine overview", 26, height=38)
        self.description = label("", 13, MUTED, 26)
        heading.add_widget(self.heading)
        heading.add_widget(self.description)
        self.workspaces = ScreenManager(transition=NoTransition())
        main.add_widget(self.workspaces)
        body.add_widget(main)
        self.add_widget(body)
        self._build_overview()
        self._build_setup()
        self._build_job()
        from carveracontroller.desktop_surface_planning import SurfacePlanningPanel

        self.surface_planning_panel = SurfacePlanningPanel(self)
        self.setup_tasks.sections["Surface"].add_widget(self.surface_planning_panel)
        from carveracontroller.desktop_hole_planning import HolePlanningPanel

        self.hole_planning_panel = HolePlanningPanel(self)
        self.setup_tasks.sections["Holes"].add_widget(self.hole_planning_panel)
        from carveracontroller.desktop_repeat_parts import RepeatPartsPanel

        self.repeat_parts_panel = RepeatPartsPanel(self)
        self.setup_tasks.sections["Repeat"].add_widget(self.repeat_parts_panel)
        self._build_monitor()
        self._build_console()
        self._build_camera()
        self._build_settings()
        self._install_command_center(body)
        self._restore_profiles()
        # A successful machine restore already seeds its complete saved scene.
        if self.selected_machine_profile is None and not self.machine_profile_loading:
            self.seed_scene_choices(None)
        self._build_footer()
        # Existing menu/file callbacks still change the original screen manager.
        root.content.bind(current=self._legacy_navigation)
        app.bind(state=self._state_changed, playing=self._state_changed)
        app.bind(selected_local_filename=self._program_changed, selected_remote_filename=self._program_changed)
        app.bind(invert_y_axis_jogging=self._update_y_placement)
        self.select("Job")
        self.event = Clock.schedule_interval(self.refresh, 0.2)
        Window.bind(mouse_pos=self._hover, on_focus=self._window_focus)
        Window.bind(on_key_down=self._workspace_keydown)
        self.refresh(0)
        from carveracontroller.machine.ui_stalls import UIStallMonitor

        self.stall_monitor = UIStallMonitor()
        self.stall_monitor.start()
        self._stall_heartbeat_event = Clock.schedule_interval(self._stall_heartbeat, 0.2)

    def _stall_heartbeat(self, _dt):
        self.stall_monitor.heartbeat(getattr(self, "active_section", "workspace"))

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

    def _open_command_palette(self):
        from carveracontroller.desktop_commands import CommandPalette

        if not hasattr(self, "command_palette"):
            self.command_palette = CommandPalette(self)
        self.command_palette.open()

    def _workspace_keydown(self, _window, key, _scan, _text, modifiers):
        if key == ord("k") and any(modifier in modifiers for modifier in ("ctrl", "meta", "super")):
            self._open_command_palette()
            return True
        if key == 9 and set(modifiers) <= {"shift"}:
            modal = next((item for item in Window.children if isinstance(item, ModalView) and item._is_open), None)
            scope = modal or self
            controls = [
                item
                for item in scope.walk()
                if isinstance(item, FocusBehavior) and item.is_focusable and displayed_control(item)
            ]
            if controls and not any(item.focus for item in controls):
                controls[-1 if "shift" in modifiers else 0].focus = True
                return True
        return False

    @property
    def has_keyboard_focus(self):
        return any(getattr(item, "focus", False) for item in self.walk())

    def dispose(self):
        if hasattr(self, "setup_tasks"):
            self.setup_tasks.dispose()
        if hasattr(self, "machine_tasks"):
            self.machine_tasks.dispose()
        if hasattr(self, "kinematic_review_panel"):
            self.kinematic_review_panel.dispose()
        self._stall_heartbeat_event.cancel()
        self.stall_monitor.stop()
        if hasattr(self, "repeat_parts_panel"):
            self.repeat_parts_panel.closed = True
            self.repeat_parts_panel.cancel_event.set()
        self.navigation.dispose()
        self.machine.gcode_viewer.cancel_default_machine_profile()
        self._profile_load_closed = True
        self._profile_load_generation += 1
        self._profile_load_pending = None
        self.machine_profile_loading = False
        if hasattr(self, "scene_component_loads"):
            self.scene_component_loads.close()
        if hasattr(self, "setup_editor_loads"):
            self.setup_editor_loads.close()
        if hasattr(self, "scene_interaction"):
            self.scene_interaction.dispose()
        self.event.cancel()
        if self._timing_clock_event:
            self._timing_clock_event.cancel()
        Window.unbind(on_flip=self._navigation_flip)
        if hasattr(self, "run_recording_panel"):
            self.run_recording_panel.shutdown_camera()
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
        Window.unbind(on_key_down=self._workspace_keydown)
        if self.readiness.record_popup:
            self.readiness.record_popup.dismiss()
        if self.readiness.popup:
            self.readiness.popup.dismiss()
        if hasattr(self, "command_palette") and self.command_palette.popup:
            self.command_palette.popup.dismiss()

    def _guarded(self, text, callback, guard, **kwargs):
        button = Action(text, lambda: callback() if callback and guard() else None, **kwargs)
        self.guards.append((button, guard))
        return button

    def _build_machine_controls(self):
        connection = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(42))
        metadata = BoxLayout(spacing=dp(8), size_hint_y=None, height=dp(42))
        status = BoxLayout(orientation="vertical", size_hint_x=0.4)
        self.state_label = label("Disconnected", 14, ACCENT, 22, bold=True, shorten=True, max_lines=1)
        self.connection_label = label("Connect a machine to begin", 10, MUTED, 20, shorten=True, max_lines=1)
        status.add_widget(self.state_label)
        status.add_widget(self.connection_label)
        metadata.add_widget(status)
        self.profile_status = label("Local profiles • no toolset loaded", 11, MUTED, 42, size_hint_x=0.6, max_lines=2)
        metadata.add_widget(self.profile_status)
        connection.add_widget(metadata)
        actions = BoxLayout(spacing=dp(8), size_hint=(None, None), width=dp(256), height=dp(36))
        self.connect_button = Action("Connection", self._connection_menu, size_hint_x=None, width=dp(92))
        actions.add_widget(self.connect_button)
        self.hold_button = self._guarded(
            "Feed hold",
            self._feed_hold,
            lambda: (
                self.app.state in ("Run", "Idle", "Hold")
                and (self.app.state != "Hold" or not self.machine.controller.status_reacquisition_pending)
            ),
            size_hint_x=None,
            width=dp(84),
        )
        actions.add_widget(self.hold_button)
        actions.add_widget(
            self._guarded(
                "STOP",
                self.machine.controller.estopCommand,
                lambda: self.connected,
                danger=True,
                size_hint_x=None,
                width=dp(64),
            )
        )
        connection.add_widget(actions)

        def layout(_widget, width):
            compact = width < dp(500)
            connection.orientation = "vertical" if compact else "horizontal"
            connection.height = dp(86 if compact else 42)

        self.machine_controls = connection
        connection.bind(width=layout)
        layout(connection, connection.width)
        return connection

    @property
    def connected(self):
        return self.app.state not in ("N/A", "", "Disconnected")

    def _connection_menu(self):
        self.select("Settings")
        self.machine_tasks.show("Connect")
        from carveracontroller.desktop_scroll_navigation import queue_reveal

        queue_reveal(self.connection_card, active=lambda: self.active_section == "Settings", align_top=True)

    def _feed_hold(self):
        self.machine.controller.toggleFeedholdCommand(self.app.state == "Hold")

    def _page(self, name, scroll=False):
        content = BoxLayout(orientation="vertical", spacing=dp(10))
        screen = Screen(name=name)
        if scroll:
            content.size_hint_y = None
            content.bind(minimum_height=content.setter("height"))
            view = ScrollView(do_scroll_x=False, bar_width=dp(9))
            view.add_widget(content)
            screen.add_widget(view)
        else:
            screen.add_widget(content)
        self.workspaces.add_widget(screen)
        return content

    def _build_overview(self):
        from carveracontroller.desktop_inspectors import build_overview

        build_overview(self)

    def _toggle_light(self):
        self.machine.controller.setLightSwitch(not bool(CNC.vars.get("sw_light", 0)))

    def _jog_button(self, axis, direction):
        button = self._guarded(
            f"{axis}{'+' if direction > 0 else '−'}",
            None,
            lambda: self.machine._machine_allows_jogging(),
            keyboard_activation=False,
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
        from carveracontroller.desktop_inspectors import build_setup

        build_setup(self)

    def _setup_check(self, mode):
        popup = self.machine.coord_popup
        popup.mode = mode
        for feature, selected in (("margin", "Margin"), ("zprobe", "ZProbe"), ("leveling", "Leveling")):
            popup.set_config(feature, "active", mode == selected)
        popup.load_config()
        popup.open()

    def _build_job(self):
        from kivy.uix.anchorlayout import AnchorLayout

        page = self._page("Job")
        self.program_label = label("No program selected", 13, MUTED, 24, shorten=True)
        viewer = self.machine.gcode_viewer
        if self.machine.float_layout.parent:
            parent = self.machine.float_layout.parent
            # KV ids are weak proxies. Keep the detached overlay alive because
            # asynchronous G-code callbacks still update its legend and toolbar.
            self._legacy_viewer_overlay = next(child for child in parent.children if child == self.machine.float_layout)
            parent.remove_widget(self._legacy_viewer_overlay)
        viewer.parent.remove_widget(viewer)
        viewer.desktop_viewport = True
        viewer.set_display_offset(0, 0)
        viewer.size_hint = (1, 1)
        self.media_holder = AnchorLayout(anchor_x="center", anchor_y="center")
        self.preview_row = BoxLayout(orientation="vertical", spacing=dp(12), size_hint=(None, None))
        self.model_card = Surface(orientation="vertical", padding=dp(8), spacing=dp(2), size_hint_y=None)
        self.model_caption = label("Machine & toolpath", 12, height=18, bold=True)
        self.model_card.add_widget(self.model_caption)
        self.stage_context = label("", 11, MUTED, 40)
        self.stage_tool_context = label("", 11, MUTED, 40)
        self.stage_process_context = label("", 11, MUTED, 40)
        self.stage_telemetry = AdaptiveGrid(max_cols=3, min_width=220, row_height=40, spacing=dp(8))
        for item in (self.stage_context, self.stage_tool_context, self.stage_process_context):
            self.stage_telemetry.add_widget(item)
        self.model_card.add_widget(viewer)
        self.preview_row.add_widget(self.model_card)
        self.job_camera_splitter = BoxLayout(size_hint_y=None)
        self.job_camera_splitter.add_widget(self._camera_surface(compact=True))
        self.preview_row.add_widget(self.job_camera_splitter)
        self.media_holder.add_widget(self.preview_row)
        self.media_holder.bind(size=self._layout_media)
        page.add_widget(self.media_holder)
        self.empty_preview = label("", height=0)
        self.machine_preview_note = label("Nominal preview", 10, MUTED, 42)
        self.job_tool_label = label("", 11, MUTED, 28)
        # Commands belong in the Workbench; the two panes contain only media
        # and a compact live context caption.
        program_page = self._page("Preview", scroll=True)
        self.program_scroll = program_page.parent
        tools = BoxLayout(orientation="vertical", spacing=dp(6), size_hint_y=None)
        tools.bind(minimum_height=tools.setter("height"))
        program_page.add_widget(tools)
        tools.add_widget(self.program_label)
        tools.add_widget(self.stage_telemetry)
        actions = AdaptiveGrid(max_cols=4, min_width=150, row_height=36, spacing=dp(6))
        self.program_actions = actions
        actions.add_widget(
            self._guarded(
                "Choose program", self._choose_program, lambda: self.app.state in ("Idle", "N/A") or self.app.playing
            )
        )
        actions.add_widget(
            self._guarded(
                "Review & start",
                self._review_start,
                lambda: (
                    not self.machine.controller.status_reacquisition_pending
                    and (
                        (
                            self.app.state == "Idle"
                            and self.machine.config_loaded
                            and bool(self.app.selected_remote_filename)
                            and not self.app.playing
                        )
                        or self.app.state == "Pause"
                    )
                ),
                primary=True,
            )
        )
        tools.add_widget(actions)
        from carveracontroller.desktop_program_tasks import ProgramTasks

        self.program_tasks = ProgramTasks(
            on_choice=lambda: self.operation_panel.queue_reveal(self.program_tasks.tabs, align_top=True)
        )
        tasks = self.program_tasks.sections
        from carveracontroller.desktop_operations import OperationPanel

        self.operation_panel = OperationPanel(self)
        tasks["Operations"].add_widget(self.operation_panel)
        from carveracontroller.desktop_run_recording import RunRecordingPanel

        self.run_recording_panel = RunRecordingPanel(self)
        tasks["Run record"].add_widget(self.run_recording_panel)
        from carveracontroller.desktop_job_packages import export_job, import_job

        packages = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
        packages.add_widget(Action("Export complete job", lambda: export_job(self)))
        packages.add_widget(Action("Restore job preview", lambda: import_job(self)))
        tasks["Job package"].add_widget(packages)
        self.package_note = label("Portable jobs include program, setup and referenced CAD assets.", 11, MUTED, 48)
        tasks["Job package"].add_widget(self.package_note)
        from carveracontroller.desktop_simulation import SimulationPanel

        self.simulation_panel = SimulationPanel(self)
        tasks["Simulation"].add_widget(self.simulation_panel)
        pose_controls = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        pose_controls.add_widget(label("Machine pose", 11, MUTED, 36))
        self.pose_choice = Choice(text="Preview", values=("Preview", "Live", "Compare"))
        self.pose_choice.bind(text=lambda _widget, mode: self.set_pose_mode(mode))
        pose_controls.add_widget(self.pose_choice)
        tasks["View & playback"].add_widget(pose_controls)
        self.pose_note = label(
            "Preview uses the local setup; live pose requires a fresh machine packet.", 11, MUTED, 58
        )
        tasks["View & playback"].add_widget(self.pose_note)
        tasks["View & playback"].add_widget(self.job_tool_label)
        preview_guard = lambda: bool(self.app.selected_remote_filename or self.app.selected_local_filename)
        playback_guard = lambda: preview_guard() and self.app.state in ("Idle", "N/A")
        view_actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
        for text, callback in (
            ("Fit view", viewer.restore_default_view),
            ("Orbit", lambda: viewer.set_orbit(True)),
            ("Pan", lambda: viewer.set_orbit(False)),
            ("Zoom +", viewer.zoom_in),
            ("Zoom −", viewer.zoom_out),
        ):
            view_actions.add_widget(Action(text, callback))
        self.machine_view_button = Action("Machine off", self._toggle_machine_view)
        view_actions.add_widget(self.machine_view_button)
        view_actions.add_widget(Action("Simulation setup", self._machine_setup))
        self.camera_pane_button = Action("Hide camera", self._toggle_job_camera)
        view_actions.add_widget(self.camera_pane_button)
        tasks["View & playback"].add_widget(view_actions)
        self.scene_buttons = {}
        from carveracontroller.desktop_scene import build_scene_controls

        build_scene_controls(self)
        tasks["View & playback"].add_widget(label("Toolpath playback", 12, MUTED, 28))
        playback = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        playback.add_widget(
            self._guarded("|‹", self.machine.gcode_play_to_start, playback_guard, size_hint_x=None, width=dp(40))
        )
        self.simulate_button = self._guarded("Play preview", self.machine.gcode_play_toggle, playback_guard)
        playback.add_widget(self.simulate_button)
        playback.add_widget(
            self._guarded("›|", self.machine.gcode_play_to_end, playback_guard, size_hint_x=None, width=dp(40))
        )
        tasks["View & playback"].add_widget(playback)
        slider = self.machine.ids["gcode_play_slider"]
        slider.parent.remove_widget(slider)
        slider.size_hint = (1, None)
        slider.height = dp(36)
        tasks["View & playback"].add_widget(slider)
        tasks["View & playback"].add_widget(self.machine_preview_note)
        tasks["Operations"].add_widget(Action("Program & console", lambda: self.select("Console")))
        controls = actions
        controls.add_widget(
            self._guarded(
                "Pause program",
                self.machine.controller.suspendCommand,
                lambda: self.app.state == "Run" and self.app.playing,
            )
        )
        controls.add_widget(
            self._guarded(
                "Abort program",
                self.machine.controller.abortCommand,
                lambda: self.app.state in ("Run", "Pause") and self.app.playing,
                danger=True,
            )
        )
        self.program_tools = self.program_tasks.host
        self.program_tasks.size_hint_y = None
        program_page.add_widget(self.program_tasks)
        self._program_resize_trigger = Clock.create_trigger(self._resize_program_tasks)
        self.program_scroll.bind(size=self._program_resize_trigger)
        tools.bind(height=self._program_resize_trigger)
        self.program_tasks.tabs.bind(height=self._program_resize_trigger)
        self._program_resize_trigger()
        Clock.schedule_once(
            lambda _dt: viewer.set_machine_visible(True) if hasattr(viewer, "set_machine_visible") else None, 0.3
        )

    def _resize_program_tasks(self, *_args):
        """Short windows scroll the Program page instead of overlapping actions."""
        page = self.program_scroll.children[0]
        header = next(child for child in page.children if child is not self.program_tasks)
        available = self.program_scroll.height - header.height - page.spacing
        self.program_tasks.height = max(
            self.program_tasks.tabs.height + self.program_tasks.spacing + dp(128), available
        )

    def _layout_media(self, *_args):
        """Both images stay visible, with geometry sized to their aspect ratios."""
        camera = self.job_camera_splitter.parent is self.preview_row
        available = max(1, self.media_holder.height)
        inverse = 1 / 1.6 + (1 / getattr(self, "camera_aspect", 16 / 9) if camera else 0)
        # Each pane has 8dp insets, an 18dp caption and a 2dp caption gap.
        chrome = dp(36 + (48 if camera else 0))
        width = max(1, min(self.media_holder.width, max(1, (available - chrome) / inverse + dp(16))))
        media_width = max(1, width - dp(16))
        self.model_card.height = media_width / 1.6 + dp(36)
        self.job_camera_splitter.height = media_width / getattr(self, "camera_aspect", 16 / 9) + dp(36)
        self.preview_row.size = (
            width,
            self.model_card.height + (self.job_camera_splitter.height + dp(12) if camera else 0),
        )

    def _toggle_job_camera(self):
        if self.job_camera_splitter.parent:
            self.preview_row.remove_widget(self.job_camera_splitter)
            self.camera_pane_button.text = "Show camera"
        else:
            self.preview_row.add_widget(self.job_camera_splitter)
            self.camera_pane_button.text = "Hide camera"
        self._layout_media()

    def _toggle_machine_view(self):
        viewer = self.machine.gcode_viewer
        if not hasattr(viewer, "set_machine_visible"):
            self.machine_preview_note.text = "Machine scene is being integrated."
            return
        enabled = not getattr(viewer, "machine_visible", False)
        enabled = viewer.set_machine_visible(enabled)
        self.machine_view_button.text = "Machine on" if enabled else "Machine off"
        self.machine_preview_note.text = (
            "Nominal machine kinematics • set program origin and stock in Simulation setup"
            if enabled
            else "Toolpath preview • simulation does not send machine commands"
        )

    def _refresh_observed_pose(self, viewer):
        pose = getattr(self.machine.controller, "observed_pose", None)
        if not self.connected or pose is None or not pose.fresh(time.monotonic()):
            pose = None
        viewer.set_observed_pose(pose)
        if pose:
            delta = pose.preview_delta_mm(viewer.machine_setup, viewer._preview_program_point)
            self.pose_note.text = (
                f"Reported MCS {tuple(round(v, 3) for v in pose.machine_mm)} · T{pose.tool if pose.tool is not None else '?'}"
                f" · TLO {pose.tool_length_mm if pose.tool_length_mm is not None else 'unknown'} mm\n"
                f"Live − preview Δ XYZ: {tuple(round(v, 3) for v in delta)} mm · CAD registration unqualified"
            )
            if abs(pose.rotary_deg) > 1e-6:
                self.pose_note.text += (
                    f"\nReported A {pose.rotary_deg:g}° · rotary workholding pose not represented in this C1 view"
                )
        else:
            self.pose_note.text = "Live pose unavailable or stale · Preview remains local; Live display is frozen, not a current position."
        mode = viewer.pose_mode
        panel = self.operation_panel
        operation = panel.selected_operation
        context = (
            f"{operation.name} · line {panel.selected_line}"
            if operation and panel.selected_line is not None
            else "No operation selected"
        )
        if hasattr(self, "pose_status"):
            self.pose_status.text = (
                "Live view · fresh reported pose"
                if mode == "Live" and pose
                else "Live view · stale / unavailable; display frozen"
                if mode == "Live"
                else f"{mode} view · {context}"
                + (" · live marker unavailable" if mode == "Compare" and not pose else "")
            )
            self.pose_status.color = ACCENT if mode == "Live" and pose else AMBER
            self.return_live_action.disabled = pose is None or mode == "Live"

    def set_pose_mode(self, mode):
        """Change only local visualization; Live stops local animation, not CNC motion."""
        viewer = self.machine.gcode_viewer
        if mode == "Live":
            self.machine.gcode_playing = False
            viewer.dynamic_display = False
        if viewer.pose_mode != mode:
            viewer.set_pose_mode(mode)
        if self.pose_choice.text != mode:
            self.pose_choice.text = mode
        if hasattr(self, "operation_panel"):
            self.operation_panel.refresh_path_highlight()
        self._refresh_observed_pose(viewer)

    def enter_preview(self):
        """A deliberate seek/play gesture owns the preview, retaining Compare if selected."""
        self.set_pose_mode("Compare" if self.machine.gcode_viewer.pose_mode == "Compare" else "Preview")

    def return_to_live(self):
        viewer = self.machine.gcode_viewer
        self._refresh_observed_pose(viewer)
        if viewer.observed_pose is None:
            return False
        self.set_pose_mode("Live")
        return True

    def _toggle_scene_group(self, group):
        viewer = self.machine.gcode_viewer
        viewer.set_machine_group_visible(group, not viewer.machine_group_visibility[group])
        button, title = self.scene_buttons[group]
        button.text = f"{title}: {'shown' if viewer.machine_group_visibility[group] else 'hidden'}"

    def _workholding_setup(self):
        from carveracontroller.desktop_setup_editor import open_setup_editor

        return open_setup_editor(self, "workholding")

    def _machine_setup(self):
        from carveracontroller.desktop_setup_editor import open_setup_editor

        return open_setup_editor(self, "stock")

    def _choose_program(self):
        from carveracontroller.desktop_program_picker import ProgramBrowser

        self.select("Job")
        self.program_browser = ProgramBrowser(self)
        self.program_browser.open()

    def _review_start(self):
        if self.machine.controller.status_reacquisition_pending:
            return
        if self.app.state == "Pause":
            self.machine.controller.resumeCommand()
        else:
            self.machine.coord_popup.mode = "Run"
            self.machine.coord_popup.load_config()
            self.machine.coord_popup.open()

    def _build_monitor(self):
        from carveracontroller.desktop_inspectors import build_monitor

        build_monitor(self)

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
        # Keep the original MDI widget and handlers, giving it an intentional
        # compact composer rather than the inherited 66px icon strip.
        composer = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(60))
        entry = self.machine.manual_cmd
        old_row = entry.parent
        old_row.remove_widget(entry)
        old_row.height, old_row.opacity = 0, 0
        old_row.disabled = True
        entry.size_hint = (1, 1)
        entry.padding = (dp(8), dp(8))
        entry.bind(
            focus=lambda _w, focused: (
                self.machine.toggle_keyboard_jog_control(disable=True)
                if focused and self.machine.keyboard_jog_control
                else None
            )
        )
        composer.add_widget(entry)
        composer.add_widget(
            self._guarded(
                "Send",
                self.machine.send_cmd,
                lambda: (
                    self.connected
                    and (
                        self.app.state in ("Idle", "Pause")
                        or self.machine.allow_mdi_while_machine_running in ("1", True)
                    )
                ),
                size_hint_x=None,
                width=dp(56),
                height=dp(60),
            )
        )
        page.add_widget(composer)
        page.add_widget(label("MDI • commands act on the connected machine", 10, MUTED, 28))
        for rv in (self.machine.manual_rv, self.machine.gcode_rv):
            rv.bar_width = dp(4)

    def _camera_surface(self, compact=False):
        card = Surface(orientation="vertical", padding=dp(8), spacing=dp(2))
        heading = BoxLayout(size_hint_y=None, height=dp(18), spacing=dp(8))
        heading.add_widget(label("Camera", 12, height=18, bold=True, size_hint_x=None, width=dp(70)))
        status = label("Connecting…", 10, MUTED, 18, halign="right", shorten=True)
        self.camera_status_labels.append(status)
        heading.add_widget(status)
        card.add_widget(heading)
        card.add_widget(self.camera_texture.new_view())
        return card

    def _build_camera(self):
        from carveracontroller.desktop_inspectors import build_camera

        build_camera(self)

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
        recorder = getattr(self, "run_recording_panel", None)
        recorded = recorder is not None and recorder.camera_replay_enabled
        if recorded:
            frame = recorder.recorded_camera_frame
        age = frame.age() if frame else None
        if frame:
            aspect = frame.size[0] / frame.size[1]
            if aspect != getattr(self, "camera_aspect", None):
                self.camera_aspect = aspect
                self._layout_media()
        if recorded:
            text, color = recorder.camera_replay_status, AMBER
        elif not enabled:
            text, color = "Paused • last image frozen", MUTED
        elif error:
            text, color = error, AMBER
        elif frame is None:
            text, color = "Waiting for a camera image", MUTED
        elif age is None:
            text, color = "Frame received • capture time unavailable", AMBER
        elif age > 2:
            text, color = f"Stale image • captured {age:.1f}s ago", AMBER
        else:
            text, color = f"Live • captured {age:.1f}s ago", ACCENT
        for item in self.camera_status_labels:
            item.text, item.color = text, color
        self.camera_toggle.text = (
            ("Pause live capture" if enabled else "Resume live capture")
            if recorded
            else ("Pause viewing" if enabled else "Resume viewing")
        )
        if self.workspaces.current == "Job":
            for view in self.camera_texture.views:
                view.empty_text = (
                    text if recorded or error else "Camera paused" if not enabled else "Waiting for a camera image"
                )
            self.camera_texture.update(frame)
            if recorded:
                for view in self.camera_texture.views:
                    view.set_overlay((), None)
            elif hasattr(self, "camera_registration_panel"):
                self.camera_registration_panel.update_overlay()

    def _retry_configuration(self):
        if self.app.state != "Idle" or self.machine.config_loading:
            return
        self.machine._config_download_failures = 0
        self.machine._config_apply_failed = False
        self.machine.config_loading = True
        self.machine.download_config_file()

    def _build_settings(self):
        from carveracontroller.desktop_inspectors import build_settings

        build_settings(self)

    def _build_footer(self):
        footer = Surface(radius=0, padding=(dp(24), dp(5)), size_hint_y=None, height=dp(34))
        self.footer_status = label("", 11, MUTED, 24)
        footer.add_widget(self.footer_status)
        self.recording_alert = Action(
            "Telemetry log stopped",
            self._open_recording_diagnostics,
            height=dp(24),
            size_hint_x=None,
            width=0,
            opacity=0,
            disabled=True,
        )
        self.recording_alert.base_color = AMBER
        self.recording_alert.color = BG
        self.recording_alert._paint()
        footer.add_widget(self.recording_alert)
        self.progress = label("", 11, MUTED, 24, halign="right")
        footer.add_widget(self.progress)
        footer.add_widget(
            Action(
                "Find action · Cmd/Ctrl+K", self._open_command_palette, height=dp(24), size_hint_x=None, width=dp(158)
            )
        )
        self.add_widget(footer)

    def _open_recording_diagnostics(self):
        self.select("Monitor")
        self.monitor_section_buttons["Diagnostics"].dispatch("on_release")

    def _install_command_center(self, body):
        """A single media stage and a dedicated, sectioned Workbench."""
        self.inspector = Surface(orientation="vertical", padding=dp(10), spacing=dp(6), size_hint_x=0.5)
        self.section_names = {
            "Preview": "Program & simulation",
            "Scene": "Scene & components",
            "Overview": "Position & motion",
            "Setup": "Setup & tools",
            "Monitor": "Spindle & engagement",
            "Console": "Commands & program",
            "Settings": "Machine & connection",
            "Camera": "Camera source",
        }
        self.section_choice = Choice(text=self.section_names["Preview"], values=tuple(self.section_names.values()))
        self.section_choice.bind(text=self._select_capability)
        self.tab_buttons = {}
        tabs = AdaptiveGrid(max_cols=9, min_width=48, row_height=32, spacing=dp(4))
        self.workbench_tabs = tabs
        for key, title in (
            ("Preview", "Program"),
            ("Scene", "Scene"),
            ("Overview", "Position"),
            ("Setup", "Setup"),
            ("Monitor", "Spindle"),
            ("Console", "Console"),
            ("Settings", "Machine"),
            ("Camera", "Camera"),
        ):
            button = Action(title, lambda key=key: self.select("Job" if key == "Preview" else key), height=dp(32))
            self.tab_buttons[key] = button
            tabs.add_widget(button)
        self.tab_buttons["Profiles"] = Action("Profiles", self._open_profiles, height=dp(32))
        tabs.add_widget(self.tab_buttons["Profiles"])
        self.workbench_navigation = BoxLayout(size_hint_y=None, height=dp(32))
        self.workbench_compact_navigation = BoxLayout(spacing=dp(6))
        self.section_choice.height = dp(32)
        self.workbench_compact_navigation.add_widget(self.section_choice)
        self.workbench_compact_navigation.add_widget(
            Action("Profiles", self._open_profiles, height=dp(32), size_hint_x=None, width=dp(80))
        )
        self.workbench_navigation.bind(width=self._reflow_workbench_navigation)
        self.inspector.add_widget(self.workbench_navigation)
        trail = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(26))
        self.workspace_back = Action(
            "Back", lambda: self.navigation.navigate(-1), size_hint_x=None, width=dp(64), height=dp(26), disabled=True
        )
        self.workspace_forward = Action(
            "Forward", lambda: self.navigation.navigate(1), size_hint_x=None, width=dp(76), height=dp(26), disabled=True
        )
        trail.add_widget(self.workspace_back)
        trail.add_widget(self.workspace_forward)
        self.navigation_label = label("Selection history", 11, MUTED, 26, shorten=True, max_lines=1)
        trail.add_widget(self.navigation_label)
        self.inspector.add_widget(trail)
        self.inspector.add_widget(self._build_machine_controls())
        self.connection_recovery = BoxLayout(size_hint_y=None, height=0, spacing=dp(6), opacity=0, disabled=True)
        self.recovery_note = label("", 10, AMBER, 28)
        self.recovery_note.bind(width=lambda obj, width: setattr(obj, "text_size", (width, None)))
        self.recovery_note.bind(texture_size=lambda *_: self.refresh_connection_recovery())
        self.connection_recovery.add_widget(self.recovery_note)
        self.recovery_retry = Action(
            "Reconnect now",
            lambda: self.machine.reconnection_popup.reconnect(),
            size_hint_x=None,
            width=dp(100),
            height=dp(28),
        )
        self.recovery_cancel = Action(
            "Cancel retries",
            lambda: self.machine.reconnection_popup.cancel_reconnect(),
            size_hint_x=None,
            width=dp(94),
            height=dp(28),
        )
        self.connection_recovery.add_widget(self.recovery_retry)
        self.connection_recovery.add_widget(self.recovery_cancel)
        self.inspector.add_widget(self.connection_recovery)
        pose_context = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(28))
        self.pose_status = label("Preview view · No operation selected", 11, AMBER, 28, shorten=True, max_lines=1)
        self.return_live_action = Action(
            "Return to live", self.return_to_live, height=dp(28), size_hint_x=None, width=dp(108), disabled=True
        )
        pose_context.add_widget(self.pose_status)
        pose_context.add_widget(self.return_live_action)
        self.pose_context = pose_context
        self.inspector.add_widget(pose_context)
        from carveracontroller.desktop_readiness import SetupReadiness

        self.readiness = SetupReadiness(self)
        self.inspector.add_widget(self.readiness.strip)
        self.inspector_pages = ScreenManager(transition=NoTransition())
        for key in self.section_names:
            old = self.workspaces.get_screen(key)
            content = old.children[0]
            old.remove_widget(content)
            screen = Screen(name=key)
            screen.add_widget(content)
            self.inspector_pages.add_widget(screen)
            self.nav[key] = self.tab_buttons[key]
        readiness_screen = Screen(name="Readiness")
        readiness_screen.add_widget(self.readiness.build_page())
        self.inspector_pages.add_widget(readiness_screen)
        self.section_names["Readiness"] = "Setup evidence"
        self.section_choice.values = tuple(self.section_names.values())
        self.nav["Job"] = self.tab_buttons["Preview"]
        self.inspector.add_widget(self.inspector_pages)
        self.rail_note = label("Spindle monitor · shadow proposals only", 10, MUTED, 16)
        self.inspector.add_widget(self.rail_note)
        from carveracontroller.desktop_pane_divider import PaneDivider

        self.pane_divider = PaneDivider(self)
        body.add_widget(self.pane_divider)
        body.add_widget(self.inspector)
        self.active_section = "Job"
        self.workspaces.current = "Job"
        for page, deck in (("Job", self.program_tasks), ("Setup", self.setup_tasks), ("Settings", self.machine_tasks)):
            deck.before_change = lambda page=page: self.navigation.task_changed(page, arriving=False)
            deck.after_change = lambda page=page: self.navigation.task_changed(page, arriving=True)
        self._reflow_workbench_navigation()

    def _reflow_workbench_navigation(self, *_args):
        """Keep navigation on one row and keep legacy menu anchors visible."""
        if not hasattr(self, "inspector_pages"):
            return
        compact = self.workbench_navigation.width < dp(464)
        target = self.workbench_compact_navigation if compact else self.workbench_tabs
        if target.parent is self.workbench_navigation:
            return
        from carveracontroller.desktop_components import release_screen_focus

        self.section_choice.is_open = False
        for child in tuple(self.workbench_navigation.children):
            release_screen_focus(child)
            self.workbench_navigation.remove_widget(child)
        self.workbench_navigation.add_widget(target)
        for key in self.section_names:
            self.nav[key] = self.section_choice if compact else self.tab_buttons.get(key, self.tab_buttons["Setup"])
        self.nav["Job"] = self.nav["Preview"]

    def _select_capability(self, _choice, title):
        key = next(key for key, value in self.section_names.items() if value == title)
        page = "Job" if key == "Preview" else key
        if page != self.active_section:
            self.select(page)

    def _refresh_setup_strip_visibility(self):
        """Reserve setup actions for the sections where they inform the task."""
        strip = self.readiness.strip
        if self.active_section in ("Job", "Scene", "Setup", "Readiness"):
            if strip.parent is None:
                # Kivy children are reverse ordered: insert immediately above pages.
                self.inspector.add_widget(strip, index=self.inspector.children.index(self.inspector_pages) + 1)
        elif strip.parent is self.inspector:
            from carveracontroller.desktop_components import release_screen_focus

            release_screen_focus(strip)
            self.inspector.remove_widget(strip)

    def _toggle_inspector(self):
        if self.inspector.parent:
            self.body.remove_widget(self.inspector)
            if self.machine.keyboard_jog_control:
                self.machine.toggle_keyboard_jog_control(disable=True)
        else:
            self.body.add_widget(self.inspector)

    def _open_profiles(self):
        from carveracontroller.desktop_profiles import ProfileLibrary

        generation = self.profile_store.generation if self.profile_store else None
        if self.active_section != "Profiles":
            self.profile_return_section = self.active_section
        if not hasattr(self, "profile_library"):
            self.profile_library = ProfileLibrary(self, store=self.profile_store, embedded=True)
            self.profile_library_generation = generation
            screen = Screen(name="Profiles")
            screen.add_widget(self.profile_library)
            self.inspector_pages.add_widget(screen)
            self.section_names["Profiles"] = "Machine & tool profiles"
            self.section_choice.values = tuple(self.section_names.values())
            self.nav["Profiles"] = (
                self.section_choice
                if self.workbench_compact_navigation.parent is self.workbench_navigation
                else self.tab_buttons["Profiles"]
            )
        if self.profile_library_generation != generation:
            self.profile_library.refresh()
            self.profile_library_generation = generation
        self.select("Profiles")

    def close_profile_library(self):
        target = getattr(self, "profile_return_section", "Setup")
        if target == "Profiles" or (target != "Job" and target not in self.section_names):
            target = "Setup"
        self.select(target)

    def apply_machine_profile(self, profile):
        """Select local connection/preview metadata without changing the CNC."""
        from carveracontroller.machine.desktop_profiles import validate_record

        profile = validate_record("machines", profile)
        cad = self._prepare_selected_profile_cad(profile, self.machine.gcode_viewer.machine_profile)
        self.apply_prepared_machine_profile(profile, cad)

    def apply_prepared_machine_profile(self, profile, cad):
        """Publish worker-prepared CAD without loading geometry on the UI thread."""
        from carveracontroller.machine.desktop_profiles import validate_record

        profile = validate_record("machines", profile)
        self.machine.gcode_viewer.cancel_default_machine_profile()
        self._profile_load_generation += 1
        self._profile_load_pending = None
        self.machine_profile_loading = False
        self._publish_machine_profile(profile, cad)

    def _publish_machine_profile(self, profile, cad):
        """Publish the complete selection with one final GPU scene construction."""
        viewer = self.machine.gcode_viewer
        was_visible = viewer.machine_visible
        if was_visible:
            viewer.set_machine_visible(False)
        try:
            self._publish_machine_profile_selection(profile, cad)
        finally:
            if was_visible:
                viewer.set_machine_visible(True)

    def _publish_machine_profile_selection(self, profile, cad):
        # Validate the complete selection before replacing any current metadata.
        if profile["camera_url"]:
            self.camera_client.configure(profile["camera_url"])
            self.camera_url_input.text = profile["camera_url"]
            Config.set("carvera", "webcam_snapshot_url", profile["camera_url"])
        viewer = self.machine.gcode_viewer
        viewer.machine_component_profiles.clear()
        if cad is not None:
            viewer.machine_profile = cad
            viewer.machine_profile_error = None
            if viewer.machine_visible:
                viewer._build_machine_scene()
        viewer.configure_workholding(
            (profile["vise_x"], profile["vise_y"], profile["vise_z"]),
            profile["vise_rotation"],
            profile["vise_jaw_offset"],
        )
        viewer.clear_repeat_stock()
        self.selected_machine_profile = profile
        Config.set("carvera", "desktop_machine_profile_id", profile["id"])
        Config.write()
        self.selected_machine_label.text = (
            f"Selected: {profile['name']}\n{profile['host']}:{profile['port']} • connect explicitly"
        )
        self.profile_status.text = f"{profile['name']} • local profile\n" + (
            self.loaded_toolset["name"] if self.loaded_toolset else "No toolset loaded"
        )

        if hasattr(self, "seed_scene_choices"):
            self.seed_scene_choices(profile)

    def _profile_scene_identity(self):
        viewer = self.machine.gcode_viewer
        return (
            viewer.machine_profile,
            viewer.machine_setup,
            tuple(viewer.machine_component_profiles.items()),
            viewer.workholding_offset_mm,
            viewer.workholding_rotation_deg,
            viewer.jaw_offset_mm,
            getattr(self.run_recording_panel, "previous_scene", None),
            getattr(self.run_recording_panel, "busy", False),
            viewer.move_scale_by_positon,
        )

    def request_machine_profile(self, profile, on_result=None):
        """Prepare CAD off the UI thread; retain one active and one latest request."""
        from carveracontroller.machine.desktop_profiles import validate_record

        if self._profile_load_closed:
            return False
        profile = validate_record("machines", profile)
        self.machine.gcode_viewer.cancel_default_machine_profile()
        self._profile_load_generation += 1
        request = (self._profile_load_generation, profile, self._profile_scene_identity(), on_result)
        self.machine_profile_loading = True
        self.profile_status.text = f"Preparing {profile['name']}… • current scene retained"
        if self._profile_load_active:
            self._profile_load_pending = request
        else:
            self._start_machine_profile_request(request)
        return True

    @staticmethod
    def _prepare_selected_profile_cad(profile, previous):
        from carveracontroller.addons.machine_simulation.profile import DEFAULT_PROFILE, MachineProfile

        if profile["cad_path"]:
            return MachineProfile.reuse_or_load(Path(profile["cad_path"]), previous)
        if previous is None:
            try:
                return MachineProfile.load(DEFAULT_PROFILE)
            except FileNotFoundError:
                return None
        return None

    def _start_machine_profile_request(self, request):
        generation, profile, scene_identity, on_result = request
        self._profile_load_active = True
        previous = scene_identity[0]
        saved = self.scene_setup_store.get(profile["id"]) if hasattr(self, "scene_setup_store") else None
        placement = (
            (saved["workholding_offset_mm"], saved["workholding_rotation_deg"], saved["jaw_offset_mm"])
            if saved
            else (
                (profile["vise_x"], profile["vise_y"], profile["vise_z"]),
                profile["vise_rotation"],
                profile["vise_jaw_offset"],
            )
        )
        from carveracontroller.addons.machine_simulation.model import MachineSetup

        work_offset = tuple(saved["work_offset_mm"]) if saved else MachineSetup().work_offset_mm
        render_scale = self.machine.gcode_viewer.move_scale_by_positon or 1.0

        def work():
            try:
                cad = self._prepare_selected_profile_cad(profile, previous)
                from carveracontroller.addons.machine_simulation.profile import MachineProfile

                assembly = cad if cad is not None else previous
                if isinstance(assembly, MachineProfile):
                    assembly.prepare_render_buffers(work_offset, render_scale, placement)
                error = None
            except Exception as exc:
                cad, error = None, str(exc)

            def finish(_dt):
                self._profile_load_active = False
                pending, self._profile_load_pending = self._profile_load_pending, None
                if self._profile_load_closed:
                    return
                if pending is not None:
                    self._start_machine_profile_request(pending)
                    return
                if generation != self._profile_load_generation:
                    return
                self.machine_profile_loading = False
                if error is None and scene_identity != self._profile_scene_identity():
                    message = "Scene changed during preparation; select the profile again to review it."
                else:
                    message = error
                if message is None:
                    try:
                        self._publish_machine_profile(profile, cad)
                    except (ValueError, OSError) as exc:
                        message = str(exc)
                if message is not None:
                    self.profile_status.text = "Profile not loaded • " + message
                if on_result is not None:
                    on_result(message is None, message)

            Clock.schedule_once(finish, 0)

        threading.Thread(target=work, name="machine-profile-prepare", daemon=True).start()

    def _connection_opening(self):
        return any(
            (
                getattr(self.machine, "_wifi_connect_in_progress", False),
                getattr(self.machine, "_usb_connect_in_progress", False),
                getattr(self.machine.controller, "_connecting", False),
            )
        )

    def _can_connect_profile(self):
        profile = self.selected_machine_profile
        return bool(
            profile
            and profile.get("host")
            and profile.get("port")
            and not self.connected
            and not self._connection_opening()
        )

    def _connect_profile(self):
        if not self._can_connect_profile():
            return
        profile = self.selected_machine_profile
        self.machine.openWIFI(f"{profile['host']}:{profile['port']}")

    def _assembly_preview_request(self, assembly_id, slot=None):
        from carveracontroller.machine.assembly_preview import assembly_definition, design_fingerprint

        assembly = self.machine.tool_custody.assembly(assembly_id)
        if assembly is None or not self.profile_store:
            raise ValueError("Select a saved assembly and cutter library first")
        profile = next((p for p in self.profile_store.data["tools"] if p["id"] == assembly["profile_id"]), None)
        if profile is None:
            raise ValueError("Linked cutter design is missing; relink the assembly first")
        definition = assembly_definition(assembly, profile, slot)
        viewer = self.machine.gcode_viewer
        definitions = dict(viewer.library_tool_table_mm)
        previous_binding = viewer.assembly_preview_binding
        if previous_binding:
            old_number = previous_binding["number"]
            if previous_binding["previous_definition"] is None:
                definitions.pop(old_number, None)
            else:
                definitions[old_number] = previous_binding["previous_definition"]
        previous = definitions.get(definition.number)
        definitions[definition.number] = definition
        binding = {
            "assembly_id": assembly["id"],
            "revision_id": assembly["revision_id"],
            "profile_id": profile["id"],
            "design_fingerprint": design_fingerprint(profile),
            "number": definition.number,
            "name": assembly["name"],
            "previous_definition": previous,
            "previous_override": previous_binding["previous_override"]
            if previous_binding
            else viewer.preview_tool_override,
        }
        return definitions, binding, deepcopy(assembly), deepcopy(profile)

    def _publish_assembly_preview(self, prepared, binding, assembly, profile):
        from carveracontroller.machine.assembly_preview import design_fingerprint

        current = self.machine.tool_custody.assembly(assembly["id"])
        current_profile = next((p for p in self.profile_store.data["tools"] if p["id"] == profile["id"]), None)
        if current is None or current["revision_id"] != assembly["revision_id"] or current_profile is None:
            raise ValueError("Assembly revision changed during preparation; preview it again")
        if design_fingerprint(current_profile) != binding["design_fingerprint"]:
            raise ValueError("Linked cutter changed during preparation; preview the assembly again")
        viewer = self.machine.gcode_viewer
        viewer.publish_tool_profiles(prepared)
        viewer.assembly_preview_binding = binding
        viewer.select_preview_tool(binding["number"])
        self.tool_library_summary.text = f"Assembly preview T{binding['number']}: {assembly['name']} · revision {assembly['revision_count']}\nDeclared stickout: {assembly['stickout_mm']} mm · holder {'CAD supplied' if prepared[0][binding['number']].holder_geometry_path else 'geometry missing'}"

    def preview_physical_assembly(self, assembly_id, slot=None):
        from carveracontroller.addons.tool_visualization.profile_loading import prepare_tool_profiles

        definitions, binding, assembly, profile = self._assembly_preview_request(assembly_id, slot)
        viewer = self.machine.gcode_viewer
        prepared = prepare_tool_profiles(
            definitions,
            viewer.library_tool_table_mm,
            viewer.tool_table or {},
            viewer.move_scale_by_positon,
            viewer.tool_unit_scale,
        )
        self._publish_assembly_preview(prepared, binding, assembly, profile)
        return binding["number"]

    def request_assembly_preview(self, assembly_id, slot=None, on_result=None):
        definitions, binding, assembly, profile = self._assembly_preview_request(assembly_id, slot)
        return self._request_tool_profiles(
            definitions,
            True,
            lambda prepared: self._publish_assembly_preview(prepared, binding, assembly, profile),
            on_result,
        )

    def _restored_assembly_definitions(self):
        viewer = self.machine.gcode_viewer
        binding = viewer.assembly_preview_binding
        definitions = dict(viewer.library_tool_table_mm)
        if binding is None:
            return definitions, viewer.preview_tool_override
        if binding["previous_definition"] is None:
            definitions.pop(binding["number"], None)
        else:
            definitions[binding["number"]] = binding["previous_definition"]
        return definitions, binding["previous_override"]

    def _publish_cleared_assembly(self, prepared, override):
        viewer = self.machine.gcode_viewer
        viewer.publish_tool_profiles(prepared)
        viewer.select_preview_tool(override if override in prepared[0] else None)
        if viewer.preview_tool_override is None:
            self._restore_profile_status()
        self.tool_library_summary.text = "Assembly preview cleared; previous local tool definitions restored."

    def _restore_profile_status(self):
        profile = getattr(self, "selected_machine_profile", None)
        toolset = getattr(self, "loaded_toolset", None)
        machine = f"{profile['name']} • local profile" if profile else "Local profiles"
        self.profile_status.text = machine + "\n" + (toolset["name"] if toolset else "No toolset loaded")

    def clear_assembly_preview(self):
        viewer = self.machine.gcode_viewer
        if viewer.assembly_preview_binding is None:
            return
        definitions, override = self._restored_assembly_definitions()
        viewer.load_tool_profiles(definitions)
        viewer.select_preview_tool(override if override in definitions else None)
        if viewer.preview_tool_override is None:
            self._restore_profile_status()
        self.tool_library_summary.text = "Assembly preview cleared; previous local tool definitions restored."

    def request_clear_assembly_preview(self, on_result=None, *, follow_program=False):
        definitions, override = self._restored_assembly_definitions()
        return self._request_tool_profiles(
            definitions,
            True,
            lambda prepared: self._publish_cleared_assembly(prepared, None if follow_program else override),
            on_result,
        )

    def request_scene_tool_profile(self, profile, on_result=None):
        from carveracontroller.machine.desktop_profiles import to_tool_definition

        profile = deepcopy(profile)
        definitions, _override = self._restored_assembly_definitions()
        definition = to_tool_definition(profile)
        definitions[definition.number] = definition

        def publish(prepared):
            current = next((p for p in self.profile_store.data["tools"] if p["id"] == profile["id"]), None)
            if current != profile:
                raise ValueError("Saved cutter changed during preparation; select it again")
            self.apply_tool_profile(profile, prepared=prepared)
            self.machine.gcode_viewer.select_preview_tool(definition.number)

        return self._request_tool_profiles(definitions, True, publish, on_result)

    def request_tool_profile(self, profile, slot=None, on_result=None):
        profile = deepcopy(profile)
        from carveracontroller.machine.desktop_profiles import to_tool_definition

        definition = to_tool_definition(profile, number=slot, units="mm")
        return self._request_tool_profiles(
            {definition.number: definition},
            False,
            lambda prepared: self.apply_tool_profile(profile, slot, prepared),
            on_result,
        )

    def request_toolset_profile(self, toolset, definitions, on_result=None):
        toolset = deepcopy(toolset)
        if not isinstance(definitions, dict):
            definitions = {tool.number: tool for tool in definitions}
        return self._request_tool_profiles(
            definitions,
            True,
            lambda prepared: self.apply_toolset_profile(toolset, prepared[0], prepared),
            on_result,
        )

    def _request_tool_profiles(self, definitions, replace, publish, on_result):
        from carveracontroller.desktop_tool_profile_loading import ToolProfileLoads

        if not hasattr(self, "tool_profile_loads"):
            self.tool_profile_loads = ToolProfileLoads(self)
        accepted = self.tool_profile_loads.request(definitions, replace, publish, on_result)
        if accepted:
            self.tool_library_summary.text = "Preparing tool geometry… Current preview retained."
        return accepted

    def apply_tool_profile(self, profile, slot=None, prepared=None):
        from carveracontroller.machine.desktop_profiles import to_tool_definition

        definition = to_tool_definition(profile, number=slot, units="mm")
        if prepared is None:
            self.machine.gcode_viewer.load_tool_profiles({definition.number: definition}, replace=False)
        else:
            self.machine.gcode_viewer.publish_tool_profiles(prepared)
        if not hasattr(self, "loaded_tool_profiles"):
            self.loaded_tool_profiles = {}
        self.loaded_tool_profiles[definition.number] = deepcopy(profile)
        self.loaded_toolset = None
        Config.remove_option("carvera", "desktop_toolset_id")
        Config.write()
        self.profile_status.text = f"Preview T{definition.number}: {profile['name']}"
        self.tool_library_summary.text = (
            f"Preview T{definition.number}: {profile['name']}\n"
            + ("CAD mesh" if definition.geometry_path else "Dimension-based geometry")
            + (
                f" • stickout {definition.stickout:g} mm"
                if definition.stickout
                else " • stickout unknown / illustrative"
            )
        )

    def apply_toolset_profile(self, toolset, definitions, prepared=None):
        if not isinstance(definitions, dict):
            definitions = {tool.number: tool for tool in definitions}
        if prepared is None:
            self.machine.gcode_viewer.load_tool_profiles(definitions)
        else:
            self.machine.gcode_viewer.publish_tool_profiles(prepared)
        self.loaded_tool_profiles = {}
        self.loaded_toolset = dict(toolset)
        Config.set("carvera", "desktop_toolset_id", toolset["id"])
        Config.write()
        self.profile_status.text = f"{toolset['name']} • {len(definitions)}/6 preview slots"
        self.tool_library_summary.text = (
            "\n".join(
                f"T{number}  {tool.description or tool.tool_type.value.replace('_', ' ')} • Ø{tool.diameter:g} mm"
                for number, tool in sorted(definitions.items())
            )
            or "Empty toolset • no assigned preview tools"
        )

        self.tool_library_summary.height = dp(max(56, len(definitions) * 22))

    def _restore_profiles(self):
        if not self.profile_store:
            self.profile_status.text = self.profile_error or "Profile library unavailable"
            return
        store = self.profile_store
        try:
            if not store.data["machines"]:
                from carveracontroller.addons.machine_simulation.profile import DEFAULT_PROFILE

                address = getattr(self.machine, "past_machine_addr", "") or ""
                if address:
                    store.save_machine(
                        {
                            "name": "Workshop Carvera",
                            "model": "C1",
                            "host": address.split(":")[0],
                            "port": 2222,
                            "camera_url": self.camera_client.url,
                            "cad_path": str(DEFAULT_PROFILE) if DEFAULT_PROFILE.is_file() else "",
                        }
                    )
            selected = Config.get("carvera", "desktop_machine_profile_id", fallback="")
            machine = next((p for p in store.data["machines"] if p["id"] == selected), None)
            if machine:
                self.request_machine_profile(machine)
            selected = Config.get("carvera", "desktop_toolset_id", fallback="")
            toolset = next((p for p in store.data["toolsets"] if p["id"] == selected), None)
            if toolset:
                self.request_toolset_profile(toolset, store.toolset_definitions(toolset))
        except (ValueError, OSError) as exc:
            self.profile_status.text = f"Profile restore: {exc}"

    def choose_asset_file(self, callback, suffixes=(".json", ".json.gz")):
        from carveracontroller.desktop_file_picker import ArtifactBrowser

        self.artifact_browser = ArtifactBrowser(self, callback, suffixes, title="Choose registered asset")
        self.artifact_browser.open()

    def choose_profile_file(self, callback, save=False, extension=".json", title=None):
        from carveracontroller.desktop_file_picker import ArtifactBrowser

        self.artifact_browser = ArtifactBrowser(
            self,
            callback,
            (extension,),
            save=save,
            title=title or ("Export profiles" if save else "Import profiles"),
        )
        self.artifact_browser.open()

    def select(self, page, *, record_navigation=True):
        timings = self.navigation_timings
        if self._timing_pending_flip:
            self._timing_pending_flip["superseded"] = True
        if self._timing_clock_event:
            self._timing_clock_event.cancel()
        self._timing_pending_flip = None
        record = timings.begin(getattr(self, "active_section", None), page)
        completed = False
        try:
            self._select_timed(page, record_navigation, record)
            completed = True
        finally:
            timings.finish(record, completed=completed)
        self._timing_pending_flip = record
        self._timing_clock_event = Clock.schedule_once(
            lambda _dt: timings.observe(record, "clock_turn_s", current=self.active_section), 0
        )

    def _navigation_flip(self, *_args):
        record = self._timing_pending_flip
        if record is not None:
            self.navigation_timings.observe(record, "window_flip_s", current=self.active_section)
            self._timing_pending_flip = None

    def _select_timed(self, page, record_navigation, record):
        timings = self.navigation_timings
        if record_navigation:
            with timings.phase(record, "history_depart"):
                self.navigation.depart()
        self.active_section = page
        if page == "Scene" and hasattr(self, "object_inspector"):
            with timings.phase(record, "scene_selection"):
                self.machine.gcode_viewer.set_inspected_component(self.object_inspector.selected)
                self.object_inspector.refresh_trigger()
        self.workspaces.current = "Job"
        self.app.show_gcode_ctl_bar = False
        key = "Preview" if page == "Job" else page
        if key in self.section_names:
            if self.inspector_pages.current != key:
                from carveracontroller.desktop_components import release_screen_focus

                with timings.phase(record, "focus_release"):
                    release_screen_focus(self.inspector_pages.current_screen)
            if not self.inspector.parent:
                self.body.add_widget(self.inspector)
            with timings.phase(record, "page_activation"):
                self.inspector_pages.current = key
                self._refresh_setup_strip_visibility()
            with timings.phase(record, "tab_styling"):
                for name, button in self.tab_buttons.items():
                    button.base_color = ACCENT if name == key else RAISED
                    button.color = BG if name == key else TEXT
                    button._paint()
                title = self.section_names[key]
                if self.section_choice.text != title:
                    self.section_choice.text = title
        if page == "Console":
            self.machine.cmd_manager.current = "manual_cmd_page"
        else:
            self.machine.manual_cmd.focus = False
        if page != "Overview" and self.machine.keyboard_jog_control:
            self.machine.toggle_keyboard_jog_control(disable=True)
        if record_navigation:
            with timings.phase(record, "history_arrive"):
                self.navigation.enter(page)

    def _program_changed(self, _app, filename):
        if filename:
            self.select("Job")
        if hasattr(self, "operation_panel"):
            self.operation_panel.load(self.app.selected_local_filename)

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

    def refresh_connection_recovery(self):
        if not hasattr(self, "connection_recovery"):
            return
        recovery = self.machine.reconnection_popup
        visible = recovery.desktop_visible
        # Zero-height BoxLayouts still dispatch touches to overflowing children.
        # Detach hidden recovery controls so they cannot swallow header clicks.
        if visible and self.connection_recovery.parent is None:
            self.inspector.add_widget(
                self.connection_recovery, index=self.inspector.children.index(self.machine_controls)
            )
        elif not visible and self.connection_recovery.parent is self.inspector:
            self.inspector.remove_widget(self.connection_recovery)
        self.connection_recovery.disabled = not visible
        self.connection_recovery.opacity = 1 if visible else 0
        self.connection_recovery.height = max(dp(36), self.recovery_note.texture_size[1]) if visible else 0
        if hasattr(self, "pose_context"):
            self.pose_context.height = 0 if visible else dp(28)
            self.pose_context.opacity = 0 if visible else 1
            self.pose_context.disabled = visible
        self.recovery_note.text = (
            (
                f"Connection lost · retry {recovery.current_attempt + 1}/{recovery.max_attempts} in {recovery.countdown}s"
                if recovery.auto_reconnect_mode
                else recovery.desktop_message or "Connection lost · reconnect when ready"
            )
            if visible
            else ""
        )
        self.recovery_retry.disabled = not visible or self._connection_opening()
        self.recovery_cancel.text = "Cancel retries" if recovery.auto_reconnect_mode else "Dismiss"

    def refresh(self, _dt):
        record = self.refresh_timings.begin("periodic_refresh", getattr(self, "active_section", None))
        completed = False
        try:
            self._refresh_timed(_dt, record)
            completed = True
        finally:
            self.refresh_timings.finish(record, completed=completed)

    def _refresh_timed(self, _dt, timing_record):
        now = time.monotonic()
        previous = getattr(self, "_last_ui_refresh_at", now)
        gap = max(0.0, now - previous)
        self._last_ui_refresh_at = now
        self._largest_ui_refresh_gap = max(gap, getattr(self, "_largest_ui_refresh_gap", 0))
        response_age = self.machine.controller.machine_response_age(now)
        self.receive_age_metric.value.text = f"{response_age:.2f}s" if response_age is not None else "—"
        self.receive_age_metric.value.color = (
            MUTED if response_age is None else ACCENT if response_age <= 0.8 else AMBER
        )
        reacquiring = self.machine.controller.status_reacquisition_remaining(now)
        self.receive_age_metric.detail.text = (
            f"Awaiting post-transfer status · {reacquiring:.1f}s remaining"
            if self.machine.controller.status_reacquisition_pending
            else "Receive thread • independent of UI updates"
        )
        self.ui_gap_metric.value.text = f"{gap:.2f}s"
        self.ui_gap_metric.detail.text = f"Largest interval {self._largest_ui_refresh_gap:.2f}s since launch"
        from carveracontroller.desktop_ui_timing import refresh_navigation_timing

        refresh_navigation_timing(self)
        connecting = self._connection_opening()
        self.refresh_connection_recovery()
        attempt = getattr(self.machine, "_connection_attempt", None)
        failed = bool(not connecting and not self.connected and attempt is not None and attempt.success is False)
        protocol = self.machine.controller.comms.name if self.machine.controller.protocol_ready else "Not detected"
        self.connection_health_note.text = (
            attempt.summary(now)
            if attempt is not None and (connecting or failed)
            else "Opening transport / detecting protocol • controls remain responsive"
            if connecting
            else f"Protocol: {protocol} • camera freshness is reported separately in its pane"
            if self.connected
            else "No active connection • UI timing remains available"
        )
        self.connection_health_note.color = AMBER if failed else MUTED
        self.profile_connect_button.text = (
            "Connecting…" if connecting else "Retry profile" if failed else "Connect profile"
        )
        with self.refresh_timings.phase(timing_record, "readiness"):
            self.readiness.refresh()
        with self.refresh_timings.phase(timing_record, "capabilities"):
            self.capability_panel.refresh()
        with self.refresh_timings.phase(timing_record, "tool_comparison"):
            self.tool_comparison.refresh()
            if (
                self.active_section == "Setup"
                and self.slot_inventory_panel is not None
                and self.slot_inventory_panel.parent is not None
            ):
                self.slot_inventory_panel.refresh()
        with self.refresh_timings.phase(timing_record, "operation_context"):
            self.operation_panel.refresh_tool_context()
            if self.operation_panel.bank_workbench.parent:
                self.operation_panel.bank_workbench.refresh_if_changed()
        with self.refresh_timings.phase(timing_record, "simulation_inputs"):
            self.simulation_panel.refresh_inputs()
        if self.active_section == "Job" and self.program_tasks.active == "Run record":
            with self.refresh_timings.phase(timing_record, "recorded_run"):
                self.run_recording_panel.refresh()
        for button, guard in self.guards:
            button.disabled = not guard()
        connected = self.connected
        data = CNC.vars
        self.hold_button.text = "Resume motion" if self.app.state == "Hold" else "Feed hold"
        self.state_label.text = (
            "Connecting…"
            if connecting
            else "Connection failed"
            if failed
            else "Disconnected"
            if not connected
            else "Awaiting status…"
            if self.machine.controller.status_reacquisition_pending
            else self.app.state
        )
        self.state_label.color = (
            AMBER
            if failed
            else MUTED
            if not connected
            else AMBER
            if self.machine.controller.status_reacquisition_pending
            else ACCENT
            if self.app.state == "Idle"
            else AMBER
        )
        address = getattr(self.machine, "past_machine_addr", "")
        self.connection_label.text = (
            f"{self.app.model or 'Carvera'}  •  {address or 'USB'}"
            if connected
            else f"{attempt.transport} • {attempt.target}"
            if attempt is not None and (connecting or failed)
            else "Choose a connection to begin"
        )
        self.connect_button.text = "Connecting…" if connecting else "Connection" if connected else "Connect…"
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
        pending_stock = getattr(self, "pending_job_rest_stock", None)
        if (
            pending_stock
            and not self.machine.loading_file
            and self.machine._last_loaded_file_key == pending_stock[0]
            and self.operation_panel.program
        ):
            from carveracontroller.machine.simulation_preview import stock_geometry

            self.pending_job_rest_stock = None
            try:
                panel = self.simulation_panel
                panel.rest_stock = pending_stock[1]
                panel.rest_identity = panel._identity()
                viewer.set_rest_stock_geometry(stock_geometry(panel.rest_stock))
                panel.stock_source.text = "Continue rest stock"
                panel.note.text = "Restored residual stock from job package · physical setup unverified"
            except ValueError as exc:
                self.package_note.text = "Residual stock not applied: " + str(exc)
        self._refresh_observed_pose(viewer)
        if hasattr(viewer, "get_machine_simulation_info"):
            info = viewer.get_machine_simulation_info()
            self.model_caption.text = (
                f"Machine & toolpath · {viewer.pose_mode}"
                + (" · preparing profile" if self.machine_profile_loading or viewer._default_profile_loading else "")
                + (" · draft setup" if info.get("fixture_registration") or info.get("workholding") else "")
            )
            self.machine_view_button.text = "Machine on" if info["visible"] else "Machine off"
            self._syncing_scene_controls = True
            try:
                for group, check in self.component_checks.items():
                    visible = (
                        viewer.cutter_visible
                        if group == "cutter"
                        else info["groups"]["fixed"]
                        if group == "outer"
                        else info["groups"][group]
                    )
                    if check.active != visible:
                        check.active = visible
            finally:
                self._syncing_scene_controls = False
            for group, (button, title) in self.scene_buttons.items():
                button.text = f"{title}: {'shown' if info['groups'][group] else 'hidden'}"
            if info["visible"]:
                placement = (
                    "origin configured"
                    if info.get("alignment_configured", info.get("alignment_confirmed"))
                    else "illustrative origin"
                )
                fixture = " • Saunders plate (draft)" if info.get("fixture_registration") else ""
                if info.get("workholding"):
                    fixture += " • Gen3 Mod Vise (draft)"
                self.machine_preview_note.text = f"{info['model']} • {placement}{fixture} • " + (
                    "computed rest stock; clearance unqualified"
                    if self.simulation_panel.report
                    else "setup preview; clearance unqualified"
                )
            elif getattr(viewer, "_machine_has_rotary_motion", False):
                self.machine_preview_note.text = (
                    "Rotary toolpath • full-machine scene is available for 3-axis previews only"
                )
        self.simulate_button.text = "Pause preview" if self.machine.gcode_playing else "Play preview"
        self.job_tool_label.text = (
            f"Active tool T{self.app.tool}  •  Length offset {data['tlo']:.3f} mm" if connected else "Preview only"
        )
        self.empty_preview.height = 0
        self.empty_preview.opacity = 0 if filename else 1
        self.progress.text = self.machine.progress_info or "No program running"
        self.stage_context.text = (
            f"{self.machine.coord_system_data_view.main_text} · Work position · mm\n"
            f"X {data['wx']:.2f}   Y {data['wy']:.2f}   Z {data['wz']:.2f}"
            if connected
            else "Local preview\nConnect to receive live position"
        )
        self.stage_tool_context.text = (
            f"Reported tool T{self.app.tool}\nLength offset {data['tlo']:.3f} mm"
            if connected
            else "Tool state unavailable"
        )
        self.stage_process_context.text = (
            f"Spindle {data['curspindle']:,.0f} RPM\nFeed {data['curfeed']:,.0f} mm/min"
            if connected
            else "Spindle and feed unavailable"
        )
        self.repeat_parts_panel.refresh_frame_review()
        self._refresh_monitor(connected)
        if connected and not self.machine.config_loaded:
            self.footer_status.text += " • " + (
                "Loading machine configuration" if self.machine.config_loading else "Machine configuration unavailable"
            )
        self._refresh_camera()

    def _refresh_monitor(self, connected):
        with self.machine.controller._adaptive_lock:
            state = self.machine.controller.adaptive_monitor.snapshot(time.monotonic())
            samples = list(self.machine.controller.adaptive_monitor.history)
        state["persistence"] = self.machine.controller.telemetry_persistence()
        storage = state["persistence"]
        alert = bool(
            storage
            and (
                storage.get("error") or storage.get("prior_lost_records", 0) or storage["rejected"] or storage["failed"]
            )
        )
        self.recording_alert.width = dp(150) if alert else 0
        self.recording_alert.opacity = 1 if alert else 0
        self.recording_alert.disabled = not alert
        self.recording_alert.text = (
            "Telemetry log stopped" if storage and storage.get("error") else "Telemetry gap • review"
        )
        sample = state["sample"]
        self.telemetry_diagnostics.update(state, connected)
        age = time.monotonic() - sample["timestamp"] if sample else None
        fresh = connected and age is not None and 0 <= age <= 0.8
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
        fault = state.get("fault")
        self.monitor_droop.value.text = f"{state['filtered_droop'] * 100:.2f}%" if fresh and baseline else "—"
        self.monitor_feed.value.text = (
            f"{state['proposed_override']:.0f}%"
            if fresh and baseline and not fault and state["mode"] == "shadow"
            else "—"
        )
        self.monitor_feed.detail.text = "Fault latched • no proposal" if fault else "Shadow proposal • not applied"
        self.monitor_reason.text = (
            ("Current complete telemetry fresh" if fresh else "Current complete telemetry stale / unavailable")
            + "\nLatched monitor fault • "
            + fault
            + "\nReset monitor or capture a fresh unloaded baseline to rearm."
            if connected and fault
            else state["reason"].replace(
                "baseline required (adaptive baseline); no feed proposal",
                "Capture an unloaded baseline before using feed proposals.",
            )
            if connected
            else "Connect a machine to receive live telemetry."
        )
        self.rail_note.text = f"Spindle monitor · {state['mode']} proposals only"
        if self.inspector_pages.current == "Monitor" and self.monitor_sections.current == "Signal":
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
