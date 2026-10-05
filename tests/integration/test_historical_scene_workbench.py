import copy
import json
import time
from unittest.mock import Mock

import pytest
from kivy.config import Config
from kivy.core.window import Window

from tests.integration.conftest import load_gcode_file, pump_frames
from tests.integration.test_run_recording_workbench import wait_for_record
from tests.unit.test_historical_scene import historical_fixture


@pytest.mark.parametrize("crlf", [False, True])
def test_historical_scene_and_tool_cad_publish_and_return_without_settings_or_commands(
    kivy_app, monkeypatch, tmp_path, crlf
):
    from carveracontroller.desktop_historical_scene import capture_scene
    from carveracontroller.desktop_job_packages import capture_job

    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.run_recording_panel, ws.machine.gcode_viewer
    program, replay, archive, _ = historical_fixture(tmp_path, crlf=crlf)
    monkeypatch.setattr(ws.profile_store, "path", tmp_path / "profiles.json")
    monkeypatch.setattr(ws.app, "selected_local_filename", str(program))
    load_gcode_file(kivy_app, str(program))
    ws.operation_panel.load(str(program))
    deadline = time.monotonic() + 10
    while ws.operation_panel.program is None and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert ws.operation_panel.program is not None
    viewer.set_machine_visible(True)
    assert viewer.machine_visible
    before = capture_scene(viewer)
    saved_library = copy.deepcopy(ws.profile_store.data)
    source = ws.camera_client.url
    previous_labels = ws.profile_status.text, ws.tool_library_summary.text
    send, write = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(Config, "write", write)
    monkeypatch.setattr(ws.app, "state", "Idle")
    monkeypatch.setattr(ws.app, "playing", False)
    panel.setup_archives[replay.payload["session_id"]] = archive
    panel.load(replay)
    ws.select("Job")
    ws.program_tasks.choose("Run record")
    panel.historical_action.dispatch("on_release")
    wait_for_record(panel)
    assert "Recorded scene and 1 tools loaded" in panel.notice.text
    assert viewer.machine_profile is not before["machine_profile"]
    assert set(viewer.library_tool_table_mm) == {2}
    assert viewer._tool_meshes[2][1] == [0, 1, 2]
    assert viewer._inspection_geometry["fixture"].indices
    assert viewer.machine_setup.work_offset_mm == (-10, -20, -30)
    assert not viewer.machine_setup.alignment_confirmed
    assert ws.historical_preview["session_id"] == replay.payload["session_id"]
    assert "Recorded setup preview" in ws.profile_status.text
    assert "SHA-256 prefix" in panel.binding_note.text
    assert replay.payload["context"]["configuration"]["sha256"] in panel.full_binding_note.text
    panel.recorded_tool_choice.text = next(
        title for title, number in panel.recorded_tool_options.items() if number == 2
    )
    assert viewer.preview_tool_override == 2 and "Archived T2 geometry shown" in panel.notice.text
    panel.scene_section.set_expanded(True)
    original_size = Window.system_size
    rendered = []
    try:
        for name, size in (("wide", (1600, 1000)), ("narrow", (900, 1000))):
            Window.system_size = size
            pump_frames(8)
            path = tmp_path / f"historical-scene-{name}.png"
            panel.scene_section.export_to_png(str(path))
            assert panel.recorded_tool_choice.width <= panel.scene_section.width
            rendered.append(str(path))
        from pathlib import Path

        Path("/tmp/carvera-historical-scene-render-paths.json").write_text(json.dumps(rendered))
    finally:
        Window.system_size = original_size
        pump_frames(4)
        assert tuple(Window.system_size) == tuple(original_size)
    assert ws.profile_store.data == saved_library and ws.camera_client.url == source
    with pytest.raises(ValueError, match="Restore the previous scene"):
        capture_job(ws)
    panel.start_recording(retain_setup=True)
    assert "Restore the previous scene" in panel.notice.text
    panel.previous_scene_action.dispatch("on_release")
    wait_for_record(panel)
    assert capture_scene(viewer) == before
    assert ws.historical_preview is None
    assert (ws.profile_status.text, ws.tool_library_summary.text) == previous_labels
    assert panel.previous_scene is None
    send.assert_not_called()
    write.assert_not_called()
    panel.return_live()
    panel.scene_section.set_expanded(False)
    ws.program_tasks.choose("Operations")
