"""Threaded-hole planning UI: generated geometry, explicit tools and local staging."""

import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_hole_planning import HolePlanningPanel, parse_holes
from tests.integration.conftest import pump_frames


@pytest.fixture
def panel(kivy_app, monkeypatch):
    root = kivy_app.root
    definitions = {
        2: ToolDefinition(2, ToolType.DRILL, diameter=5.1054, flute_length=15, stickout=20, description="Pilot #7"),
        3: ToolDefinition(3, ToolType.THREAD_MILL, diameter=3, flute_length=2, stickout=12, description="Single form"),
        4: ToolDefinition(4, ToolType.FLAT_END_MILL, diameter=3, flute_length=12, stickout=15),
        5: ToolDefinition(5, ToolType.CHAMFER_MILL, diameter=8, tip_diameter=0, flute_length=8, stickout=15),
    }
    monkeypatch.setattr(root.gcode_viewer, "library_tool_table_mm", definitions)
    workspace = root.desktop_workspace
    monkeypatch.setattr(workspace, "choose_profile_file", Mock())
    item = HolePlanningPanel(workspace)
    item.holes.text = "10 20 8 6\n30 20 8 6"
    for kind, number in (("drill", 2), ("threadmill", 3)):
        item.tools[kind].text = next(
            title for title in item.tools[kind].values if item.tool_labels.get(title) == number
        )
    return item


def test_complete_threaded_plan_stages_local_preview_only(panel, monkeypatch, tmp_path):
    import carveracontroller.desktop_planning as planning

    stage = Mock(return_value=tmp_path / "preview.cnc")
    send = Mock()
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.generate()
    wait_for_plan(panel)
    assert panel.last_plan is not None, panel.note.text
    text = stage.call_args.args[1]
    assert "T2 M6" in text and "T3 M6" in text
    assert "G0 X30.00000 Y20.00000" in text
    assert "G3" in text and "G54" in text
    assert "2 holes" in panel.note.text
    send.assert_not_called()


