"""Desktop navigation and machine action invariants, with no real hardware."""

from unittest.mock import Mock

import pytest

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


def test_setup_strip_is_contextual_without_rebuilding_views_or_losing_machine_controls(kivy_app, monkeypatch):
    root = kivy_app.root
    ws = root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    ws.select("Job")
    pump_frames(3)
    pages, strip = ws.inspector_pages, ws.readiness.strip
    job_height = pages.height
    controls = tuple(ws.guards)
    camera = ws.camera_texture
    ws.readiness.next_button.focus = True
    for page in ("Camera", "Settings", "Monitor", "Console", "Overview"):
        ws.select(page)
        pump_frames(3)
        assert strip.parent is None
        assert not ws.readiness.next_button.focus
        assert ws.inspector_pages is pages
        assert pages.height >= job_height + strip.height
        assert ws.camera_texture is camera
        assert tuple(ws.guards) == controls
        assert ws.pose_status.parent is not None
        assert ws.return_live_action.parent is ws.pose_status.parent
    for page in ("Scene", "Setup", "Readiness", "Job"):
        ws.select(page)
        pump_frames(3)
        assert strip.parent is ws.inspector
        assert ws.inspector.children.count(strip) == 1
        assert ws.inspector.children.index(strip) == ws.inspector.children.index(pages) + 1
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
    assert view._image_rect()[2:4] == (800, 450)


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
    usable = workspace.inspector.width + workspace.media_column.width
    assert abs(workspace.inspector.width / usable - 0.5) < 0.02
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
    workspace.close_profile_library()
    pump_frames(3)
    workspace._open_profiles()
    pump_frames(3)
    assert workspace.profile_library.parent is workspace.inspector_pages.get_screen("Profiles")
    workspace.close_profile_library()


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
                # Inactive tasks intentionally leave their fields unmounted.
                # Exercise each task and compare only its rendered controls in
                # the same window coordinate space as the editor card.
                for task in library.editor_tasks.names:
                    library.editor_tasks.show(task)
                    pump_frames(8)
                    mounted = set(library.form.walk(restrict=True))
                    card_left = library.editor_card.to_window(library.editor_card.x, library.editor_card.y)[0]
                    card_right = card_left + library.editor_card.width
                    for control in library.fields.values():
                        if control not in mounted:
                            continue
                        left = control.to_window(control.x, control.y)[0]
                        right = control.to_window(control.right, control.y)[0]
                        assert left >= card_left
                        assert right <= card_right
                    assert library.form.width <= library.editor_scroll.width
                    if width == 480:
                        for section in library.form.children:
                            if section.children and hasattr(section.children[0], "cols"):
                                assert section.children[0].cols == 1
                assert library.fields["name"].text == "Unsaved draft"
                assert library.list_scroll.height >= dp(54)
                if width == 1200:
                    assert library.list_card.width <= dp(280)
        send.assert_not_called()
    finally:
        library.dispose()
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


