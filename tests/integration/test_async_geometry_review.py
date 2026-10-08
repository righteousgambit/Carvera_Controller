"""Exact CAD change review keeps Close usable and never publishes obsolete input."""

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


def settle(popup):
    deadline = time.monotonic() + 5
    while popup.active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not popup.active


@pytest.fixture
def review_case(kivy_app, monkeypatch, tmp_path):
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
    baseline = capture_context(viewer, program)
    monkeypatch.setattr(panel, "rest_context", baseline)
    monkeypatch.setattr(panel, "clearance_context", None)
    monkeypatch.setattr(panel, "change_review", None, raising=False)
    # Isolate review publication from the independent periodic input invalidator.
    monkeypatch.setattr(panel, "refresh_inputs", Mock())
    monkeypatch.setattr(panel, "hide_single_residual", Mock())
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    yield panel, viewer, path, send
    if panel.change_review is not None:
        panel.change_review.dismiss()
    pump_frames(2)


@pytest.mark.parametrize("condition", ["complete", "close", "setup", "baseline", "changed", "missing"])
def test_blocked_hash_keeps_ui_and_close_available_with_exact_byte_review(review_case, monkeypatch, condition):
    import carveracontroller.desktop_geometry_review as module
    import carveracontroller.machine.geometry_changes as identity_module

    panel, viewer, path, send = review_case
    before = path.stat()
    real = identity_module.asset_digest
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    ui = threading.get_ident()
    threads = []

    def digest(*args, **kwargs):
        assert threading.get_ident() != ui
        threads.append(threading.get_ident())
        entered.set()
        assert release.wait(5)
        return real(*args, **kwargs)

    real_verify = module.verify_context_assets

    def verify(*args, **kwargs):
        try:
            return real_verify(*args, **kwargs)
        finally:
            returned.set()

    monkeypatch.setattr(identity_module, "asset_digest", digest)
    monkeypatch.setattr(module, "verify_context_assets", verify)
    popup = panel.review_changes()
    try:
        assert entered.wait(3)
        assert popup.active and "Verifying CAD" in popup.summary.text
        tick = []
        Clock.schedule_once(lambda dt: tick.append(dt), 0)
        pump_frames(3, sleep=0.01)
        assert tick and not popup.rows.children
        if condition == "close":
            close = next(w for w in popup.content.walk() if getattr(w, "text", None) == "Close")
            close.dispatch("on_release")
            assert popup.closed.is_set()
        elif condition == "setup":
            viewer.machine_setup = replace(viewer.machine_setup, stock_size_mm=(3, 3, 3))
        elif condition == "baseline":
            panel.rest_context = deepcopy(panel.rest_context)
            panel.rest_context["stock"]["size_mm"] = (4, 4, 4)
        elif condition == "changed":
            path.write_bytes(b"new mesh")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        elif condition == "missing":
            path.unlink()
    finally:
        release.set()
    assert returned.wait(3)
    settle(popup)
    pump_frames(3)
    if condition in ("setup", "baseline"):
        assert "Inputs changed" in popup.summary.text and not popup.entries
        panel.hide_single_residual.assert_not_called()
    elif condition == "close":
        assert not popup.entries and panel.change_review is None
        panel.hide_single_residual.assert_not_called()
    elif condition in ("changed", "missing"):
        labels = [getattr(w, "text", "") for w in popup.rows.children]
        assert any("CAD requires attention" in text for text in labels)
        assert any(("CAD bytes changed" if condition == "changed" else "asset unreadable") in text for text in labels)
        panel.hide_single_residual.assert_called_once()
        if condition == "changed":
            assert path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
    else:
        assert "No changed inputs" in popup.summary.text
        panel.hide_single_residual.assert_not_called()
    assert threads and set(threads) != {ui}
    send.assert_not_called()
    popup.dismiss()


@pytest.mark.parametrize("failure", [RuntimeError, OSError])
@pytest.mark.parametrize("stage", ["construct", "start"])
def test_review_launch_failure_keeps_close_and_previous_results(review_case, monkeypatch, failure, stage):
    import carveracontroller.desktop_geometry_review as module

    panel, _viewer, _path, send = review_case

    class FailedThread:
        def __init__(self, **kwargs):
            if stage == "construct":
                raise failure("private platform failure")

        def start(self):
            raise failure("private platform failure")

    monkeypatch.setattr(module.threading, "Thread", FailedThread)
    popup = panel.review_changes()
    assert not popup.active and "could not start" in popup.summary.text
    assert "private platform" not in popup.summary.text
    panel.hide_single_residual.assert_not_called()
    popup.dismiss()
    send.assert_not_called()


