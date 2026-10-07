from copy import deepcopy
from dataclasses import replace

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from tests.integration import test_component_isolation
from tests.integration.conftest import pump_frames


@pytest.fixture
def setup_workspace(kivy_app, tmp_path, monkeypatch):
    yield from test_component_isolation.setup_workspace.__wrapped__(kivy_app, tmp_path, monkeypatch)


def test_inspector_draws_current_tool_reuses_widgets_and_drops_stale_geometry(setup_workspace, monkeypatch):
    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    tool = ToolDefinition(7, ToolType.FLAT_END_MILL, diameter=0.25, shank_diameter=0.25, length=3, flute_length=1)
    monkeypatch.setattr(viewer, "tool_table", {7: tool})
    monkeypatch.setattr(viewer, "tool_unit_scale", 25.4)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {})
    monkeypatch.setattr(viewer, "_active_tool_number", 7)
    stores = deepcopy(ws.profile_store.data)
    ws.select("Scene")
    inspector.select("cutter", reveal=False)
    pump_frames(3)
    drawing = inspector.cutter_drawing
    assert drawing and drawing.parent is inspector.cutter_drawing_card
    assert drawing.definition.length == pytest.approx(76.2)
    assert drawing.definition.diameter == 6.35
    assert "CAM tool metadata" in inspector.cutter_drawing_status.text
    drawing.dispatch("on_dimension_selected", "stickout")
    assert drawing.selected_dimension == "stickout"
    assert drawing.dimensions[2].caption == "Stickout: unknown"
    inspector.refresh()
    assert inspector.cutter_drawing is drawing
    assert drawing.selected_dimension == "stickout"
    viewer.library_tool_table_mm[7] = replace(tool, diameter=8, shank_diameter=8, length=60, flute_length=20)
    inspector.refresh()
    assert inspector.cutter_drawing is drawing
    assert drawing.definition.diameter == 8 and drawing.definition.length == 60
    assert "Local tool profile" in inspector.cutter_drawing_status.text
    viewer.library_tool_table_mm[7].stickout = 10  # Incompatible with its cutting length.
    inspector.refresh()
    assert drawing.disposed and inspector.cutter_drawing is None
    assert "Cutting length exceeds" in inspector.cutter_drawing_status.text
    assert inspector.cutter_drawing_card.parent is inspector
    inspector.select("stock", reveal=False)
    assert inspector.cutter_drawing_card.parent is None
    inspector.select("cutter", reveal=False)
    viewer.library_tool_table_mm.clear()
    viewer.tool_table.clear()
    inspector.refresh()
    assert inspector.cutter_drawing_card.parent is None
    assert ws.profile_store.data == stores and tool.length == 3
    send.assert_not_called()
