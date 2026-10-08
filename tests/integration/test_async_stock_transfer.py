"""Residual transfers keep the UI live and retain prior results/output on rejection."""

import json
import os
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.manufacturing_simulation import AABB, StockVolume, Vec3
from carveracontroller.machine.geometry_changes import capture_context, digest_context
from carveracontroller.machine.program_operations import ProgramOperations
from tests.integration.conftest import pump_frames


def settle(panel):
    deadline = time.monotonic() + 5
    while panel.artifact_transfer is not None and panel.artifact_transfer.active and time.monotonic() < deadline:
        pump_frames(2, sleep=0.01)
    assert panel.artifact_transfer is None or not panel.artifact_transfer.active


@pytest.fixture
def transfer_case(kivy_app, monkeypatch, tmp_path):
    ws = kivy_app.root.desktop_workspace
    panel, viewer = ws.simulation_panel, ws.machine.gcode_viewer
    program = ProgramOperations.from_text("G21 G90 G17 G94\nT1 M6\nG1 X1 F100\n")
    monkeypatch.setattr(ws.operation_panel, "program", program)
    monkeypatch.setattr(viewer, "machine_setup", MachineSetup(stock_size_mm=(2, 2, 2)))
    monkeypatch.setattr(viewer, "library_tool_table_mm", {})
    asset = tmp_path / "fixture.json"
    asset.write_bytes(b"old mesh")
    monkeypatch.setattr(viewer, "machine_profile", None)
    monkeypatch.setattr(viewer, "assembly_preview_binding", None)
    monkeypatch.setattr(
        viewer,
        "machine_component_profiles",
        {
            "fixture": SimpleNamespace(
                asset_path=str(asset), asset_sha256=asset_digest(asset), source_revision="1", source_sha256="synthetic"
            )
        },
    )
    context = capture_context(viewer, program)
    stock = StockVolume(AABB(Vec3(0, 0, 0), Vec3(2, 2, 2)), 1)
    monkeypatch.setattr(panel, "rest_stock", stock)
    monkeypatch.setattr(panel, "rest_context", context)
    monkeypatch.setattr(panel, "rest_identity", (context["program"], digest_context(context)))
    monkeypatch.setattr(panel, "running", False)
    monkeypatch.setattr(ws.repeat_parts_panel, "calculating", False)
    monkeypatch.setattr(panel, "artifact_transfer", None)
    monkeypatch.setattr(panel, "refresh_inputs", Mock())
    geometry = Mock()
    monkeypatch.setattr(viewer, "set_rest_stock_geometry", geometry)
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    path = tmp_path / "rest.cvstock"
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "program_sha256": context["program"],
                "context": context,
                "context_sha256": digest_context(context),
                "stock": stock.snapshot(),
            }
        )
    )
    yield panel, viewer, asset, path, stock, geometry, send
    if panel.artifact_transfer is not None:
        panel.artifact_transfer.dismiss()
    pump_frames(2)


