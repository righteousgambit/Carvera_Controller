"""Ordinary local previews retain exactly the text their worker parsed."""

import copy
import hashlib
import threading
import time
from unittest.mock import Mock

import pytest

from tests.integration.conftest import pump_frames

SOURCE = "(operation: Read once)\nG21 G90 G54\nT1 M6\nG0 X1 Y2 Z10\nG1 X5 F100\n"


def until(predicate, message):
    deadline = time.monotonic() + 10
    while not predicate() and time.monotonic() < deadline:
        pump_frames(1, sleep=0.005)
    assert predicate(), message


def load(app, path):
    completed = []
    app.root.file_popup.local_rv.curr_selected_file = str(path)
    app.root.view_local_file(on_loaded=lambda *args: completed.append(args))
    until(lambda: completed, "Local preview did not finish")
    assert completed == [(True, "")]
    panel = app.root.desktop_workspace.operation_panel
    until(lambda: panel.program is not None, panel.note.text)
    return panel.program


@pytest.mark.parametrize("with_callback", [False, True])
@pytest.mark.parametrize("mutation", ["replace", "delete"])
def test_local_preview_completion_analyses_worker_text_without_reopening_path(
    kivy_app, tmp_path, monkeypatch, mutation, with_callback
):
    app, root = kivy_app, kivy_app.root
    ws, panel = root.desktop_workspace, root.desktop_workspace.operation_panel
    path = tmp_path / "ordinary.nc"
    path.write_bytes(SOURCE.replace("\n", "\r\n").encode())
    entered, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()
    source_threads = []

    def source_observer(_path, lines):
        source_threads.append(threading.get_ident())
        assert isinstance(lines, tuple) and "".join(lines) == SOURCE
        entered.set()
        assert release.wait(10)

    monkeypatch.setattr(root.controller, "set_program_source", source_observer)
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    completed = []
    root.file_popup.local_rv.curr_selected_file = str(path)
    try:
        options = {"on_loaded": lambda *args: completed.append(args)} if with_callback else {}
        root.view_local_file(**options)
        until(entered.is_set, "Parser worker did not retain its input")
        if mutation == "replace":
            path.write_text("G20 G90\nT9 M6\nG0 X99\n")
        else:
            path.unlink()
        release.set()
        until(lambda: ws.retained_program_source(str(path)) is not None, "Preview source completion missing")
        assert completed == ([(True, "")] if with_callback else [])
        until(
            lambda: panel.program is not None and panel.program.file_hash == root.gcode_viewer.loaded_program_hash,
            panel.note.text,
        )
        digest = hashlib.sha256(SOURCE.encode()).hexdigest()
        assert panel.program.file_hash == digest
        retained = ws.retained_program_source(str(path))
        assert retained is not None and retained.source_hash == digest
        assert tuple(root.lines) == retained.lines
        assert source_threads and main_thread not in source_threads
        settings = panel.analysis_settings
        settings.dialect.text = "LinuxCNC · spline study"
        settings.apply_action.dispatch("on_release")
        until(lambda: panel.program is not None, panel.note.text)
        assert panel.program.file_hash == digest and panel.program.dialect == "linuxcnc"
        send.assert_not_called()
    finally:
        release.set()


def test_same_path_ordinary_reload_replaces_analysis_and_retained_owner(kivy_app, tmp_path, monkeypatch):
    app = kivy_app
    path = tmp_path / "reload.nc"
    path.write_text(SOURCE)
    send = Mock()
    monkeypatch.setattr(app.root.controller, "executeCommand", send)
    monkeypatch.setattr(app.root.controller, "set_program_source", Mock())
    first = load(app, path)
    old = app.root.desktop_workspace.retained_program_source(str(path))
    replacement = SOURCE.replace("Read once", "Reloaded").replace("X5", "X15")
    path.write_text(replacement)
    second = load(app, path)
    current = app.root.desktop_workspace.retained_program_source(str(path))
    assert second is not first and second.file_hash == hashlib.sha256(replacement.encode()).hexdigest()
    assert current.lines is not old.lines and current.generation > old.generation
    assert not app.root.desktop_workspace.accept_completed_program_source(old)
    assert app.root.desktop_workspace.retained_program_source(str(path)) is current
    send.assert_not_called()


