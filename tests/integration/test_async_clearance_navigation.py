"""Current-path navigation verifies bytes off UI; historical review remains immediate."""

import os
import threading
import time
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames


def settle(panel):
    deadline = time.monotonic() + 5
    while panel.clearance_navigation.active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.clearance_navigation.active
    pump_frames(2)


@pytest.fixture
def navigation_case(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\nG1 Z0 F100\nG1 X1\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    monkeypatch.setattr(viewer, "library_tool_table_mm", {})
    path = tmp_path / "fixture.json"
    path.write_bytes(b"old mesh")
    monkeypatch.setattr(
        viewer,
        "machine_component_profiles",
        {
            "fixture": SimpleNamespace(
                asset_path=str(path), asset_sha256=asset_digest(path), source_revision="1", source_sha256="synthetic"
            )
        },
    )
    monkeypatch.setattr(viewer, "machine_profile", None)
    context = capture_context(viewer, program)
    monkeypatch.setattr(panel, "clearance_context", context)
    monkeypatch.setattr(panel, "clearance_identity", panel._identity())
    monkeypatch.setattr(panel, "clearance_stale", False)
    monkeypatch.setattr(panel, "report", SimpleNamespace(clearance_details=()))
    monkeypatch.setattr(panel, "refresh_inputs", Mock())
    monkeypatch.setattr(panel, "refresh_controls", Mock())
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    monkeypatch.setattr(panel, "reveal_clearance_inspector", Mock())
    monkeypatch.setattr(ws.operation_panel, "queue_reveal", Mock())
    point = SimpleNamespace(line=5, source_ratio=0.25)
    monkeypatch.setattr(panel.clearance_card.plot, "selected", point)
    monkeypatch.setattr(panel.clearance_card.plot, "paint", Mock())
    monkeypatch.setattr(panel.clearance_card, "refresh_navigation", Mock())
    inspect, seek, reveal, send = Mock(), Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.operation_panel, "inspect_line", inspect)
    monkeypatch.setattr(viewer, "set_distance_by_lineidx", seek)
    monkeypatch.setattr(ws.operation_panel, "_reveal", reveal)
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    yield panel, viewer, path, point, inspect, seek, reveal, send
    panel.clearance_navigation.cancel()
    panel.close_clearance_inspector()
    settle(panel)


@pytest.mark.parametrize("action", ["select", "seek", "source", "inspector"])
@pytest.mark.parametrize(
    "condition", ["complete", "cancel", "setup", "baseline", "bytes", "missing", "selection", "report"]
)
def test_navigation_checks_exact_bytes_off_ui_and_rejects_obsolete_requests(
    navigation_case, monkeypatch, action, condition
):
    import carveracontroller.machine.geometry_changes as identity

    panel, viewer, path, point, inspect, seek, reveal, send = navigation_case
    entered, release = threading.Event(), threading.Event()
    ui = threading.get_ident()
    real = identity.asset_digest
    before = path.stat()

    def digest(*args, **kwargs):
        assert threading.get_ident() != ui
        entered.set()
        assert release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(identity, "asset_digest", digest)
    body = None
    if action == "inspector":
        body = panel.inspect_clearance(5, "holder", "vise")
        assert not entered.is_set()  # Captured geometry is usable without a disk read.
        trigger = next(w for w in body.walk() if getattr(w, "text", "") == "Show motion in preview")
        trigger.dispatch("on_release")
    elif action == "select":
        panel.select_clearance(point)
    elif action == "seek":
        panel.seek_clearance(point)
    else:
        panel.reveal_clearance_source()
    try:
        assert entered.wait(3)
        frames = []
        Clock.schedule_once(lambda dt: frames.append(dt), 0)
        pump_frames(3, sleep=0.01)
        assert frames and not panel.navigation_cancel.disabled
        inspect.assert_not_called()
        seek.assert_not_called()
        reveal.assert_not_called()
        if condition == "cancel":
            panel.navigation_cancel.dispatch("on_release")
        elif condition == "setup":
            viewer.machine_setup = replace(viewer.machine_setup, stock_size_mm=(3, 3, 3))
        elif condition == "baseline":
            panel.clearance_context = deepcopy(panel.clearance_context)
            panel.clearance_context["stock"]["size_mm"] = (4, 4, 4)
        elif condition == "bytes":
            path.write_bytes(b"new mesh")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        elif condition == "missing":
            path.unlink()
        elif condition == "selection":
            if body:
                panel.close_clearance_inspector()
            else:
                panel.clearance_card.plot.selected = None
        elif condition == "report":
            panel.report = SimpleNamespace(clearance_details=())
    finally:
        release.set()
    settle(panel)
    if condition == "complete":
        inspect.assert_called_once_with(5, seek=action == "inspector")
        if action == "seek":
            seek.assert_called_once_with(5, 0.25)
        if action == "source":
            reveal.assert_called_once_with(panel.workspace.operation_panel.inspection)
        assert "CAD bytes checked" in panel.navigation_status.text
    else:
        inspect.assert_not_called()
        seek.assert_not_called()
        reveal.assert_not_called()
        if condition in ("bytes", "missing"):
            assert panel.clearance_stale and "Current CAD rejected" in panel.navigation_status.text
        if condition == "bytes":
            assert path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
    assert panel.report is not None
    assert panel.navigation_cancel.disabled
    send.assert_not_called()


