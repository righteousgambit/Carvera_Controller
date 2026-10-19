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
    clock, queued = main.Clock, []

    class ClockProxy:
        def __getattr__(self, name):
            return getattr(clock, name)

        def schedule_once(self, callback, timeout=0):
            if getattr(callback, "__name__", "") == "finish_loaded":
                queued.append(callback)
                return None
            return clock.schedule_once(callback, timeout)

    monkeypatch.setattr(main, "Clock", ClockProxy())
    completed = []
    root.file_popup.local_rv.curr_selected_file = str(path)
    root.view_local_file(on_loaded=lambda *args: completed.append(args))
    until(lambda: queued, "Ordinary completion was not queued")
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
        root.gcode_viewer.meshmanager = type(root.gcode_viewer.meshmanager)()
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
    clock, chunks, finishes = main.Clock, [], []

    class ClockProxy:
        def __getattr__(self, name):
            return getattr(clock, name)

        def schedule_once(self, callback, timeout=0):
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
    if change == "display":
        root.gcode_viewer.set_loaded_program_identity("a" * 64)
    elif change == "same_none":
        root.gcode_viewer.set_loaded_program_identity(None)
    elif change == "identity_aba":
        root.gcode_viewer.set_loaded_program_identity("a" * 64)
        root.gcode_viewer.set_loaded_program_identity(None)
    elif change == "manager":
        root.gcode_viewer.meshmanager = type(root.gcode_viewer.meshmanager)()
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
    clock, chunks, finishes, replacements, completed = main.Clock, [], [], [], []

    class ClockProxy:
        def __getattr__(self, name):
            return getattr(clock, name)

        def schedule_once(self, callback, timeout=0):
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
        monkeypatch.setattr(root, "gcode_playing", True)
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
