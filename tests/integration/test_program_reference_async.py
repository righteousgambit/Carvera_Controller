"""Disk persistence cannot block inspection, navigation or dismissal."""

import threading
from unittest.mock import Mock

from kivy.clock import Clock

import carveracontroller.desktop_program_picker as picker
from carveracontroller.desktop_program_picker import ProgramBrowser
from carveracontroller.machine.program_places import ProgramPlaces
from carveracontroller.machine.program_preview import inspect_program
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_inspection import wait_for_inspection, wait_for_listing


def wait_for_saves(browser):
    for _ in range(60):
        pump_frames(2)
        if not browser._places_worker_running and not browser._favorite_pending:
            return
    raise AssertionError("Reference saves did not finish")


def test_workspace_reopen_serializes_accepted_saves_from_dismissed_browsers(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    store_path = tmp_path / "places.json"
    paths = [tmp_path / name for name in ("old.nc", "new.nc")]
    for path in paths:
        path.write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X8 F100\n")
    original_init, original_save = ProgramPlaces.__init__, ProgramPlaces._save
    entered, release, favorite_saved = (threading.Event() for _ in range(3))
    main_thread, save_threads, ticks = threading.get_ident(), [], []
    browsers = []

    def isolated_init(store, path=None, **kwargs):
        original_init(store, store_path if path is None else path, **kwargs)

    def delayed_save(store, recent, favorites):
        save_threads.append(threading.get_ident())
        if recent == [str(paths[0])] and not entered.is_set():
            entered.set()
            assert release.wait(5)
        original_save(store, recent, favorites)
        if favorites == [str(paths[1])]:
            favorite_saved.set()

    monkeypatch.setattr(ProgramPlaces, "__init__", isolated_init)
    monkeypatch.setattr(ProgramPlaces, "_save", delayed_save)
    monkeypatch.setattr(ws.machine.file_popup.local_rv, "curr_dir", str(tmp_path))
    monkeypatch.setattr(ws.app, "selected_local_filename", "")
    monkeypatch.setattr(ws, "program_browser", None, raising=False)
    send, upload, preview = Mock(), Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    monkeypatch.setattr(ws.machine, "view_local_file", preview)
    event = Clock.schedule_interval(lambda _dt: ticks.append(1), 0)
    try:
        ws._choose_program()
        first = ws.program_browser
        browsers.append(first)
        first.navigate(str(paths[0]))
        wait_for_inspection(first)
        assert entered.wait(1)
        first.dismiss()
        first_status = first.status.text

        ws._choose_program()
        reopened = ws.program_browser
        browsers.append(reopened)
        assert reopened is not first and reopened.saved_places is not first.saved_places
        assert reopened.saved_places.path == first.saved_places.path == store_path
        reopened.navigate(str(paths[1]))
        wait_for_inspection(reopened)
        reopened.toggle_favorite()
        reopened.toggle_favorite()  # One accepted click, even while the old writer is held.
        ticks_before = len(ticks)
        pump_frames(5)
        assert len(ticks) > ticks_before and reopened.thumbnail.segments and not reopened.preview_button.disabled
        # Give the previous per-browser workers time to demonstrate the lost
        # update: without store serialization this receipt precedes the old save.
        saved_while_old_pending = favorite_saved.wait(0.2)
        reopened.dismiss()
        reopened_status = reopened.status.text
        release.set()
        wait_for_saves(first)
        wait_for_saves(reopened)
        stored = ProgramPlaces(store_path)
        assert stored.recent == [str(paths[1]), str(paths[0])]
        assert stored.favorites == [str(paths[1])]
        assert not saved_while_old_pending
        assert main_thread not in save_threads
        assert first.status.text == first_status and reopened.status.text == reopened_status

        ws._choose_program()
        restored = ws.program_browser
        browsers.append(restored)
        restored.choose_collection("favorites")
        wait_for_listing(restored)
        assert [entry.path for entry in restored.entries] == [str(paths[1])]
        send.assert_not_called()
        upload.assert_not_called()
        preview.assert_not_called()
    finally:
        release.set()
        event.cancel()
        for browser in browsers:
            wait_for_saves(browser)
            browser.dismiss()


def test_blocked_recent_save_leaves_inspection_live_and_serializes_favorite_after_dismissal(
    kivy_app, tmp_path, monkeypatch
):
    entered, release = threading.Event(), threading.Event()
    main_thread = threading.get_ident()
    save_threads, ticks = [], []
    original = ProgramPlaces._save
    path = tmp_path / "part.nc"
    path.write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X8 F100\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace, places=ProgramPlaces(tmp_path / "places.json"))
    browser.local_path = str(tmp_path)
    browser.open()
    wait_for_listing(browser)
    send = Mock()
    monkeypatch.setattr(browser.root.controller, "executeCommand", send)

    def delayed(store, recent, favorites):
        save_threads.append(threading.get_ident())
        if not entered.is_set():
            entered.set()
            assert release.wait(5)
        original(store, recent, favorites)

    monkeypatch.setattr(ProgramPlaces, "_save", delayed)
    event = Clock.schedule_interval(lambda _dt: ticks.append(1), 0)
    try:
        browser.navigate(str(path))
        wait_for_inspection(browser)
        assert entered.wait(1)
        assert browser.inspection and browser.thumbnail.segments
        browser.toggle_favorite()
        browser.toggle_favorite()  # Duplicate pending click cannot toggle back.
        pump_frames(5)
        assert ticks and browser.favorite_button.disabled
        assert browser.favorite_button.text == "Saving favorite..."
        assert not browser.preview_button.disabled
        browser.dismiss()
        before = browser.status.text
        release.set()
        wait_for_saves(browser)
        stored = ProgramPlaces(browser.saved_places.path)
        assert stored.recent == [str(path)] and stored.favorites == [str(path)]
        assert len(save_threads) == 2 and main_thread not in save_threads
        assert browser.status.text == before
        send.assert_not_called()
    finally:
        release.set()
        event.cancel()
        browser.dismiss()


