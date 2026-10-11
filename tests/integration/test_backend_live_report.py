"""Actual backend telemetry drives read-only native scene/metrics, without GUI commands."""

import copy
import time
from unittest.mock import Mock

import pytest
from kivy.core.window import Window
from kivy.uix.popup import Popup

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.CNC import CNC
from carveracontroller.desktop_camera_registration import CameraRegistrationPanel
from carveracontroller.machine.desktop_control_owner import ControlBinding, DesktopControlOwner
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.webcam import WebcamClient
from tests.integration import test_backend_connection as backend_support
from tests.integration.conftest import pump_frames, set_window_viewport
from tests.unit.test_camera_calibration_file import reference

backend_connection = backend_support.backend_connection
wait_for = backend_support.wait_for


@pytest.fixture
def backend_scene(backend_connection, kivy_app, monkeypatch):
    panel, original_ws, machine, methods = backend_connection
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    pump_frames(20, sleep=0.02)
    original_tools = copy.deepcopy(viewer.library_tool_table_mm)
    previous_state = ws.app.state
    previous_section, previous_task = ws.active_section, ws.program_tasks.active
    monkeypatch.setattr(ws, "backend_panel", panel)
    monkeypatch.setattr(ws, "control_owner", DesktopControlOwner())
    monkeypatch.setattr(ws, "selected_machine_profile", {**original_ws.selected_machine_profile, "model": "C1"})
    monkeypatch.setattr(ws.machine.controller, "stream", None)
    monkeypatch.setattr(ws, "_connection_opening", lambda: False)
    gui_send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", gui_send)
    monkeypatch.setattr(
        ws.machine.controller,
        "observed_pose",
        ObservedPose(time.monotonic(), "Idle", (900, 900, 900), (777, 777, 777), 99, 999),
    )
    for key, value in {"curspindle": 1, "tarspindle": 2, "curfeed": 3, "tlo": 999, "wx": 777, "mx": 900}.items():
        monkeypatch.setitem(CNC.vars, key, value)
    ws.app.state = "N/A"
    panel.workspace = ws
    machine.status = (
        b"<Idle|MPos:-190,-125,-100,0,0|WPos:1,2,3,0,0|C:1,4,0,1|R:0|G:0|S:11950,12000,100|F:600,600,80|T:2,47.5>\n"
    )
    viewer.load_tool_profiles(
        {
            2: ToolDefinition(2, diameter=6.35, stickout=30, description="Declared quarter-inch cutter"),
            3: ToolDefinition(3, diameter=3.175, stickout=25, description="Declared detail cutter"),
        }
    )
    viewer.set_machine_visible(True)
    try:
        ws.select("Settings")
        ws.machine_tasks.show("Backend")
        panel.connect_action.dispatch("on_release")
        wait_for(lambda: not panel.busy and "actual 11950 RPM" in panel.telemetry.text)
        panel.claim_action.dispatch("on_release")
        assert ws.control_owner.backend_selected and not ws.connected
        wait_for(lambda: ws.reported_pose() is not None)
        yield ws, viewer, panel, machine, methods, gui_send
    finally:
        # Close the fixture server before retiring the child, avoiding an unread
        # loopback TCP response racing hard process shutdown. Keep all errors.
        machine.stop.set()
        pump_frames(2, sleep=0.06)
        viewer.set_pose_mode("Preview")
        viewer.set_observed_pose(None)
        viewer.load_tool_profiles(original_tools)
        ws.app.state = previous_state
        ws.select(previous_section)
        ws.program_tasks.show(previous_task)
        panel.workspace = original_ws
        gui_send.assert_not_called()


def refresh(ws):
    ws.refresh(0)
    ws.tool_comparison.refresh(force=True)
    ws.readiness.refresh()


