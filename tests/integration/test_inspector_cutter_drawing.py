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
    for key, caption in (("diameter", "Diameter: 6.35 mm"), ("shank_diameter", "Shank diameter: 6.35 mm")):
        drawing.dispatch("on_dimension_selected", key)
        pump_frames(2)
        assert drawing.radial_label.text == caption and drawing.radial_label.opacity == 1
        assert drawing.y <= drawing.radial_label.y < drawing.radial_label.top <= drawing.top
    drawing.dispatch("on_dimension_selected", "stickout")
    pump_frames(2)
    assert drawing.radial_label.opacity == 0
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
    drawing.dispatch("on_dimension_selected", "diameter")
    pump_frames(2)
    assert drawing.radial_label.text == "Diameter: 8 mm"
    viewer.library_tool_table_mm[7].shank_diameter = None
    inspector.refresh()
    drawing.dispatch("on_dimension_selected", "shank_diameter")
    pump_frames(2)
    assert drawing.radial_label.text == "Shank diameter: unknown"
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


@pytest.mark.parametrize(
    "header",
    [
        "(T7  End mill  D=0.25 SD=0.25 FL=1 BL=3 - flat end mill)",
        "(@FC|TOOL|number=7|name=End mill|type=Endmill|diameter=0.25|shankdiameter=0.25|flutelength=1|length=3)",
        ";@MKR|TOOL|number=7|name=End mill|type=Flat End|diameter=0.25|handlediameter=0.25|flutelength=1|sticklength=3",
    ],
)
def test_streamed_cam_metadata_reaches_unit_scaled_nominal_drawing_without_commands(
    setup_workspace,
    monkeypatch,
    header,
):
    from carveracontroller.addons.tool_visualization.extractor import extract_tool_table

    ws, send = setup_workspace
    viewer, inspector = ws.machine.gcode_viewer, ws.object_inspector
    profiles = deepcopy(ws.profile_store.data)
    table = extract_tool_table(iter([header, "G20", "G0 X0"]))
    assert list(table) == [7]
    monkeypatch.setattr(viewer, "tool_table", table)
    monkeypatch.setattr(viewer, "tool_unit_scale", 25.4)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {})
    monkeypatch.setattr(viewer, "_active_tool_number", 7)
    ws.select("Scene")
    inspector.select("cutter", reveal=False)
    pump_frames(3)
    drawing = inspector.cutter_drawing
    assert drawing.definition.diameter == pytest.approx(6.35)
    assert drawing.definition.length == pytest.approx(76.2)
    assert drawing.definition.flute_length == pytest.approx(25.4)
    assert "nominal schematic" in inspector.cutter_drawing_status.text
    assert ws.profile_store.data == profiles
    send.assert_not_called()