@pytest.mark.parametrize("rotary", [False, True])
def test_empty_local_preview_clears_previous_distance_and_retains_empty_text(kivy_app, tmp_path, monkeypatch, rotary):
    app, root = kivy_app, kivy_app.root
    path = tmp_path / "empty.nc"
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    path.write_text(SOURCE + ("G0 A90\n" if rotary else ""))
    load(app, path)
    assert root.gcode_viewer_distance > 0
    viewer = root.gcode_viewer
    assert viewer.raw_positions and viewer.raw_linenumbers
    assert viewer._machine_has_rotary_motion is rotary
    path.write_text("")
    program = load(app, path)
    assert program.lines == () and root.gcode_viewer_distance == 0
    for field in (
        "positions",
        "raw_positions",
        "raw_linenumbers",
        "raw_feed_rates",
        "raw_tools",
        "angles_of_vertices",
        "lengths",
        "line_times",
    ):
        assert not getattr(viewer, field), field
    assert viewer.total_distance == viewer.total_line_count == viewer.total_time == 0
    assert not viewer._machine_has_rotary_motion and not viewer.is_4_axis and not app.has_4axis
    assert viewer._preview_program_point == (0, 0, 0)
    visible = viewer.machine_visible
    try:
        assert viewer.set_machine_visible(True) and viewer.machine_visible
    finally:
        viewer.set_machine_visible(visible)
    assert root.desktop_workspace.retained_program_source(str(path)).lines == ()
    path.unlink()
    root.desktop_workspace.operation_panel.load(str(path))
    until(lambda: root.desktop_workspace.operation_panel.program is not None, "Empty retained analysis unavailable")
    assert root.desktop_workspace.operation_panel.program.file_hash == hashlib.sha256(b"").hexdigest()
    send.assert_not_called()


def test_analysis_observer_failure_preserves_completed_preview_and_callback(kivy_app, tmp_path, monkeypatch):
    app, root = kivy_app, kivy_app.root
    path = tmp_path / "observer-fault.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    monkeypatch.setattr(
        root.desktop_workspace, "accept_completed_program_source", Mock(side_effect=RuntimeError("observer fault"))
    )
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    completed = []
    root.file_popup.local_rv.curr_selected_file = str(path)
    root.view_local_file(on_loaded=lambda *args: completed.append(args))
    until(lambda: completed, "Observer failure lost preview completion")
    assert completed == [(True, "")]
    assert root.gcode_viewer.loaded_program_hash == hashlib.sha256(SOURCE.encode()).hexdigest()
    assert not root.loading_file
    send.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        "generation",
        "local",
        "remote",
        "parser_identity",
        "display",
        "same_hash",
        "same_none",
        "identity_aba",
        "manager",
    ],
)
def test_superseded_ordinary_completion_cannot_finish_or_publish_old_preview(kivy_app, tmp_path, monkeypatch, change):
    import carveracontroller.main as main

    app, root = kivy_app, kivy_app.root
    path = tmp_path / "superseded.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    clock, starts, chunks, queued = main.Clock, [], [], []

    class ClockProxy:
        def __getattr__(self, name):
            return getattr(clock, name)

        def schedule_once(self, callback, timeout=0):
            if getattr(callback, "__name__", "") == "start_loaded":
                starts.append(callback)
                return None
            if getattr(getattr(callback, "func", None), "__name__", "") == "load_owned_chunk":
                chunks.append(callback)
                return None
            if getattr(callback, "__name__", "") == "finish_loaded":
                queued.append(callback)
                return None
            return clock.schedule_once(callback, timeout)

    monkeypatch.setattr(main, "Clock", ClockProxy())
    completed = []
    root.file_popup.local_rv.curr_selected_file = str(path)
    root.view_local_file(on_loaded=lambda *args: completed.append(args))
    until(lambda: queued, "Ordinary completion was not queued")
    assert len(starts) == len(chunks) == len(queued) == 1
    # Queueing completion does not mean the UI has started or drawn the load.
    # Establish both real phases before superseding this owned completion.
    starts[0](0)
    chunks[0](0)
    assert root.loading_file and root.gcode_viewer.raw_positions
    if change == "generation":
        root.program_preview_generation += 1
    elif change == "local":
        app.selected_local_filename = str(tmp_path / "newer.nc")
    elif change == "remote":
        app.selected_remote_filename = "newer-remote.nc"
    elif change == "parser_identity":
        root._loading_program_hash = "e" * 64
    elif change == "display":
        root.gcode_viewer.set_loaded_program_identity("e" * 64)
    elif change == "same_hash":
        root.gcode_viewer.set_loaded_program_identity(hashlib.sha256(SOURCE.encode()).hexdigest())
    elif change == "same_none":
        root.gcode_viewer.set_loaded_program_identity(None)
    elif change == "identity_aba":
        root.gcode_viewer.set_loaded_program_identity("e" * 64)
        root.gcode_viewer.set_loaded_program_identity(None)
    else:
        # Preserve valid geometry for the live frame while changing ownership.
        root.gcode_viewer.meshmanager = copy.deepcopy(root.gcode_viewer.meshmanager)
    new_hash = root.gcode_viewer.loaded_program_hash
    new_manager = root.gcode_viewer.meshmanager
    finish = Mock(wraps=root.load_end)
    accept = Mock(wraps=root.desktop_workspace.accept_completed_program_source)
    monkeypatch.setattr(root, "load_end", finish)
    monkeypatch.setattr(root.desktop_workspace, "accept_completed_program_source", accept)
    try:
        queued[0](0)
        assert completed == [(False, "Program preview superseded by a newer load")]
        finish.assert_not_called()
        accept.assert_not_called()
        assert root.gcode_viewer.loaded_program_hash == new_hash
        assert root.gcode_viewer.meshmanager is new_manager
        assert root.loading_file  # A stale completion cannot release a newer owner.
        send.assert_not_called()
    finally:
        root.loading_file = False
        root.progress_popup.dismiss()


