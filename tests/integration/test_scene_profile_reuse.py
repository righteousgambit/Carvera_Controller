"""Machine-owned plate and vise references reuse verified CAD without reloading."""

import copy
import gzip
import json
from unittest.mock import Mock

from carveracontroller.addons.machine_simulation.profile import MachineProfile
from tests.unit.test_machine_profile import profile_data


def test_machine_selection_validates_once_and_restores_shared_components(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    previous_profile = ws.selected_machine_profile
    previous_cad = viewer.machine_profile
    previous_components = dict(viewer.machine_component_profiles)
    previous_setup = viewer.machine_setup
    data = profile_data()
    triangle = data["components"][0]["vertices"]
    for group in ("fixture", "workholding"):
        data["components"].append({"group": group, "vertices": list(triangle)})
    source = tmp_path / "saunders-test.json.gz"
    source.write_bytes(gzip.compress(json.dumps(data).encode()))
    loader = Mock(wraps=MachineProfile.load)
    send = Mock()
    monkeypatch.setattr(MachineProfile, "load", loader)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    try:
        ws.apply_machine_profile({"id": "reuse-scene", "name": "Reuse test", "cad_path": str(source)})
        loader.assert_called_once_with(source)
        profile = viewer.machine_profile
        assert viewer.machine_component_profiles["fixture"] is profile
        assert viewer.machine_component_profiles["workholding"] is profile
        assert viewer._machine_scene()["fixture"].indices == profile.groups["fixture"].indices
        baseline = copy.deepcopy(profile.geometry_json)
        ws.seed_scene_choices(ws.selected_machine_profile)
        loader.assert_called_once_with(source)
        assert viewer.machine_component_profiles["fixture"] is profile
        assert viewer.machine_component_profiles["workholding"] is profile
        assert profile.geometry_json == baseline
        send.assert_not_called()
    finally:
        if previous_profile:
            ws.apply_machine_profile(previous_profile)
        else:
            ws.selected_machine_profile = None
            viewer.machine_profile = previous_cad
            viewer.machine_component_profiles = previous_components
            viewer.machine_setup = previous_setup
            viewer._build_machine_scene()
