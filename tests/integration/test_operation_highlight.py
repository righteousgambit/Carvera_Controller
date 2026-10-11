import json
from pathlib import Path
from unittest.mock import Mock

from kivy.core.window import Window
from PIL import Image

from carveracontroller.machine.program_operations import ProgramOperations

from .conftest import load_gcode_file, pump_frames


def test_real_loader_operation_selection_and_revision_replacement(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.operation_panel, ws.machine.gcode_viewer
    text = "G21 G90 G94 G54\n(Operation: Facing)\nT1 M6\nS12000 M3\nG0 X0 Y0 Z2\nG1 X5 F100\nG1 Y5\n(Operation: Finish)\nG1 X0\nG1 Y0\n"
    path = tmp_path / "operations.cnc"
    path.write_text(text)
    program = ProgramOperations.from_text(text)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.app, "selected_local_filename", str(path))
    load_gcode_file(kivy_app, str(path))
    panel._loaded(panel.generation, program, None)
    pump_frames(3)
    assert viewer.loaded_program_hash == program.file_hash
    assert len(program.operations) >= 2
    operation = program.operations[-1]
    viewer.linemesh["show_rapid"] = 0.0
    panel.select(operation)
    pump_frames(3)
    assert viewer.operation_highlight == (program.file_hash, operation.start_line, operation.end_line)
    assert viewer.linemesh["operation_selected"] == 1.0
    assert viewer.linemesh["show_rapid"] == 0.0
    assert "Complete selected operation" in panel.path_highlight_note.text
    viewer.set_machine_visible(False)
    viewer.restore_default_view()
    for key, value in {
        "m_xRot": 90,
        "m_yRot": 0,
        "m_xLookAt": 0,
        "m_yLookAt": 0,
        "m_zLookAt": 0,
        "m_distance": 3,
        "m_zoom": 3,
        "m_xPan": 0,
        "m_yPan": 0,
    }.items():
        monkeypatch.setattr(viewer, key, value)
    viewer.update_proj()
    viewer.update_view()
    ws.select("Job")
    ws.program_tasks.show("Operations")
    viewer._scene_dirty = True
    pump_frames(8)
    viewer._on_frame_tick(0)
    Path("/tmp/carvera-operation-highlight-render.json").write_text(
        json.dumps(
            {
                "lines": viewer.raw_linenumbers,
                "points": viewer.raw_positions,
                "feeds": viewer.raw_feed_rates,
                "tools": viewer.raw_tools,
                "camera": {
                    key: getattr(viewer, key)
                    for key in ("m_distance", "m_xRot", "m_yRot", "m_zoom", "m_xPan", "m_yPan")
                },
                "vertices": viewer.meshmanager.meshes[0][0][:44],
                "canvas_has_lines": viewer.linemesh in viewer.canvas.children,
                "line_instructions": [type(item).__name__ for item in viewer.linemesh.children],
                "lengths": viewer.lengths,
                "center": viewer.lines_center,
                "shader_success": viewer.linemesh.shader.success,
                "uniforms": {
                    key: viewer.linemesh[key]
                    for key in (
                        "operation_start",
                        "operation_end",
                        "operation_selected",
                        "show_feed",
                        "show_rapid",
                        "tool_filter_count",
                        "tool_bits",
                        "tool_ids0",
                        "color_scheme",
                        "speed_bucket_bits",
                        "z_bucket_bits",
                    )
                },
                "position_scale": viewer.move_scale_by_positon,
            },
            indent=2,
        )
    )
    screenshot = Window.screenshot(name="/tmp/carvera-operation-highlight.png")
    with Image.open(screenshot) as rendered:
        x, y = viewer.to_window(viewer.x, viewer.y)
        sx, sy = rendered.width / Window.width, rendered.height / Window.height
        pane = rendered.convert("RGB").crop(
            (
                int(x * sx),
                int((Window.height - y - viewer.height) * sy),
                int((x + viewer.width) * sx),
                int((Window.height - y) * sy),
            )
        )
        selected_pixels = [
            (index % pane.width, index // pane.width)
            for index, (r, g, b) in enumerate(pane.getdata())
            # Single-pixel vertical lines can blend with the pane background.
            if r < 90 and g > 90 and b > 80 and g - r > 60 and b - r > 50
        ]
        assert len(selected_pixels) > 20, "Selected path must actually render in the pane"
        assert max(x for x, y in selected_pixels) - min(x for x, y in selected_pixels) > 20
        assert max(y for x, y in selected_pixels) - min(y for x, y in selected_pixels) > 20
    panel.toggle_path_highlight()
    assert viewer.operation_highlight is None
    panel.toggle_path_highlight()
    assert viewer.operation_highlight is not None
    ws.set_pose_mode("Live")
    assert viewer.operation_highlight is None
    assert "paused in Live" in panel.path_highlight_note.text
    ws.set_pose_mode("Preview")
    assert viewer.operation_highlight is not None
    replacement = tmp_path / "replacement.cnc"
    replacement.write_text("G21 G90 G94 G54\nG0 X0 Y0 Z2\nG1 X20 F100\n")
    load_gcode_file(kivy_app, str(replacement))
    assert viewer.loaded_program_hash != program.file_hash
    panel.refresh_path_highlight()
    assert viewer.operation_highlight is None
    assert "matching loaded preview" in panel.path_highlight_note.text
    viewer.begin_new_file_load()
    assert viewer.loaded_program_hash is None
    assert viewer.linemesh["operation_selected"] == 0.0
    send.assert_not_called()
