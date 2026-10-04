"""Local selection must not rebuild or replace loaded CAD buffers."""

import json
import os
import time
from pathlib import Path
from unittest.mock import Mock

from tests.integration.conftest import pump_frames


def test_selection_and_tabs_reuse_cad_buffers(kivy_app, monkeypatch):
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from carveracontroller.machine.scene_inspection import GEOMETRY_GROUPS

    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    path = os.environ.get("CARVERA_TIMING_CAD")
    original = viewer.machine_profile
    original_selected = viewer.inspected_component
    original_section = ws.active_section
    original_profile = ws.selected_machine_profile
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        if path:
            viewer.machine_profile = MachineProfile.load(Path(path))
        ws.selected_machine_profile = {"id": "tab-render-test"}
        viewer.set_machine_visible(True)
        viewer._build_machine_scene()
        pump_frames(3)
        geometry = viewer._inspection_geometry
        meshes = {name: tuple(ctx.children) for name, ctx in viewer._machine_contexts.items()}
        rebuild = Mock(side_effect=AssertionError("Selection must not rebuild CAD"))
        with monkeypatch.context() as patch:
            patch.setattr(viewer, "_build_machine_scene", rebuild)
            results = []
            for key in (None, "stock", "fixture", "workholding", None):
                started = time.perf_counter()
                viewer.set_inspected_component(key)
                results.append({"selection": key, "callback_seconds": time.perf_counter() - started})
                selected = GEOMETRY_GROUPS.get(key, ())
                for name, context in viewer._machine_contexts.items():
                    assert context["inspection_highlight"] == float(name in selected)
                assert viewer.pointermesh["inspection_highlight"] == 0.0
                pump_frames(2)
            for key, button in ws.tab_buttons.items():
                started = time.perf_counter()
                button.dispatch("on_release")
                results.append({"tab": key, "callback_seconds": time.perf_counter() - started})
                assert ws.active_section == ("Job" if key == "Preview" else key)
                pump_frames(2)
            rebuild.assert_not_called()
            assert viewer._inspection_geometry is geometry
            assert all(tuple(ctx.children) == meshes[name] for name, ctx in viewer._machine_contexts.items())
            send.assert_not_called()
            if os.environ.get("CARVERA_TIMING_OUTPUT"):
                Path(os.environ["CARVERA_TIMING_OUTPUT"]).write_text(json.dumps(results, indent=2))
    finally:
        viewer.machine_profile = original
        ws.selected_machine_profile = original_profile
        viewer.set_inspected_component(original_selected)
        viewer._build_machine_scene()
        ws.select(original_section, record_navigation=False)
        ws.navigation.reset()
