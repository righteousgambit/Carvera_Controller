"""A stalled local child cannot retain the program browser's read queue."""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock

import carveracontroller.desktop_program_picker as picker
from carveracontroller.machine import artifact_fs
from carveracontroller.machine.program_places import ProgramPlaces
from tests.integration.conftest import pump_frames


def wait_until(predicate, message, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        pump_frames(2)
        if predicate():
            return
    raise AssertionError(message)


def wait_for_folder(browser, folder):
    wait_until(
        lambda: (
            browser.local_path == str(folder)
            and browser.status.text != "Reading local programs..."
            and [entry.name for entry in browser.entries] == [folder.name + ".nc"]
        ),
        f"The {folder.name} folder did not publish",
    )


@pytest.fixture(autouse=True)
def no_machine_effects(kivy_app, monkeypatch):
    machine = kivy_app.root.desktop_workspace.machine
    effects = []
    for owner, method in (
        (machine.controller, "executeCommand"),
        (machine, "view_local_file"),
        (machine, "check_and_upload"),
        (machine, "check_and_download"),
        (machine.file_popup.remote_rv, "list_dir"),
    ):
        effect = Mock()
        monkeypatch.setattr(owner, method, effect)
        effects.append(effect)
    yield
    for effect in effects:
        effect.assert_not_called()


@pytest.fixture
def folders(tmp_path):
    values = {}
    for name in ("slow", "skipped", "latest"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / (name + ".nc")).write_text("G21 G90 G54\nG0 X0 Y0 Z5\n")
        values[name] = folder
    return SimpleNamespace(**values)


def use_child(monkeypatch, tmp_path, slow, *, stage="listing", timeout=5, hold_cancel=False):
    """Inject a real helper that stalls inside one selected filesystem phase."""
    entered, release = tmp_path / "child-entered", tmp_path / "child-release"
    script = tmp_path / "program-list-helper.py"
    source = Path(artifact_fs.__file__).with_name("artifact_fs_worker.py")
    script.write_text(
        "import json, runpy, sys, time\n"
        "from pathlib import Path\n"
        f"worker = runpy.run_path({str(source)!r})\n"
        "request = json.loads(sys.stdin.readline())\n"
        f"slow = request['path'] == {str(slow)!r}\n"
        "def block():\n"
        f"    Path({str(entered)!r}).write_text('entered')\n"
        f"    while not Path({str(release)!r}).exists():\n"
        "        time.sleep(0.01)\n"
        f"stage = {stage!r}\n"
        "scope = worker['execute'].__globals__\n"
        "if slow and stage == 'startup':\n"
        "    original = Path.stat\n"
        "    def delayed(path, *args, **kwargs):\n"
        "        if str(path) == request['initial_candidates'][0]:\n"
        "            block()\n"
        "        return original(path, *args, **kwargs)\n"
        "    Path.stat = delayed\n"
        "elif slow and stage == 'places':\n"
        "    original = scope['read_program_places']\n"
        "    def delayed(*args, **kwargs):\n"
        "        block()\n"
        "        return original(*args, **kwargs)\n"
        "    scope['read_program_places'] = delayed\n"
        "elif slow and stage == 'listing':\n"
        "    original = scope['os'].scandir\n"
        "    def delayed(*args, **kwargs):\n"
        "        block()\n"
        "        return original(*args, **kwargs)\n"
        "    scope['os'].scandir = delayed\n"
        "elif slow and stage == 'reference':\n"
        "    document = json.loads(Path(request['places_path']).read_text())\n"
        "    references = document.get(request['collection'], [])\n"
        "    original = Path.stat\n"
        "    def delayed(path, *args, **kwargs):\n"
        "        if str(path) in references:\n"
        "            block()\n"
        "        return original(path, *args, **kwargs)\n"
        "    Path.stat = delayed\n"
        "elif slow and stage == 'malformed':\n"
        f"    Path({str(entered)!r}).write_text('entered')\n"
        "    print('not valid JSON')\n"
        "    sys.exit(0)\n"
        "try:\n"
        "    result = worker['execute'](request)\n"
        "    print(json.dumps({'result': result, 'error': None}))\n"
        "except Exception as error:\n"
        "    print(json.dumps({'result': None, 'error': str(error)}))\n"
    )
    original = picker.filesystem_request
    calls, processes, errors = [], [], []
    returned, finish = threading.Event(), threading.Event()
    popen = artifact_fs.subprocess.Popen

    def record_process(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    def request(value, **kwargs):
        calls.append(value)
        try:
            return original(value, command=[sys.executable, str(script)], timeout=timeout, **kwargs)
        except (OSError, ValueError, RuntimeError) as error:
            errors.append((value["path"], str(error)))
            raise
        finally:
            if hold_cancel and value["path"] == str(slow):
                returned.set()
                assert finish.wait(5)

    monkeypatch.setattr(artifact_fs.subprocess, "Popen", record_process)
    monkeypatch.setattr(picker, "filesystem_request", request)
    return SimpleNamespace(
        entered=entered,
        release=release,
        calls=calls,
        processes=processes,
        errors=errors,
        returned=returned,
        finish=finish,
    )


def browser_at(kivy_app, tmp_path, folder, *, startup=False):
    browser = picker.ProgramBrowser(
        kivy_app.root.desktop_workspace, places=ProgramPlaces(tmp_path / "places.json", load=False)
    )
    browser.local_path = str(folder)
    browser._initial_candidates = (str(folder),) if startup else None
    return browser


def close_and_retire(browser, child):
    child.finish.set()
    browser.dismiss()
    try:
        wait_until(lambda: not browser._local_worker_running, "Dismissed read worker did not retire")
    finally:
        # Cleanup if an assertion failed before cancellation was exercised.
        child.release.touch()
        wait_until(lambda: not browser._local_worker_running, "Released test child did not retire", timeout=6)
    pump_frames(2)


@pytest.mark.parametrize("stage", ["startup", "places", "listing"])
def test_superseding_stalled_child_publishes_latest_without_releasing_old_storage(
    kivy_app, tmp_path, monkeypatch, folders, stage
):
    child = use_child(monkeypatch, tmp_path, folders.slow, stage=stage)
    browser = browser_at(kivy_app, tmp_path, folders.slow, startup=stage == "startup")
    ticks = []
    event = Clock.schedule_interval(lambda _dt: ticks.append(1), 0)
    try:
        browser.open()
        wait_until(child.entered.exists, "Child did not reach the selected filesystem phase")
        pump_frames(3)
        assert ticks and browser.entries == [] and browser.preview_button.disabled
        browser.navigate(str(folders.latest))
        wait_for_folder(browser, folders.latest)
        assert not child.release.exists()
        assert len(child.processes) == 2 and child.processes[0].poll() is not None
        assert child.errors == [(str(folders.slow), "Filesystem request cancelled")]
        assert browser.selected is None and browser.inspection is None
        assert browser.preview_button.disabled and browser.upload_button.disabled
    finally:
        event.cancel()
        close_and_retire(browser, child)


def test_cancellation_keeps_only_newest_pending_folder(kivy_app, tmp_path, monkeypatch, folders):
    child = use_child(monkeypatch, tmp_path, folders.slow, hold_cancel=True)
    browser = browser_at(kivy_app, tmp_path, folders.slow)
    try:
        browser.open()
        wait_until(child.entered.exists, "Child did not start its blocked listing")
        browser.navigate(str(folders.skipped))
        wait_until(child.returned.is_set, "Superseded child was not cancelled")
        assert child.processes[0].poll() is not None
        assert child.errors == [(str(folders.slow), "Filesystem request cancelled")]
        # Hold the retiring worker so both navigations precede its next dequeue.
        browser.navigate(str(folders.latest))
        assert browser.entries == [] and browser.preview_button.disabled
        child.finish.set()
        wait_for_folder(browser, folders.latest)
        assert [request["path"] for request in child.calls] == [str(folders.slow), str(folders.latest)]
        assert not child.release.exists()
    finally:
        close_and_retire(browser, child)


@pytest.mark.parametrize("collection", ["recent", "favorites"])
def test_stalled_saved_reference_stat_cannot_hold_new_folder(kivy_app, tmp_path, monkeypatch, folders, collection):
    store = ProgramPlaces(tmp_path / "places.json", load=False)
    reference = folders.slow / "slow.nc"
    if collection == "recent":
        store.record_recent(reference)
    else:
        store.toggle_favorite(reference)
    child = use_child(monkeypatch, tmp_path, folders.slow, stage="reference")
    browser = browser_at(kivy_app, tmp_path, folders.slow)
    try:
        browser.open()
        wait_for_folder(browser, folders.slow)
        browser.choose_collection(collection)
        wait_until(child.entered.exists, "Child did not reach the saved reference stat")
        assert browser.entries == [] and browser.preview_button.disabled
        browser.navigate(str(folders.latest))
        wait_for_folder(browser, folders.latest)
        assert not child.release.exists()
        assert len(child.processes) == 3 and child.processes[1].poll() is not None
        assert child.errors == [(str(folders.slow), "Filesystem request cancelled")]
        assert [request["collection"] for request in child.calls] == [None, collection, None]
        assert browser.selected is None and browser.inspection is None
    finally:
        close_and_retire(browser, child)


def test_close_cancels_stalled_child_and_reopen_can_read(kivy_app, tmp_path, monkeypatch, folders):
    child = use_child(monkeypatch, tmp_path, folders.slow, stage="places")
    browser = browser_at(kivy_app, tmp_path, folders.slow)
    try:
        browser.open()
        wait_until(child.entered.exists, "Child did not start reading saved places")
        browser.dismiss()
        before = browser.status.text
        wait_until(lambda: not browser._local_worker_running, "Closed browser retained its blocked read")
        pump_frames(2)  # Deliver a queued cancellation result while the browser is closed.
        assert child.processes[0].poll() is not None and not child.release.exists()
        assert child.errors == [(str(folders.slow), "Filesystem request cancelled")]
        assert browser.entries == [] and browser.selected is None and browser.status.text == before
        browser.local_path = str(folders.latest)
        browser.open()
        wait_for_folder(browser, folders.latest)
        assert not child.release.exists()
    finally:
        close_and_retire(browser, child)


@pytest.mark.parametrize("stage, message", [("listing", "timed out"), ("malformed", "invalid metadata")])
def test_failed_child_settles_visible_error_and_allows_retry(kivy_app, tmp_path, monkeypatch, folders, stage, message):
    child = use_child(monkeypatch, tmp_path, folders.slow, stage=stage, timeout=1)
    browser = browser_at(kivy_app, tmp_path, folders.slow)
    try:
        browser.open()
        wait_until(lambda: message in browser.status.text, "Helper failure was not published")
        assert browser.entries == [] and browser.selected is None
        assert browser.preview_button.disabled and browser.upload_button.disabled
        assert child.processes[0].poll() is not None and not child.release.exists()
        browser.navigate(str(folders.latest))
        wait_for_folder(browser, folders.latest)
    finally:
        close_and_retire(browser, child)


@pytest.mark.parametrize(
    "path, message",
    [("bad\x00.nc", "Cannot read folder"), ("~codex-nonexistent-user-765412/part.nc", "Cannot read path")],
)
def test_invalid_input_does_not_poison_the_next_navigation(kivy_app, tmp_path, monkeypatch, folders, path, message):
    child = use_child(monkeypatch, tmp_path, folders.slow)
    browser = browser_at(kivy_app, tmp_path, folders.latest)
    try:
        browser.open()
        wait_for_folder(browser, folders.latest)
        browser.navigate(path)
        wait_until(lambda: message in browser.status.text, "Invalid input did not settle its error")
        assert browser.entries == [] and browser.selected is None
        assert browser.local_path == str(folders.latest)
        browser.navigate(str(folders.skipped))
        wait_for_folder(browser, folders.skipped)
    finally:
        close_and_retire(browser, child)


@pytest.mark.parametrize("path_kind", ["hidden", "case_alias"])
@pytest.mark.parametrize("action", ["preview", "favorite", "upload"])
def test_typed_unlisted_program_remains_visible_and_admits_only_current_actions(
    kivy_app, tmp_path, monkeypatch, path_kind, action
):
    stored = tmp_path / (".hidden.nc" if path_kind == "hidden" else "part.NC")
    stored.write_text("G21 G90 G54\nG0 X0 Y0 Z5\nG1 X8 F100\n")
    requested = stored if path_kind == "hidden" else tmp_path / "PART.nc"
    if not requested.is_file():
        pytest.skip("The test volume does not support this case-insensitive alias")
    (tmp_path / ".unrequested.nc").write_text("G21\n")
    (tmp_path / "visible.nc").write_text("G21\n")
    browser = browser_at(kivy_app, tmp_path, tmp_path)
    workspace = kivy_app.root.desktop_workspace
    browser.workspace = SimpleNamespace(
        connected=True,
        app=SimpleNamespace(state="Idle"),
        selected_machine_profile=workspace.selected_machine_profile,
        loaded_toolset=workspace.loaded_toolset,
    )
    monkeypatch.setattr(browser, "_remote_allowed", lambda: True)
    save = Mock()
    monkeypatch.setattr(browser, "_queue_place_save", save)
    original = picker.filesystem_request
    responses = []

    def capture(request, **kwargs):
        result = original(request, **kwargs)
        if request["navigate"] and request["path"] == str(requested):
            responses.append(result)
        return result

    monkeypatch.setattr(picker, "filesystem_request", capture)
    try:
        browser.open()
        wait_until(lambda: browser.status.text != "Reading local programs...", "Initial folder did not publish")
        assert str(requested) not in {entry.path for entry in browser.visible_entries}
        browser.path_field.text = str(requested)
        browser.path_field.dispatch("on_text_validate")
        wait_until(lambda: browser.inspection is not None, "Typed program did not finish inspection")
        selected = browser.selected
        assert selected is not None and selected.path == str(requested)
        assert str(requested) not in {entry["path"] for entry in responses[0]["entries"]}
        assert selected in browser.visible_entries and browser.cursor_path == selected.path
        assert browser._explicit_entry is selected
        assert ".unrequested.nc" not in {entry.name for entry in browser.visible_entries}
        assert "Entered path" in next(row["text"] for row in browser.files.data if row["entry"] == selected)
        actions = (browser.preview_button, browser.upload_button, browser.favorite_button)
        assert all(not button.disabled for button in actions)
        save.assert_called_once_with("recent", str(requested))

        browser.search.text = "visible.nc"
        assert selected not in browser.visible_entries and all(button.disabled for button in actions)
        browser.preview()
        browser.upload()
        browser.toggle_favorite()
        save.assert_called_once_with("recent", str(requested))
        assert browser._pending_upload is None and browser._reference_visible
        browser.search.text = ""
        assert selected in browser.visible_entries and all(not button.disabled for button in actions)

        # Exercise the accepted action through its button. Only inert boundary
        # spies receive its effects; the fixture still rejects other machine I/O.
        with monkeypatch.context() as admitted:
            admitted.setattr(browser.root.file_popup.local_rv, "curr_selected_file", "")
            if action == "favorite":
                browser.favorite_button.trigger_action(duration=0)
                assert save.call_args_list[-1].args == ("favorite", str(requested))
                assert save.call_count == 2 and browser._favorite_pending
            elif action == "preview":
                preview = Mock()
                admitted.setattr(browser.root, "view_local_file", preview)
                browser.preview_button.trigger_action(duration=0)
                preview.assert_called_once_with()
                assert browser.root.file_popup.local_rv.curr_selected_file == str(requested)
                assert not browser._reference_visible
            else:
                listing, upload = Mock(), Mock()
                admitted.setattr(browser.root.file_popup.remote_rv, "list_dir", listing)
                admitted.setattr(browser.root, "check_and_upload", upload)
                admitted.setattr(browser.root.file_popup, "firmware_mode", False)
                admitted.setattr(browser.root.controller, "loadERR", False)
                admitted.setattr(browser, "_busy", lambda: False)
                browser.upload_button.trigger_action(duration=0)
                listing.assert_called_once_with(browser.remote_path)
                assert browser._pending_upload == str(requested)
                upload.assert_not_called()
                browser._started -= 1
                assert browser._poll_remote(0) is False
                upload.assert_called_once_with()
                assert browser.root.file_popup.local_rv.curr_selected_file == str(requested)
                assert not browser._reference_visible

        if browser._reference_visible:
            browser.refresh()
        else:
            browser.open()
        wait_until(lambda: browser.status.text != "Reading local programs...", "Refreshed folder did not publish")
        assert browser._explicit_entry is None and browser.selected is None
        assert str(requested) not in {entry.path for entry in browser.visible_entries}
        assert ".unrequested.nc" not in {entry.name for entry in browser.visible_entries}
    finally:
        browser.dismiss()
        wait_until(lambda: not browser._local_worker_running, "Typed-path read worker did not retire")
        pump_frames(2)