@pytest.mark.parametrize("change", ["display", "same_none", "identity_aba", "manager", "unfinished"])
def test_queued_chunk_cannot_adopt_a_replaced_display_or_complete_without_buffers(
    kivy_app, tmp_path, monkeypatch, change
):
    import carveracontroller.main as main

    app, root = kivy_app, kivy_app.root
    path = tmp_path / "queued-chunk.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    clock, starts, chunks, finishes = main.Clock, [], [], []

    class ClockProxy:
        def __getattr__(self, name):
            return getattr(clock, name)

        def schedule_once(self, callback, timeout=0):
            if getattr(callback, "__name__", "") == "start_loaded":
                starts.append(callback)
                return None
            if getattr(getattr(callback, "func", None), "__name__", "") == "load_owned_chunk":
                chunks.append(callback)
                return None
            if getattr(callback, "__name__", "") == "finish_loaded":
                finishes.append(callback)
                return None
            return clock.schedule_once(callback, timeout)

    monkeypatch.setattr(main, "Clock", ClockProxy())
    completed = []
    root.file_popup.local_rv.curr_selected_file = str(path)
    root.view_local_file(on_loaded=lambda *args: completed.append(args))
    until(lambda: chunks and finishes, "Loader did not queue its final chunk and completion")
    assert len(starts) == len(chunks) == len(finishes) == 1
    # Start owns the empty display before a replacement invalidates its chunk.
    # Keep the chunk queued so this test can reject it, or leave it unfinished.
    starts[0](0)
    assert root.loading_file
    if change == "display":
        root.gcode_viewer.set_loaded_program_identity("a" * 64)
    elif change == "same_none":
        root.gcode_viewer.set_loaded_program_identity(None)
    elif change == "identity_aba":
        root.gcode_viewer.set_loaded_program_identity("a" * 64)
        root.gcode_viewer.set_loaded_program_identity(None)
    elif change == "manager":
        root.gcode_viewer.meshmanager = copy.deepcopy(root.gcode_viewer.meshmanager)
    display_hash, manager = root.gcode_viewer.loaded_program_hash, root.gcode_viewer.meshmanager
    draw = Mock(wraps=root.load_gcodes)
    finish = Mock(wraps=root.load_end)
    monkeypatch.setattr(root, "load_gcodes", draw)
    monkeypatch.setattr(root, "load_end", finish)
    try:
        if change != "unfinished":
            chunks[0](0)
        finishes[0](0)
        draw.assert_not_called()
        finish.assert_not_called()
        assert completed == [(False, "Program preview superseded by a newer load")]
        assert root.gcode_viewer.loaded_program_hash == display_hash
        assert root.gcode_viewer.meshmanager is manager
        assert root.loading_file
        send.assert_not_called()
    finally:
        root.loading_file = False
        root.progress_popup.dismiss()