def test_large_affected_operation_review_keeps_every_entry_in_bounded_pages(review_case, monkeypatch):
    panel, viewer, _path, send = review_case
    text = "G21 G90 G17 G94\nT1 M6\nG0 X0 Y0 Z1\n"
    text += "".join(f"(Operation: Finish {index})\nG1 X{index + 1} F100\n" for index in range(100))
    program = ProgramOperations.from_text(text)
    monkeypatch.setattr(panel.workspace.operation_panel, "program", program)
    baseline = capture_context(viewer, program)
    monkeypatch.setattr(panel, "rest_context", baseline)
    viewer.machine_setup = replace(viewer.machine_setup, stock_size_mm=(3, 3, 3))
    selected = Mock()
    monkeypatch.setattr(panel.workspace.operation_panel, "select", selected)
    popup = panel.review_changes()
    settle(popup)
    operations = [value for kind, value in popup.entries if kind == "operation"]
    assert len(operations) >= 100 and operations == list(program.operations)
    seen = []
    while True:
        assert len(popup.rows.children) <= popup.page_size
        for widget in reversed(popup.rows.children):
            if widget.text.startswith("Inspect "):
                seen.append(widget.text)
        if popup.next.disabled:
            break
        popup.next.dispatch("on_release")
    assert len(seen) == len(operations) and len(set(seen)) == len(operations)
    final = next(w for w in popup.rows.children if w.text.startswith("Inspect "))
    final.dispatch("on_release")
    selected.assert_called_once_with(operations[-1])
    send.assert_not_called()


@pytest.mark.parametrize("calculation", ["stock", "clearance"])
@pytest.mark.parametrize("condition", ["complete", "cancel", "setup", "bytes", "missing"])
def test_completed_result_rechecks_exact_bytes_off_ui_before_accepting(
    review_case, monkeypatch, calculation, condition
):
    import carveracontroller.desktop_simulation as module
    import carveracontroller.machine.geometry_changes as identity_module
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    panel, viewer, path, send = review_case
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(module, "collision_geometry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", "1")
    identity = panel._identity()
    context = panel._context()
    previous_report, previous_stock = object(), object()
    inputs = ((), {}, None, None)
    for name, value in (
        ("report", previous_report),
        ("rest_stock", previous_stock),
        ("rest_context", context),
        ("clearance_context", context),
        ("clearance_identity", identity),
        ("clearance_inputs", inputs),
        ("clearance_stale", False),
    ):
        monkeypatch.setattr(panel, name, value)
    monkeypatch.setattr(panel.artifact_status, "text", "Previous snapshot")
    rendered, publish = Mock(), Mock()
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", rendered)
    monkeypatch.setattr(panel.clearance_card, "set_report", publish)
    monkeypatch.setattr(module, "analyze_clearance", Mock(return_value=object()))
    before = path.stat()
    entered, release = threading.Event(), threading.Event()
    ui = threading.get_ident()
    count = []
    real = identity_module.asset_digest

    def digest(*args, **kwargs):
        assert threading.get_ident() != ui, "result acceptance read CAD on UI"
        count.append(threading.get_ident())
        if len(count) == 2:
            entered.set()
            assert release.wait(5)
        return real(*args, **kwargs)

    monkeypatch.setattr(identity_module, "asset_digest", digest)
    try:
        if calculation == "stock":
            panel.start(False)
        else:
            panel.review_clearance()
        assert entered.wait(3)
        ticks = []
        Clock.schedule_once(lambda dt: ticks.append(dt), 0)
        pump_frames(3, sleep=0.01)
        assert ticks and panel.running and not panel.cancel_action.disabled
        assert panel.report is previous_report and panel.rest_stock is previous_stock
        rendered.assert_not_called()
        publish.assert_not_called()
        if condition == "cancel":
            panel.cancel_action.dispatch("on_release")
        elif condition == "setup":
            viewer.machine_setup = replace(viewer.machine_setup, stock_size_mm=(3, 3, 3))
        elif condition == "bytes":
            path.write_bytes(b"new mesh")
            os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        elif condition == "missing":
            path.unlink()
    finally:
        release.set()
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running and panel.cancel_action.disabled
    assert len(count) == 2
    if condition == "complete":
        if calculation == "stock":
            assert panel.report is not previous_report and panel.rest_stock is not previous_stock
            rendered.assert_called_once()
        else:
            publish.assert_called_once()
    else:
        assert panel.report is previous_report and panel.rest_stock is previous_stock and panel.rest_context is context
        assert panel.artifact_status.text == "Previous snapshot"
        rendered.assert_not_called()
        publish.assert_not_called()
        assert "cancelled" in panel.note.text if condition == "cancel" else "older" in panel.note.text
        if condition == "bytes":
            assert path.stat().st_size == before.st_size and path.stat().st_mtime_ns == before.st_mtime_ns
    send.assert_not_called()


