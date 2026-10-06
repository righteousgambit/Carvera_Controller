"""Named layouts round trip presentation while preserving drafts and machine state."""

from unittest.mock import Mock

import pytest

from carveracontroller.desktop_layouts import LayoutPanel
from carveracontroller.machine.workspace_layouts import WorkspaceLayouts
from tests.integration.conftest import pump_frames


def test_layout_persistence_restore_and_invalid_task_are_command_free(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = LayoutPanel(ws, WorkspaceLayouts(tmp_path / "layouts.json"))
    old_share = ws.media_column.size_hint_x
    camera = ws.job_camera_splitter.parent is ws.preview_row
    ws.select("Setup")
    ws.setup_tasks.show("Holes")
    panel.share.text = "60"
    panel.resize()
    original_camera = ws.camera_stage_view.capture_framing()
    ws.camera_stage_view.restore_framing({"zoom": 2, "center_x": 0.5, "center_y": 0.5})
    assert ws.media_column.size_hint_x == 0.6 and ws.inspector.size_hint_x == 0.4
    view = ws.machine.gcode_viewer
    original_zoom = view.m_zoom
    panel.name.text = "Feature work"
    panel.save()
    assert len(panel.store.records) == 1
    loaded = WorkspaceLayouts(panel.store.path)
    assert loaded.load_error is None and loaded.records == panel.store.records
    view.m_zoom = original_zoom * 1.5
    ws.camera_stage_view.reset_framing()
    ws.select("Settings")
    ws.machine_tasks.show("Preferences")
    panel.share.text = "35"
    panel.resize()
    ws._toggle_job_camera()
    panel.restore()
    pump_frames(10)
    assert ws.active_section == "Setup" and ws.setup_tasks.active == "Holes"
    assert view.m_zoom == original_zoom
    assert ws.camera_stage_view.zoom == 2
    assert ws.media_column.size_hint_x == 0.6
    assert (ws.job_camera_splitter.parent is ws.preview_row) == camera
    before = panel.capture("Before")
    panel.store.records[0]["task"] = "Removed task"
    panel.restore()
    assert "unavailable" in panel.note.text.lower()
    assert panel.capture("Before") == before
    panel.share.text = "nan"
    panel.resize()
    assert ws.media_column.size_hint_x == 0.6
    send.assert_not_called()
    ws.media_column.size_hint_x = old_share
    ws.inspector.size_hint_x = 1 - old_share
    ws.workspace_media_share = old_share
    ws.camera_stage_view.restore_framing(original_camera)


def test_layout_preferences_are_reachable_in_compact_workbench(kivy_app, tmp_path):
    from kivy.metrics import dp
    from kivy.uix.popup import Popup

    ws = kivy_app.root.desktop_workspace
    panel = LayoutPanel(ws, WorkspaceLayouts(tmp_path / "profiles.json"))
    popup = Popup(content=panel, size_hint=(None, None), size=(dp(400), dp(500)))
    popup.open(animation=False)
    try:
        pump_frames(10)
        assert panel.choice.width > dp(300)
        assert panel.name.width > dp(300)
        assert panel.height < dp(450)
        assert panel.note.height >= dp(58)
        panel.export_to_png(str(tmp_path / "named-layouts-compact.png"))
    finally:
        popup.dismiss(animation=False)
        pump_frames(3)


def test_palette_layout_dialog_preserves_source_section_and_task(kivy_app, tmp_path):
    from carveracontroller.desktop_commands import workspace_commands

    ws = kivy_app.root.desktop_workspace
    ws.layout_panel.store = WorkspaceLayouts(tmp_path / "palette-layouts.json")
    ws.select("Setup")
    ws.setup_tasks.show("Datum")
    command = next(c for c in workspace_commands(ws) if c.id == "workspace.layouts")
    from kivy.core.window import Window

    assert command.invoke()
    popup = next(w for w in Window.children if getattr(w, "title", "") == "Workspace layouts")
    try:
        pump_frames(8)
        panel = popup.content.children[0]
        assert abs(panel.to_window(0, panel.top)[1] - popup.content.to_window(0, popup.content.top)[1]) <= 2
        panel.name.text = "Datum review"
        panel.save()
        assert panel.store.records[0]["section"] == "Setup"
        assert panel.store.records[0]["task"] == "Datum"
        assert ws.active_section == "Setup"
    finally:
        popup.dismiss(animation=False)
        pump_frames(3)


def test_direct_divider_and_exchange_preserve_machine_context(kivy_app, monkeypatch, tmp_path):
    from types import SimpleNamespace

    from kivy.core.window import Window

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = LayoutPanel(ws, WorkspaceLayouts(tmp_path / "layouts.json"))
    ws.select("Setup")
    ws.setup_tasks.show("Holes")
    pump_frames(8)
    divider = ws.pane_divider
    assert divider.parent is ws.body
    assert divider.height >= ws.inspector.height - 2
    assert divider.keyboard_on_key_down(Window, (275, "right"), "", ["shift"])
    assert ws.workspace_media_share == 0.55
    assert divider.keyboard_on_key_down(Window, (278, "home"), "", [])
    assert ws.workspace_media_share == 0.5
    touch = SimpleNamespace(pos=divider.center, x=divider.center_x, grab_current=None, is_double_tap=False)
    touch.grab = lambda item: setattr(touch, "grab_current", item)
    touch.ungrab = lambda item: setattr(touch, "grab_current", None)
    assert divider.on_touch_down(touch)
    touch.grab_current = None  # ordinary dispatch precedes grabbed dispatch
    touch.x = ws.body.right + 100
    assert divider.on_touch_move(touch)
    assert ws.workspace_media_share == 0.75
    touch.x = ws.body.x - 100
    assert divider.on_touch_move(touch)
    assert ws.workspace_media_share == 0.25
    assert divider.on_touch_up(touch) and touch.grab_current is None
    pump_frames(8)
    assert ws.preview_row.width <= ws.media_holder.width + 1
    assert ws.model_card.width <= ws.media_holder.width + 1
    assert ws.active_section == "Setup" and ws.setup_tasks.active == "Holes"
    panel.name.text = "Portable"
    panel.save()
    exported = tmp_path / "portable.cvlayout"
    monkeypatch.setattr(ws, "choose_profile_file", lambda callback, **kwargs: callback(exported))
    panel.exchange(True)
    assert exported.exists() and "read back" in panel.note.text
    imported = LayoutPanel(ws, WorkspaceLayouts(tmp_path / "imported.json"))
    monkeypatch.setattr(ws, "choose_asset_file", lambda callback, **kwargs: callback(exported))
    imported.exchange(False)
    assert len(imported.store.records) == 1 and ws.workspace_media_share == 0.25
    assert ws.active_section == "Setup" and ws.setup_tasks.active == "Holes"
    send.assert_not_called()
    divider.keyboard_on_key_down(Window, (278, "home"), "", [])
    divider.focus = False


def test_saved_cutaways_restore_and_mismatch_is_transactional(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.section_view import SectionClip

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = LayoutPanel(ws, WorkspaceLayouts(tmp_path / "cutaways.json"))
    original = dict(viewer.component_cutaways)
    try:
        viewer.component_cutaways = {"stock": SectionClip(2, 35.5, True), "fixture": SectionClip(0, 12, False)}
        panel.name.text = "Section review"
        panel.save()
        assert "saved and read back" in panel.note.text
        panel.store = WorkspaceLayouts(panel.store.path)
        viewer.component_cutaways = {}
        panel.restore()
        assert viewer.component_cutaways == {"stock": SectionClip(2, 35.5, True), "fixture": SectionClip(0, 12, False)}
        assert "setup-bound" in panel.note.text
        # A stored setup mismatch must reject the entire restoration, including
        # pane width and framing, before any presentation mutation.
        panel.store.records[0]["media_share"] = 0.7
        panel.store.records[0]["cutaway_state"]["setup_sha256"] = "0" * 64
        before = panel.capture("Before")
        panel.restore()
        assert "another setup or CAD revision" in panel.note.text
        assert panel.capture("Before") == before
        # Legacy layouts explicitly restore full components rather than retain
        # invisible cuts from a later editing session.
        panel.store.records[0]["cutaway_state"] = None
        panel.restore()
        assert viewer.component_cutaways == {}
        send.assert_not_called()
    finally:
        viewer.component_cutaways = original
        viewer._update_cutaway_uniforms()
        panel._set_share(0.5)


def test_cutaway_identity_tracks_geometry_but_ignores_display(kivy_app, monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace

    import carveracontroller.desktop_cutaway_state as state

    ws = kivy_app.root.desktop_workspace
    scene = state.capture_scene_setup(ws)
    monkeypatch.setattr(state, "capture_scene_setup", lambda _: deepcopy(scene))
    viewer = ws.machine.gcode_viewer
    monkeypatch.setattr(viewer, "machine_profile", SimpleNamespace(geometry_sha256="a" * 64))
    baseline = state.cutaway_setup_hash(ws)
    scene["visibility"] = {key: not value for key, value in scene["visibility"].items()}
    scene["scope"] = "changed presentation"
    scene["choices"]["cutter"] = "another cutter"
    assert state.cutaway_setup_hash(ws) == baseline
    monkeypatch.setattr(viewer, "machine_profile", SimpleNamespace(geometry_sha256="b" * 64))
    assert state.cutaway_setup_hash(ws) != baseline


def test_exploded_layout_restore_is_preview_bound_and_command_free(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    old_mode, old_distance = viewer.pose_mode, viewer.explosion_mm
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = LayoutPanel(ws, WorkspaceLayouts(tmp_path / "exploded.json"))
    try:
        viewer.set_pose_mode("Preview")
        ws.object_inspector.explode_distance.text = "25 mm"
        ws.object_inspector.explode()
        assert viewer.explosion_mm == 25
        ws.object_inspector.explode_distance.text = "invalid"
        ws.object_inspector.explode()
        assert viewer.explosion_mm == 25
        ws.object_inspector.explode_distance.text = "25 mm"
        ws.object_inspector.explode()
        geometry, setup, pose = viewer._inspection_geometry, viewer.machine_setup, dict(viewer._machine_pose)
        panel.name.text = "Assembly inspection"
        panel.save()
        panel.store = WorkspaceLayouts(panel.store.path)
        portable = tmp_path / "exploded.cvlayout"
        panel.store.export_file(portable)
        exchanged = WorkspaceLayouts(tmp_path / "exchanged.json")
        exchanged.import_file(portable)
        assert exchanged.records == panel.store.records
        viewer.set_explosion(0)
        panel.restore()
        assert viewer.explosion_mm == 25
        assert viewer._inspection_geometry is geometry and viewer.machine_setup is setup
        assert viewer._machine_pose == pose
        scale = viewer.move_scale_by_positon or 1
        assert viewer._machine_contexts["stock"]["inspection_offset"] == pytest.approx((0, 0, 75 * scale))
        assert viewer.pointermesh["inspection_offset"] == pytest.approx((50 * scale, 0, 75 * scale))
        ws.set_pose_mode("Live")
        pump_frames(4)
        assert "exploded" not in ws.model_caption.text.lower()
        assert "Exploded" not in ws.object_inspector.status.text
        assert viewer.pointermesh["inspection_offset"] == (0, 0, 0)
        assert viewer._machine_contexts["stock"]["inspection_offset"] == (0, 0, 0)
        before = panel.capture("Before")
        panel.restore()
        assert "Choose Preview" in panel.note.text and panel.capture("Before") == before
        ws.object_inspector.size_hint_x = None
        ws.object_inspector.width = 360
        pump_frames(6)
        assert ws.object_inspector.explode_distance.width > 250
        assert ws.object_inspector.choice.width > 250
        assert ws.object_inspector.section_panel.normal_row.parent is None
        ws.object_inspector.export_to_png(str(tmp_path / "exploded-controls-360.png"))
        send.assert_not_called()
    finally:
        ws.object_inspector.size_hint_x = 1
        viewer.set_explosion(0)
        viewer.set_pose_mode(old_mode)
        if old_mode == "Preview":
            viewer.set_explosion(old_distance)