@pytest.mark.parametrize("observer", ["start", "progress", "render"])
def test_reentrant_observer_cannot_turn_its_replacement_into_loader_owned_state(
    kivy_app, tmp_path, monkeypatch, observer
):
    import carveracontroller.main as main

    app, root = kivy_app, kivy_app.root
    viewer = root.gcode_viewer
    path = tmp_path / "observer-replacement.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    clock, starts, chunks, finishes, replacements, completed = main.Clock, [], [], [], [], []

    class ClockProxy:
        def __getattr__(self, name):
            return getattr(clock, name)

        def schedule_once(self, callback, timeout=0):
            if getattr(callback, "__name__", "") == "start_loaded":
                starts.append(callback)
                return None
            if getattr(getattr(callback, "func", None), "__name__", "") == "load_owned_chunk":
                chunks.append(callback)
                return None
            if getattr(callback, "__name__", "") == "finish_loaded":
                finishes.append(callback)
                return None
            return clock.schedule_once(callback, timeout)

    monkeypatch.setattr(main, "Clock", ClockProxy())

    def replace():
        if not replacements:
            # Publish an independently owned but internally coherent model;
            # replacing only a manager with empty data would invalidate the
            # live frame's existing array aliases before this test's teardown.
            manager = copy.deepcopy(viewer.meshmanager)
            replacements.append(manager)
            viewer.meshmanager = manager
            viewer.set_loaded_program_identity("e" * 64)

    def progress_changed(_popup, value):
        if value > 0:
            replace()

    def playing_changed(_root, value):
        if value is False:
            replace()

    if observer == "start":
        root.bind(gcode_playing=playing_changed)
    elif observer == "progress":
        root.progress_popup.bind(progress_value=progress_changed)
    else:
        publish = viewer._publish_program_mesh

        def render_then_replace(*args, **kwargs):
            publish(*args, **kwargs)
            replace()

        monkeypatch.setattr(viewer, "_publish_program_mesh", render_then_replace)
    root.file_popup.local_rv.curr_selected_file = str(path)
    end = Mock(wraps=root.load_end)
    accept = Mock(wraps=root.desktop_workspace.accept_completed_program_source)
    monkeypatch.setattr(root, "load_end", end)
    monkeypatch.setattr(root.desktop_workspace, "accept_completed_program_source", accept)
    try:
        root.view_local_file(on_loaded=lambda *args: completed.append(args))
        until(lambda: finishes, "Loader did not queue completion")
        assert len(starts) == 1
        # A fast worker can queue finish before the UI clock runs start.
        # Drive the real queued callbacks explicitly and arm the property
        # transition immediately before start, independent of frame cadence.
        if observer == "start":
            monkeypatch.setattr(root, "gcode_playing", True)
        starts[0](0)
        if observer != "start":
            assert chunks
            chunks[0](0)
        assert replacements, "Observer did not publish a replacement"
        finishes[0](0)
        assert completed == [(False, "Program preview superseded by a newer load")]
        assert viewer.meshmanager is replacements[0] and viewer.loaded_program_hash == "e" * 64
        end.assert_not_called()
        accept.assert_not_called()
        send.assert_not_called()
    finally:
        root.unbind(gcode_playing=playing_changed)
        root.progress_popup.unbind(progress_value=progress_changed)
        root.loading_file = False
        root.progress_popup.dismiss()


