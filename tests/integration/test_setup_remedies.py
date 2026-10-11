import time
from dataclasses import replace
from unittest.mock import Mock

import pytest

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    Vec3,
)
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.desktop_remedies import RemedyPanel
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_preview import simulation_tools

from .conftest import pump_frames


def panel_for(kivy_app, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    simulation, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    monkeypatch.setattr(
        ws.operation_panel,
        "program",
        ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X4\n"),
    )
    first = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=3, flute_length=1, stickout=10)
    alternate = replace(first, number=2, flute_length=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: first, 2: alternate})
    path = (SimulationSegment(Vec3(0, 0, 0), Vec3(4, 0, 0), "1", line=5),)
    scene = CollisionScene((CollisionObstacle("vise", AABB(Vec3(1, -1, 2), Vec3(2, 1, 3))),))
    stock = StockVolume(AABB(Vec3(0, -1, 0), Vec3(4, 1, 1)), 0.5)
    monkeypatch.setattr(simulation, "clearance_inputs", (path, simulation_tools({1: first}, {"1"}), scene, stock))
    monkeypatch.setattr(simulation, "clearance_identity", simulation._identity())
    monkeypatch.setattr(simulation, "clearance_stale", False)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    panel = RemedyPanel(simulation, 5, "shank", "vise")
    panel.alternative.text = "T2"
    return panel, viewer, send


def wait(panel):
    deadline = time.monotonic() + 10
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running