def test_scene_inspection_navigation_preserves_setup_and_visibility(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    inspector = workspace.object_inspector
    setup = viewer.machine_setup
    choices = {key: choice.text for key, choice in workspace.component_choices.items()}
    visibility = dict(viewer.machine_group_visibility)
    inspector.select("stock")
    inspector.select("workholding")
    assert "Vise holds (declared) Stock" in inspector.relationship_details.text
    assert "physical" in inspector.status.text
    inspector.navigate(-1)
    assert inspector.selected == viewer.inspected_component == "stock"
    inspector.navigate(1)
    assert inspector.selected == viewer.inspected_component == "workholding"
    assert workspace.active_section == "Scene"
    assert viewer.machine_setup is setup
    assert viewer.machine_group_visibility == visibility
    assert {key: choice.text for key, choice in workspace.component_choices.items()} == choices
    send.assert_not_called()


def test_scene_tab_entry_highlights_existing_inspector_selection(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    workspace.object_inspector.select("fixture", reveal=False)
    viewer.set_inspected_component(None)
    history = list(workspace.object_inspector.history.items)
    workspace.select("Scene")
    assert viewer.inspected_component == "fixture"
    assert workspace.object_inspector.history.items == history


def test_scene_inspector_converts_cam_units_and_handles_missing_dimensions(kivy_app, monkeypatch):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition

    viewer = kivy_app.root.gcode_viewer
    # Dimensions describe the displayed mesh, not a pending preview request.
    monkeypatch.setattr(viewer, "_active_tool_number", 77)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {})
    inspector = kivy_app.root.desktop_workspace.object_inspector
    original = viewer.tool_table, viewer.tool_unit_scale, viewer.preview_tool_override
    try:
        viewer.tool_table = {77: ToolDefinition(77, diameter=0.25, length=3, flute_length=1)}
        viewer.tool_unit_scale = 25.4
        viewer.preview_tool_override = 77
        inspector.select("cutter", reveal=False)
        assert "Diameter 6.35 mm · cutting length 25.4 mm" in inspector.facts.text
        assert "Overall length 76.2 mm · shank unknown" in inspector.facts.text
        viewer.tool_table[77] = ToolDefinition(77)
        inspector.refresh()
        assert "Diameter unknown · cutting length unknown" in inspector.facts.text
        assert "physical seating not established" in inspector.facts.text
    finally:
        viewer.tool_table, viewer.tool_unit_scale, viewer.preview_tool_override = original


def test_scene_inspector_never_reports_cached_bounds_when_machine_hidden(kivy_app):
    viewer = kivy_app.root.gcode_viewer
    original = viewer.machine_visible
    try:
        viewer.set_machine_visible(True)
        viewer.set_inspected_component("table")
        assert viewer.inspected_component_bounds("table") is not None
        viewer.set_machine_visible(False)
        assert viewer.inspected_component_bounds("table") is None
    finally:
        viewer.set_machine_visible(original)


def test_scene_highlight_does_not_mutate_source_geometry(kivy_app):
    viewer = kivy_app.root.gcode_viewer
    source = viewer._machine_scene()["table"]
    before = tuple(source.vertices)
    viewer.set_machine_visible(True)
    meshes = [widget for widget in viewer._machine_contexts["table"].children if hasattr(widget, "vertices")]
    before_buffers = [list(mesh.vertices) for mesh in meshes]
    viewer.set_inspected_component("table")
    assert tuple(source.vertices) == before
    assert meshes
    assert [list(mesh.vertices) for mesh in meshes] == before_buffers
    assert viewer._machine_contexts["table"]["inspection_highlight"] == 1.0
    assert viewer._machine_contexts["fixed"]["inspection_highlight"] == 0.0
    assert viewer._machine_contexts["table"].shader.success
    viewer.set_inspected_component(None)
    assert viewer._machine_contexts["table"]["inspection_highlight"] == 0.0


def test_scene_profiles_panel_preserves_selection_and_returns_to_tab(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace.object_inspector.select("fixture")
    workspace._open_profiles()
    assert workspace.active_section == "Profiles"
    assert workspace.object_inspector.selected == "fixture"
    workspace.close_profile_library()
    assert workspace.active_section == "Scene"
    send.assert_not_called()


def test_scene_inspector_relationships_and_controls_fit_narrow_workbench(kivy_app):
    from carveracontroller.desktop_object_inspector import SceneObjectInspector

    inspector = SceneObjectInspector(kivy_app.root.desktop_workspace, size_hint_x=None, width=360)
    inspector.selected = "stock"
    inspector.refresh()
    pump_frames(4)
    assert inspector.facts.text_size[0] <= 360
    assert inspector.relationship_details.text_size[0] <= 360
    for control in (inspector.choice, inspector.back, inspector.forward, *inspector.relations.children):
        assert control.x >= inspector.x
        assert control.right <= inspector.right


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


def test_command_palette_search_and_navigation_do_not_send(kivy_app, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace._open_command_palette()
    pump_frames(2)
    palette = workspace.command_palette
    palette.input.text = "workbench console"
    pump_frames(2)
    assert palette.matches
    assert palette.execute(palette.matches[0])
    assert workspace.active_section == "Console"
    send.assert_not_called()
    palette.popup.dismiss()


def test_operation_panel_displays_and_selects_without_machine_commands(kivy_app, monkeypatch):
    from carveracontroller.machine.program_operations import ProgramOperations

    workspace = kivy_app.root.desktop_workspace
    send = Mock()
    seek = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(kivy_app.root.gcode_viewer, "set_distance_by_lineidx", seek)
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\n(Operation: Face)\nG1 X0 Y0 Z0 F100\nG1 X10\n")
    panel = workspace.operation_panel
    panel.generation += 1
    panel._loaded(panel.generation, program, None)
    panel.select(program.operations[-1])
    pump_frames(2)
    seek.assert_called_once_with(program.operations[-1].start_line, 0)
    send.assert_not_called()


def test_live_and_compare_pose_are_packet_bound_and_navigation_only(kivy_app, monkeypatch):
    import time

    from carveracontroller.machine.observed_pose import ObservedPose

    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    pose = ObservedPose(time.monotonic(), "Idle", (-190, -125, -100), (1, 2, 3), 1, 40)
    viewer.set_observed_pose(pose)
    viewer.set_pose_mode("Live")
    assert viewer._machine_pose["tool_machine_mm"][0] == -190
    viewer.set_pose_mode("Compare")
    assert viewer.observed_pose is pose
    assert viewer._machine_contexts["live_pose"].children
    viewer.set_observed_pose(None)
    assert not viewer._machine_contexts["live_pose"].children
    viewer.set_pose_mode("Preview")
    send.assert_not_called()


@pytest.mark.parametrize("destination", ["Simulation", "Operations", "Scene"])
def test_workbench_stock_removal_changes_display_without_machine_commands(kivy_app, monkeypatch, tmp_path, destination):
    import json
    import time

    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
    from carveracontroller.machine.program_operations import ProgramOperations

    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace.operation_panel.program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z0 F100\nG1 X10\n"
    )
    viewer.configure_machine((-180, -120, -110), (10, 2, 2), (0, -1, 0))
    viewer.load_tool_profiles(
        {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, flute_length=3, stickout=4)}
    )
    panel = workspace.simulation_panel
    panel.stock_source.text = "Initial stock"
    panel.resolution.text = "1"
    monkeypatch.setattr(panel, "clearance_stale", True)
    workspace.select("Job")
    workspace.program_tasks.show("Simulation")
    if not panel.details_open:
        panel.toggle_details()
    pump_frames(5)
    panel.start(False)
    if destination == "Scene":
        workspace.select("Scene")
    elif destination == "Operations":
        workspace.program_tasks.choose("Operations")
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2)
    assert not panel.running
    pump_frames(5)
    if destination == "Scene":
        assert workspace.active_section == "Scene"
    else:
        assert workspace.active_section == "Job"
        assert workspace.program_tasks.active == destination
    assert panel.report is not None, panel.note.text
    assert not panel.clearance_stale and not panel.clearance_action.disabled
    assert panel.clearance_context == panel.rest_context
    assert panel.report.removed_volume_mm3 > 0
    assert viewer._rest_stock_geometry is not None
    assert "unresolved" in panel.note.text
    initial = panel.clearance_inputs[3]
    assert initial is not panel.rest_stock
    assert initial.remaining_volume_mm3 > panel.rest_stock.remaining_volume_mm3
    before = initial.snapshot()
    summary = panel.note.text
    target = tmp_path / "residual.cvstock"
    monkeypatch.setattr(workspace, "choose_profile_file", lambda callback, **_kwargs: callback(str(target)))
    panel.save_stock()
    deadline = time.monotonic() + 5
    while panel.artifact_transfer is not None and panel.artifact_transfer.active and time.monotonic() < deadline:
        pump_frames(2)
    assert panel.artifact_transfer is None or not panel.artifact_transfer.active
    saved = json.loads(target.read_text())
    from carveracontroller.addons.manufacturing_simulation import StockVolume

    restored = StockVolume.from_snapshot(saved["stock"])
    assert restored.snapshot() == panel.rest_stock.snapshot()
    assert saved["context"] == json.loads(json.dumps(panel.rest_context))
    assert panel.note.text == summary
    assert str(target) in panel.artifact_status.text
    panel.review_clearance()
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2)
    assert not panel.running
    assert panel.clearance_card.report.stock_resolution_mm == 1
    assert "numerical tolerance does not bound stock-model error" in panel.clearance_card.summary.text
    assert initial.snapshot() == before
    panel.reset_display()
    assert viewer._rest_stock_geometry is None
    send.assert_not_called()


