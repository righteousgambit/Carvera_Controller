"""Prepared portable programs publish retained source and recover previous models."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.desktop_program_preparation import prepare_program_preview
from carveracontroller.desktop_program_publication import publish_program_preview
from carveracontroller.machine.job_program_validation import PreviewParserInputs
from tests.integration.conftest import load_gcode_file, pump_frames


@pytest.fixture
def staged(kivy_app, tmp_path, monkeypatch):
    app, root = kivy_app, kivy_app.root
    old = tmp_path / "old.nc"
    old.write_text("G21 G90\nT1 M6\nG0 X1 Y2 Z3\nG1 X2 F100\n")
    root.gcode_viewer.set_machine_visible(False)
    app.selected_local_filename = str(old)
    load_gcode_file(app, str(old))
    viewer = root.gcode_viewer
    new = tmp_path / "new.nc"
    raw = b"(operation: retained)\r\nG21 G90\r\nT2 M6\r\nG0 X8 Y9 Z10\r\nG1 X12 F100\r\n"
    new.write_bytes(raw)
    inputs = PreviewParserInputs(**PreviewParserInputs.declarations(CNC.vars, inch=CNC.inch, accuracy=CNC.accuracy))
    prepared = prepare_program_preview(
        raw.decode().replace("\r\n", "\n").splitlines(keepends=True),
        inputs,
        viewer.library_tool_table_mm,
        local_path=str(new),
        raw=raw,
    )
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    # Journal submission is tested separately; avoid shared fixture evidence writes.
    record = Mock()
    monkeypatch.setattr(root.controller, "publish_prepared_program_source", record)
    old_manager, old_hash = viewer.meshmanager, viewer.loaded_program_hash
    rows = list(root.gcode_rv.data)
    yield SimpleNamespace(
        app=app,
        root=root,
        viewer=viewer,
        prepared=prepared,
        path=new,
        old=old,
        old_manager=old_manager,
        old_hash=old_hash,
        rows=rows,
        record=record,
        send=send,
    )
    root.desktop_workspace.close_local_preview()
    pump_frames(2)
    send.assert_not_called()


def test_apply_retains_worker_buffers_and_source_even_when_staging_file_changes(staged, monkeypatch):
    s = staged
    s.path.write_text("G20\nT9\n")
    callback = Mock()
    monkeypatch.setattr(CNC, "parseLine", Mock(side_effect=AssertionError("No UI parsing")))
    s.root.file_popup.local_rv.curr_selected_file = str(s.path)
    s.root.view_local_file(program_lines=s.prepared.program.lines, prepared_program=s.prepared, on_loaded=callback)
    assert s.viewer.meshmanager is s.prepared.manager
    assert s.viewer.loaded_program_hash == s.prepared.program.source_hash
    assert s.root.lines == list(s.prepared.program.lines)
    assert s.root.used_tools == [2] and s.root.upcoming_tool == 2
    assert s.app.selected_local_filename == str(s.path) and s.app.selected_remote_filename == ""
    assert s.root.gcode_rv.data[-1]["text"] == "G1 X12 F100"
    s.record.assert_called_once_with(s.prepared.manifest)
    callback.assert_called_once_with(True, "")
    assert s.old_manager is not s.viewer.meshmanager
    assert s.old_manager.raw_positions != s.viewer.meshmanager.raw_positions


@pytest.mark.parametrize("stage", ["draw", "page", "finish"])
def test_failed_publication_restores_previous_program_and_keeps_generation_advanced(staged, monkeypatch, stage):
    s = staged
    generation = s.root.program_preview_generation
    original = {"draw": s.viewer._publish_program_mesh, "page": s.root.load_page, "finish": s.root.load_end}[stage]
    calls = 0

    def fail_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            CNC.vars["wx"] = 123.456  # New telemetry must survive model recovery.
            raise RuntimeError("injected publication failure")
        return original(*args, **kwargs)

    target, name = (
        (s.viewer, "_publish_program_mesh")
        if stage == "draw"
        else (s.root, "load_page" if stage == "page" else "load_end")
    )
    monkeypatch.setattr(target, name, fail_once)
    monkeypatch.setitem(CNC.vars, "wx", CNC.vars.get("wx", 0))
    callback = Mock()
    with pytest.raises(RuntimeError, match="injected"):
        publish_program_preview(s.root, s.app, s.path, s.prepared, on_loaded=callback)
    assert s.viewer.meshmanager is s.old_manager and s.viewer.loaded_program_hash == s.old_hash
    assert s.app.selected_local_filename == str(s.old)
    assert s.root.gcode_rv.data == s.rows
    assert s.root.program_preview_generation == generation + 1 and not s.root.loading_file
    assert CNC.vars["wx"] == 123.456
    s.record.assert_not_called()
    callback.assert_not_called()


def test_persistent_renderer_failure_retains_model_and_withholds_identity(staged, monkeypatch):
    s = staged
    monkeypatch.setattr(s.viewer, "_publish_program_mesh", Mock(side_effect=RuntimeError("draw unavailable")))
    with pytest.raises(RuntimeError, match="draw unavailable"):
        publish_program_preview(s.root, s.app, s.path, s.prepared)
    assert s.viewer.meshmanager is s.old_manager and s.viewer.loaded_program_hash is None
    assert s.app.selected_local_filename == str(s.old) and s.root.gcode_rv.data == s.rows
    s.record.assert_not_called()


@pytest.mark.parametrize("change", ["path", "inputs", "busy", "tools", "identity"])
def test_stale_or_mismatched_preparation_never_replaces_previous_model(staged, monkeypatch, change):
    s = staged
    path, prepared = s.path, s.prepared
    if change == "path":
        path = s.old
    elif change == "inputs":
        monkeypatch.setitem(CNC.vars, "wcoz", CNC.vars.get("wcoz", 0) + 1)
    elif change == "busy":
        monkeypatch.setattr(s.root, "loading_file", True)
    elif change == "tools":
        prepared = replace(prepared, tool_profiles=({999: object()}, *prepared.tool_profiles[1:]))
    else:
        prepared = replace(prepared, manifest=replace(prepared.manifest, parsed_lines_sha256="a" * 64))
    with pytest.raises(ValueError):
        publish_program_preview(s.root, s.app, path, prepared)
    assert s.viewer.meshmanager is s.old_manager and s.viewer.loaded_program_hash == s.old_hash
    assert s.app.selected_local_filename == str(s.old)
    s.record.assert_not_called()


def test_completion_observer_failure_does_not_rewind_committed_program(staged):
    s = staged
    callback = Mock(side_effect=RuntimeError("observer failure"))
    assert publish_program_preview(s.root, s.app, s.path, s.prepared, on_loaded=callback)
    assert s.viewer.meshmanager is s.prepared.manager and s.viewer.loaded_program_hash == s.prepared.program.source_hash
    s.record.assert_called_once()
    callback.assert_called_once_with(True, "")


@pytest.mark.parametrize(
    "text",
    [
        "G21 G90\nT1 M6\nG0 X2 Y3 Z4\nG1 X5 F100\nG0 Z8\n",
        "G20 G90\nG0 X1 Y2 Z3\nG1 X2 F5\n",
        "G90\nG0 X1 Y0\nG2 X0 Y1 I-1 J0 F100\n",
        "G0 X1 A30\nG1 X2 A90 F100\n",
    ],
)
def test_worker_mesh_buffers_match_incremental_legacy(text, kivy_app, tmp_path):
    from carveracontroller.GcodeViewer import MeshManager
    from carveracontroller.machine.program_render_preparation import bridge_program_colors

    lines = text.splitlines(keepends=True)
    inputs = PreviewParserInputs(-3.0, 0.0, False, 0.1)
    prepared = prepare_program_preview(lines, inputs, {}, local_path=str(tmp_path / "missing.nc"), raw=text.encode())
    parser = CNC(variables={"clearance_z": -3.0, "wcoz": 0.0})
    parser.inch, parser.accuracy = False, 0.1
    legacy = MeshManager()
    for number, line in enumerate(lines, 1):
        parser.parseLine(line, number)
    legacy.add_data_arrs(bridge_program_colors(parser.coordinates), True)
    for key in (
        "positions",
        "raw_positions",
        "lengths",
        "vertex_types",
        "raw_linenumbers",
        "raw_tools",
        "raw_feed_rates",
        "angles_of_vertices",
        "vertices",
        "meshes",
        "position_scale",
    ):
        assert getattr(prepared.manager, key) == getattr(legacy, key), key
    assert prepared.manager._cancelled is None


def test_preparation_can_run_on_worker_while_ui_events_continue(kivy_app, tmp_path, monkeypatch):
    import threading
    import time

    from kivy.clock import Clock

    from carveracontroller import desktop_program_preparation as preparation

    entered, release = threading.Event(), threading.Event()
    original = preparation.prepare_legacy_program
    result = []

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(preparation, "prepare_legacy_program", held)
    worker = threading.Thread(
        target=lambda: result.append(
            preparation.prepare_program_preview(
                ["G1 X1 F100\n"],
                PreviewParserInputs(-3.0, 0.0, False, 0.1),
                {},
                local_path=str(tmp_path / "worker.nc"),
                raw=b"G1 X1 F100\n",
            )
        )
    )
    worker.start()
    assert entered.wait(5)
    pulses = []
    Clock.schedule_once(lambda _dt: pulses.append(threading.get_ident()), 0)
    try:
        pump_frames(2)
        assert pulses == [threading.get_ident()] and not result
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and len(result) == 1


def test_retained_manager_survives_next_reset(staged):
    s = staged
    positions = list(s.old_manager.raw_positions)
    s.viewer.begin_new_file_load()
    assert s.viewer.meshmanager is not s.old_manager
    assert s.old_manager.raw_positions == positions


def test_controller_manifest_publication_uses_retained_identity_without_source_io(staged, monkeypatch):
    from carveracontroller.Controller import Controller

    s = staged
    controller = s.root.controller
    evidence = Mock(side_effect=RuntimeError("journal fault"))
    monkeypatch.setattr(controller, "_write_evidence", evidence)
    old = controller.run_evidence.program
    try:
        s.path.unlink()
        record = Controller.publish_prepared_program_source(controller, s.prepared.manifest)
        assert record["sha256"] == s.prepared.manifest.sha256
        assert record["machine_file_identity"] == "unverified"
        assert controller.run_evidence.program == record
        assert "journal fault" in controller._recording_last_error
        s.send.assert_not_called()
    finally:
        controller.run_evidence.program = old


def test_late_time_estimate_cannot_overwrite_replacement_or_cleared_display(staged, monkeypatch):
    import carveracontroller.GcodeViewer as renderer

    s = staged
    workers = []

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    monkeypatch.setattr(renderer, "threading", SimpleNamespace(Thread=DeferredThread))
    apply = Mock()
    progress = Mock()
    monkeypatch.setattr(s.viewer, "_apply_line_times_result", apply)
    monkeypatch.setattr(s.viewer, "_report_time_estimate_progress", progress)
    s.viewer._compute_line_times_async()
    s.viewer._compute_line_times_async()
    assert len(workers) == 2
    workers[0]()
    pump_frames(2)
    apply.assert_not_called()
    # Only the current worker's queued start is permitted.
    progress.assert_called_once_with("start", 0)
    workers[1]()
    pump_frames(2)
    apply.assert_called_once()
    apply.reset_mock()
    s.viewer._compute_line_times_async()
    s.viewer.clearDisplay()
    workers[2]()
    pump_frames(2)
    apply.assert_not_called()
