"""Simulation launch failures preserve the last completed local review."""

from unittest.mock import Mock

import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.program_operations import ProgramOperations


@pytest.mark.parametrize("calculation", ["stock", "clearance"])
@pytest.mark.parametrize("failure", [RuntimeError, OSError])
@pytest.mark.parametrize("stage", ["construct", "start"])
def test_launch_failure_restores_controls_and_preserves_results(kivy_app, monkeypatch, calculation, failure, stage):
    import carveracontroller.desktop_simulation as module

    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(viewer, "_machine_scene", lambda: {})
    monkeypatch.setattr(panel, "_alignment_key", None)
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel, "clearance_stale", False)
    monkeypatch.setattr(panel, "clearance_inputs", ((), {}, None, None))
    monkeypatch.setattr(panel, "clearance_identity", panel._identity())
    report, stock, context = object(), object(), object()
    monkeypatch.setattr(panel, "report", report)
    monkeypatch.setattr(panel, "rest_stock", stock)
    monkeypatch.setattr(panel, "rest_context", context)
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", "1")
    monkeypatch.setattr(panel.artifact_status, "text", "Previous stock snapshot retained")
    candidates_parent = panel.hits.parent
    calls = Mock()
    monkeypatch.setattr(panel.hits, "set_candidates", calls)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    launched = []

    class FailedThread:
        def __init__(self, **kwargs):
            launched.append(kwargs)
            if stage == "construct":
                raise failure("private platform diagnostic")

        def start(self):
            raise failure("private platform diagnostic")

    monkeypatch.setattr(module.threading, "Thread", FailedThread)
    if calculation == "stock":
        panel.start(False)
    else:
        panel.review_clearance()
    assert [item["name"] for item in launched] == ["stock-path-review", "local-simulation"]
    assert "Stock/path review worker could not start" in panel.alignment_status.text
    assert not panel.running
    assert not panel.simulate_action.disabled
    assert not panel.clearance_action.disabled
    assert panel.cancel_action.disabled
    assert panel.report is report and panel.rest_stock is stock and panel.rest_context is context
    assert panel.artifact_status.text == "Previous stock snapshot retained"
    assert panel.hits.parent is candidates_parent
    assert "could not start" in panel.note.text
    assert "previous results preserved" in panel.note.text
    assert "private platform diagnostic" not in panel.note.text
    calls.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize(
    "phase, message",
    [("motion", "Motion"), ("allocation", "Stock"), ("clone", "Stock"), ("scene", "Collision scene")],
)
def test_preparation_runs_off_ui_and_cancel_preserves_previous_review(kivy_app, monkeypatch, phase, message):
    import threading
    import time

    import carveracontroller.desktop_simulation as module
    from tests.integration.conftest import pump_frames

    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(viewer, "_machine_scene", lambda: {})
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    monkeypatch.setattr(panel, "running", False)
    report, stock, context = object(), object(), panel._context()
    monkeypatch.setattr(panel, "report", report)
    monkeypatch.setattr(panel, "rest_stock", stock)
    monkeypatch.setattr(panel, "rest_context", context)
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", "1")
    monkeypatch.setattr(panel.artifact_status, "text", "Previous snapshot")
    calls, rendered, send, simulate = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(panel.hits, "set_candidates", calls)
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", rendered)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(module, "simulate", simulate)
    entered, release = threading.Event(), threading.Event()
    worker_threads = []

    def prepare(*_args, cancelled=None, **_kwargs):
        worker_threads.append(threading.current_thread())
        entered.set()
        assert release.wait(5)
        assert cancelled()
        raise InterruptedError("cancelled fixture")

    if phase == "motion":
        monkeypatch.setattr(module, "simulation_segments", prepare)
    elif phase == "allocation":
        monkeypatch.setattr(module, "StockVolume", prepare)
    elif phase == "clone":
        monkeypatch.setattr(module.StockVolume, "clone", prepare)
    else:
        monkeypatch.setattr(module, "scene_from_geometry", prepare)
    try:
        panel.start(False)
        assert entered.wait(5)
        assert worker_threads[0] is not threading.current_thread()
        assert panel.running and not panel.cancel_action.disabled
        assert panel.report is report and panel.rest_stock is stock
        pump_frames(3, sleep=0.01)
        assert panel.running and not panel.cancel_action.disabled
        panel.cancel_action.dispatch("on_release")
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running
    assert panel.report is report and panel.rest_stock is stock and panel.rest_context is context
    assert panel.artifact_status.text == "Previous snapshot"
    assert panel.note.text == f"{message} preparation cancelled; previous results preserved."
    calls.assert_not_called()
    rendered.assert_not_called()
    simulate.assert_not_called()
    send.assert_not_called()


def test_obsolete_stock_alignment_cancels_motion_preparation_without_delivery(kivy_app, monkeypatch):
    import threading

    import carveracontroller.desktop_simulation as module
    from tests.integration.conftest import pump_frames

    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    monkeypatch.setattr(panel, "_alignment_key", None)
    entered, release = threading.Event(), threading.Event()
    real_thread, threads = threading.Thread, []
    calls = []

    def thread(**kwargs):
        worker = real_thread(**kwargs)
        threads.append(worker)
        return worker

    def prepare(*_args, cancelled=None, **_kwargs):
        entered.set()
        assert release.wait(5)
        calls.append(cancelled())
        raise InterruptedError("obsolete selection")

    monkeypatch.setattr(module.threading, "Thread", thread)
    monkeypatch.setattr(module, "simulation_segments", prepare)
    try:
        panel.refresh_stock_alignment(program, None, ())
        assert entered.wait(5)
        monkeypatch.setattr(panel, "_alignment_key", object())
        panel.alignment_status.text = "New selection retained"
    finally:
        release.set()
        for worker in threads:
            worker.join(5)
            assert not worker.is_alive()
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    pump_frames(4)
    assert calls == [True]
    assert panel.alignment_status.text == "New selection retained"