def test_generated_holes_use_real_local_viewer_on_first_load(panel, monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    send = Mock()
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.generate()
    wait_for_plan(panel)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        pump_frames(2, sleep=0.02)
        machine = panel.workspace.machine
        if not machine.loading_file and machine.selected_file_line_count > 0:
            break
    assert panel.last_plan is not None, panel.note.text
    assert machine.selected_file_line_count > 0
    assert not machine.loading_file
    path = Path(machine.file_popup.local_rv.curr_selected_file)
    text = path.read_text()
    assert "T2 M6" in text and "T3 M6" in text
    from carveracontroller.machine.program_operations import ProgramOperations

    program = ProgramOperations.from_text(text)
    arcs = {i for i, line in enumerate(text.splitlines(), 1) if line.startswith(("G2 ", "G3 "))}
    assert arcs and not arcs.intersection(program.unresolved_motion_lines)
    assert arcs <= {segment.line_number for segment in program.motion_segments}
    send.assert_not_called()


def test_disclosure_reveals_heading_after_layout(panel, monkeypatch):
    from kivy.uix.scrollview import ScrollView

    scroll = ScrollView()
    scroll.add_widget(panel)
    reveal = Mock()
    monkeypatch.setattr(scroll, "scroll_to", reveal)
    panel.toggle_details()
    pump_frames(4)
    reveal.assert_called_once()
    assert reveal.call_args.args[0] is panel.header


def test_linked_hole_recipe_review_save_restore_and_other_tool_mismatch(panel, kivy_app, monkeypatch, tmp_path):
    from carveracontroller.desktop_components import Action, Field
    from carveracontroller.machine.desktop_profiles import ProfileStore
    from carveracontroller.machine.tool_custody import ToolCustodyStore
    from carveracontroller.machine.tool_process import review_hole_recipe

    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(panel, "workspace", ws)
    monkeypatch.setattr(ws, "hole_planning_panel", panel)
    profiles = ProfileStore(tmp_path / "profiles.json")
    design = profiles.save_tool(
        {
            "name": "Single form",
            "shape": "thread_mill",
            "diameter": 3,
            "flute_length": 2,
            "stickout": 40,
            "shank_diameter": 6.35,
        }
    )
    store = ToolCustodyStore(tmp_path / "custody.json")
    identity = store.create_assembly("Physical threadmill", "Holder", 12, design["id"])["id"]
    monkeypatch.setattr(ws, "profile_store", profiles)
    monkeypatch.setattr(ws.machine, "_tool_custody", store)
    path = tmp_path / "workflow.cvholes"
    path.write_text(json.dumps({"schema": "carvera-hole-recipe", "version": 1, "workflow": panel.workflow().to_dict()}))
    assembly = store.assembly(identity)
    recipe = review_hole_recipe(path, assembly, design, "threadmill")
    custody = ws.tool_comparison.custody
    custody.selected_id = identity
    custody.refresh(force=True)
    stage_popup = custody.review_hole_recipe()
    from carveracontroller.desktop_components import Choice

    stage_choice = next(widget for widget in stage_popup.content.walk() if isinstance(widget, Choice))
    choose = next(
        widget
        for widget in stage_popup.content.walk()
        if isinstance(widget, Action) and widget.text == "Choose recipe file"
    )
    assert choose.disabled
    stage_choice.text = "threadmill"
    assert not choose.disabled
    monkeypatch.setattr(ws, "choose_profile_file", Mock())
    choose.dispatch("on_release")
    assert ws.choose_profile_file.call_args.kwargs["extension"] == ".cvholes"
    popup = custody._show_recipe_review(assembly, design, recipe, "hole_recipe")
    note = next(widget for widget in popup.content.walk() if isinstance(widget, Field))
    save = next(
        widget for widget in popup.content.walk() if isinstance(widget, Action) and widget.text == "Save recipe link"
    )
    save.dispatch("on_release")
    assert not any(e["kind"] == "hole_recipe" for e in store.events)
    note.text = "6061 threaded attachment; preparation only"
    save.dispatch("on_release")
    assert save.disabled
    for _ in range(50):
        pump_frames(2)
        if any(e["kind"] == "hole_recipe" for e in store.events):
            break
    pump_frames(3)
    reloaded = ToolCustodyStore(store.path)
    assert reloaded.events[-1]["recipe"]["stage"] == "threadmill"
    assert reloaded.events[-1]["recipe"]["sha256"] == recipe["sha256"]
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.holes.text = "1 2 3"
    custody.restore_recipe()
    for _ in range(50):
        pump_frames(2)
        if "Recipe restored" in custody.result.text:
            break
    assert "10 20 8 6" in panel.holes.text
    assert panel.details_open and ws.active_section == "Setup"
    assert ws.setup_tasks.active == "Holes"
    # The selected assembly still matches, but a different required stage does not.
    ws.machine.gcode_viewer.library_tool_table_mm[2] = replace(
        ws.machine.gcode_viewer.library_tool_table_mm[2], diameter=4
    )
    panel.holes.text = "1 2 3"
    custody.restore_recipe()
    for _ in range(50):
        pump_frames(2)
        if "T2: recipe geometry differs" in custody.result.text:
            break
    assert "T2: recipe geometry differs" in custody.result.text
    assert panel.holes.text == "1 2 3"
    send.assert_not_called()


def test_loaded_tool_choices_follow_shape_and_missing_dimensions_reject(panel):
    assert all("T3" not in text for text in panel.tools["drill"].values)
    definition = panel.workspace.machine.gcode_viewer.library_tool_table_mm[2]
    panel.workspace.machine.gcode_viewer.library_tool_table_mm[2] = replace(definition, stickout=None)
    with pytest.raises(ValueError, match="exposed stickout"):
        panel.workflow()


def test_invalid_rows_and_nonfinite_inputs_have_specific_errors(panel):
    with pytest.raises(ValueError, match="Hole row 2"):
        parse_holes("1 2 3\n4 5 nan")
    with pytest.raises(ValueError, match="Hole row 1"):
        parse_holes("1 2")
    panel.inputs["radial_passes"].text = "1.5"
    with pytest.raises(ValueError, match="whole number.*radial passes"):
        panel.workflow()
    panel.inputs["radial_passes"].text = "2"
    panel.inputs["drill_angle"].text = "invalid"
    with pytest.raises(ValueError, match="included tip angle"):
        panel.workflow()


def test_optional_stage_requires_pointed_geometry_and_depth_clearance(panel):
    title = next(text for text in panel.tools["chamfer"].values if panel.tool_labels.get(text) == 5)
    panel.tools["chamfer"].text = title
    plan = panel.workflow().plan()
    assert [stage.name for stage in plan.stages] == ["drill", "chamfer", "threadmill"]
    profile = panel.workspace.machine.gcode_viewer.library_tool_table_mm[5]
    panel.workspace.machine.gcode_viewer.library_tool_table_mm[5] = replace(profile, tip_diameter=0.5)
    with pytest.raises(ValueError, match="zero tip diameter"):
        panel.workflow()
    panel.tools["chamfer"].text = "Skip"
    panel.inputs["floor_z_mm"].text = "-8"
    with pytest.raises(ValueError, match="floor"):
        panel.workflow()


def test_multiform_geometry_is_not_silently_single_form(panel):
    panel.thread_form.text = "Pitch-specific multi-form"
    with pytest.raises(ValueError, match="multi-form profile"):
        panel.workflow()
    panel.thread_form.text = "Single form"
    profile = panel.workspace.machine.gcode_viewer.library_tool_table_mm[3]
    panel.workspace.machine.gcode_viewer.library_tool_table_mm[3] = replace(profile, thread_pitch=1.27)
    with pytest.raises(ValueError, match="pitch-specific profile"):
        panel.workflow()


def test_recipe_roundtrip_checks_current_tool_geometry(panel, tmp_path):
    recipe = tmp_path / "holes.cvholes"
    panel.save()
    callback = panel.workspace.choose_profile_file.call_args.args[0]
    callback(recipe)
    data = json.loads(recipe.read_text())
    assert data["workflow"]["tools"]["drill"]["diameter_mm"] == pytest.approx(5.1054)
    panel.holes.text = "1 1 3 2"
    panel.load_path(recipe)
    assert "geometry matched" in panel.note.text
    assert len(panel.workflow().holes) == 2
    profile = panel.workspace.machine.gcode_viewer.library_tool_table_mm[2]
    panel.workspace.machine.gcode_viewer.library_tool_table_mm[2] = replace(profile, flute_length=14)
    with pytest.raises(ValueError, match="differs from current tool profiles"):
        panel.workflow()
    panel.new_recipe()
    assert panel.workflow().tools["drill"].cutting_length_mm == 14


@pytest.mark.parametrize("payload", ['{"schema":"carvera-hole-recipe","version":1,"workflow":null}', "[]", "42"])
def test_malformed_recipe_cannot_stage_or_send(panel, tmp_path, monkeypatch, payload):
    source = tmp_path / "bad.cvholes"
    source.write_text(payload)
    send = Mock()
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.load_path(source)
    assert "Recipe not ready" in panel.note.text
    send.assert_not_called()


def test_disclosure_and_narrow_layout_keep_inputs_accessible(panel):
    assert panel.content.parent is None
    panel.toggle_details()
    panel.width = 350
    pump_frames(3)
    grids = [widget for widget in panel.content.children if hasattr(widget, "max_cols")]
    assert grids
    assert all(grid.cols == 1 for grid in grids)
    assert panel.content.parent is panel
    assert panel.content.height > panel.holes.height
    panel.toggle_details()
    pump_frames(2)
    assert panel.content.parent is None


def test_changed_recipe_geometry_does_not_partially_replace_inputs(panel, tmp_path):
    path = tmp_path / "changed.cvholes"
    panel.save()
    panel.workspace.choose_profile_file.call_args.args[0](path)
    original = panel.workspace.machine.gcode_viewer.library_tool_table_mm[2]
    panel.workspace.machine.gcode_viewer.library_tool_table_mm[2] = replace(original, stickout=21)
    panel.holes.text = "7 7 4 2"
    panel.load_path(path)
    assert "recipe geometry differs" in panel.note.text
    assert panel.holes.text == "7 7 4 2"
    assert panel.recipe_tools is None


def wait_for_plan(panel):
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(1, sleep=0.005)
    assert not panel.running


def test_background_plan_rejects_inputs_changed_during_calculation(panel, monkeypatch, tmp_path):
    import carveracontroller.desktop_planning as planning
    from carveracontroller.machine.hole_planning import HoleWorkflow

    entered, release = threading.Event(), threading.Event()
    original = HoleWorkflow.plan

    def delayed(workflow):
        entered.set()
        assert release.wait(3)
        return original(workflow)

    stage = Mock(return_value=tmp_path / "ignored.cnc")
    monkeypatch.setattr(HoleWorkflow, "plan", delayed)
    monkeypatch.setattr(planning, "stage_program", stage)
    panel.generate()
    assert entered.wait(2)
    panel.holes.text = "10 20 7 5"
    release.set()
    wait_for_plan(panel)
    stage.assert_not_called()
    assert "changed during calculation" in panel.note.text


def test_save_recipe_exclusive_create_preserves_existing_file(panel, tmp_path):
    path = tmp_path / "existing.cvholes"
    path.write_text("original")
    panel.save()
    panel.workspace.choose_profile_file.call_args.args[0](path)
    assert path.read_text() == "original"
    assert "File exists" in panel.note.text


def test_multiform_loaded_profile_preview_and_recipe_restoration(panel, monkeypatch, tmp_path):
    import carveracontroller.desktop_planning as planning

    profile = panel.workspace.machine.gcode_viewer.library_tool_table_mm[3]
    table = panel.workspace.machine.gcode_viewer.library_tool_table_mm
    table[3] = replace(profile, thread_pitch=1.27, flute_length=8, thread_teeth=6, thread_tip_offset=0.25)
    panel.thread_form.text = "Pitch-specific multi-form"
    workflow = panel.workflow()
    stage = Mock(return_value=tmp_path / "multi.cnc")
    send = Mock()
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.generate()
    wait_for_plan(panel)
    assert panel.last_plan is not None, panel.note.text
    assert sum(line.startswith("G3 ") for line in stage.call_args.args[1].splitlines()) == 4
    panel.new_recipe()
    panel.thread_form.text = "Single form"
    panel.restore_reviewed_recipe(workflow)
    assert panel.thread_form.text == "Pitch-specific multi-form"
    assert panel.workflow() == workflow
    before = panel.holes.text
    table[3] = replace(table[3], thread_teeth=5)
    with pytest.raises(ValueError, match="geometry differs"):
        panel.restore_reviewed_recipe(workflow)
    assert panel.holes.text == before
    send.assert_not_called()


@pytest.mark.parametrize("width", [360, 760])
def test_multiform_summary_wraps_and_explains_axial_reference(panel, width):
    profile = panel.workspace.machine.gcode_viewer.library_tool_table_mm[3]
    panel.workspace.machine.gcode_viewer.library_tool_table_mm[3] = replace(
        profile, thread_pitch=1.27, flute_length=8, thread_teeth=6, thread_tip_offset=0.25
    )
    panel.thread_form.text = "Pitch-specific multi-form"
    panel.width = width
    panel.toggle_details()
    pump_frames(8)
    assert "6 complete teeth" in panel.cutter_summary.text
    assert "One 1.27 mm axial turn" in panel.cutter_summary.text
    assert "0.25 mm below" in panel.cutter_summary.text
    assert panel.cutter_summary.height >= panel.cutter_summary.texture_size[1]
    assert panel.cutter_summary.width <= width
    from kivy.metrics import dp

    assert panel.cutter_summary.height < dp(300)
    settled_height = panel.cutter_summary.height
    pump_frames(12)
    assert panel.cutter_summary.height == settled_height


@pytest.fixture
def deferred_hole_worker(monkeypatch):
    from carveracontroller import desktop_hole_planning

    workers = []
    original_thread = threading.Thread

    class DeferredThread:
        def __init__(self, target, **kwargs):
            self.target = target
            self.kwargs = kwargs

        def start(self):
            if self.kwargs.get("name") == "hole-plan-preview":
                workers.append(self.target)
            else:
                original_thread(target=self.target, **self.kwargs).start()

    monkeypatch.setattr(desktop_hole_planning.threading, "Thread", DeferredThread)
    return workers


@pytest.mark.parametrize("change", ["stock", "workholding", "machine", "local", "remote", "reload", "cutter"])
def test_pending_holes_cannot_replace_preview_under_changed_context(
    panel, deferred_hole_worker, monkeypatch, tmp_path, change
):
    ws = panel.workspace
    viewer = ws.machine.gcode_viewer
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(ws, "selected_machine_profile", {"id": "holes-machine"})
    monkeypatch.setattr(ws.app, "selected_local_filename", "original.cnc")
    monkeypatch.setattr(ws.app, "selected_remote_filename", "")
    preview, send = Mock(), Mock()
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel.generate()
    assert panel.running and len(deferred_hole_worker) == 1
    if change == "stock":
        monkeypatch.setattr(
            viewer,
            "machine_setup",
            replace(viewer.machine_setup, stock_origin_mm=tuple(v + 2 for v in viewer.machine_setup.stock_origin_mm)),
        )
    elif change == "workholding":
        monkeypatch.setattr(viewer, "workholding_offset_mm", tuple(v + 10 for v in viewer.workholding_offset_mm))
    elif change == "machine":
        ws.selected_machine_profile = {"id": "another-machine"}
    elif change == "local":
        ws.app.selected_local_filename = "chosen-after-generation.cnc"
    elif change == "remote":
        ws.app.selected_remote_filename = "/sd/new.cnc"
    elif change == "reload":
        monkeypatch.setattr(ws.machine, "program_preview_generation", ws.machine.program_preview_generation + 1)
    else:
        viewer.library_tool_table_mm[2] = replace(viewer.library_tool_table_mm[2], stickout=21)
    deferred_hole_worker[0]()
    pump_frames(3)
    assert not panel.running
    assert "changed during calculation" in panel.note.text
    assert not (tmp_path / ".carvera" / "jobs").exists()
    preview.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("phase", ["plan", "gcode"])
@pytest.mark.parametrize("failure", [ValueError(), MemoryError(), RuntimeError("injected")])
def test_hole_worker_errors_release_busy_and_allow_retry(
    panel, deferred_hole_worker, monkeypatch, tmp_path, caplog, phase, failure
):
    import carveracontroller.desktop_planning as planning
    from carveracontroller.machine.hole_planning import HolePlan, HoleWorkflow

    owner = HoleWorkflow if phase == "plan" else HolePlan
    original = getattr(owner, phase)
    attempts = []

    def fail_once(value):
        attempts.append(True)
        if len(attempts) == 1:
            raise failure
        return original(value)

    monkeypatch.setattr(owner, phase, fail_once)
    stage, send = Mock(return_value=tmp_path / "preview.cnc"), Mock()
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.generate()
    deferred_hole_worker[0]()
    pump_frames(3)
    assert not panel.running and panel.last_plan is None
    assert type(failure).__name__ in panel.note.text
    stage.assert_not_called()
    if not isinstance(failure, ValueError):
        assert any(record.exc_info for record in caplog.records if record.message == "Hole calculation failed")
    panel.generate()
    deferred_hole_worker[1]()
    pump_frames(3)
    assert not panel.running and panel.last_plan is not None, panel.note.text
    stage.assert_called_once()
    send.assert_not_called()


def test_hole_worker_start_failure_can_retry(panel, monkeypatch, tmp_path):
    import carveracontroller.desktop_hole_planning as holes
    import carveracontroller.desktop_planning as planning

    workers, attempts = [], []
    original_thread = threading.Thread

    class RetryThread:
        def __init__(self, target, **kwargs):
            self.target = target
            self.kwargs = kwargs

        def start(self):
            if self.kwargs.get("name") != "hole-plan-preview":
                original_thread(target=self.target, **self.kwargs).start()
                return
            attempts.append(True)
            if len(attempts) == 1:
                raise RuntimeError("thread unavailable")
            workers.append(self.target)

    stage, send = Mock(return_value=tmp_path / "preview.cnc"), Mock()
    monkeypatch.setattr(holes.threading, "Thread", RetryThread)
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.generate()
    assert not panel.running and "Could not start calculation" in panel.note.text
    stage.assert_not_called()
    panel.generate()
    workers[0]()
    pump_frames(3)
    assert not panel.running and panel.last_plan is not None, panel.note.text
    stage.assert_called_once()
    send.assert_not_called()


def test_new_recipe_supersedes_pending_holes(panel, deferred_hole_worker, monkeypatch):
    import carveracontroller.desktop_planning as planning

    stage, send = Mock(), Mock()
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    panel.generate()
    panel.new_recipe()
    deferred_hole_worker[0]()
    pump_frames(3)
    assert not panel.running and panel.last_plan is None
    assert "New recipe" in panel.note.text
    stage.assert_not_called()
    send.assert_not_called()


def test_view_changes_preserve_pending_holes_and_encoding_stays_off_ui(
    panel, deferred_hole_worker, monkeypatch, tmp_path
):
    import carveracontroller.desktop_planning as planning
    from carveracontroller.machine.hole_planning import HolePlan

    viewer = panel.workspace.machine.gcode_viewer
    stage, send = Mock(return_value=tmp_path / "preview.cnc"), Mock()
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(panel.workspace.machine.controller, "executeCommand", send)
    encoding, active = [], [False]
    original = HolePlan.gcode

    def encode(plan):
        encoding.append(active[0])
        return original(plan)

    monkeypatch.setattr(HolePlan, "gcode", encode)
    panel.generate()
    monkeypatch.setattr(viewer, "cutter_visible", not viewer.cutter_visible)
    monkeypatch.setattr(viewer, "m_zoom", viewer.m_zoom * 1.2)
    active[0] = True
    deferred_hole_worker[0]()
    active[0] = False
    assert encoding == [True]
    stage.assert_not_called()
    pump_frames(3)
    assert not panel.running and panel.last_plan is not None, panel.note.text
    stage.assert_called_once()
    assert encoding == [True]
    send.assert_not_called()
