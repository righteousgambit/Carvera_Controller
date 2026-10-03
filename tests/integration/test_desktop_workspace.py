"""Desktop navigation and machine action invariants, with no real hardware."""

from unittest.mock import Mock

from carveracontroller.CNC import CNC
from tests.integration.conftest import apply_machine_state, pump_frames


def button(workspace, text):
    return next(w for w, _guard in workspace.guards if w.text == text)


def test_navigation_does_not_send_machine_commands(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    for key, _title in workspace.pages:
        workspace.select(key)
        pump_frames(2)
        assert workspace.workspaces.current == "Job"
        assert workspace.active_section == key
    send.assert_not_called()


def test_detached_legacy_legend_survives_garbage_collection(kivy_app):
    import gc

    root = kivy_app.root
    gc.collect()
    assert root.desktop_workspace._legacy_viewer_overlay.parent is None
    root.refresh_gcode_color_legend()
    root.refresh_gcode_visibility_legend()


def test_disconnected_controls_are_gated(kivy_app, disconnected_state):
    apply_machine_state(kivy_app)
    workspace = kivy_app.root.desktop_workspace
    workspace.refresh(0)
    assert all(b.disabled for b in workspace.jog_buttons)
    assert button(workspace, "STOP").disabled
    assert button(workspace, "Review & start").disabled
    assert workspace.rpm_metric.value.text == "—"
    assert workspace.position_values["X"].text == "—"


def test_jog_labels_match_commands_and_live_gate(kivy_app, connected_idle_state, monkeypatch):
    root = kivy_app.root
    apply_machine_state(kivy_app)
    workspace = root.desktop_workspace
    jog = Mock()
    monkeypatch.setattr(root.controller, "jog", jog)
    workspace.xy_step.text = "0.1"
    workspace._jog("X", -1)
    jog.assert_called_once_with("X-0.1")
    jog.reset_mock()
    # A state change after drawing the button must still block a press.
    kivy_app.state = "Alarm"
    workspace._jog("X", 1)
    jog.assert_not_called()


def test_console_navigation_disables_keyboard_jog(kivy_app, connected_idle_state):
    apply_machine_state(kivy_app)
    root = kivy_app.root
    root.desktop_workspace.select("Overview")
    root.toggle_keyboard_jog_control()
    assert root.keyboard_jog_control
    root.desktop_workspace.select("Console")
    assert not root.keyboard_jog_control
    assert root.cmd_manager.current == "manual_cmd_page"
    root._global_keyboard_keydown(None, 109, 0, "m", ["ctrl"])
    assert root.desktop_workspace.workspaces.current == "Job"
    assert root.desktop_workspace.active_section == "Console"
    assert root.manual_cmd.focus
    root.manual_cmd.focus = False


def test_review_start_opens_existing_setup_without_starting(kivy_app, connected_idle_state, monkeypatch):
    apply_machine_state(kivy_app)
    root = kivy_app.root
    open_review, load_review, send = Mock(), Mock(), Mock()
    monkeypatch.setattr(root.coord_popup, "open", open_review)
    monkeypatch.setattr(root.coord_popup, "load_config", load_review)
    monkeypatch.setattr(root.controller, "executeCommand", send)
    kivy_app.selected_remote_filename = "/test.ngc"
    root.desktop_workspace.refresh(0)
    assert not button(root.desktop_workspace, "Review & start").disabled
    button(root.desktop_workspace, "Review & start").dispatch("on_release")
    assert root.coord_popup.mode == "Run"
    load_review.assert_called_once()
    open_review.assert_called_once()
    send.assert_not_called()
    kivy_app.selected_remote_filename = ""


def test_selecting_program_opens_job_view(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    workspace.select("Settings")
    kivy_app.selected_local_filename = "/tmp/example.ngc"
    assert workspace.workspaces.current == "Job"
    workspace.refresh(0)
    assert workspace.program_label.text == "example.ngc"
    assert workspace.empty_preview.height == 0
    kivy_app.selected_local_filename = ""


def test_stale_telemetry_never_displays_a_live_proposal(kivy_app, connected_idle_state):
    from carveracontroller.machine.adaptive_monitor import Sample

    apply_machine_state(kivy_app)
    root = kivy_app.root
    monitor = root.controller.adaptive_monitor
    monitor.reset()
    monitor.observe(Sample(0, "Run", 11850, 12000, 0.5, 600, 100, (-232, -195, -3)))
    root.desktop_workspace.refresh(0)
    assert root.desktop_workspace.monitor_feed.value.text == "—"
    assert "stale" in root.desktop_workspace.footer_status.text.lower()
    monitor.reset()


def test_work_and_machine_positions_remain_distinct(kivy_app, connected_idle_state):
    CNC.vars["wx"], CNC.vars["mx"] = 12.345, -232.0
    apply_machine_state(kivy_app)
    workspace = kivy_app.root.desktop_workspace
    workspace.refresh(0)
    assert workspace.position_values["X"].text == "12.345"
    assert workspace.machine_values["X"].text == "Machine -232.000"


def test_navigation_and_focus_loss_stop_keyboard_jog(kivy_app, connected_idle_state, monkeypatch):
    apply_machine_state(kivy_app)
    root = kivy_app.root
    stop = Mock()
    monkeypatch.setattr(root.controller, "stopContinuousJog", stop)
    root.desktop_workspace.select("Overview")
    if not root.keyboard_jog_control:
        root.toggle_keyboard_jog_control()
    root._held_jog_keys.add(273)
    root.desktop_workspace.select("Console")
    stop.assert_called_once()
    assert not root._held_jog_keys
    stop.reset_mock()
    root.desktop_workspace.select("Overview")
    root.toggle_keyboard_jog_control()
    root.desktop_workspace._window_focus(None, False)
    stop.assert_called_once()
    assert not root.keyboard_jog_control


def test_hold_label_describes_resume_action(kivy_app, connected_idle_state):
    apply_machine_state(kivy_app)
    kivy_app.state = "Hold"
    kivy_app.root.desktop_workspace.refresh(0)
    assert kivy_app.root.desktop_workspace.hold_button.text == "Resume motion"


def test_camera_and_toolpath_panes_toggle_without_machine_commands(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace.select("Job")
    assert workspace.job_camera_splitter.parent is workspace.preview_row
    workspace._toggle_job_camera()
    assert workspace.job_camera_splitter.parent is None
    workspace._toggle_job_camera()
    assert workspace.job_camera_splitter.parent is workspace.preview_row
    send.assert_not_called()


def test_camera_source_change_clears_previous_texture(kivy_app):
    import time

    from carveracontroller.machine.webcam import CameraFrame

    workspace = kivy_app.root.desktop_workspace
    workspace.select("Camera")
    workspace.camera_client.frame = CameraFrame((1, 1), b"abc", time.time(), time.monotonic(), 999)
    workspace._refresh_camera()
    assert workspace.camera_texture.texture is not None
    workspace.camera_client.configure("http://localhost/new.jpg")
    workspace._refresh_camera()
    assert workspace.camera_texture.texture is None


def test_action_surface_is_transparent_in_all_states(kivy_app):
    from carveracontroller.desktop_workspace import Action

    action = Action("Stop", danger=True)
    for state in ("normal", "down", "normal"):
        action.state = state
        pump_frames(2)
        assert action.background_color == [0, 0, 0, 0]
    assert action._fill.rgba[0] > action._fill.rgba[1]


def test_job_renderer_has_own_slot_and_camera_can_scale_up(kivy_app):
    from kivy.graphics.texture import Texture

    root = kivy_app.root
    workspace = root.desktop_workspace
    workspace.select("Job")
    pump_frames(3)
    assert root.gcode_viewer.parent is workspace.model_card
    root.gcode_viewer.set_display_offset(300, 100)
    assert (root.gcode_viewer.off_x, root.gcode_viewer.off_y) == (0, 0)
    origin = root.gcode_viewer.to_window(*root.gcode_viewer.pos)
    assert root.gcode_viewer._view_cube_gl_origin() == origin
    assert origin != tuple(root.gcode_viewer.pos)  # parent Screen contributes its origin
    assert root.ids["gcode_play_slider"].parent is not workspace.model_card
    assert root.float_layout.parent is None
    view = workspace.camera_texture.new_view()
    view.size = (800, 450)
    view.texture = Texture.create(size=(320, 180))
    assert view.fit_mode == "contain"
    assert view.norm_image_size == [800, 450]


def test_command_center_keeps_stage_visible_and_stacks_camera(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    pump_frames(4)
    assert workspace.preview_row.orientation == "vertical"
    assert workspace.model_card.y > workspace.job_camera_splitter.y
    for key in workspace.section_names:
        workspace.select("Job" if key == "Preview" else key)
        pump_frames(3)
        assert workspace.workspaces.current == "Job"
        assert workspace.inspector_pages.current == key
        assert workspace.section_choice.text == workspace.section_names[key]
        assert workspace.model_card.parent is workspace.preview_row
    assert abs(kivy_app.root.gcode_viewer.width / kivy_app.root.gcode_viewer.height - 1.6) < 0.02
    assert kivy_app.root.gcode_viewer.height / workspace.model_card.height >= 0.85
    camera_card = workspace.job_camera_splitter.children[0]
    camera_view = camera_card.children[0]
    assert camera_view.height / camera_card.height >= 0.85
    assert abs(workspace.inspector.width / workspace.body.width - 0.5) < 0.02
    assert abs(camera_view.width / camera_view.height - getattr(workspace, "camera_aspect", 16 / 9)) < 0.02


def test_toolset_load_keeps_cam_metadata_and_never_sends_commands(kivy_app, tmp_path, monkeypatch):
    from carveracontroller.machine.desktop_profiles import ProfileStore

    root = kivy_app.root
    workspace = root.desktop_workspace
    store = ProfileStore(tmp_path / "profiles.json")
    toolset = store.save_toolset({"name": "First cycle", "slots": {"1": store.data["tools"][0]["id"]}})
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    before = dict(root.gcode_viewer.tool_table)
    workspace.apply_toolset_profile(toolset, store.toolset_definitions(toolset))
    assert workspace.loaded_toolset["name"] == "First cycle"
    assert root.gcode_viewer.library_tool_table_mm[1].diameter == 6.35
    assert root.gcode_viewer.tool_table == before
    assert "1/6" in workspace.profile_status.text
    send.assert_not_called()
    root.gcode_viewer.load_tool_profiles({})


def test_profile_editor_can_reopen_without_parent_conflicts(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    workspace._open_profiles()
    pump_frames(3)
    workspace.profile_popup.dismiss()
    pump_frames(3)
    workspace._open_profiles()
    pump_frames(3)
    assert workspace.profile_popup.content is workspace.profile_library
    workspace.profile_popup.dismiss()


def test_machine_profile_selection_does_not_reconnect(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    connect, send = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root, "openWIFI", connect)
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace.apply_machine_profile({"id": "test-preview", "name": "Bench Carvera", "host": "192.0.2.1", "port": 2222})
    assert workspace.selected_machine_profile["name"] == "Bench Carvera"
    assert "192.0.2.1" in workspace.selected_machine_label.text
    connect.assert_not_called()
    send.assert_not_called()


def test_workbench_can_hide_without_replacing_stage(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace._toggle_inspector()
    assert workspace.inspector.parent is None
    assert workspace.preview_row.parent is not None
    workspace.select("Setup")
    assert workspace.inspector.parent is workspace.body
    send.assert_not_called()


def test_profile_forms_reflow_without_losing_edits_or_covering_actions(kivy_app, tmp_path, monkeypatch):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from carveracontroller.desktop_profiles import ProfileLibrary
    from carveracontroller.machine.desktop_profiles import ProfileStore

    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    library = ProfileLibrary(workspace, ProfileStore(tmp_path / "profiles.json"), size_hint=(None, None))
    Window.add_widget(library)
    try:
        for kind in ("machines", "tools", "toolsets"):
            library.select_kind(kind)
            library.fields["name"].text = "Unsaved draft"
            for width in (1200, 700, 480):
                library.size = (dp(width), dp(780))
                pump_frames(12)
                assert library.body.orientation == ("horizontal" if width >= 760 else "vertical")
                assert library.fields["name"].text == "Unsaved draft"
                assert library.editor_scroll.y >= library.actions.top - dp(1)
                assert library.editor_scroll.height > dp(100)
                assert library.save_button.width >= dp(130)
                for control in library.fields.values():
                    left = control.to_window(control.x, control.y)[0]
                    right = control.to_window(control.right, control.y)[0]
                    assert left >= library.editor_card.x
                    assert right <= library.editor_card.right
                assert library.form.width <= library.editor_scroll.width
                assert library.list_scroll.height >= dp(54)
                if width == 1200:
                    assert library.list_card.width <= dp(280)
                if width == 480:
                    for section in library.form.children:
                        if section.children and hasattr(section.children[0], "cols"):
                            assert section.children[0].cols == 1
        send.assert_not_called()
    finally:
        Window.remove_widget(library)


def test_camera_probe_ignores_removed_legacy_desktop_widget(kivy_app):
    root = kivy_app.root

    class RemovedSplitter:
        def __getattr__(self, name):
            raise ReferenceError("legacy camera widget removed")

    previous = root.ids.get("camera_splitter")
    root.ids["camera_splitter"] = RemovedSplitter()
    try:
        root._on_camera_detected(root.camera_probe, False)
        assert not kivy_app.supports_camera
    finally:
        if previous is None:
            root.ids.pop("camera_splitter", None)
        else:
            root.ids["camera_splitter"] = previous


def test_scene_controls_are_independent_and_do_not_send(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace.select("Scene")
    workspace.scene_scope.text = "Full machine"
    assert viewer.machine_view_scope == "machine"
    workspace.component_checks["outer"].active = False
    assert not viewer.machine_group_visibility["fixed"]
    assert not viewer.machine_group_visibility["carriage"]
    assert viewer.machine_group_visibility["spindle"]
    for group in ("spindle", "fixture", "workholding", "stock", "table", "atc"):
        workspace.component_checks[group].active = False
        assert not viewer.machine_group_visibility[group]
        workspace.component_checks[group].active = True
        assert viewer.machine_group_visibility[group]
    workspace.component_checks["cutter"].active = False
    assert not viewer.cutter_visible
    assert viewer.pointermesh not in viewer.canvas.children
    workspace.component_checks["cutter"].active = True
    workspace.component_checks["outer"].active = True
    send.assert_not_called()


def test_atc_rack_tracks_table_translation_not_spindle(kivy_app):
    viewer = kivy_app.root.gcode_viewer
    viewer.set_machine_visible(True)
    for point in ((0, 0, 0), (47, -23, 11)):
        viewer._update_machine_uniforms(point)
        assert viewer._machine_contexts["atc"]["offset"] == viewer._machine_contexts["table"]["offset"]


def test_manual_cutter_can_render_without_program_and_follow_program(kivy_app):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition

    viewer = kivy_app.root.gcode_viewer
    viewer.clearDisplay()
    viewer.load_tool_profiles(
        {19: ToolDefinition(19, diameter=6.35, shank_diameter=6.35, flute_length=25.4, length=76.2)}
    )
    viewer.select_preview_tool(19)
    pump_frames(4)
    assert viewer._tool_number_at_index(0) == 19
    assert len(viewer.pointer_mesh_instrs) == 2
    assert viewer.pointer_mesh_instrs[0].indices
    viewer.set_cutter_visible(False)
    viewer.select_preview_tool(19)
    assert viewer.pointermesh not in viewer.canvas.children
    viewer.select_preview_tool(None)
    assert viewer._tool_number_at_index(0) is None
    assert not viewer.pointer_mesh_instrs
    viewer.set_cutter_visible(True)


def test_component_selection_preserves_machine_and_other_fixture(kivy_app):
    import pytest

    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from tests.unit.test_machine_profile import profile_data

    viewer = kivy_app.root.gcode_viewer
    data = profile_data()
    triangle = data["components"][0]["vertices"]
    data["components"].append({"group": "fixture", "vertices": list(triangle)})
    plate = MachineProfile(data)
    data = profile_data()
    data["components"].append({"group": "workholding", "vertices": list(triangle)})
    vise = MachineProfile(data)
    original = viewer.machine_profile
    viewer.select_machine_component("fixture", plate)
    viewer.select_machine_component("workholding", vise)
    assert viewer.machine_profile is original
    assert viewer.machine_component_profiles["fixture"] is plate
    assert viewer.machine_component_profiles["workholding"] is vise
    scene = viewer._machine_scene()
    assert scene["fixture"].indices == plate.groups["fixture"].indices
    with pytest.raises(ValueError):
        viewer.select_machine_component("fixture", vise)
    assert viewer.machine_component_profiles["fixture"] is plate
    viewer.machine_component_profiles.clear()
    viewer._build_machine_scene()
