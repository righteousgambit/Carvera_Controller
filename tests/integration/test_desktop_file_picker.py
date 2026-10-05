"""Artifact selection, async navigation and overwrite semantics."""

import threading
import time
from pathlib import Path
from unittest.mock import Mock

from carveracontroller.desktop_file_picker import ArtifactBrowser, artifact_entries
from tests.integration.conftest import pump_frames


def wait_for(predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        pump_frames(2)
        if predicate():
            return
    assert predicate(), "Picker did not settle"


def navigate(browser, directory):
    browser.navigate(directory)
    wait_for(lambda: browser.ready)


def test_picker_filters_suffixes_and_keeps_folders(tmp_path):
    (tmp_path / "subfolder").mkdir()
    (tmp_path / "machine.json.gz").write_text("model")
    (tmp_path / "profile.JSON").write_text("{}")
    (tmp_path / ".hidden.json").write_text("{}")
    (tmp_path / "unrelated.cnc").write_text("M2")
    entries = artifact_entries(tmp_path, (".json", ".json.gz"))
    assert [e.name for e in entries] == ["subfolder", "machine.json.gz", "profile.JSON"]
    assert [e.name for e in artifact_entries(tmp_path, (".json",), "PROFILE")] == ["profile.JSON"]


def test_file_picker_stale_navigation_and_selection(kivy_app, tmp_path):
    workspace = kivy_app.root.desktop_workspace
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "first.cvmap").write_text("{}")
    (second / "second.cvmap").write_text("{}")
    chosen = Mock()
    browser = ArtifactBrowser(workspace, chosen, (".cvmap",))
    browser.navigate(first)
    browser.navigate(second)
    for _ in range(20):
        pump_frames(2)
        if browser.entries and browser.entries[0].name == "second.cvmap":
            break
    assert [e.name for e in browser.entries] == ["second.cvmap"]
    browser.select(browser.entries[0])
    browser.choose()
    wait_for(lambda: browser.closed)
    chosen.assert_called_once_with(str(second / "second.cvmap"))
    assert browser.closed


def test_save_preserves_existing_and_rejects_path_escape(kivy_app, tmp_path):
    target = tmp_path / "existing.cvface"
    target.write_text("original")
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvface",), save=True)
    navigate(browser, tmp_path)
    for name in ("existing.cvface", "../escape.cvface", "/tmp/escape.cvface", "wrong.json"):
        browser.filename.text = name
        browser.choose()
        wait_for(lambda: not browser.choosing)
        chosen.assert_not_called()
    assert target.read_text() == "original"
    browser.filename.text = "new.cvface"
    browser.choose()
    wait_for(lambda: browser.closed)
    chosen.assert_called_once_with(str(tmp_path / "new.cvface"))


def test_artifact_callback_failure_keeps_dialog_open(kivy_app, tmp_path):
    file = tmp_path / "model.json.gz"
    file.write_text("not a model")
    browser = ArtifactBrowser(
        kivy_app.root.desktop_workspace, Mock(side_effect=ValueError("Unsupported model")), (".json.gz",)
    )
    navigate(browser, tmp_path)
    browser.filename.text = file.name
    try:
        browser.choose()
        wait_for(lambda: not browser.choosing)
        assert not browser.closed
        assert browser.note.text == "Unsupported model"
    finally:
        # This test deliberately keeps the modal open after a rejected import;
        # it must not intercept pointer events in subsequent shared-app tests.
        browser.dismiss()


def test_jobs_shortcut_initializes_owned_folder_without_selecting_file(kivy_app, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvface",))
    browser.open_jobs()
    wait_for(lambda: browser.ready)
    assert browser.path == tmp_path / ".carvera" / "jobs"
    assert browser.path.is_dir()
    chosen.assert_not_called()
    browser.dismiss()


def test_stalled_path_check_keeps_clock_live_and_coalesces_navigation(kivy_app, tmp_path, monkeypatch):
    first, skipped, latest = (tmp_path / name for name in ("first", "skipped", "latest"))
    for directory in (first, skipped, latest):
        directory.mkdir()
    (latest / "latest.cvmap").write_text("{}")
    entered, release = threading.Event(), threading.Event()
    checked = []
    original = Path.is_file
    main_thread = threading.get_ident()

    def blocked(path):
        if path in (first, skipped, latest):
            assert threading.get_ident() != main_thread
            checked.append(path)
        if path == first:
            entered.set()
            assert release.wait(5)
        return original(path)

    monkeypatch.setattr(Path, "is_file", blocked)
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, Mock(), (".cvmap",))
    try:
        browser.navigate(first)
        wait_for(entered.is_set)
        browser.navigate(skipped)
        browser.navigate(latest)
        from kivy.clock import Clock

        ticked = []
        Clock.schedule_once(lambda _dt: ticked.append(True), 0)
        pump_frames(4)
        assert ticked and not browser.ready and browser.choose_action.disabled
        assert browser.entries == []
        release.set()
        wait_for(lambda: browser.ready)
        assert browser.path == latest
        assert checked == [first, latest]
        assert [entry.name for entry in browser.entries] == ["latest.cvmap"]
    finally:
        release.set()
        browser.dismiss()