@pytest.mark.parametrize("stage", ["clear", "begin", "render", "progress", "finish", "finish_late"])
@pytest.mark.parametrize("with_callback", [False, True])
def test_owned_preview_fault_releases_busy_state_and_reports_original_error(
    kivy_app, tmp_path, monkeypatch, stage, with_callback
):
    app, root = kivy_app, kivy_app.root
    viewer, ws = root.gcode_viewer, root.desktop_workspace
    path = tmp_path / "owned-fault.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    events, faults = [], []
    error = "owned-" + stage + "-fault"

    def fail(*_args, **_kwargs):
        faults.append(1)
        raise RuntimeError(error)

    def progress_fail(_popup, value):
        if value > 0:
            fail()

    if stage == "progress":
        root.progress_popup.bind(progress_value=progress_fail)
    elif stage == "finish":
        monkeypatch.setattr(root, "refresh_gcode_color_legend", fail)
    elif stage == "finish_late":
        monkeypatch.setattr(root, "_apply_tool_change_markers", fail)
    else:
        target = {
            "clear": "_detach_machine_scene",
            "begin": "set_rest_stock_geometry",
            "render": "_publish_program_mesh",
        }[stage]
        monkeypatch.setattr(viewer, target, fail)
    root.file_popup.local_rv.curr_selected_file = str(path)
    options = {"on_loaded": lambda *args: events.append(args)} if with_callback else {}
    try:
        root.view_local_file(**options)
        until(
            lambda: (
                error in root.message_popup.lb_content.text
                and not root.loading_file
                and root.progress_popup.parent is None
            ),
            "Owned preview fault did not finish error reporting and release its progress modal",
        )
        assert faults and not root.loading_file and root.progress_popup.parent is None
        assert viewer.loaded_program_hash is None and root._last_loaded_file_key is None
        assert ws.retained_program_source(str(path)) is None
        assert ws.operation_panel.program is None and root.gcode_cannot_visualise
        assert events == ([(False, error)] if with_callback else [])
        send.assert_not_called()
    finally:
        root.progress_popup.unbind(progress_value=progress_fail)
        root.message_popup.dismiss()


@pytest.mark.parametrize("replacement", ["display", "generation"])
def test_render_fault_cannot_release_or_report_over_a_replacement_owner(kivy_app, tmp_path, monkeypatch, replacement):
    app, root = kivy_app, kivy_app.root
    viewer = root.gcode_viewer
    path = tmp_path / "retired-fault.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    replaced, events = [], []

    def fail():
        if replacement == "display":
            manager = copy.deepcopy(viewer.meshmanager)
            viewer.meshmanager = manager
            viewer.set_loaded_program_identity("e" * 64)
            replaced.append(manager)
        else:
            root.program_preview_generation += 1
        # Establish the replacement owner's actual modal, rather than assume
        # a prior test/request's closing progress animation is still open.
        from kivy.animation import Animation

        Animation.cancel_all(root.progress_popup)
        root.progress_popup.dismiss(animation=False)
        root.progress_popup.open()
        root.progress_popup.progress_text = "Newer owner progress"
        raise RuntimeError("retired-render-fault")

    monkeypatch.setattr(viewer, "_publish_program_mesh", fail)
    report = Mock(wraps=root.load_error)
    end = Mock(wraps=root.load_end)
    accept = Mock(wraps=root.desktop_workspace.accept_completed_program_source)
    monkeypatch.setattr(root, "load_error", report)
    monkeypatch.setattr(root, "load_end", end)
    monkeypatch.setattr(root.desktop_workspace, "accept_completed_program_source", accept)
    root.file_popup.local_rv.curr_selected_file = str(path)
    try:
        root.view_local_file(on_loaded=lambda *args: events.append(args))
        until(lambda: events, "Retired request lost its failure callback")
        assert events == [(False, "retired-render-fault")]
        assert root.loading_file and root.progress_popup.parent is not None
        assert root.progress_popup.progress_text == "Newer owner progress"
        if replaced:
            assert viewer.meshmanager is replaced[0] and viewer.loaded_program_hash == "e" * 64
        report.assert_not_called()
        end.assert_not_called()
        accept.assert_not_called()
        send.assert_not_called()
    finally:
        root.loading_file = False
        root.progress_popup.dismiss()