def test_model_wheel_stays_in_model_pane(kivy_app):
    from kivy.core.window import Window
    from kivy.tests.common import UnitTestTouch

    root = kivy_app.root
    workspace = root.desktop_workspace
    workspace.select("Job")
    pump_frames(5)
    viewer = root.gcode_viewer
    scroll = workspace.program_tasks.scroll
    before_scroll, before_zoom = scroll.scroll_y, viewer.m_zoom
    x, y = viewer.to_window(*viewer.center)
    touch = UnitTestTouch(x, y)
    touch.scale_for_screen(Window.width, Window.height)
    touch.profile.append("button")
    touch.button = "scrollup"
    assert root.on_touch_down(touch)
    pump_frames(5)
    assert viewer.m_zoom < before_zoom
    assert scroll.scroll_y == before_scroll


def test_compact_workbench_header_preserves_controls_and_task_area(kivy_app, monkeypatch, tmp_path):
    from kivy.metrics import dp

    ws = kivy_app.root.desktop_workspace
    original = ws.inspector.size_hint_x, ws.inspector.width
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        ws.inspector.size_hint_x = None
        for width, compact, orientation in (
            (530, False, "horizontal"),
            (440, True, "vertical"),
            (360, True, "vertical"),
        ):
            ws.inspector.width = dp(width)
            pump_frames(10)
            visible_navigation = ws.workbench_compact_navigation if compact else ws.workbench_tabs
            assert visible_navigation.parent is ws.workbench_navigation
            assert ws.workbench_navigation.height == dp(32)
            assert ws.nav["Settings"] is (ws.section_choice if compact else ws.tab_buttons["Settings"])
            assert ws.machine_controls.orientation == orientation
            controls = [ws.connect_button, ws.hold_button, button(ws, "STOP")]
            for control in controls:
                assert control.width >= dp(64)
                assert control.x >= ws.inspector.x
                assert control.right <= ws.inspector.right
            for control in visible_navigation.children:
                assert control.width >= dp(48)
                assert control.x >= ws.inspector.x
                assert control.right <= ws.inspector.right
                assert control.texture_size[0] <= control.width
            assert ws.readiness.summary.text.endswith(f"{ws.readiness.measured_count}/4 measured")
            assert ws.readiness.summary.texture_size[0] <= ws.readiness.summary.width
            show_next = bool(ws.app.selected_local_filename or ws.app.selected_remote_filename)
            show_next = show_next or ws.active_section != "Job"
            assert (ws.readiness.next_button.parent is ws.readiness.strip) == show_next
            if show_next:
                assert ws.readiness.next_button.top <= ws.readiness.strip.top
                assert ws.readiness.next_button.y >= ws.readiness.strip.y
            previous_section = ws.active_section
            ws.select("Scene")
            pump_frames(5)
            assert ws.readiness.next_button.parent is ws.readiness.strip
            if width == 360:
                assert ws.readiness.summary.text == f"{ws.readiness.measured_count}/4 measured"
            assert ws.readiness.next_button.top <= ws.readiness.strip.top
            assert ws.readiness.next_button.y >= ws.readiness.strip.y
            ws.select(previous_section)
            pump_frames(5)
            assert (ws.readiness.next_button.parent is ws.readiness.strip) == show_next
            assert ws.inspector_pages.height > 0
            ws.inspector.export_to_png(str(tmp_path / f"workbench-{width}.png"))
        send.assert_not_called()
    finally:
        ws.inspector.size_hint_x, ws.inspector.width = original
        pump_frames(5)