def test_actual_backend_scene_metrics_tooling_and_readiness_use_selected_reports(backend_scene, tmp_path):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    ws.select("Job")
    refresh(ws)
    assert ws.return_to_live()
    pump_frames(3)
    refresh(ws)
    assert viewer.pose_mode == "Live" and viewer.observed_pose.machine_mm == (-190, -125, -100)
    expected = viewer._machine_pose_for(viewer.machine_setup.work_point((-190, -125, -100)))
    assert viewer._machine_pose == expected
    tip = viewer._machine_pose["tool_machine_mm"]
    assert (tip[0], tip[1] - viewer._machine_pose["table"][1], tip[2]) == pytest.approx((-190, -125, -100))
    assert viewer._active_tool_number == 2 and viewer.pointer_mesh_instrs
    assert viewer._machine_contexts["live_pose"].children
    assert ws.rpm_metric.value.text == "11,950" and ws.feed_metric.value.text == "600"
    assert ws.tool_metric.value.text == "T2" and "47.500" in ws.tool_metric.detail.text
    assert "firmware units/reference" in ws.tool_metric.detail.text
    assert ws.position_values["X"].text == "1.000" and ws.machine_values["X"].text == "Machine -190.000"
    assert "G54" in ws.wcs_label.text and "Backend report" in ws.pose_note.text
    assert "Backend report" in ws.readiness.telemetry_note.text
    ws.tool_comparison.choose(2)
    assert next(row for row in ws.tool_comparison.rows if row.number == 2).reported_active
    assert "Backend-reported offset: 47.5" in ws.tool_comparison.detail.text
    assert "Current reported TLO: Unknown" in ws.tool_comparison.detail.text
    before = viewer._preview_program_point
    ws.set_pose_mode("Compare")
    assert viewer.observed_pose.tool == 2 and viewer._preview_program_point == before
    machine.status = machine.status.replace(b"-190,-125,-100", b"-180,-120,-90").replace(b"T:2,47.5", b"T:3,48.2")
    wait_for(lambda: ws.reported_pose() is not None and ws.reported_pose().tool == 3)
    refresh(ws)
    ws.return_to_live()
    assert viewer.observed_pose.machine_mm == (-180, -120, -90) and viewer._active_tool_number == 3
    assert not ws.connected and ws.machine.controller.observed_pose.tool == 99
    assert CNC.vars["curspindle"] == 1 and CNC.vars["mx"] == 900
    assert all(method in ("snapshot", "connect") for method in methods)
    assert all(command in (b"?", b"diagnose\n", b"M105\n") for command in machine.wire)
    note_parent = ws.pose_note.parent
    note_index = note_parent.children.index(ws.pose_note)
    note_parent.remove_widget(ws.pose_note)
    try:
        for width in (300, 650):
            popup = Popup(title="Backend report", content=ws.pose_note, size_hint=(None, None), size=(width + 48, 360))
            popup.open()
            pump_frames(5)
            assert abs(ws.pose_note.width - width) <= 5
            assert ws.pose_note.height >= ws.pose_note.texture_size[1]
            ws.pose_note.export_to_png(str(tmp_path / f"backend-live-note-{width}.png"))
            popup.dismiss(animation=False)
            ws.pose_note.parent.remove_widget(ws.pose_note)
    finally:
        if ws.pose_note.parent is not None:
            ws.pose_note.parent.remove_widget(ws.pose_note)
        note_parent.add_widget(ws.pose_note, index=note_index)
    previous_window, previous_opacity = Window.system_size, panel.opacity
    try:
        panel.opacity = 0
        set_window_viewport(1400, 1000)
        ws.program_tasks.show("View & playback")
        viewer.restore_default_view()
        pump_frames(5)
        assert viewer._machine_contexts_added and viewer._machine_contexts["spindle"].children
        assert viewer.width > 500 and viewer.height > 200
        Window.screenshot(name=str(tmp_path / "backend-live-workspace.png"))
    finally:
        panel.opacity = previous_opacity
        Window.system_size = previous_window
        pump_frames(5)
    gui_send.assert_not_called()


@pytest.mark.parametrize("change", ["profile", "binding", "child", "stopped", "stale"])
def test_replaced_retired_or_stale_backend_retires_scene_and_readouts_without_gui_fallback(
    backend_scene, monkeypatch, change
):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    ws.return_to_live()
    refresh(ws)
    pump_frames(10, sleep=0.04)
    refresh(ws)
    before = copy.deepcopy(viewer._machine_pose)
    binding = ws.control_owner.binding
    if change == "profile":
        ws.selected_machine_profile = {**ws.selected_machine_profile, "host": "192.0.2.1"}
    elif change == "binding":
        ws.control_owner.binding = ControlBinding(binding.session_id, "replacement")
    elif change == "child":
        monkeypatch.setattr(panel.client, "session_id", "replacement")
    elif change == "stopped":
        panel.client.close()
    else:
        panel.monitoring = False
        pump_frames(30, sleep=0.04)
    refresh(ws)
    assert viewer.observed_pose is None and viewer._machine_pose == before
    assert not viewer._machine_contexts["live_pose"].children
    assert ws.rpm_metric.value.text == ws.tool_metric.value.text == "—"
    assert "unavailable" in ws.pose_note.text or "stale" in ws.pose_note.text
    assert ws.return_live_action.disabled
    assert ws.control_owner.backend_selected and ws.machine.controller.observed_pose.tool == 99
    assert "Backend report unavailable or stale" in ws.readiness.telemetry_note.text
    gui_send.assert_not_called()