def test_stalled_selection_cannot_dispatch_after_edit_or_dismiss(kivy_app, tmp_path, monkeypatch):
    target = tmp_path / "selected.cvmap"
    target.write_text("{}")
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",))
    navigate(browser, tmp_path)
    browser.filename.text = target.name
    entered, release = threading.Event(), threading.Event()
    original = Path.is_file
    main_thread = threading.get_ident()

    def blocked(path):
        if path == target:
            assert threading.get_ident() != main_thread
            entered.set()
            assert release.wait(5)
        return original(path)

    monkeypatch.setattr(Path, "is_file", blocked)
    try:
        browser.choose()
        wait_for(entered.is_set)
        browser.choose()  # Duplicate gestures do not queue callbacks.
        browser.filename.text = "different.cvmap"
        pump_frames(4)
        assert browser.choosing and browser.choose_action.disabled
        release.set()
        wait_for(lambda: not browser.choosing)
        chosen.assert_not_called()
        assert "Selection changed" in browser.note.text
        entered.clear()
        release.clear()
        browser.filename.text = target.name
        browser.choose()
        wait_for(entered.is_set)
        browser.dismiss()
        release.set()
        wait_for(lambda: not browser._worker_running)
        pump_frames(4)
        chosen.assert_not_called()
    finally:
        release.set()
        browser.dismiss()


def test_invalid_navigation_blocks_selection_from_previous_folder(kivy_app, tmp_path):
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",), save=True)
    navigate(browser, tmp_path)
    browser.filename.text = "new.cvmap"
    browser.location.text = str(tmp_path / "missing")
    browser.choose()
    wait_for(lambda: not browser._worker_running)
    pump_frames(4)
    assert not browser.ready and browser.choose_action.disabled
    browser.choose()
    chosen.assert_not_called()
    browser.dismiss()


def test_initial_fallback_and_jobs_filesystem_work_is_off_ui(kivy_app, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    main_thread = threading.get_ident()
    calls = []
    watched = (tmp_path, tmp_path / "Downloads", tmp_path / ".carvera" / "jobs")
    for operation in ("is_file", "is_dir", "resolve", "mkdir"):
        original = getattr(Path, operation)

        def checked(path, *args, _operation=operation, _original=original, **kwargs):
            if path in watched:
                assert threading.get_ident() != main_thread
                calls.append(_operation)
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(Path, operation, checked)
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, Mock(), (".cvmap",))
    assert calls == []
    try:
        browser.open()
        wait_for(lambda: browser.ready)
        assert browser.path == tmp_path  # Downloads does not exist.
        browser.open_jobs()
        wait_for(lambda: browser.ready)
        assert browser.path == tmp_path / ".carvera" / "jobs"
        assert {"is_file", "is_dir", "resolve", "mkdir"} <= set(calls)
    finally:
        browser.dismiss()


def test_stalled_save_check_cannot_dispatch_in_new_folder(kivy_app, tmp_path, monkeypatch):
    destination = tmp_path / "other"
    destination.mkdir()
    chosen = Mock()
    browser = ArtifactBrowser(kivy_app.root.desktop_workspace, chosen, (".cvmap",), save=True)
    navigate(browser, tmp_path)
    browser.filename.text = "new.cvmap"
    entered, release = threading.Event(), threading.Event()
    original = Path.exists
    main_thread = threading.get_ident()

    def blocked(path):
        if path == tmp_path / "new.cvmap":
            assert threading.get_ident() != main_thread
            entered.set()
            assert release.wait(5)
        return original(path)

    monkeypatch.setattr(Path, "exists", blocked)
    try:
        browser.choose()
        wait_for(entered.is_set)
        browser.navigate(destination)
        pump_frames(4)
        assert not browser.ready
        release.set()
        wait_for(lambda: browser.ready)
        assert browser.path == destination
        chosen.assert_not_called()
        browser.choose()
        wait_for(lambda: browser.closed)
        chosen.assert_called_once_with(str(destination / "new.cvmap"))
    finally:
        release.set()
        browser.dismiss()