@pytest.mark.parametrize("width,columns", [(360, 1), (650, 2), (1000, 3)])
def test_job_telemetry_fields_reflow_without_shortening_lines(
    kivy_app, connected_idle_state, monkeypatch, width, columns
):
    from kivy.metrics import dp

    root = kivy_app.root
    apply_machine_state(kivy_app)
    ws = root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    ws.refresh(0)
    panel = ws.stage_telemetry
    original = panel.size_hint_x, panel.width
    try:
        panel.size_hint_x = None
        panel.width = dp(width)
        pump_frames(4)
        assert panel.cols == columns
        for item in (ws.stage_context, ws.stage_tool_context, ws.stage_process_context):
            assert item.parent is panel and not item.shorten
            assert "\n" in item.text
            assert item.texture_size[1] <= item.height + 1
        assert "Work position" in ws.stage_context.text
        assert "Reported tool" in ws.stage_tool_context.text
        assert "Spindle" in ws.stage_process_context.text
        send.assert_not_called()
    finally:
        panel.size_hint_x, panel.width = original


def test_job_telemetry_does_not_show_last_values_when_disconnected(kivy_app, disconnected_state):
    apply_machine_state(kivy_app)
    ws = kivy_app.root.desktop_workspace
    ws.refresh(0)
    assert "Connect" in ws.stage_context.text
    assert ws.stage_tool_context.text == "Tool state unavailable"
    assert ws.stage_process_context.text == "Spindle and feed unavailable"