def test_tool_and_obstacle_comparisons_are_local_and_draft_bound(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    original = panel.inputs[3].snapshot()
    panel.start()
    wait(panel)
    assert panel.comparison is not None
    assert "Selected contact: absent in candidate" in panel.result.text
    assert "captured T2 geometry" in panel.result.text
    assert "Holder geometry missing" in panel.result.text
    panel.mode.text = "Shift obstacle bounds"
    assert panel.comparison is None
    panel.shifts[1].text = "10 mm"
    panel.start()
    wait(panel)
    assert panel.comparison is not None
    assert "Selected contact: absent in candidate" in panel.result.text
    assert panel.inputs[3].snapshot() == original
    assert viewer.library_tool_table_mm[1].flute_length == 1
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_alternative_outside_program_identity_cannot_change_unnoticed(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    viewer.library_tool_table_mm[2] = replace(viewer.library_tool_table_mm[2], stickout=11)
    assert panel.current()  # Program only references T1; alternative needs its own guard.
    panel.start()
    assert not panel.running
    assert panel.comparison is None
    assert "Alternative definition changed" in panel.result.text
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_changed_draft_or_setup_rejects_worker_result(kivy_app, monkeypatch):
    panel, _, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    panel.alternative.text = "T1"
    wait(panel)
    assert panel.comparison is None
    assert "Draft changed during comparison" in panel.result.text
    panel.alternative.text = "T2"
    panel.start()
    monkeypatch.setattr(panel.simulation, "clearance_stale", True)
    wait(panel)
    assert panel.comparison is None
    assert "Historical result was not accepted" in panel.result.text
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_alternative_change_while_worker_runs_is_rejected(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    viewer.library_tool_table_mm[2] = replace(viewer.library_tool_table_mm[2], flute_length=6)
    wait(panel)
    assert panel.current()
    assert panel.comparison is None
    assert "Alternative geometry changed during comparison" in panel.result.text
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_actual_asset_identity_detects_same_path_replacement(tmp_path):
    from carveracontroller.desktop_remedies import asset_identity

    asset = tmp_path / "cutter.json"
    asset.write_bytes(b"first bytes")
    definition = ToolDefinition(2, geometry_path=str(asset))
    captured = asset_identity(definition)
    asset.write_bytes(b"other bytes")
    assert asset_identity(definition) != captured


def test_missing_choices_explain_required_input_without_starting_worker(kivy_app, monkeypatch):
    panel, _, send = panel_for(kivy_app, monkeypatch)
    panel.alternative.text = "Select loaded tool geometry"
    panel.start()
    assert "Choose a loaded alternative" in panel.result.text
    assert not panel.running
    panel.alternative.text = "T2"
    panel.target.text = "Select program tool"
    panel.start()
    assert "Choose a program tool" in panel.result.text
    assert not panel.running
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_changed_contact_navigation_is_preview_only_and_rejects_stale_setup(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    wait(panel)
    comparison = panel.comparison
    assert comparison and panel.contact_actions.children
    browser = panel.changed_browser
    assert panel.changed_kind.text == ("New contacts" if comparison.new_contacts else "Removed contacts")
    panel.changed_kind.text = "Removed contacts"
    assert (5, "shank", "vise") in browser.candidates
    browser.view.text = "Individual contacts"
    browser.filter()
    from kivy.metrics import dp

    action = next(row for row in browser.rows.children if row.text.startswith("Line 5"))
    action.width = dp(120)
    action.text = "Removed contact: line 5\nlong fixture obstacle name with additional mounting details"
    pump_frames(8)
    assert action.height >= action.texture_size[1] + dp(16)
    assert action.height > dp(44)
    from carveracontroller.machine.move_inspection import MoveInspector

    operations = panel.simulation.workspace.operation_panel
    monkeypatch.setattr(operations, "inspector", MoveInspector(operations.program))
    inspect, seek = Mock(wraps=operations.inspect_line), Mock()
    monkeypatch.setattr(panel.simulation.workspace.operation_panel, "inspect_line", inspect)
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", seek)
    panel.inspect_contact(5, comparison)
    inspect.assert_called_once_with(5, seek=True)
    seek.assert_called_once_with(5, 0)
    monkeypatch.setattr(panel.simulation, "clearance_stale", True)
    panel.inspect_contact(5, comparison)
    assert inspect.call_count == 1 and seek.call_count == 1
    assert not panel.contact_actions.children
    assert "Recompute" in panel.result.text
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_contact_seek_preserves_requested_line_against_old_playback_callback(kivy_app, monkeypatch):
    from carveracontroller.machine.move_inspection import MoveInspector

    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    operations = panel.simulation.workspace.operation_panel
    monkeypatch.setattr(operations, "inspector", MoveInspector(operations.program))
    monkeypatch.setattr(panel.simulation.workspace, "active_section", "Job")
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", lambda *_: operations.observe_preview_line(4))
    panel.start()
    wait(panel)
    panel.inspect_contact(5, panel.comparison)
    assert operations.selected_line == 5
    assert operations.line_field.text == "5"
    send.assert_not_called()
    panel.close()
    pump_frames(8)


def test_comparison_browser_retains_all_changed_motions_and_invalidates_detached_actions(kivy_app, monkeypatch):
    panel, viewer, send = panel_for(kivy_app, monkeypatch)
    simulation = panel.simulation
    path, tools, scene, stock = panel.inputs
    path = tuple(replace(path[0], line=line) for line in range(5, 35))
    monkeypatch.setattr(
        simulation.workspace.operation_panel,
        "program",
        ProgramOperations.from_text("G21 G90 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\n" + "G1 X4\n" * 30),
    )
    monkeypatch.setattr(simulation, "clearance_inputs", (path, tools, scene, stock))
    monkeypatch.setattr(simulation, "clearance_identity", simulation._identity())
    panel.close()
    panel = RemedyPanel(simulation, 5, "shank", "vise")
    panel.alternative.text = "T2"
    panel.start()
    wait(panel)
    comparison = panel.comparison
    assert comparison and len(comparison.removed_contacts) >= 30
    browser = panel.changed_browser
    panel.changed_kind.text = "Removed contacts"
    assert browser.candidates == comparison.removed_contacts
    browser.view.text = "Individual contacts"
    browser.filter()
    browser.turn_page(2)
    assert browser.page == 2
    actions = [row for row in reversed(browser.rows.children) if row.text.startswith("Line")]
    inspect = Mock()
    monkeypatch.setattr(simulation.workspace.operation_panel, "inspect_line", inspect)
    actions[-1].dispatch("on_release")
    inspect.assert_called_once_with(comparison.removed_contacts[-1][0], seek=True)
    panel.changed_kind.text = "New contacts"
    assert browser.candidates == comparison.new_contacts
    if not comparison.new_contacts:
        assert browser.status.text == "No new contact locations in this comparison."
    panel.alternative.text = "T1"
    assert panel.changed_browser is None and not panel.contact_actions.children
    actions[-1].dispatch("on_release")
    assert inspect.call_count == 1
    send.assert_not_called()
    panel.close()
    pump_frames(3)


@pytest.mark.parametrize("stage", ["construct", "start"])
@pytest.mark.parametrize("failure", [RuntimeError, OSError])
def test_worker_launch_failure_preserves_accepted_comparison(kivy_app, monkeypatch, stage, failure):
    import carveracontroller.desktop_remedies as module

    panel, _, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    wait(panel)
    previous, browser = panel.comparison, panel.changed_browser
    assert previous is not None and browser is not None
    children = tuple(panel.contact_actions.children)
    launches = []

    class FailedThread:
        def __init__(self, **kwargs):
            launches.append(kwargs["name"])
            if stage == "construct":
                raise failure("private platform diagnostic")

        def start(self):
            raise failure("private platform diagnostic")

    monkeypatch.setattr(module.threading, "Thread", FailedThread)
    panel.start()
    assert launches == ["setup-remedy-comparison"]
    assert not panel.running and not panel.compare_action.disabled and panel.cancel_action.disabled
    assert panel.comparison is previous and panel.changed_browser is browser
    assert tuple(panel.contact_actions.children) == children
    assert panel.result.text == "Comparison worker could not start; previous results preserved."
    send.assert_not_called()
    panel.close()
    pump_frames(8)


@pytest.mark.parametrize("phase", ["assets", "baseline", "candidate", "delivery"])
def test_cancelled_repeat_comparison_preserves_previous_review(kivy_app, monkeypatch, phase):
    import threading

    import carveracontroller.desktop_remedies as module

    panel, _, send = panel_for(kivy_app, monkeypatch)
    panel.start()
    wait(panel)
    previous, browser = panel.comparison, panel.changed_browser
    children = tuple(panel.contact_actions.children)
    snapshot = panel.inputs[3].snapshot()
    entered, release = threading.Event(), threading.Event()
    threads = []

    def pause():
        threads.append(threading.current_thread())
        entered.set()
        assert release.wait(5)

    if phase == "assets":
        original = module.asset_identity

        def assets(*args, **kwargs):
            pause()
            return original(*args, **kwargs)

        monkeypatch.setattr(module, "asset_identity", assets)
    elif phase == "delivery":
        original = module.compare_remedy

        def compare(*args, **kwargs):
            result = original(*args, **kwargs)
            pause()
            return result

        monkeypatch.setattr(module, "compare_remedy", compare)
    else:
        original = StockVolume.clone
        calls = 0

        def clone(self, **kwargs):
            nonlocal calls
            calls += 1
            if calls == (1 if phase == "baseline" else 2):
                pause()
            return original(self, **kwargs)

        monkeypatch.setattr(StockVolume, "clone", clone)
    try:
        panel.start()
        assert entered.wait(5)
        assert threads[0] is not threading.current_thread()
        pump_frames(3, sleep=0.01)
        assert panel.running and not panel.cancel_action.disabled
        panel.cancel_action.dispatch("on_release")
    finally:
        release.set()
    wait(panel)
    assert panel.result.text == "Comparison cancelled; previous results preserved."
    assert not panel.compare_action.disabled and panel.cancel_action.disabled
    assert panel.comparison is previous and panel.changed_browser is browser
    assert tuple(panel.contact_actions.children) == children
    assert panel.inputs[3].snapshot() == snapshot
    send.assert_not_called()
    panel.close()
    pump_frames(8)
