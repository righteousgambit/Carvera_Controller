"""Ordinary local previews retain exactly the text their worker parsed."""

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


def test_empty_local_preview_clears_previous_distance_and_retains_empty_text(kivy_app, tmp_path, monkeypatch):
    app, root = kivy_app, kivy_app.root
    path = tmp_path / "empty.nc"
    monkeypatch.setattr(root.controller, "set_program_source", Mock())
    send = Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    path.write_text(SOURCE)
    load(app, path)
    assert root.gcode_viewer_distance > 0
    path.write_text("")
    program = load(app, path)
    assert program.lines == () and root.gcode_viewer_distance == 0
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


@pytest.mark.parametrize("change", ["generation", "local", "remote", "parser_identity"])
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
    else:
        root._loading_program_hash = "e" * 64
    new_hash = "e" * 64
    root.gcode_viewer.set_loaded_program_identity(new_hash)
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
        assert root.loading_file  # A stale completion cannot release a newer owner.
        send.assert_not_called()
    finally:
        root.loading_file = False
        root.progress_popup.dismiss()