def test_compact_navigation_preserves_selection_and_closes_detached_menu(kivy_app, monkeypatch):
    from kivy.metrics import dp

    ws = kivy_app.root.desktop_workspace
    original = ws.inspector.size_hint_x, ws.inspector.width, ws.active_section
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        ws.inspector.size_hint_x = None
        ws.inspector.width = dp(360)
        pump_frames(10)
        for key, title in ws.section_names.items():
            ws.section_choice.text = title
            pump_frames(2)
            assert ws.active_section == ("Job" if key == "Preview" else key)
            assert ws.inspector_pages.current == key
            assert ws.nav[key] is ws.section_choice
        selected = ws.active_section
        ws.section_choice.is_open = True
        pump_frames(2)
        ws.inspector.width = dp(650)
        pump_frames(10)
        assert not ws.section_choice.is_open
        assert ws.workbench_tabs.parent is ws.workbench_navigation
        assert ws.active_section == selected
        assert ws.nav["Settings"] is ws.tab_buttons["Settings"]
        ws.tab_buttons["Camera"].dispatch("on_release")
        pump_frames(2)
        assert ws.active_section == "Camera"
        assert ws.section_choice.text == ws.section_names["Camera"]
        ws.inspector.width = dp(360)
        pump_frames(10)
        assert ws.active_section == "Camera"
        assert ws.section_choice.text == ws.section_names["Camera"]
        send.assert_not_called()
    finally:
        ws.inspector.size_hint_x, ws.inspector.width = original[:2]
        ws.select(original[2])
        pump_frames(5)


