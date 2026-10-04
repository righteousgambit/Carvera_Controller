import json
from unittest.mock import Mock

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.desktop_profiles import ProfileStore
from carveracontroller.machine.tool_custody import ToolCustodyStore

from .conftest import pump_frames


def test_preview_assembly_mesh_revision_and_transactional_restore(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    profiles = ProfileStore(tmp_path / "profiles.json")
    design = profiles.save_tool(
        {
            "name": "Ball design",
            "number": 2,
            "shape": "ball_end_mill",
            "diameter": 6.35,
            "shank_diameter": 6.35,
            "flute_length": 10,
            "length": 75,
            "stickout": 40,
        }
    )
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Physical ball", "A", 28, design["id"])
    monkeypatch.setattr(ws, "profile_store", profiles)
    monkeypatch.setattr(ws.machine, "_tool_custody", store)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    original_library = dict(viewer.library_tool_table_mm)
    original_override = viewer.preview_tool_override
    original_binding = viewer.assembly_preview_binding
    try:
        baseline = ToolDefinition(
            2, ToolType.FLAT_END_MILL, diameter=3.175, shank_diameter=6.35, stickout=20, flute_length=10
        )
        viewer.load_tool_profiles({2: baseline})
        profile_bytes = profiles.path.read_bytes()
        panel = ws.tool_comparison.custody
        panel.selected_id = assembly["id"]
        inspected = panel.inspect_dimensions()
        try:
            pump_frames(5)
            assert inspected.content.drawing.definition.stickout == 28
            assert inspected.content.drawing.dimensions[-1].value == 47
            assert inspected.content.mode.text == "Dimensioned drawing"
            assert viewer.library_tool_table_mm == {2: baseline}
            assert viewer.assembly_preview_binding is None
            assert profiles.path.read_bytes() == profile_bytes
            send.assert_not_called()
        finally:
            inspected.dismiss()
        ws.preview_physical_assembly(assembly["id"], 2)
        assert profiles.path.read_bytes() == profile_bytes
        assert viewer.library_tool_table_mm[2].stickout == 28
        assert viewer.library_tool_table_mm[2].tool_type == ToolType.BALL_END_MILL
        assert viewer.preview_tool_override == 2
        vertices = viewer._get_tool_mesh(2)[0]
        assert max(vertices[2::12]) / viewer.move_scale_by_positon == pytest.approx(28)
        panel.selected_id = assembly["id"]
        panel.refresh(force=True)
        assert "current declared definition" in panel.summary.text
        revised = store.revise(assembly["id"], assembly["id"], "Physical ball", "A", 30, design["id"], "Reseated")
        panel.refresh(force=True)
        assert "OLDER assembly" in panel.summary.text
        changed_design = dict(design, diameter=6)
        profiles.save_tool(changed_design)
        panel.refresh()
        assert "OLDER assembly" in panel.summary.text
        profiles.save_tool(design)
        assert viewer.library_tool_table_mm[2].stickout == 28  # no silent geometry change
        ws.preview_physical_assembly(assembly["id"], 2)
        assert viewer.assembly_preview_binding["revision_id"] == revised["id"]
        assert viewer.library_tool_table_mm[2].stickout == 30
        broken = store.revise(
            assembly["id"],
            revised["id"],
            "Physical ball",
            "A",
            30,
            design["id"],
            "Holder reference",
            holder_geometry_path=str(tmp_path / "missing.json"),
        )
        binding = viewer.assembly_preview_binding
        with pytest.raises(OSError):
            ws.preview_physical_assembly(assembly["id"], 2)
        assert viewer.assembly_preview_binding is binding
        assert viewer.library_tool_table_mm[2].stickout == 30
        holder = tmp_path / "holder.json"
        holder.write_text(
            json.dumps(
                {
                    "schema": "carvera-tool-mesh-v1",
                    "units": "mm",
                    "axis": "+Z",
                    "origin": "collet",
                    "triangles": [0, 0, 0, 2, 0, 5, 0, 2, 5],
                }
            )
        )
        store.revise(
            assembly["id"],
            broken["id"],
            "Physical ball",
            "A",
            30,
            design["id"],
            "Verified CAD registration",
            holder_geometry_path=str(holder),
        )
        ws.preview_physical_assembly(assembly["id"], 2)
        assert max(viewer._get_tool_mesh(2)[0][2::12]) / viewer.move_scale_by_positon == pytest.approx(35)
        ws.clear_assembly_preview()
        assert viewer.assembly_preview_binding is None
        assert viewer.library_tool_table_mm == {2: baseline}
        assert viewer.preview_tool_override is None
        assert profiles.path.read_bytes() == profile_bytes
        send.assert_not_called()
    finally:
        panel.selected_id = None
        viewer.load_tool_profiles(original_library)
        viewer.assembly_preview_binding = original_binding
        viewer.select_preview_tool(original_override)