@pytest.mark.parametrize("second_cancel", [False, True])
def test_cancelled_partial_simulation_is_verified_and_second_cancel_stops_acceptance(
    review_case, monkeypatch, second_cancel
):
    import carveracontroller.desktop_simulation as module
    import carveracontroller.machine.geometry_changes as identity_module
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    panel, viewer, _path, send = review_case
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(module, "collision_geometry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", "1")
    previous = object()
    monkeypatch.setattr(panel, "report", previous)
    real_simulate, real_digest = module.simulate, identity_module.asset_digest
    sim_entered, sim_release, hash_entered, hash_release = (threading.Event() for _ in range(4))
    count = []
    rendered = Mock()
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", rendered)

    def simulate(*args, **kwargs):
        sim_entered.set()
        assert sim_release.wait(5)
        result = real_simulate(*args, **kwargs)
        assert result.cancelled
        return result

    def digest(*args, **kwargs):
        count.append(1)
        if len(count) == 2:
            hash_entered.set()
            assert hash_release.wait(5)
        return real_digest(*args, **kwargs)

    monkeypatch.setattr(module, "simulate", simulate)
    monkeypatch.setattr(identity_module, "asset_digest", digest)
    try:
        panel.start(False)
        assert sim_entered.wait(3)
        panel.cancel_action.dispatch("on_release")
        sim_release.set()
        assert hash_entered.wait(3)
        pump_frames(3)
        assert panel.running and panel.report is previous
        if second_cancel:
            panel.cancel_action.dispatch("on_release")
    finally:
        sim_release.set()
        hash_release.set()
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running
    if second_cancel:
        assert panel.report is previous and "Result CAD acceptance preparation cancelled" in panel.note.text
        rendered.assert_not_called()
    else:
        assert panel.report.cancelled and "Cancelled · partial result" in panel.note.text
        rendered.assert_called_once_with(None)
    send.assert_not_called()


@pytest.mark.parametrize("condition", ["cancel_before_delivery", "verification_error_before_ui"])
def test_acceptance_delivery_cancel_and_queued_phase_callback_keep_previous_result(review_case, monkeypatch, condition):
    import carveracontroller.desktop_simulation as module
    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType

    panel, viewer, _path, send = review_case
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=1, shank_diameter=1, flute_length=2, stickout=5)
    monkeypatch.setattr(viewer, "library_tool_table_mm", {1: definition})
    monkeypatch.setattr(module, "collision_geometry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(panel, "refresh_stock_alignment", Mock())
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(panel.stock_source, "text", "Initial stock")
    monkeypatch.setattr(panel.resolution, "text", "1")
    prior_report, prior_stock = object(), object()
    monkeypatch.setattr(panel, "report", prior_report)
    monkeypatch.setattr(panel, "rest_stock", prior_stock)
    verify_done = threading.Event()
    calls = []
    real_verify = module.verify_context_assets
    rendered = Mock()
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", rendered)

    def verify(*args, **kwargs):
        calls.append(1)
        result = real_verify(*args, **kwargs)
        if len(calls) == 2:
            verify_done.set()
            if condition == "verification_error_before_ui":
                raise InterruptedError("injected final-check interruption")
        return result

    monkeypatch.setattr(module, "verify_context_assets", verify)
    panel.start(False)
    assert verify_done.wait(3)  # Deliberately do not pump UI until the phase callback is queued.
    if condition == "cancel_before_delivery":
        panel.cancel_action.dispatch("on_release")
    deadline = time.monotonic() + 5
    while panel.running and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert not panel.running and "previous results preserved" in panel.note.text
    assert panel.report is prior_report and panel.rest_stock is prior_stock
    rendered.assert_not_called()
    send.assert_not_called()
