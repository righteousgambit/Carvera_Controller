"""Fixed per-part angles survive actual desktop editing, retained results and playback."""

import time
from dataclasses import replace
from unittest.mock import Mock

import pytest
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_historical_scene import capture_scene, publish_scene
from carveracontroller.desktop_repeat_parts import RepeatPartsPanel
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.repeat_parts import RepeatPartPlan, RepeatPartStore
from tests.unit.test_imported_stock_arrays import array

from .conftest import load_gcode_file, pump_frames


def finish(panel):
    deadline = time.monotonic() + 20
    while (panel.io_busy or panel.calculating) and time.monotonic() < deadline:
        pump_frames(1, sleep=0.01)
    assert not panel.io_busy and not panel.calculating, panel.simulation_note.text


@pytest.mark.parametrize("width,imported", [(360, False), (760, True)])
def test_oriented_part_drafts_save_restore_preview_simulate_exchange_and_playback(
    kivy_app, monkeypatch, tmp_path, width, imported
):
    ws, viewer = kivy_app.root.desktop_workspace, kivy_app.root.desktop_workspace.machine.gcode_viewer
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "oriented-workflow"})
    monkeypatch.setattr(ws.app, "state", "N/A")
    monkeypatch.setattr(ws.app, "playing", False)
    monkeypatch.setattr(ws, "machine_profile_loading", False)
    text = "G21 G90 G17 G94 G54\nT1 M6\nG0 X1.8 Y2.8 Z8\nG1 Z-1 F100\nG1 X2.1\n"
    path = tmp_path / "angles.cnc"
    path.write_text(text)
    monkeypatch.setattr(ws.app, "selected_local_filename", str(path))
    load_gcode_file(kivy_app, str(path))
    program = ProgramOperations.from_text(text)
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=10, stickout=12)},
    )
    before = capture_scene(viewer)
    panel = RepeatPartsPanel(ws)
    panel.store = RepeatPartStore(tmp_path / "plans.json")
    panel.resolution.text = "0.5"
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel)
    popup = Popup(title="Repeat parts · fixed stock angles", content=scroll, size_hint=(None, None), size=(width, 850))
    try:
        if imported:
            plan, _source = array(tmp_path)
        else:
            plan = RepeatPartPlan.grid(1, 2, (40, 0, 0), (10, 20, 30), (1, 2, -2), (8, 6, 4))
        panel.show_plan(plan, "oriented-workflow")
        panel.toggle()
        panel.show_page("Review")
        panel.part_editor.toggle()
        popup.open()
        panel.part_orientation.text = "23, -32, 41"
        panel.choice.text = panel.choice.values[1]
        panel.part_orientation.text = "24, -32, 41"
        panel.choice.text = panel.choice.values[0]
        assert panel.part_orientation.text == "23, -32, 41"
        panel.apply_all_parts()
        plan = panel.plan
        assert tuple(p.stock_orientation_deg for p in plan.parts) == ((23, -32, 41), (24, -32, 41))
        assert all(control.disabled for control in panel.layout_controls)  # Individually oriented custom layout.
        panel.part_orientation.text = "NaN, 0, 0"
        panel.apply_part()
        assert panel.plan is plan and panel.part_drafts
        panel.discard_part_draft()
        pump_frames(12)
        scroll.scroll_to(panel.part_orientation, animate=False)
        pump_frames(8)
        field = panel.part_orientation
        assert field.width >= 120
        assert field.parent.x >= panel.x and field.parent.right <= panel.right + 1
        caption = next(child for child in field.parent.children if child is not field)
        assert caption.texture_size[0] <= caption.width + 1
        popup.export_to_png(str(tmp_path / f"oriented-array-{width}.png"))
        panel.save()
        finish(panel)
        assert panel.store.load("oriented-workflow") == plan
        panel.plan = None
        panel.restore()
        finish(panel)
        assert panel.plan == plan
        assert panel.part_orientation.text == "23.0, -32.0, 41.0"
        panel.preview()
        finish(panel)
        assert viewer.machine_setup.stock_orientation.degrees == (23, -32, 41)
        assert viewer.repeat_stock_plan == plan
        assert "23" in panel.frame_detail.text
        panel.simulate()
        finish(panel)
        assert panel.result is not None, panel.simulation_note.text
        assert panel.result.reports[0].removed_volume_mm3 > 0
        assert tuple(s["tilt_deg"] for s in panel.result.snapshots) == ((23, -32), (24, -32))
        archive = tmp_path / "angles.cvstocks"
        panel.exchange_result(str(archive), True)
        finish(panel)
        assert archive.exists(), panel.artifact_status.text
        panel.exchange_result(str(archive), False)
        finish(panel)
        assert "Loaded all rest stocks" in panel.artifact_status.text
        panel.prepare_playback()
        finish(panel)
        assert viewer.declared_playback.plan == plan
        expected = (12.1, 22.8, 29)
        assert viewer.declared_playback.machine_rows[-1][:3] == pytest.approx(expected)
        panel.restore_playback()
        panel.choice.text = panel.choice.values[1]
        panel.preview()
        finish(panel)
        assert viewer.machine_setup.stock_orientation.degrees == (24, -32, 41)
        previous_result = panel.result
        panel.part_orientation.text = "25, -32, 41"
        assert panel.result is previous_result  # Draft alone retains displayed results.
        panel.apply_part()
        assert panel.result is None
        assert panel.plan.parts[1] == replace(plan.parts[1], stock_orientation_deg=(25, -32, 41))
        send.assert_not_called()
    finally:
        panel.closed = True
        popup.dismiss()
        viewer.restore_file_playback()
        publish_scene(viewer, before)
        pump_frames(3)
