"""Desktop workflow shell over the existing controller and preflight actions.

Navigation and telemetry are read-only. Machine actions use the same guarded
controller paths as the original UI; adaptive control remains shadow-only.
"""

import time
from pathlib import Path

from kivy.clock import Clock
from kivy.config import Config
from kivy.core.window import Window
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
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
    label,
)
from carveracontroller.desktop_components import DesktopScrollView as ScrollView
from carveracontroller.machine.webcam import DEFAULT_CAMERA_URL, WebcamClient
from carveracontroller.webcam_view import WebcamTexture


class DesktopWorkspace(Surface):
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
        self.setup_page.add_widget(self.surface_planning_panel, index=len(self.setup_page.children))
        from carveracontroller.desktop_hole_planning import HolePlanningPanel

        self.hole_planning_panel = HolePlanningPanel(self)
        self.setup_page.add_widget(self.hole_planning_panel, index=len(self.setup_page.children) - 1)
        self._build_monitor()
        self._build_console()
        self._build_camera()
        self._build_settings()
        self._install_command_center(body)
        self._restore_profiles()
        self.seed_scene_choices(self.selected_machine_profile)
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
        return False

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
            lambda: self.app.state in ("Run", "Idle", "Hold"),
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
            compact = width < dp(560)
            connection.orientation = "vertical" if compact else "horizontal"
            connection.height = dp(86 if compact else 42)

        connection.bind(width=layout)
        layout(connection, connection.width)
        return connection

    @property
    def connected(self):
        return self.app.state not in ("N/A", "", "Disconnected")

    def _connection_menu(self):
        self.select("Settings")

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
        self.stage_context = label("", 11, MUTED, 48)
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
        tools = self._page("Preview", scroll=True)
        tools.add_widget(label("Program & preview", 16, height=28, bold=True))
        tools.add_widget(self.program_label)
        tools.add_widget(self.stage_context)
        actions = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
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
                    (
                        self.app.state == "Idle"
                        and self.machine.config_loaded
                        and bool(self.app.selected_remote_filename)
                        and not self.app.playing
                    )
                    or self.app.state == "Pause"
                ),
                primary=True,
            )
        )
        tools.add_widget(actions)
        from carveracontroller.desktop_operations import OperationPanel

        self.operation_panel = OperationPanel(self)
        tools.add_widget(self.operation_panel)
        from carveracontroller.desktop_job_packages import export_job, import_job

        packages = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
        packages.add_widget(Action("Export complete job", lambda: export_job(self)))
        packages.add_widget(Action("Restore job preview", lambda: import_job(self)))
        tools.add_widget(packages)
        self.package_note = label("Portable jobs include program, setup and referenced CAD assets.", 11, MUTED, 48)
        tools.add_widget(self.package_note)
        from carveracontroller.desktop_simulation import SimulationPanel

        self.simulation_panel = SimulationPanel(self)
        tools.add_widget(self.simulation_panel)
        pose_controls = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        pose_controls.add_widget(label("Machine pose", 11, MUTED, 36))
        self.pose_choice = Choice(text="Preview", values=("Preview", "Live", "Compare"))
        self.pose_choice.bind(text=lambda _widget, mode: viewer.set_pose_mode(mode))
        pose_controls.add_widget(self.pose_choice)
        tools.add_widget(pose_controls)
        self.pose_note = label(
            "Preview uses the local setup; live pose requires a fresh machine packet.", 11, MUTED, 58
        )
        tools.add_widget(self.pose_note)
        tools.add_widget(self.job_tool_label)
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
        tools.add_widget(view_actions)
        self.scene_buttons = {}
        from carveracontroller.desktop_scene import build_scene_controls

        build_scene_controls(self)
        tools.add_widget(label("Toolpath playback", 12, MUTED, 28))
        playback = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(6))
        playback.add_widget(
            self._guarded("|‹", self.machine.gcode_play_to_start, playback_guard, size_hint_x=None, width=dp(40))
        )
        self.simulate_button = self._guarded("Play preview", self.machine.gcode_play_toggle, playback_guard)
        playback.add_widget(self.simulate_button)
        playback.add_widget(
            self._guarded("›|", self.machine.gcode_play_to_end, playback_guard, size_hint_x=None, width=dp(40))
        )
        tools.add_widget(playback)
        slider = self.machine.ids["gcode_play_slider"]
        slider.parent.remove_widget(slider)
        slider.size_hint = (1, None)
        slider.height = dp(36)
        tools.add_widget(slider)
        tools.add_widget(self.machine_preview_note)
        tools.add_widget(Action("Program & console", lambda: self.select("Console")))
        controls = AdaptiveGrid(max_cols=2, min_width=120, row_height=36, spacing=dp(6))
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
        tools.add_widget(controls)
        Clock.schedule_once(
            lambda _dt: viewer.set_machine_visible(True) if hasattr(viewer, "set_machine_visible") else None, 0.3
        )

    def _layout_media(self, *_args):
        """Both images stay visible, with geometry sized to their aspect ratios."""
        camera = self.job_camera_splitter.parent is self.preview_row
        available = max(1, self.media_holder.height)
        inverse = 1 / 1.6 + (1 / getattr(self, "camera_aspect", 16 / 9) if camera else 0)
        # Each pane has 8dp insets, an 18dp caption and a 2dp caption gap.
        chrome = dp(36 + (48 if camera else 0))
        width = max(dp(180), min(self.media_holder.width, (available - chrome) / inverse + dp(16)))
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
            self.pose_note.text = (
                "Live pose unavailable or stale · Preview remains local; Live freezes the last reported machine pose."
            )

    def _toggle_scene_group(self, group):
        viewer = self.machine.gcode_viewer
        viewer.set_machine_group_visible(group, not viewer.machine_group_visibility[group])
        button, title = self.scene_buttons[group]
        button.text = f"{title}: {'shown' if viewer.machine_group_visibility[group] else 'hidden'}"

    def _workholding_setup(self):
        from carveracontroller.desktop_planning import planning_popup

        viewer = self.machine.gcode_viewer
        body = BoxLayout(orientation="vertical", padding=dp(14), spacing=dp(10))
        note = label(
            "Draft CAD placement. Offsets are relative to the plate-centered model.\nJaw shift follows CAD Y before rotation; it is not a measured clamping gap.",
            12,
            AMBER,
            60,
        )
        body.add_widget(note)
        grid = AdaptiveGrid(max_cols=2, min_width=170, row_height=80, spacing=dp(8))
        values = (*viewer.workholding_offset_mm, viewer.workholding_rotation_deg, viewer.jaw_offset_mm)
        entries = []
        for title, value in zip(
            ("X offset · mm", "Y offset · mm", "Z offset · mm", "Rotation · degrees", "Movable jaw shift · mm"), values
        ):
            cell = BoxLayout(orientation="vertical")
            cell.add_widget(label(title, 11, MUTED, 24))
            field = QuantityField(
                text=f"{value:g}", kind="angle" if "Rotation" in title else "length", minimum=-1000, maximum=1000
            )
            entries.append(field)
            cell.add_widget(field)
            grid.add_widget(cell)
        body.add_widget(grid)
        popup = planning_popup("Mod Vise placement", body)
        actions = BoxLayout(size_hint_y=None, height=dp(36), spacing=dp(8))

        def apply():
            try:
                placement = [field.value() for field in entries]
                viewer.configure_workholding(placement[:3], placement[3], placement[4])
                if self.selected_machine_profile:
                    profile = dict(self.selected_machine_profile)
                    profile.update(
                        dict(zip(("vise_x", "vise_y", "vise_z", "vise_rotation", "vise_jaw_offset"), placement))
                    )
                    self.selected_machine_profile = self.profile_store.save_machine(profile)
                if hasattr(self, "save_scene_setup"):
                    self.save_scene_setup()
                self.object_inspector.refresh_trigger()
                popup.dismiss()
            except (ValueError, OSError) as exc:
                note.text = str(exc)

        actions.add_widget(Action("Save draft placement", apply, primary=True))
        actions.add_widget(Action("Cancel", popup.dismiss))
        body.add_widget(actions)
        popup.open()

    def _machine_setup(self):
        from carveracontroller.desktop_planning import planning_popup

        layout = BoxLayout(orientation="vertical", padding=dp(18), spacing=dp(12))
        layout.add_widget(
            label(
                "Draft preview • enter mm, fractions such as 1/4 in, or arithmetic.\nEach field shows its interpretation; saved coordinates use millimeters.",
                13,
                MUTED,
                60,
            )
        )
        fields = AdaptiveGrid(max_cols=3, min_width=170, row_height=82, spacing=dp(12))
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
                entry = QuantityField(text=f"{value:g}", minimum=0 if group == "size" else -1000, maximum=1000)
                cell.add_widget(entry)
                entries[group, index] = entry
                fields.add_widget(cell)
        layout.add_widget(fields)
        note = label(
            "Stock values and fixture mounting are drafts; confirm your actual setup.\nThe preview does not qualify collisions or stock removal.",
            12,
            AMBER,
            56,
        )
        layout.add_widget(note)
        actions = BoxLayout(spacing=dp(12), size_hint_y=None, height=dp(40))
        popup = planning_popup("Machine simulation setup", layout)

        def apply():
            import math

            try:
                values = {
                    group: tuple(entries[group, i].value() for i in range(3)) for group in ("size", "origin", "offset")
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
                self.component_choices["stock"].text = "Current stock"
                if hasattr(self, "save_scene_setup"):
                    self.save_scene_setup()
                note.text = "Simulation geometry updated."
                self.object_inspector.refresh_trigger()
                popup.dismiss()

        actions.add_widget(Action("Apply to preview", apply, primary=True))
        actions.add_widget(Action("Cancel", popup.dismiss))
        layout.add_widget(actions)
        popup.open()

    def _choose_program(self):
        from carveracontroller.desktop_program_picker import ProgramBrowser

        self.select("Job")
        self.program_browser = ProgramBrowser(self)
        self.program_browser.open()

    def _review_start(self):
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
        age = frame.age() if frame else None
        if frame:
            aspect = frame.size[0] / frame.size[1]
            if aspect != getattr(self, "camera_aspect", None):
                self.camera_aspect = aspect
                self._layout_media()
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
        if self.workspaces.current == "Job":
            self.camera_texture.update(frame)
            if hasattr(self, "camera_registration_panel"):
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
        self.progress = label("", 11, MUTED, 24, halign="right")
        footer.add_widget(self.progress)
        footer.add_widget(
            Action("Find action · ⌘K", self._open_command_palette, height=dp(24), size_hint_x=None, width=dp(130))
        )
        self.add_widget(footer)

    def _install_command_center(self, body):
        """A single media stage and a dedicated, sectioned Workbench."""
        self.inspector = Surface(orientation="vertical", padding=dp(10), spacing=dp(8), size_hint_x=0.5)
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
        tabs = AdaptiveGrid(max_cols=9, min_width=62, row_height=34, spacing=dp(6))
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
            button = Action(title, lambda key=key: self.select("Job" if key == "Preview" else key), height=dp(34))
            self.tab_buttons[key] = button
            tabs.add_widget(button)
        tabs.add_widget(Action("Profiles", self._open_profiles, height=dp(34)))
        self.inspector.add_widget(tabs)
        trail = BoxLayout(spacing=dp(6), size_hint_y=None, height=dp(26))
        self.workspace_back = Action(
            "Back", lambda: self.navigation.navigate(-1), size_hint_x=None, width=dp(64), disabled=True
        )
        self.workspace_forward = Action(
            "Forward", lambda: self.navigation.navigate(1), size_hint_x=None, width=dp(76), disabled=True
        )
        trail.add_widget(self.workspace_back)
        trail.add_widget(self.workspace_forward)
        self.navigation_label = label("Selection history", 11, MUTED, 26, shorten=True, max_lines=1)
        trail.add_widget(self.navigation_label)
        self.inspector.add_widget(trail)
        self.inspector.add_widget(self._build_machine_controls())
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
        self.rail_note = label("SPINDLE MONITOR • Shadow only", 10, MUTED, 28)
        self.inspector.add_widget(self.rail_note)
        body.add_widget(self.inspector)
        self.active_section = "Job"
        self.workspaces.current = "Job"

    def _select_capability(self, _choice, title):
        key = next(key for key, value in self.section_names.items() if value == title)
        self.select("Job" if key == "Preview" else key)

    def _toggle_inspector(self):
        if self.inspector.parent:
            self.body.remove_widget(self.inspector)
            if self.machine.keyboard_jog_control:
                self.machine.toggle_keyboard_jog_control(disable=True)
        else:
            self.body.add_widget(self.inspector)

    def _open_profiles(self):
        from kivy.uix.popup import Popup

        from carveracontroller.desktop_profiles import ProfileLibrary

        if not hasattr(self, "profile_library"):
            self.profile_library = ProfileLibrary(self, store=self.profile_store)
            self.profile_popup = Popup(
                title="Machine & tool library", content=self.profile_library, size_hint=(0.92, 0.92)
            )
        self.profile_library.refresh()
        self.profile_popup.open()

    def close_profile_library(self):
        self.profile_popup.dismiss()

    def apply_machine_profile(self, profile):
        """Select local connection/preview metadata without changing the CNC."""
        from carveracontroller.addons.machine_simulation.profile import MachineProfile
        from carveracontroller.machine.desktop_profiles import validate_record

        profile = validate_record("machines", profile)
        cad = MachineProfile.load(Path(profile["cad_path"]).expanduser()) if profile["cad_path"] else None
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

    def _connect_profile(self):
        profile = self.selected_machine_profile
        if not profile or not profile["host"] or self.connected:
            return
        self.machine.openWIFI(f"{profile['host']}:{profile['port']}")

    def apply_tool_profile(self, profile, slot=None):
        from carveracontroller.machine.desktop_profiles import to_tool_definition

        definition = to_tool_definition(profile, number=slot, units="mm")
        self.machine.gcode_viewer.load_tool_profiles({definition.number: definition}, replace=False)
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

    def apply_toolset_profile(self, toolset, definitions):
        if not isinstance(definitions, dict):
            definitions = {tool.number: tool for tool in definitions}
        self.machine.gcode_viewer.load_tool_profiles(definitions)
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
                self.apply_machine_profile(machine)
            selected = Config.get("carvera", "desktop_toolset_id", fallback="")
            toolset = next((p for p in store.data["toolsets"] if p["id"] == selected), None)
            if toolset:
                self.apply_toolset_profile(toolset, store.toolset_definitions(toolset))
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
        if record_navigation:
            self.navigation.depart()
        self.active_section = page
        if page == "Scene" and hasattr(self, "object_inspector"):
            self.machine.gcode_viewer.set_inspected_component(self.object_inspector.selected)
            self.object_inspector.refresh_trigger()
        self.workspaces.current = "Job"
        self.app.show_gcode_ctl_bar = False
        key = "Preview" if page == "Job" else page
        if key in self.section_names:
            if not self.inspector.parent:
                self.body.add_widget(self.inspector)
            self.inspector_pages.current = key
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

    def refresh(self, _dt):
        self.readiness.refresh()
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
            self.model_caption.text = "Machine & toolpath" + (
                " · draft setup" if info.get("fixture_registration") or info.get("workholding") else ""
            )
            self.machine_view_button.text = "Machine on" if info["visible"] else "Machine off"
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
            f"{self.machine.coord_system_data_view.main_text} • XYZ {data['wx']:.2f}, {data['wy']:.2f}, {data['wz']:.2f} mm\n"
            f"Physical T{self.app.tool} • TLO {data['tlo']:.3f} mm\n{data['curspindle']:,.0f} RPM • {data['curfeed']:,.0f} mm/min"
            if connected
            else "Local preview • connect to receive live position and physical tool state"
        )
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
        if self.inspector_pages.current == "Monitor":
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