def test_profiles_stay_in_workbench_with_media_visible_and_draft_retained(kivy_app, tmp_path, monkeypatch):
    from kivy.metrics import dp

    from carveracontroller.desktop_components import ACCENT

    ws = kivy_app.root.desktop_workspace
    original = ws.inspector.size_hint_x, ws.inspector.width, ws.active_section
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    before = ws.profile_store.path.read_bytes() if ws.profile_store.path.exists() else None
    try:
        ws.select("Scene")
        ws._open_profiles()
        library = ws.profile_library
        library.fields["name"].text = "Retained inline draft"
        for width in (360, 600):
            ws.inspector.size_hint_x = None
            ws.inspector.width = dp(width)
            pump_frames(12)
            assert ws.active_section == "Profiles" and ws.inspector_pages.current == "Profiles"
            assert library.parent is ws.inspector_pages.get_screen("Profiles")
            assert ws.media_holder.parent and ws.preview_row.parent is ws.media_holder
            assert ws.preview_row.width > 0 and ws.preview_row.height > 0
            assert library.compact_layout
            assert library.editor_scroll.height >= dp(160)
            assert not library.browser_expanded
            assert library.list_scroll.parent is None
            library.browser_toggle.dispatch("on_release")
            pump_frames(5)
            assert library.browser_expanded and library.list_scroll.parent is library.list_card
            assert library.browser_toggle.text.startswith("Back to editor")
            library.browser_toggle.dispatch("on_release")
            pump_frames(5)
            assert not library.browser_expanded
            assert library.browser_toggle.text.startswith("Browse")
            assert library.fields["name"].text == "Retained inline draft"
            assert library.actions.width <= library.editor_card.width
            assert ws.tab_buttons["Profiles"].base_color == ACCENT
            assert "Save &" in library.apply_button.text
            ws.export_to_png(str(tmp_path / f"inline-profiles-{width}.png"))
        ws.select("Scene")
        refresh = Mock(wraps=library.refresh)
        monkeypatch.setattr(library, "refresh", refresh)
        ws._open_profiles()
        refresh.assert_not_called()
        assert ws.profile_library is library
        assert library.fields["name"].text == "Retained inline draft"
        ws.close_profile_library()
        assert ws.active_section == "Scene"
        assert (ws.profile_store.path.read_bytes() if ws.profile_store.path.exists() else None) == before
        send.assert_not_called()
    finally:
        library.revert()
        ws.inspector.size_hint_x, ws.inspector.width = original[:2]
        ws.select(original[2])
        pump_frames(5)


def test_cancel_stock_view_retains_computed_results_without_displaying_partial_mesh(kivy_app, monkeypatch):
    import time

    import carveracontroller.desktop_simulation as module
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
    from carveracontroller.machine.program_operations import ProgramOperations

    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    workspace.operation_panel.program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z2\nG1 Z0 F100\nG1 X10\n"
    )
    viewer.configure_machine((-180, -120, -110), (10, 2, 2), (0, -1, 0))
    viewer.load_tool_profiles(
        {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, flute_length=3, stickout=4)}
    )
    panel = workspace.simulation_panel
    panel.stock_source.text = "Initial stock"
    panel.resolution.text = "1"
    build_geometry = module.stock_geometry

    def cancel_during_view(stock, **kwargs):
        panel.cancel_event.set()
        return build_geometry(stock, **kwargs)

    monkeypatch.setattr(module, "stock_geometry", cancel_during_view)
    panel.start(False)
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2)
    assert not panel.running
    assert panel.report is not None, panel.note.text
    assert not panel.report.cancelled
    assert panel.report.removed_volume_mm3 > 0
    assert panel.rest_stock.remaining_volume_mm3 == panel.report.remaining_volume_mm3
    assert viewer._rest_stock_geometry is None
    assert "Stock visualization cancelled; completed stock results retained" in panel.note.text
    assert not panel.simulate_action.disabled
    send.assert_not_called()
