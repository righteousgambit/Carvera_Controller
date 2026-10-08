import json
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from kivy.metrics import dp

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.geometry_changes import digest_context
from carveracontroller.machine.program_operations import ProgramOperations

from .conftest import pump_frames


def settle_transfer(panel):
    deadline = time.monotonic() + 5
    while panel.artifact_transfer is not None and panel.artifact_transfer.active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert panel.artifact_transfer is None or not panel.artifact_transfer.active


def test_simulation_refresh_and_operation_tools_do_not_traverse_motion(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text(
        "G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 X1 F100\n(Operation: Finish)\nT2 M6\nG1 Y1\n"
    )
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(ws.operation_panel, "selected_operation", None)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=None))
    monkeypatch.setattr(viewer, "library_tool_table_mm", {})
    monkeypatch.setattr(panel, "_tool_readiness_key", None)
    monkeypatch.setattr(panel, "_input_signature", None)
    monkeypatch.setattr(panel, "_alignment_key", None)
    monkeypatch.setattr(panel, "rest_context", None)
    monkeypatch.setattr(panel, "rest_identity", None)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(
        ProgramOperations, "motion_segments", property(lambda _: pytest.fail("UI refresh scanned program motion"))
    )
    panel.refresh_inputs()
    assert {number for number, _reason in panel._tool_issues} == {"1", "2"}
    panel.refresh_inputs()
    issues = panel.refresh_tool_readiness(program, program.operations[-1])
    assert {number for number, _reason in issues} == {"2"}
    viewer.library_tool_table_mm[2] = ToolDefinition(
        2, ToolType.FLAT_END_MILL, diameter=1, flute_length=2, stickout=5, shank_diameter=1
    )
    assert panel.refresh_tool_readiness(program, program.operations[-1]) == ()
    send.assert_not_called()


def test_change_review_and_snapshot_roundtrip_keep_exact_context_without_commands(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    panel = ws.simulation_panel
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    monkeypatch.setattr(
        viewer,
        "library_tool_table_mm",
        {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, flute_length=2, stickout=5)},
    )
    monkeypatch.setattr(viewer, "assembly_preview_binding", None)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(panel, "rest_stock", StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 2, 2)), 1))
    monkeypatch.setattr(panel, "rest_context", panel._context())
    monkeypatch.setattr(panel, "rest_identity", panel._identity())
    # A different earlier clearance capture must not replace the loaded residual
    # baseline in change review, even when that clearance capture is stale.
    previous_clearance = deepcopy(panel.rest_context)
    previous_clearance["tools"]["1"]["stickout"] = 4
    monkeypatch.setattr(panel, "clearance_context", previous_clearance)
    monkeypatch.setattr(panel, "clearance_stale", True)
    snapshot = tmp_path / "rest.cvstock"
    monkeypatch.setattr(ws, "choose_profile_file", lambda callback, **kw: callback(str(snapshot)))
    monkeypatch.setattr(ws, "choose_asset_file", lambda callback, **kw: callback(str(snapshot)))
    panel.save_stock()
    settle_transfer(panel)
    assert json.loads(snapshot.read_text())["schema"] == 2
    panel.load_stock()
    settle_transfer(panel)
    assert "Loaded rest stock" in panel.note.text
    assert digest_context(panel.rest_context) == panel.rest_identity[1]
    baseline_stock = panel.rest_stock
    viewer.library_tool_table_mm[1] = replace(viewer.library_tool_table_mm[1], stickout=7)
    panel.refresh_inputs()
    assert "previous residual is hidden" in panel.input_status.text
    popup = panel.review_changes()
    try:
        pump_frames(5)
        labels = [widget.text for widget in popup.content.walk() if hasattr(widget, "text")]
        assert any("Comparing: Residual result" in text for text in labels)
        assert any("1 affected operations" in text for text in labels)
        assert any("T1 stickout" in text and "Previous: 5" in text and "Current: 7" in text for text in labels)
        assert viewer._rest_stock_geometry is None
        assert panel.rest_stock is baseline_stock
        assert "older" in panel.note.text
    finally:
        popup.dismiss()
    popup = panel.review_changes("clearance")
    try:
        pump_frames(3)
        labels = [widget.text for widget in popup.content.walk() if hasattr(widget, "text")]
        assert any("Comparing: Captured clearance" in text for text in labels)
        assert any("T1 stickout" in text and "Previous: 4" in text and "Current: 7" in text for text in labels)
        selector = next(
            widget
            for widget in popup.content.walk()
            if tuple(getattr(widget, "values", ())) == ("Residual stock", "Captured clearance")
        )
        assert popup.width <= dp(700) and popup.height <= dp(550)
        popup.content.export_to_png(str(tmp_path / "change-review-baseline.png"))
        with monkeypatch.context() as patch:
            review = Mock()
            patch.setattr(panel, "review_changes", review)
            selector.text = "Residual stock"
            review.assert_called_once_with("residual")
    finally:
        popup.dismiss()
    old_bytes = snapshot.read_bytes()
    panel.save_stock()
    settle_transfer(panel)
    assert "recompute" in panel.note.text
    assert snapshot.read_bytes() == old_bytes
    panel.load_stock()
    settle_transfer(panel)
    assert "does not match current" in panel.note.text
    assert panel.rest_stock is baseline_stock
    snapshot.write_text(
        json.dumps({"schema": 1, "program_sha256": program.file_hash, "stock": baseline_stock.snapshot()})
    )
    panel.load_stock()
    settle_transfer(panel)
    assert "Legacy snapshot" in panel.note.text
    assert panel.rest_stock is baseline_stock
    if panel.artifact_transfer is not None:
        panel.artifact_transfer.dismiss()
    viewer.set_rest_stock_geometry(None)
    send.assert_not_called()


