"""Quick inspection bounds child reads and coalesces work without machine effects."""

import hashlib
import sys
import threading
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.clock import Clock

import carveracontroller.desktop_program_picker as picker
from carveracontroller.machine import artifact_fs, program_preview
from carveracontroller.machine.program_places import ProgramPlaces
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_listing import wait_until


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
def programs(tmp_path):
    paths = [tmp_path / name for name in ("first.nc", "skipped.nc", "latest.nc")]
    for tool, path in enumerate(paths, 1):
        path.write_bytes(f"G21 G90 G54\nT{tool}\nG0 X0 Y0 Z5\nG1 X{tool} F100\n".encode())
    return paths


def open_browser(kivy_app, tmp_path):
    browser = picker.ProgramBrowser(
        kivy_app.root.desktop_workspace, places=ProgramPlaces(tmp_path / "places.json", load=False)
    )
    browser.local_path = str(tmp_path)
    browser._initial_candidates = None
    browser.open()
    try:
        wait_for_folder(browser)
    except Exception as error:
        try:
            retire(browser)
        except Exception as cleanup_error:
            add_note = getattr(error, "add_note", None)
            if add_note is not None:
                add_note(f"Initial picker cleanup failed: {cleanup_error}")
        raise
    return browser


def wait_for_folder(browser):
    # Initial folder reads have a four-second helper deadline. Allow its result
    # to reach Clock before exercising the shorter inspection/cancellation waits.
    wait_until(
        lambda: not browser._local_worker_running and browser.status.text != "Reading local programs...",
        "Initial listing did not publish",
        timeout=6,
    )
    assert browser.entries, browser.status.text


def choose(browser, path):
    browser.select(next(entry for entry in browser.entries if entry.path == str(path)))


