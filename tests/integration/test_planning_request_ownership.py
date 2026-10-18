"""Facing and hole planners share one publish intent and cancellable UI state."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller import desktop_hole_planning as holes
from carveracontroller import desktop_planning as planning
from carveracontroller import desktop_surface_planning as facing
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from tests.integration.conftest import pump_frames


@pytest.fixture
def planners(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(
        ws.machine.gcode_viewer,
        "library_tool_table_mm",
        {
            2: ToolDefinition(2, ToolType.DRILL, diameter=5.1054, flute_length=15, stickout=20),
            3: ToolDefinition(3, ToolType.THREAD_MILL, diameter=3, flute_length=2, stickout=12),
            4: ToolDefinition(4, ToolType.FLAT_END_MILL, diameter=6.35, flute_length=15, stickout=25),
        },
    )
    face = facing.SurfacePlanningPanel(ws)
    face.refresh_tools()
    face.boundary.text = "0 0\n10 0\n10 8\n0 8"
    hole = holes.HolePlanningPanel(ws)
    hole.holes.text = "10 20 8 6"
    for kind, number in (("drill", 2), ("threadmill", 3)):
        hole.tools[kind].text = next(
            title for title in hole.tools[kind].values if hole.tool_labels.get(title) == number
        )
    workers = []

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    proxy = SimpleNamespace(Thread=DeferredThread)
    monkeypatch.setattr(facing, "threading", proxy)
    monkeypatch.setattr(holes, "threading", proxy)
    stage, send = Mock(return_value=tmp_path / "preview.cnc"), Mock()
    monkeypatch.setattr(facing, "stage_program", stage)
    monkeypatch.setattr(planning, "stage_program", stage)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    yield SimpleNamespace(panels=(face, hole), workers=workers, stage=stage, send=send, workspace=ws)
    assert getattr(ws, "_planning_request", None) is None
    send.assert_not_called()


@pytest.mark.parametrize("first", [0, 1])
@pytest.mark.parametrize("completion_order", [(0, 1), (1, 0)])
def test_latest_planner_intent_wins_in_either_completion_order(planners, first, completion_order):
    older, newer = planners.panels[first], planners.panels[1 - first]
    older.generate()
    newer.generate()
    assert len(planners.workers) == 2
    assert "Replaced by a newer" in older.note.text
    assert older.cancel_button.disabled and older.generate_button.disabled
    for index in completion_order:
        planners.workers[index]()
        pump_frames(3)
        if index == 0:
            assert not older.running
            if newer.running:
                assert planners.workspace._planning_request is newer._request
    planners.stage.assert_called_once()
    assert planners.stage.call_args.args[2] == ("holes-and-threads" if first == 0 else "boundary-facing")
    assert "Replaced by a newer" in older.note.text
    assert not older.generate_button.disabled and older.cancel_button.disabled
    assert not newer.generate_button.disabled and newer.cancel_button.disabled


@pytest.mark.parametrize("kind", [0, 1])
@pytest.mark.parametrize("cancel_after_worker", [False, True])
def test_visible_cancel_discards_result_then_retries(planners, kind, cancel_after_worker):
    panel = planners.panels[kind]
    assert panel.cancel_button.disabled
    panel.generate_button.dispatch("on_release")
    assert panel.running and panel.generate_button.disabled and not panel.cancel_button.disabled
    if cancel_after_worker:
        planners.workers[0]()
    panel.cancel_button.dispatch("on_release")
    assert panel.cancel_button.disabled and "Preview cancelled" in panel.note.text
    # One in-flight worker per panel: cancel withdraws publication without
    # pretending Python calculation has stopped or starting duplicate workers.
    panel.generate()
    assert len(planners.workers) == 1
    if not cancel_after_worker:
        planners.workers[0]()
    pump_frames(3)
    assert not panel.running and not panel.generate_button.disabled
    assert "Preview cancelled" in panel.note.text
    planners.stage.assert_not_called()
    panel.generate_button.dispatch("on_release")
    planners.workers[1]()
    pump_frames(3)
    planners.stage.assert_called_once()
    assert not panel.running and panel.cancel_button.disabled


@pytest.mark.parametrize("first", [0, 1])
def test_invalid_new_planner_inputs_do_not_supersede_valid_work(planners, first):
    older, newer = planners.panels[first], planners.panels[1 - first]
    older.generate()
    if first == 0:
        newer.holes.text = "invalid"
    else:
        newer.boundary.text = "invalid"
    newer.generate()
    assert len(planners.workers) == 1 and not newer.running
    assert not older.cancel_button.disabled
    planners.workers[0]()
    pump_frames(3)
    planners.stage.assert_called_once()


@pytest.mark.parametrize("first", [0, 1])
def test_new_worker_start_failure_keeps_older_result_withdrawn(planners, monkeypatch, first):
    older, newer = planners.panels[first], planners.panels[1 - first]
    older.generate()

    class FailedThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("no worker available")

    module = holes if first == 0 else facing
    monkeypatch.setattr(module, "threading", SimpleNamespace(Thread=FailedThread))
    newer.generate()
    assert not newer.running and "Could not start" in newer.note.text
    assert not newer.generate_button.disabled and newer.cancel_button.disabled
    planners.workers[0]()
    pump_frames(3)
    planners.stage.assert_not_called()
    assert "Replaced by a newer" in older.note.text


@pytest.mark.parametrize("first", [0, 1])
def test_cancelling_newest_request_never_revives_older_result(planners, first):
    older, newer = planners.panels[first], planners.panels[1 - first]
    older.generate()
    newer.generate()
    newer.cancel_button.dispatch("on_release")
    planners.workers[1]()
    pump_frames(3)
    planners.workers[0]()
    pump_frames(3)
    planners.stage.assert_not_called()
    assert "Replaced by a newer" in older.note.text
    assert "Preview cancelled" in newer.note.text


@pytest.mark.parametrize("kind", [0, 1])
def test_cancelled_worker_error_does_not_replace_cancellation_status(planners, monkeypatch, kind):
    panel = planners.panels[kind]

    def fail(*_args):
        raise ValueError("obsolete calculation error")

    if kind == 0:
        monkeypatch.setattr(facing.FacingPlan, "from_params", fail)
    else:
        monkeypatch.setattr(holes.HoleWorkflow, "plan", fail)
    panel.generate()
    panel.cancel_button.dispatch("on_release")
    planners.workers[0]()
    pump_frames(3)
    assert not panel.running and not panel.generate_button.disabled
    assert "Preview cancelled" in panel.note.text and "obsolete" not in panel.note.text
    planners.stage.assert_not_called()
