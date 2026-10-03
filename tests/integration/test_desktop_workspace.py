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
        assert workspace.workspaces.current == key
    send.assert_not_called()


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
    assert root.desktop_workspace.workspaces.current == "Console"
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