def test_loaded_mesh_is_byte_pinned_and_explicit_reload_is_transactional(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.addons import cad_identity
    from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_mesh

    viewer = kivy_app.root.desktop_workspace.machine.gcode_viewer
    original = dict(viewer.library_tool_table_mm)
    original_binding = viewer.assembly_preview_binding
    path = tmp_path / "cutter.json"
    data = {
        "schema": "carvera-tool-mesh-v1",
        "units": "mm",
        "axis": "+Z",
        "origin": "tip",
        "triangles": [0, 0, 0, 1, 0, 2, 0, 1, 2],
    }
    path.write_text(json.dumps(data))
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, geometry_path=str(path))
    try:
        viewer.load_tool_profiles({1: definition})
        loaded = viewer.library_tool_table_mm[1]
        assert loaded.geometry_sha256 == asset_digest(path)
        data["triangles"][3] = 2
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match="CAD bytes changed"):
            build_tool_mesh(loaded)
        viewer.load_tool_profiles({1: loaded})
        assert viewer.library_tool_table_mm[1].geometry_sha256 != loaded.geometry_sha256
        assert viewer.library_tool_table_mm[1].geometry_sha256 == asset_digest(path)
        baseline = viewer.library_tool_table_mm
        real_digest = cad_identity.asset_digest

        def mutate_after_fingerprint(path, *args):
            digest = real_digest(path, *args)
            if path:
                data["triangles"][3] = 3
                Path(path).write_text(json.dumps(data))
            return digest

        with monkeypatch.context() as patch:
            patch.setattr(cad_identity, "asset_digest", mutate_after_fingerprint)
            with pytest.raises(ValueError, match="CAD bytes changed"):
                viewer.load_tool_profiles({1: loaded})
        assert viewer.library_tool_table_mm is baseline
    finally:
        viewer.load_tool_profiles(original)
        viewer.assembly_preview_binding = original_binding


def test_stale_single_stock_review_preserves_array_owned_results(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    monkeypatch.setattr(ws.operation_panel, "program", ProgramOperations.from_text("G21 G90\nG1 X1 F100\n"))
    monkeypatch.setattr(panel, "rest_context", panel._context())
    monkeypatch.setattr(panel, "_input_signature", None)
    monkeypatch.setattr(viewer, "machine_setup", replace(viewer.machine_setup, stock_size_mm=(3, 3, 3)))
    retained = {"G54": object()}
    monkeypatch.setattr(viewer, "repeat_rest_geometries", retained)
    clear = Mock()
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", clear)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.refresh_inputs()
    assert "previous residual is hidden" in panel.input_status.text
    popup = panel.review_changes()
    try:
        pump_frames(5)
        assert "older" in panel.note.text
        assert viewer.repeat_rest_geometries is retained
        clear.assert_not_called()
        send.assert_not_called()
    finally:
        popup.dismiss()
    # Without an array result the stale single-stock geometry is still hidden.
    viewer.repeat_rest_geometries = None
    panel.hide_single_residual()
    clear.assert_called_once_with(None)