@pytest.mark.parametrize("save", [False, True])
@pytest.mark.parametrize("condition", ["complete", "cancel", "setup", "baseline", "changed", "missing"])
def test_actual_blocked_cad_hash_keeps_cancel_and_ui_live(transfer_case, monkeypatch, save, condition):
    import carveracontroller.machine.geometry_changes as module

    panel, viewer, asset, path, stock, geometry, send = transfer_case
    before = path.read_bytes()
    stat = asset.stat()
    real = module.asset_digest
    entered, release, returned = threading.Event(), threading.Event(), threading.Event()
    ui = threading.get_ident()

    def digest(*args, **kwargs):
        assert threading.get_ident() != ui
        entered.set()
        assert release.wait(5)
        try:
            return real(*args, **kwargs)
        finally:
            returned.set()

    monkeypatch.setattr(module, "asset_digest", digest)
    transfer = panel._start_stock_transfer(path, save=save)
    try:
        assert entered.wait(3)
        assert transfer.active and not transfer.cancel.disabled
        assert panel.simulate_action.disabled and panel.more.disabled
        tick = []
        Clock.schedule_once(lambda dt: tick.append(dt), 0)
        pump_frames(3, sleep=0.01)
        assert tick and panel.rest_stock is stock and path.read_bytes() == before
        if condition == "cancel":
            transfer.cancel.dispatch("on_release")
            assert transfer.closed.is_set()
        elif condition == "setup":
            viewer.machine_setup = replace(viewer.machine_setup, stock_size_mm=(3, 3, 3))
        elif condition == "baseline":
            panel.rest_context = dict(panel.rest_context, work_offset_mm=(9, 0, 0))
        elif condition == "changed":
            asset.write_bytes(b"new mesh")
            os.utime(asset, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        elif condition == "missing":
            asset.unlink()
    finally:
        release.set()
    assert returned.wait(3)
    settle(panel)
    pump_frames(3)
    if condition == "complete":
        if save:
            assert "Saved rest stock" in panel.artifact_status.text
            assert json.loads(path.read_text())["stock"] == json.loads(json.dumps(stock.snapshot()))
            geometry.assert_not_called()
        else:
            assert "Loaded rest stock" in panel.note.text
            assert panel.rest_stock is not stock
            geometry.assert_called_once()
    else:
        assert panel.rest_stock is stock
        assert path.read_bytes() == before
        geometry.assert_not_called()
        if condition != "cancel":
            assert "Snapshot not applied" in transfer.status.text
    assert not list(path.parent.glob(".carvera-residual-*.pending"))
    send.assert_not_called()


@pytest.mark.parametrize("save", [False, True])
@pytest.mark.parametrize("condition", ["cancel", "setup", "complete"])
def test_snapshot_and_view_preparation_run_off_ui(transfer_case, monkeypatch, save, condition):
    import carveracontroller.desktop_stock_transfer as module

    panel, viewer, asset, path, stock, geometry, send = transfer_case
    before = path.read_bytes()
    entered, release = threading.Event(), threading.Event()
    ui = threading.get_ident()
    if save:
        original = StockVolume.snapshot

        def prepare(self, **kwargs):
            assert threading.get_ident() != ui
            entered.set()
            assert release.wait(5)
            return original(self, **kwargs)

        monkeypatch.setattr(StockVolume, "snapshot", prepare)
    else:
        original = module.stock_geometry

        def prepare(*args, **kwargs):
            assert threading.get_ident() != ui
            entered.set()
            assert release.wait(5)
            return original(*args, **kwargs)

        monkeypatch.setattr(module, "stock_geometry", prepare)
    transfer = panel._start_stock_transfer(path, save=save)
    try:
        assert entered.wait(3)
        pump_frames(3, sleep=0.01)
        assert transfer.active and not transfer.cancel.disabled
        if condition == "cancel":
            transfer.cancel.dispatch("on_release")
        elif condition == "setup":
            viewer.machine_setup = replace(viewer.machine_setup, work_offset_mm=(2, 0, 0))
    finally:
        release.set()
    settle(panel)
    pump_frames(3)
    if condition != "complete":
        assert panel.rest_stock is stock and path.read_bytes() == before
        geometry.assert_not_called()
    assert not list(path.parent.glob(".carvera-residual-*.pending"))
    send.assert_not_called()


def test_destination_changed_during_save_is_preserved(transfer_case, monkeypatch):
    panel, viewer, asset, path, stock, geometry, send = transfer_case
    entered, release = threading.Event(), threading.Event()
    original = StockVolume.snapshot

    def prepare(self, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(self, **kwargs)

    monkeypatch.setattr(StockVolume, "snapshot", prepare)
    transfer = panel._start_stock_transfer(path, save=True)
    try:
        assert entered.wait(3)
        path.write_bytes(b"other writer's new contents")
    finally:
        release.set()
    settle(panel)
    assert path.read_bytes() == b"other writer's new contents"
    assert "Destination changed" in transfer.status.text
    assert not list(path.parent.glob(".carvera-residual-*.pending"))
    send.assert_not_called()


@pytest.mark.parametrize("stage", ["construct", "start", "replace"])
def test_worker_or_publication_failure_retains_destination(transfer_case, monkeypatch, stage):
    import carveracontroller.desktop_stock_transfer as module

    panel, viewer, asset, path, stock, geometry, send = transfer_case
    before = path.read_bytes()
    if stage == "replace":
        monkeypatch.setattr(module.os, "replace", Mock(side_effect=OSError("synthetic publication failure")))
    elif stage == "construct":
        monkeypatch.setattr(module.threading, "Thread", Mock(side_effect=RuntimeError("synthetic launch failure")))
    else:
        monkeypatch.setattr(
            module.threading,
            "Thread",
            Mock(return_value=SimpleNamespace(start=Mock(side_effect=OSError("synthetic launch failure")))),
        )
    transfer = panel._start_stock_transfer(path, save=True)
    settle(panel)
    assert not transfer.active and not transfer.cancel.disabled
    assert path.read_bytes() == before and panel.rest_stock is stock
    assert not list(path.parent.glob(".carvera-residual-*.pending"))
    send.assert_not_called()


@pytest.mark.parametrize("payload", [None, [], "invalid", {}, {"schema": 1, "units": "mm"}])
def test_malformed_stock_leaves_close_available_and_prior_result_intact(transfer_case, payload):
    panel, viewer, asset, path, stock, geometry, send = transfer_case
    document = json.loads(path.read_text())
    document["stock"] = payload
    path.write_text(json.dumps(document))
    before = path.read_bytes()
    transfer = panel._start_stock_transfer(path, save=False)
    settle(panel)
    assert not transfer.active and not transfer.cancel.disabled and transfer.cancel.text == "Close"
    assert "Snapshot not applied" in transfer.status.text
    assert panel.rest_stock is stock and path.read_bytes() == before
    geometry.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize("save", [False, True])
@pytest.mark.parametrize("condition", ["complete", "cancel", "setup", "invalid"])
def test_final_ui_delivery_and_publication_decision_reject_obsolete_request(
    transfer_case, monkeypatch, save, condition
):
    import carveracontroller.desktop_stock_transfer as module

    panel, viewer, asset, path, stock, geometry, send = transfer_case
    before = path.read_bytes()
    real = module.Clock.schedule_once
    queued, reached = [], threading.Event()

    def capture(callback, timeout=0):
        target = "_approve" if save else "_finish"
        if target in callback.__code__.co_names:
            queued.append(callback)
            reached.set()
            return None
        return real(callback, timeout)

    monkeypatch.setattr(module.Clock, "schedule_once", capture)
    transfer = panel._start_stock_transfer(path, save=save)
    assert reached.wait(3)
    assert transfer.active and path.read_bytes() == before and panel.rest_stock is stock
    if condition == "cancel":
        transfer.cancel.dispatch("on_release")
    elif condition == "setup":
        viewer.machine_setup = replace(viewer.machine_setup, work_offset_mm=(1, 0, 0))
    elif condition == "invalid":
        # Deliberately corrupt a detached definition after model validation to
        # exercise the delivery guard's defensive handling of invalid UI state.
        invalid = replace(viewer.machine_setup)
        object.__setattr__(invalid, "stock_size_mm", (float("nan"), 2, 2))
        viewer.machine_setup = invalid
    monkeypatch.setattr(module.Clock, "schedule_once", real)
    queued[0](0)
    settle(panel)
    pump_frames(3)
    if condition != "complete":
        assert path.read_bytes() == before and panel.rest_stock is stock
        geometry.assert_not_called()
    assert not list(path.parent.glob(".carvera-residual-*.pending"))
    send.assert_not_called()