def test_favorite_save_failure_is_visible_and_new_selection_remains_inspectable(kivy_app, tmp_path, monkeypatch):
    paths = [tmp_path / name for name in ("first.nc", "second.nc")]
    for path in paths:
        path.write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X8 F100\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace, places=ProgramPlaces(tmp_path / "places.json"))
    browser.local_path = str(tmp_path)
    browser.open()
    entered, release = threading.Event(), threading.Event()
    original = ProgramPlaces.toggle_favorite

    def failed(store, path):
        entered.set()
        assert release.wait(5)
        raise OSError("disk unavailable")

    try:
        browser.navigate(str(paths[0]))
        wait_for_inspection(browser)
        wait_for_saves(browser)
        monkeypatch.setattr(ProgramPlaces, "toggle_favorite", failed)
        browser.toggle_favorite()
        assert entered.wait(1)
        browser.navigate(str(paths[1]))
        wait_for_inspection(browser)
        release.set()
        wait_for_saves(browser)
        assert browser.selected.path == str(paths[1])
        assert browser.inspection.digest == inspect_program(paths[1]).digest
        assert "disk unavailable" in browser.status.text
        assert not browser.favorite_button.disabled and not browser.preview_button.disabled
        assert ProgramPlaces(browser.saved_places.path).favorites == []
        monkeypatch.setattr(ProgramPlaces, "toggle_favorite", original)
        browser.toggle_favorite()
        wait_for_saves(browser)
        assert ProgramPlaces(browser.saved_places.path).favorites == [str(paths[1])]
    finally:
        release.set()
        browser.dismiss()


def test_listing_snapshot_captured_during_save_cannot_erase_saved_favorite(kivy_app, tmp_path, monkeypatch):
    save_entered, save_release = threading.Event(), threading.Event()
    read_entered, read_release = threading.Event(), threading.Event()
    path = tmp_path / "part.nc"
    path.write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X8 F100\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace, places=ProgramPlaces(tmp_path / "places.json"))
    browser.local_path = str(tmp_path)
    browser.open()
    original_save, original_read = ProgramPlaces._save, picker.filesystem_request

    def delayed_save(store, recent, favorites):
        save_entered.set()
        assert save_release.wait(5)
        original_save(store, recent, favorites)

    def delayed_read(request, **kwargs):
        # Retain the child's actual pre-save snapshot until the save publishes.
        result = original_read(request, **kwargs)
        read_entered.set()
        assert read_release.wait(5)
        return result

    try:
        browser.navigate(str(path))
        wait_for_inspection(browser)
        wait_for_saves(browser)
        monkeypatch.setattr(ProgramPlaces, "_save", delayed_save)
        browser.toggle_favorite()
        assert save_entered.wait(1)
        monkeypatch.setattr(picker, "filesystem_request", delayed_read)
        browser.refresh()
        assert read_entered.wait(1)
        save_release.set()
        wait_for_saves(browser)
        assert browser.saved_places.favorites == [str(path)]
        read_release.set()
        wait_for_listing(browser)
        assert browser.saved_places.favorites == [str(path)]
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        wait_for_saves(browser)
        assert browser.favorite_button.text == "Remove favorite"
    finally:
        save_release.set()
        read_release.set()
        browser.dismiss()