def test_burst_navigation_owns_one_reader_and_only_latest_pending(navigation_case, monkeypatch):
    import carveracontroller.machine.geometry_changes as identity

    panel, _viewer, _path, point, inspect, seek, reveal, send = navigation_case
    entered, release = threading.Event(), threading.Event()
    real = identity.asset_digest
    reads = []

    def digest(*args, **kwargs):
        reads.append(threading.get_ident())
        entered.set()
        if len(reads) == 1:
            assert release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(identity, "asset_digest", digest)
    panel.select_clearance(point)
    assert entered.wait(3)
    try:
        for _ in range(50):
            panel.seek_clearance(point)
        panel.reveal_clearance_source()
        assert len(reads) == 1 and panel.clearance_navigation.pending is not None
    finally:
        release.set()
    settle(panel)
    assert len(reads) == 2
    inspect.assert_called_once_with(5, seek=False)
    reveal.assert_called_once_with(panel.workspace.operation_panel.inspection)
    seek.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("failure", [RuntimeError, OSError])
@pytest.mark.parametrize("stage", ["construct", "start"])
def test_navigation_launch_failure_preserves_results_and_retries(navigation_case, monkeypatch, failure, stage):
    import carveracontroller.desktop_clearance_navigation as module

    panel, _viewer, _path, point, inspect, seek, reveal, send = navigation_case
    report = panel.report

    class FailedThread:
        def __init__(self, **kwargs):
            if stage == "construct":
                raise failure("private failure")

        def start(self):
            raise failure("private failure")

    with monkeypatch.context() as patch:
        patch.setattr(module.threading, "Thread", FailedThread)
        panel.seek_clearance(point)
        assert not panel.clearance_navigation.active
        assert "could not start" in panel.navigation_status.text
        assert "private failure" not in panel.navigation_status.text
        inspect.assert_not_called()
        seek.assert_not_called()
    panel.seek_clearance(point)
    settle(panel)
    seek.assert_called_once_with(5, 0.25)
    assert panel.report is report
    send.assert_not_called()


@pytest.mark.parametrize("condition", ["cancel", "setup", "baseline", "selection", "plot_report"])
def test_queued_verified_delivery_rechecks_current_owner_before_navigating(navigation_case, monkeypatch, condition):
    import carveracontroller.desktop_clearance_navigation as module

    panel, viewer, _path, point, inspect, seek, reveal, send = navigation_case
    returned = threading.Event()
    real_schedule = module.Clock.schedule_once
    queued = []
    ui = threading.get_ident()

    def schedule(callback, timeout=0):
        if threading.get_ident() != ui:
            queued.append(callback)
            returned.set()
            return None
        return real_schedule(callback, timeout)

    with monkeypatch.context() as patch:
        patch.setattr(module.Clock, "schedule_once", schedule)
        panel.seek_clearance(point)
        assert returned.wait(3) and len(queued) == 1
        assert panel.clearance_navigation.active
        if condition == "cancel":
            panel.clearance_navigation.cancel()
        elif condition == "setup":
            viewer.machine_setup = replace(viewer.machine_setup, stock_size_mm=(3, 3, 3))
        elif condition == "baseline":
            panel.clearance_identity = ("different", "capture")
        elif condition == "selection":
            panel.clearance_card.plot.selected = None
        else:
            monkeypatch.setattr(panel.clearance_card, "report", object())
        queued[0](0)
    settle(panel)
    inspect.assert_not_called()
    seek.assert_not_called()
    reveal.assert_not_called()
    send.assert_not_called()