def test_partial_packet_updates_independent_metrics_but_never_inherits_old_pose_or_offset(backend_scene):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    ws.return_to_live()
    machine.status = b"<Hold|MPos:-185,-125,-100,0|C:1,4,0,1|S:11850,12000,100>\n"
    wait_for(lambda: ws.backend_report().current and ws.backend_report().status["state"] == "Hold")
    refresh(ws)
    assert viewer.observed_pose is None and not viewer._machine_contexts["live_pose"].children
    assert ws.rpm_metric.value.text == "11,850"
    assert ws.tool_metric.value.text == "—" and ws.position_values["X"].text == "—"
    assert "Unknown" in ws.wcs_label.text and ws.backend_report().raw_tool_offset is None
    assert not any(row.reported_active for row in ws.tool_comparison.rows)
    gui_send.assert_not_called()


def test_invalid_firmware_sources_withhold_backend_metrics_without_gui_fallback(backend_scene):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    machine.status = machine.status.rstrip()[:-1] + b"|SE:1,1,1,1,100,0,0,1,1>\n"
    wait_for(
        lambda: (
            ws.backend_report().current
            and ws.backend_report().status.get("field_validity", {}).get("tool_status") is False
        )
    )
    refresh(ws)
    assert ws.rpm_metric.value.text == ws.tool_metric.value.text == "—"
    assert ws.backend_report().raw_tool_offset is None
    assert not any(row.reported_active for row in ws.tool_comparison.rows)
    assert CNC.vars["curspindle"] == 1 and ws.machine.controller.observed_pose.tool == 99
    source = ws.backend_telemetry()
    assert source.monitor.baseline is None and not source.latest_complete
    gui_send.assert_not_called()


def test_camera_reference_binds_actual_backend_pose_and_exact_lease_without_exposure_claim(backend_scene, monkeypatch):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    camera = WebcamClient(start=False)
    monkeypatch.setattr(ws, "camera_client", camera)
    view = CameraRegistrationPanel(ws)
    camera.frame = reference().frame
    view.capture_reference()
    retained = view.reference
    assert retained.machine_mm == (-190, -125, -100)
    assert retained.backend_owner == (panel.client.session_id, ws.control_owner.binding.connection_id)
    assert retained.to_dict()["backend_owner"] == {
        "session_id": panel.client.session_id,
        "connection_id": ws.control_owner.binding.connection_id,
    }
    assert "exposure synchronization unqualified" in view.reference_note.text
    assert view._reference_owner_matches()
    from carveracontroller.machine.camera_calibration_file import CalibrationReference

    assert CalibrationReference.from_dict(retained.to_dict()).backend_owner == retained.backend_owner
    view.focal.text = "20 20 12 9"
    popup = view.edit_lens()
    popup.lens_fields["fx"].text = "25"
    previous = view._owner_identity()
    ws.control_owner.binding = ControlBinding(retained.backend_owner[0], "replacement")
    assert view._owner_identity() != previous and not view._reference_owner_matches()
    try:
        popup.apply_lens()
        assert "changed" in popup.lens_note.text
        assert view.reference is retained and view.focal.text == "20 20 12 9"
    finally:
        popup.dismiss()
    camera.frame = reference().frame
    view.capture_reference()
    assert view.reference.machine_mm is None
    assert ws.machine.controller.observed_pose.machine_mm == (900, 900, 900)
    gui_send.assert_not_called()


@pytest.mark.parametrize("consumer", ["pose", "tools", "readiness"])
def test_native_consumer_retains_one_backend_packet_for_pose_freshness_and_offset(backend_scene, monkeypatch, consumer):
    ws, viewer, panel, machine, methods, gui_send = backend_scene
    report = ws.backend_report()
    assert report.current and report.pose.tool == 2 and report.raw_tool_offset == 47.5
    lookup = Mock(return_value=report)
    with monkeypatch.context() as reads:
        reads.setattr(ws, "backend_report", lookup)
        if consumer == "pose":
            ws._refresh_observed_pose(viewer)
            assert viewer.observed_pose is report.pose
            assert "T2" in ws.pose_note.text and "47.5" in ws.pose_note.text
        elif consumer == "tools":
            ws.tool_comparison.refresh(force=True)
            assert next(row for row in ws.tool_comparison.rows if row.number == 2).reported_active
        else:
            ws.readiness.refresh()
            assert "T2" in ws.readiness.telemetry_note.text and "47.5" in ws.readiness.telemetry_note.text
        lookup.assert_called_once_with()
    gui_send.assert_not_called()