def inspected(browser, path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    wait_until(
        lambda: browser.inspection is not None and browser.inspection.digest == digest,
        "The selected program did not publish its inspection",
    )
    assert browser.selected.path == str(path) and browser.cursor_path == str(path)


def retire(browser, release=None):
    browser.dismiss()
    if release is not None:
        release.touch() if isinstance(release, Path) else release.set()
    wait_until(
        lambda: not browser._inspection_worker_running and not browser._local_worker_running,
        "Browser workers did not retire",
        timeout=6,
    )
    pump_frames(2)


def use_child(monkeypatch, tmp_path, path, *, stage="read", timeout=5):
    entered, release = tmp_path / "capture-entered", tmp_path / "capture-release"
    script = tmp_path / "program-read-helper.py"
    source = Path(artifact_fs.__file__).with_name("artifact_fs_worker.py")
    script.write_text(
        "import json, runpy, sys, time\n"
        "from pathlib import Path\n"
        f"worker = runpy.run_path({str(source)!r})\n"
        "request = json.loads(sys.stdin.readline())\n"
        f"blocked = request['operation'] == 'program-read' and request['path'] == {str(path)!r}\n"
        f"stage = {stage!r}\n"
        "def block():\n"
        f"    Path({str(entered)!r}).write_text('entered')\n"
        f"    while not Path({str(release)!r}).exists():\n"
        "        time.sleep(0.01)\n"
        "class DelayedRead:\n"
        "    def __init__(self, source): self.source = source\n"
        "    def __enter__(self): return self\n"
        "    def __exit__(self, *args): self.source.close()\n"
        "    def read(self, *args):\n"
        "        block()\n"
        "        return self.source.read(*args)\n"
        "original = Path.open\n"
        "def guarded_open(item, *args, **kwargs):\n"
        "    if blocked and str(item) == request['path']:\n"
        "        if stage == 'open': block()\n"
        "        if stage == 'error': raise PermissionError('fixture capture unavailable')\n"
        "        if stage == 'read': return DelayedRead(original(item, *args, **kwargs))\n"
        "    return original(item, *args, **kwargs)\n"
        "Path.open = guarded_open\n"
        "if blocked and stage == 'malformed':\n"
        "    print('invalid helper response')\n"
        "    sys.exit(0)\n"
        "try:\n"
        "    result = worker['execute'](request)\n"
        "    print(json.dumps({'result': result, 'error': None}))\n"
        "except Exception as error:\n"
        "    print(json.dumps({'result': None, 'error': str(error)}))\n"
    )
    monkeypatch.setattr(artifact_fs, "worker_command", lambda: [sys.executable, str(script)])
    original_capture, popen = picker.read_program_bytes, artifact_fs.subprocess.Popen
    calls, errors, processes = [], [], []

    def capture(target, *, cancelled):
        calls.append(target)
        try:
            return original_capture(target, cancelled=cancelled, timeout=timeout)
        except (OSError, ValueError, UnicodeError, RuntimeError) as error:
            errors.append((target, str(error)))
            raise

    def record_process(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    monkeypatch.setattr(picker, "read_program_bytes", capture)
    monkeypatch.setattr(artifact_fs.subprocess, "Popen", record_process)
    return SimpleNamespace(entered=entered, release=release, calls=calls, errors=errors, processes=processes)


@pytest.mark.parametrize("stage", ["open", "read"])
def test_new_selection_cancels_blocked_capture_without_releasing_storage(
    kivy_app, tmp_path, monkeypatch, programs, stage
):
    first, _skipped, latest = programs
    child = use_child(monkeypatch, tmp_path, first, stage=stage)
    browser = open_browser(kivy_app, tmp_path)
    child.processes.clear()
    ticks = []
    event = Clock.schedule_interval(lambda _dt: ticks.append(1), 0)
    try:
        choose(browser, first)
        wait_until(child.entered.exists, "Child did not reach the blocked capture phase")
        pump_frames(3)
        assert ticks and browser.inspection is None
        assert browser.excerpt.text == "Inspecting captured program…"
        choose(browser, latest)
        inspected(browser, latest)
        assert not child.release.exists()
        assert child.errors == [(str(first), "Filesystem request cancelled")]
        assert child.processes[0].poll() is not None
        assert child.calls == [str(first), str(latest)]
        assert not browser.preview_button.disabled
    finally:
        event.cancel()
        retire(browser, child.release)


def test_repeated_selections_keep_one_parser_and_only_latest_pending(kivy_app, tmp_path, monkeypatch, programs):
    first, skipped, latest = programs
    browser = open_browser(kivy_app, tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = program_preview.inspect_program_bytes
    calls, active, peak = [], 0, 0
    first_content, latest_content = first.read_bytes(), latest.read_bytes()

    def parser(content, **kwargs):
        nonlocal active, peak
        calls.append(content)
        active += 1
        peak = max(peak, active)
        try:
            if content == first_content:
                entered.set()
                assert release.wait(5)
            return original(content, **kwargs)
        finally:
            active -= 1

    monkeypatch.setattr(program_preview, "inspect_program_bytes", parser)
    published = Mock(wraps=browser._finish_inspection)
    monkeypatch.setattr(browser, "_finish_inspection", published)
    try:
        choose(browser, first)
        wait_until(entered.is_set, "First parser did not start")
        for _ in range(8):
            choose(browser, skipped)
            choose(browser, latest)
        pump_frames(3)
        assert calls == [first_content] and peak == active == 1
        assert browser._inspection_pending[1].path == str(latest)
        assert browser.inspection is None
        release.set()
        inspected(browser, latest)
        assert calls == [first_content, latest_content] and peak == 1
        assert published.call_count == 1
        assert published.call_args.args[1].path == str(latest)
    finally:
        retire(browser, release)


@pytest.mark.parametrize(
    "stage, message",
    [("read", "Program read timed out"), ("error", "fixture capture unavailable"), ("malformed", "invalid metadata")],
)
def test_failed_capture_reports_once_and_next_selection_recovers(
    kivy_app, tmp_path, monkeypatch, programs, stage, message
):
    first, _skipped, latest = programs
    child = use_child(monkeypatch, tmp_path, first, stage=stage, timeout=1)
    browser = open_browser(kivy_app, tmp_path)
    published = Mock(wraps=browser._finish_inspection)
    monkeypatch.setattr(browser, "_finish_inspection", published)
    try:
        choose(browser, first)
        wait_until(lambda: message in browser.excerpt.text, "Capture error did not reach the selected entry")
        assert browser.inspection is None and "Quick inspection unavailable" in browser.status.text
        assert published.call_count == 1 and message in published.call_args.args[-1]
        assert not browser.preview_button.disabled
        choose(browser, latest)
        assert "Quick inspection unavailable" not in browser.status.text
        inspected(browser, latest)
        assert browser.status.text == "Program inspected locally."
        assert published.call_count == 2 and published.call_args.args[-1] is None
    finally:
        retire(browser, child.release)


def test_dismiss_cancels_capture_and_reopen_publishes_only_new_selection(kivy_app, tmp_path, monkeypatch, programs):
    first, _skipped, latest = programs
    child = use_child(monkeypatch, tmp_path, first)
    browser = open_browser(kivy_app, tmp_path)
    child.processes.clear()
    published = Mock(wraps=browser._finish_inspection)
    monkeypatch.setattr(browser, "_finish_inspection", published)
    try:
        choose(browser, first)
        wait_until(child.entered.exists, "Child did not reach the blocked read")
        browser.dismiss()
        before = browser.excerpt.text
        wait_until(lambda: not browser._inspection_worker_running, "Closed inspector did not retire")
        pump_frames(2)
        assert not child.release.exists() and child.processes[0].poll() is not None
        assert child.errors == [(str(first), "Filesystem request cancelled")]
        assert browser.excerpt.text == before and browser.inspection is None
        published.assert_not_called()
        browser.open()
        wait_for_folder(browser)
        choose(browser, latest)
        inspected(browser, latest)
        assert not child.release.exists() and published.call_count == 1
    finally:
        retire(browser, child.release)


def test_queued_inspection_completion_cannot_publish_after_dismissal(kivy_app, tmp_path, monkeypatch, programs):
    first, _skipped, latest = programs
    browser = open_browser(kivy_app, tmp_path)
    completions = []
    scheduled = Clock.schedule_once

    def capture(callback, timeout=0):
        if getattr(callback, "__qualname__", "").endswith("_queue_inspection.<locals>.read.<locals>.<lambda>"):
            completions.append(callback)
            return None
        return scheduled(callback, timeout)

    try:
        with monkeypatch.context() as held:
            held.setattr(Clock, "schedule_once", capture)
            choose(browser, first)
            wait_until(lambda: bool(completions), "Inspection did not queue its UI completion")
            browser.dismiss()
            before = browser.excerpt.text
            completions.pop()(0)
            assert browser.inspection is None and browser.excerpt.text == before
        browser.open()
        wait_for_folder(browser)
        choose(browser, latest)
        inspected(browser, latest)
    finally:
        retire(browser)


@pytest.mark.parametrize("stage", ["capture", "parser", "dispatch", "start"])
def test_unexpected_inspection_failure_reports_and_releases_worker_for_retry(
    kivy_app, tmp_path, monkeypatch, programs, stage
):
    from kivy.logger import Logger

    first, _skipped, latest = programs
    browser = open_browser(kivy_app, tmp_path)
    published = Mock(wraps=browser._finish_inspection)
    monkeypatch.setattr(browser, "_finish_inspection", published)
    diagnostic = Mock(wraps=Logger.exception)
    monkeypatch.setattr(Logger, "exception", diagnostic)
    failure = f"fixture unexpected {stage}"
    try:
        with monkeypatch.context() as failed:
            if stage == "capture":
                failed.setattr(picker, "read_program_bytes", Mock(side_effect=TypeError(failure)))
            elif stage == "parser":
                failed.setattr(program_preview, "inspect_program_bytes", Mock(side_effect=IndexError(failure)))
            elif stage == "dispatch":
                scheduled = Clock.schedule_once

                def reject(callback, timeout=0):
                    if getattr(callback, "__qualname__", "").endswith(
                        "_queue_inspection.<locals>.read.<locals>.<lambda>"
                    ):
                        raise TypeError(failure)
                    return scheduled(callback, timeout)

                failed.setattr(Clock, "schedule_once", reject)
            else:
                thread = threading.Thread

                def reject_start(*args, **kwargs):
                    if getattr(kwargs.get("target"), "__qualname__", "").endswith("_queue_inspection.<locals>.read"):
                        return SimpleNamespace(start=Mock(side_effect=TypeError(failure)))
                    return thread(*args, **kwargs)

                failed.setattr(picker.threading, "Thread", reject_start)
            choose(browser, first)
            wait_until(lambda: failure in browser.excerpt.text, "Unexpected failure did not publish its error")
            wait_until(lambda: not browser._inspection_worker_running, "Failed worker retained the queue")
            assert browser._inspection_worker_token is None
            assert browser.inspection is None and published.call_count == 1
            diagnostic.assert_called_once()
        choose(browser, latest)
        inspected(browser, latest)
        assert published.call_count == 2 and published.call_args.args[-1] is None
    finally:
        retire(browser)


@pytest.mark.parametrize("selection", ["unavailable", "remote"])
def test_new_nonlocal_capture_state_clears_previous_inspection_error(
    kivy_app, tmp_path, monkeypatch, programs, selection
):
    first, _skipped, _latest = programs
    browser = open_browser(kivy_app, tmp_path)
    try:
        with monkeypatch.context() as failed:
            failed.setattr(picker, "read_program_bytes", Mock(side_effect=ValueError("previous capture failure")))
            choose(browser, first)
            wait_until(lambda: "previous capture failure" in browser.status.text, "Failure did not publish")
        if selection == "unavailable":
            browser.select(replace(browser.selected, available=False))
            assert "saved reference remains available" in browser.excerpt.text
        else:
            browser.location = "remote"
            browser.select(picker.ProgramEntry("remote.nc", "/sd/gcodes/remote.nc", False))
            assert "Load this program" in browser.excerpt.text
        assert "previous capture failure" not in browser.status.text
        assert browser.inspection is None
    finally:
        retire(browser)


@pytest.mark.parametrize("stage", ["capture", "parser"])
def test_message_less_inspection_error_cannot_publish_success_or_recent_reference(
    kivy_app, tmp_path, monkeypatch, programs, stage
):
    first, _skipped, latest = programs
    browser = open_browser(kivy_app, tmp_path)
    save = Mock()
    monkeypatch.setattr(browser, "_queue_place_save", save)
    exception = ValueError() if stage == "capture" else RuntimeError()
    try:
        with monkeypatch.context() as failed:
            owner, name = (
                (picker, "read_program_bytes") if stage == "capture" else (program_preview, "inspect_program_bytes")
            )
            failed.setattr(owner, name, Mock(side_effect=exception))
            choose(browser, first)
            wait_until(
                lambda: type(exception).__name__ in browser.excerpt.text,
                "Message-less failure was not displayed as an inspection error",
            )
            wait_until(lambda: not browser._inspection_worker_running, "Failed worker retained the queue")
            assert browser.inspection is None
            assert browser.status.text.startswith("Quick inspection unavailable:")
            save.assert_not_called()
        choose(browser, latest)
        inspected(browser, latest)
        save.assert_called_once_with("recent", str(latest))
    finally:
        retire(browser)


def test_real_parser_cancellation_checkpoint_releases_latest_selection(kivy_app, tmp_path, monkeypatch, programs):
    first, _skipped, latest = programs
    first.write_text("G21 G90 G17 G94 G54\nG0 X10 Y0\n" + "G2 I-10 J0 F100\n" * 4998)
    browser = open_browser(kivy_app, tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = program_preview.ProgramOperations.from_text
    first_text, interrupted = first.read_text(), []

    def analyse(_cls, text, **kwargs):
        if text != first_text:
            return original(text, **kwargs)
        cancelled = kwargs["cancelled"]
        checkpoints = 0

        def checkpoint():
            nonlocal checkpoints
            checkpoints += 1
            if checkpoints == 10:
                entered.set()
                assert release.wait(5)
            return cancelled()

        try:
            return original(text, **{**kwargs, "cancelled": checkpoint})
        except InterruptedError as error:
            interrupted.append(str(error))
            raise

    monkeypatch.setattr(program_preview.ProgramOperations, "from_text", classmethod(analyse))
    published = Mock(wraps=browser._finish_inspection)
    monkeypatch.setattr(browser, "_finish_inspection", published)
    try:
        choose(browser, first)
        wait_until(entered.is_set, "The real parser did not reach its cancellation checkpoint")
        choose(browser, latest)
        assert browser.inspection is None and not interrupted
        release.set()
        inspected(browser, latest)
        assert len(interrupted) == 1 and "cancelled" in interrupted[0]
        assert published.call_count == 1 and published.call_args.args[1].path == str(latest)
    finally:
        retire(browser, release)
