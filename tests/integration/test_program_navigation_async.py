"""Slow filesystem reads must not freeze the clock or replace newer intent."""

import threading
from unittest.mock import Mock

from kivy.clock import Clock

import carveracontroller.desktop_program_picker as picker
from tests.integration.conftest import pump_frames
from tests.integration.test_program_picker_inspection import wait_for_listing


def test_slow_startup_validation_keeps_ui_live_and_new_navigation_wins(kivy_app, tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    startup, latest = (tmp_path / name for name in ("startup", "latest"))
    for folder in (startup, latest):
        folder.mkdir()
        (folder / (folder.name + ".nc")).write_text("G21 G90 G54\nG0 X0 Y0 Z5\n")
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws.machine.file_popup.local_rv, "curr_dir", str(startup))
    monkeypatch.setattr(ws.app, "selected_local_filename", "")
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    original = picker.filesystem_request
    threads = []

    def delayed(request, **kwargs):
        if request["initial_candidates"]:
            threads.append(threading.get_ident())
            entered.set()
            assert release.wait(5)
        return original(request, **kwargs)

    monkeypatch.setattr(picker, "filesystem_request", delayed)
    browser = picker.ProgramBrowser(ws)
    ticks = []
    event = Clock.schedule_interval(lambda _dt: ticks.append(1), 0)
    try:
        browser.open()
        assert entered.wait(1)
        browser.navigate(str(latest))
        pump_frames(5)
        assert ticks and browser.entries == [] and browser.preview_button.disabled
        assert threads == [threads[0]] and threads[0] != threading.get_ident()
        release.set()
        wait_for_listing(browser)
        assert browser.local_path == str(latest)
        assert [entry.name for entry in browser.entries] == ["latest.nc"]
        send.assert_not_called()
    finally:
        release.set()
        event.cancel()
        browser.dismiss()


def test_slow_navigation_keeps_clock_live_and_coalesces_latest_request(kivy_app, tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    slow, skipped, latest = (tmp_path / name for name in ("slow", "skipped", "latest"))
    for folder in (slow, skipped, latest):
        folder.mkdir()
        (folder / (folder.name + ".nc")).write_text("G21 G90 G54\nG0 X0 Y0 Z5\n")
    original = picker.filesystem_request
    calls = []

    def delayed(request, **kwargs):
        calls.append(request["path"])
        if request["path"] == str(slow):
            entered.set()
            assert release.wait(5)
        return original(request, **kwargs)

    ws = kivy_app.root.desktop_workspace
    send = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    browser = picker.ProgramBrowser(ws)
    browser.local_path = str(tmp_path)
    browser.open()
    wait_for_listing(browser)
    monkeypatch.setattr(picker, "filesystem_request", delayed)
    ticks = []
    event = Clock.schedule_interval(lambda _dt: ticks.append(1), 0)
    try:
        browser.navigate(str(slow))
        assert entered.wait(1)
        browser.navigate(str(skipped))
        browser.navigate(str(latest))
        pump_frames(5)
        assert ticks and browser.entries == []
        assert browser.selected is None and browser.preview_button.disabled
        assert calls == [str(slow)]
        release.set()
        wait_for_listing(browser)
        assert calls == [str(slow), str(latest)]
        assert browser.local_path == str(latest)
        assert [entry.name for entry in browser.entries] == ["latest.nc"]
        send.assert_not_called()
        browser.popup.export_to_png(str(tmp_path / "async-program-navigation.png"))
    finally:
        release.set()
        event.cancel()
        browser.dismiss()


def test_dismissed_browser_rejects_delayed_listing(kivy_app, tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = picker.filesystem_request
    browser = picker.ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    wait_for_listing(browser)

    def delayed(request, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(request, **kwargs)

    monkeypatch.setattr(picker, "filesystem_request", delayed)
    try:
        browser.refresh()
        assert entered.wait(1)
        browser.dismiss()
        before = browser.status.text
        release.set()
        for _ in range(40):
            pump_frames(2)
            if not browser._local_worker_running:
                break
        assert not browser._local_worker_running
        pump_frames(2)  # Deliver any already queued finish callback after retirement.
        assert browser.entries == [] and browser.selected is None
        assert browser.status.text == before
    finally:
        release.set()
        browser.dismiss()
