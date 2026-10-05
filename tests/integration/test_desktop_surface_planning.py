"""Facing workflow stages explicit tool programs without sending machine commands."""

from pathlib import Path
from unittest.mock import Mock

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_planning import stage_program
from carveracontroller.machine.surface_planning import HeightMap, HeightSample
from tests.integration.conftest import pump_frames


def configure(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.surface_planning_panel
    workspace.machine.gcode_viewer.library_tool_table_mm = {
        2: ToolDefinition(
            2, ToolType.FLAT_END_MILL, diameter=6.35, flute_length=15, stickout=25, description="Aluminum"
        )
    }
    panel.refresh_tools()
    panel.boundary.text = "0 0\n10 0\n10 8\n0 8"
    return workspace, panel


def test_generated_facing_selects_tool_and_opens_local_preview(kivy_app, monkeypatch, tmp_path):
    workspace, panel = configure(kivy_app)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    send = Mock()
    preview = Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    monkeypatch.setattr(workspace.machine, "view_local_file", preview)
    # A fresh machine must expose loading state before its first file load.
    assert workspace.machine.loading_file is False
    panel.generate()
    for _ in range(30):
        pump_frames(2)
        if not panel.running:
            break
    preview.assert_called_once()
    path = Path(workspace.machine.file_popup.local_rv.curr_selected_file)
    text = path.read_text()
    assert "G54\nT2 M6\n" in text
    assert "G1 Z-0.20000" in text
    assert "M3 S12000" in text
    assert panel.plan is not None
    send.assert_not_called()


def test_generation_requires_actual_loaded_dimensions(kivy_app, monkeypatch):
    workspace, panel = configure(kivy_app)
    preview = Mock()
    monkeypatch.setattr(workspace.machine, "view_local_file", preview)
    workspace.machine.gcode_viewer.library_tool_table_mm[2].stickout = None
    panel.generate()
    assert "stickout" in panel.note.text
    preview.assert_not_called()


def test_surface_provenance_interpolation_and_wcs_are_distinct(kivy_app):
    _workspace, panel = configure(kivy_app)
    panel.samples.text = "0 0 1 .01\n10 0 2 .01\n0 8 3 .01"
    panel.source.text = "Indicator 2358A-10"
    panel.timestamp.text = "2026-10-03T20:00:00Z"
    panel.review_map()
    assert len(panel.height_map.samples) == 3
    panel.query_x.text, panel.query_y.text = "2", "2"
    panel.query_height()
    assert "interpolated" in panel.map_note.text
    panel.use_measured_top()
    assert float(panel.fields["top_z_mm"].text) == pytest.approx(3.01)
    panel.wcs.text = "G55"
    panel.use_measured_top()
    assert "work offset must match" in panel.note.text


def test_loaded_map_preserves_sources_exclusions_and_no_extrapolation(kivy_app, monkeypatch, tmp_path):
    workspace, panel = configure(kivy_app)
    path = tmp_path / "measurements.cvmap"
    heights = HeightMap(
        ((0, 0), (10, 0), (10, 8), (0, 8)),
        [HeightSample(0, 0, 1, "probe-A", "2026-10-03T20:00:00Z")],
        exclusions=(((4, 4), (5, 4), (5, 5), (4, 5)),),
    )
    heights.save(path)
    monkeypatch.setattr(workspace, "choose_profile_file", lambda callback, **_kw: callback(str(path)))
    panel.load_map()
    assert panel.height_map.to_dict() == heights.to_dict()
    panel.query_x.text, panel.query_y.text = "4.5", "4.5"
    panel.query_height()
    assert "No supported measurement" in panel.map_note.text


def test_recipe_roundtrip_rejects_changed_cutter(kivy_app, monkeypatch, tmp_path):
    workspace, panel = configure(kivy_app)
    path = tmp_path / "face.cvface"
    monkeypatch.setattr(workspace, "choose_profile_file", lambda callback, **_kw: callback(str(path)))
    panel.save_recipe()
    panel.fields["final_z_mm"].text = "-4"
    panel.load_recipe()
    assert panel.fields["final_z_mm"].text == "-0.2"
    workspace.machine.gcode_viewer.library_tool_table_mm[2].diameter = 5
    panel.load_recipe()
    assert "matching cutter" in panel.note.text


def test_passport_recipe_restore_is_content_bound_and_command_free(kivy_app, monkeypatch, tmp_path):
    from carveracontroller.machine.desktop_profiles import ProfileStore
    from carveracontroller.machine.tool_custody import ToolCustodyStore
    from carveracontroller.machine.tool_process import review_facing_recipe

    workspace, panel = configure(kivy_app)
    profiles = ProfileStore(tmp_path / "profiles.json")
    design = profiles.save_tool(
        {
            "name": "Flat",
            "number": 2,
            "diameter": 6.35,
            "shank_diameter": 6.35,
            "flute_length": 15,
            "length": 75,
            "stickout": 40,
        }
    )
    store = ToolCustodyStore(tmp_path / "custody.json")
    identity = store.create_assembly("Physical flat", "Holder", 25, design["id"])["id"]
    assembly = store.assembly(identity)
    monkeypatch.setattr(workspace, "profile_store", profiles)
    monkeypatch.setattr(workspace.machine, "_tool_custody", store)
    path = tmp_path / "face.cvface"
    monkeypatch.setattr(workspace, "choose_profile_file", lambda callback, **_kw: callback(str(path)))
    panel.save_recipe()
    recipe = review_facing_recipe(path, assembly, design)
    custody = workspace.tool_comparison.custody
    custody.selected_id = identity
    custody.refresh(force=True)
    popup = custody._show_recipe_review(assembly, design, recipe)
    from carveracontroller.desktop_components import Action, Field

    note = next(widget for widget in popup.content.walk() if isinstance(widget, Field))
    save = next(
        widget for widget in popup.content.walk() if isinstance(widget, Action) and widget.text == "Save recipe link"
    )
    save.dispatch("on_release")
    assert not any(event["kind"] == "facing_recipe" for event in store.events)
    note.text = "6061 preparation"
    save.dispatch("on_release")
    assert save.disabled
    for _ in range(40):
        pump_frames(2)
        if any(event["kind"] == "facing_recipe" for event in store.events):
            break
    pump_frames(3)
    restored_store = ToolCustodyStore(store.path)
    assert restored_store.events[-1]["recipe"]["sha256"] == recipe["sha256"]
    assert restored_store.events[-1]["note"] == "6061 preparation"
    custody.passport_section.text = "Recipes"
    assert "Current definition" in custody.summary.text
    assert custody.recipe_choice.parent is custody.passport_content
    assert custody.selected_recipe_id == restored_store.events[-1]["id"]
    send = Mock()
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", send)
    panel.fields["final_z_mm"].text = "-4"
    custody.restore_recipe()
    for _ in range(40):
        pump_frames(2)
        if "restored for local review" in custody.result.text:
            break
    assert panel.fields["final_z_mm"].text == "-0.2"
    assert workspace.active_section == "Setup"
    assert panel.expanded
    source_before = path.read_bytes()
    path.write_bytes(source_before + b"\n")
    panel.fields["final_z_mm"].text = "-3"
    custody.restore_recipe()
    for _ in range(40):
        pump_frames(2)
        if "file changed" in custody.result.text:
            break
    assert "file changed" in custody.result.text
    assert panel.fields["final_z_mm"].text == "-3"
    send.assert_not_called()
    custody.passport_section.text = "Overview"
    assert custody.recipe_choice.parent is None


@pytest.mark.parametrize(
    "state,playing,loading",
    [("Run", True, False), ("Alarm", False, False), ("Idle", True, False), ("Idle", False, True)],
)
def test_staging_refuses_active_execution_or_loading(kivy_app, monkeypatch, tmp_path, state, playing, loading):
    workspace = kivy_app.root.desktop_workspace
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    kivy_app.state, kivy_app.playing = state, playing
    workspace.machine.loading_file = loading
    try:
        with pytest.raises(ValueError):
            stage_program(workspace, "G21\nM2\n", "test")
        assert not (tmp_path / ".carvera").exists()
    finally:
        kivy_app.state, kivy_app.playing = "N/A", False
        workspace.machine.loading_file = False


def test_empty_operation_card_does_not_reserve_unused_area(kivy_app):
    items = kivy_app.root.desktop_workspace.operation_panel.items
    items.clear_widgets()
    pump_frames(4)
    assert items.height == 0


def test_surface_recipe_restores_measurements_and_clears_previous_map(kivy_app, monkeypatch, tmp_path):
    workspace, panel = configure(kivy_app)
    path = tmp_path / "mapped.cvface"
    panel.samples.text = "0 0 1 .01\n10 0 2 .02\n0 8 3 .03"
    panel.source.text = "Indicator 2358A-10"
    panel.timestamp.text = "2026-10-03T20:00:00Z"
    panel.review_map()
    expected = panel.height_map.to_dict()
    monkeypatch.setattr(workspace, "choose_profile_file", lambda callback, **_kw: callback(str(path)))
    panel.save_recipe()
    panel.samples.text, panel.source.text, panel.timestamp.text = "", "", ""
    panel.load_recipe()
    assert panel.height_map.to_dict() == expected
    assert len(panel.samples.text.splitlines()) == 3
    assert panel.source.text == "Indicator 2358A-10"
    assert panel.timestamp.text == "2026-10-03T20:00:00Z"
    assert panel.plot.height > 0
    panel._restore_map_controls(None)
    assert panel.samples.text == panel.source.text == panel.timestamp.text == ""
    assert panel.plot.height == 0


def test_planning_disclosure_keeps_heading_visible_after_expansion(kivy_app):
    workspace = kivy_app.root.desktop_workspace
    panel = workspace.surface_planning_panel
    workspace.select("Setup")
    scroll = workspace.setup_page.parent
    scroll.scroll_y = 0
    if panel.expanded:
        panel.toggle()
    panel.toggle()
    pump_frames(8)
    heading_top = panel.header.to_window(panel.header.x, panel.header.top)[1]
    viewport_top = scroll.to_window(scroll.x, scroll.top)[1]
    assert heading_top <= viewport_top + 1
    assert heading_top > viewport_top - panel.header.height * 2
    panel.toggle()
    pump_frames(4)
