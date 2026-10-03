"""Profile selection restores saved visual setup without CNC commands."""

import time
from unittest.mock import Mock

from carveracontroller.desktop_scene import SceneSetupStore, capture_scene_setup, restore_scene_geometry


def test_profile_switch_and_restart_restore_stock_placement_and_visibility(kivy_app, tmp_path, monkeypatch):
    workspace = kivy_app.root.desktop_workspace
    viewer = kivy_app.root.gcode_viewer
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    rebuild = Mock(wraps=viewer._build_machine_scene)
    monkeypatch.setattr(viewer, "_build_machine_scene", rebuild)

    def seed(profile):
        rebuild.reset_mock()
        began = time.perf_counter()
        workspace.seed_scene_choices(profile)
        elapsed = time.perf_counter() - began
        assert rebuild.call_count <= 1
        print(f"Scene seed {profile and profile['id']}: {elapsed:.3f}s, {rebuild.call_count} full rebuilds")

    store = workspace.scene_setup_store
    previous_path, previous_data, previous_error = store.path, store.data, store.load_error
    previous_profile = workspace.selected_machine_profile
    previous_setup = capture_scene_setup(workspace)
    store.path, store.data, store.load_error = tmp_path / "scene-setups.json", {}, None
    first, second = {"id": "first", "cad_path": ""}, {"id": "second", "cad_path": ""}
    try:
        workspace.selected_machine_profile = first
        seed(first)
        viewer.configure_workholding((-77.9376, -45, 0), 90, -74.5953)
        viewer.configure_machine(
            work_offset_mm=(-180, -120, -110),
            stock_size_mm=(127, 69.4182, 50.8762),
            stock_origin_mm=(-118.6, -94.7091, -0.36788),
        )
        workspace.component_choices["stock"].text = "Current stock"
        workspace.component_checks["outer"].active = False
        workspace.component_checks["atc"].active = False
        assert workspace.save_scene_setup()
        expected = capture_scene_setup(workspace)

        workspace.selected_machine_profile = second
        seed(second)
        assert viewer.machine_setup.stock_size_mm is None
        assert workspace.component_checks["outer"].active
        assert workspace.component_checks["atc"].active
        viewer.configure_machine(stock_size_mm=(20, 30, 40))
        workspace.component_choices["stock"].text = "Current stock"
        assert workspace.save_scene_setup()

        # Reconstruct state from disk as startup does, then seed the chosen profile.
        restarted = SceneSetupStore(store.path)
        store.data = restarted.data
        workspace.selected_machine_profile = first
        seed(first)
        assert capture_scene_setup(workspace) == expected
        assert viewer.machine_setup.stock_size_mm == (127, 69.4182, 50.8762)
        assert viewer.workholding_rotation_deg == 90
        assert not viewer.machine_group_visibility["fixed"]
        assert not viewer.machine_group_visibility["atc"]
        assert store.get("second")["stock_size_mm"] == [20, 30, 40]
        send.assert_not_called()
    finally:
        workspace.selected_machine_profile = previous_profile
        workspace.seed_scene_choices(previous_profile)
        for kind, value in previous_setup["choices"].items():
            workspace.component_choices[kind].text = value
        workspace.scene_scope.text = "Full machine" if previous_setup["scope"] == "machine" else "Work area"
        for kind, visible in previous_setup["visibility"].items():
            workspace.component_checks[kind].active = visible
        restore_scene_geometry(workspace, previous_setup)
        store.path, store.data, store.load_error = previous_path, previous_data, previous_error