@pytest.mark.parametrize("empty_retry", [False, True])
def test_explicit_retry_after_owned_fault_can_load_nonempty_or_empty_input(
    kivy_app, tmp_path, monkeypatch, empty_retry
):
    app, root = kivy_app, kivy_app.root
    viewer = root.gcode_viewer
    path = tmp_path / "retry.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    publish = viewer._publish_program_mesh
    calls, events = [], []

    def flaky(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("recoverable-render-fault")
        return publish(*args, **kwargs)

    monkeypatch.setattr(viewer, "_publish_program_mesh", flaky)
    root.file_popup.local_rv.curr_selected_file = str(path)
    root.view_local_file(on_loaded=lambda *args: events.append(args))
    until(
        lambda: events and not root.loading_file and root.progress_popup.parent is None,
        "Initial renderer fault did not release its request",
    )
    assert events == [(False, "recoverable-render-fault")] and len(calls) == 1
    assert viewer.loaded_program_hash is None
    root.message_popup.dismiss(animation=False)
    text = "" if empty_retry else SOURCE
    path.write_text(text)
    program = load(app, path)  # A second explicit local-preview gesture.
    assert program.file_hash == hashlib.sha256(text.encode()).hexdigest()
    assert viewer.loaded_program_hash == program.file_hash
    assert not root.loading_file and not root.gcode_cannot_visualise
    assert len(calls) == (1 if empty_retry else 2)
    send.assert_not_called()


@pytest.mark.parametrize("phase", ["before_identity", "after_identity"])
@pytest.mark.parametrize("replacement", ["display", "generation", "parser_identity"])
@pytest.mark.parametrize("raises", [False, True])
def test_completion_observer_preserves_newer_request(kivy_app, tmp_path, monkeypatch, phase, replacement, raises):
    from kivy.animation import Animation

    app, root = kivy_app, kivy_app.root
    viewer = root.gcode_viewer
    path = tmp_path / "completion-owner.nc"
    path.write_text(SOURCE)
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    events, changed = [], []
    method = "refresh_gcode_color_legend" if phase == "before_identity" else "_apply_tool_change_markers"
    original = getattr(root, method)

    def replace(*args, **kwargs):
        original(*args, **kwargs)
        if changed:
            return
        if replacement == "display":
            viewer.meshmanager = copy.deepcopy(viewer.meshmanager)
            viewer.set_loaded_program_identity("e" * 64)
        elif replacement == "generation":
            root.program_preview_generation += 1
        else:
            root._loading_program_hash = "f" * 64
        changed.append((viewer.meshmanager, viewer.loaded_program_hash))
        root.loading_file = True
        root.progressStart("Replacement completion owner", None)
        if raises:
            raise RuntimeError("retired-completion-fault")

    monkeypatch.setattr(root, method, replace)
    report = Mock(wraps=root.load_error)
    accept = Mock(wraps=root.desktop_workspace.accept_completed_program_source)
    monkeypatch.setattr(root, "load_error", report)
    monkeypatch.setattr(root.desktop_workspace, "accept_completed_program_source", accept)
    root.file_popup.local_rv.curr_selected_file = str(path)
    try:
        root.view_local_file(on_loaded=lambda *args: events.append(args))
        until(lambda: events, "Completion replacement did not settle")
        assert len(changed) == 1 and events[0][0] is False
        expected = "retired-completion-fault" if raises else "Program preview superseded during completion"
        assert events == [(False, expected)]
        pump_frames(15, sleep=0.02)
        assert viewer.meshmanager is changed[0][0] and viewer.loaded_program_hash == changed[0][1]
        assert root.loading_file and root.progress_popup.parent is not None
        assert root.progress_popup.progress_text == "Replacement completion owner"
        report.assert_not_called()
        accept.assert_not_called()
        send.assert_not_called()
    finally:
        root.loading_file = False
        Animation.cancel_all(root.progress_popup)
        root.progress_popup.dismiss(animation=False)


def test_progress_reopen_survives_previous_dismiss_animation(kivy_app, monkeypatch):
    root = kivy_app.root
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    root.progressStart("First task", None)
    pump_frames(15, sleep=0.02)
    root.progressFinish()
    root.progressStart("Second task", None)
    pump_frames(15, sleep=0.02)
    assert root.progress_popup.parent is not None
    assert root.progress_popup.progress_text == "Second task"
    assert root.progress_popup._anim_alpha == 1.0
    root.progressFinish()
    until(lambda: root.progress_popup.parent is None, "Second task cannot close its own progress")
    send.assert_not_called()
