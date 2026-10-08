import sys
import threading
import time

import pytest

from carveracontroller.machine.clipboard_text import ClipboardReadError, read_text


def helper(code):
    return [sys.executable, "-c", code]


def test_unicode_and_exact_size_limit():
    assert read_text(threading.Event(), command=helper("print('café 工具', end='')")) == "café 工具"
    assert read_text(threading.Event(), max_bytes=3, command=helper("print('abc', end='')")) == "abc"
    with pytest.raises(ClipboardReadError, match="too large"):
        read_text(threading.Event(), max_bytes=3, command=helper("print('abcd', end='')"))


def test_timeout_cancel_and_failure_reap_helpers():
    started = time.monotonic()
    with pytest.raises(ClipboardReadError, match="timed out"):
        read_text(threading.Event(), timeout=0.1, command=helper("import time; time.sleep(10)"))
    assert time.monotonic() - started < 1
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(ClipboardReadError, match="cancelled"):
        read_text(cancel)
    with pytest.raises(ClipboardReadError, match="could not"):
        read_text(threading.Event(), command=helper("raise SystemExit(1)"))
    # Errors release capacity, rather than permanently making paste busy.
    assert read_text(threading.Event(), command=helper("print('ok', end='')")) == "ok"


def test_concurrency_is_bounded(monkeypatch):
    import carveracontroller.machine.clipboard_text as module

    slots = threading.BoundedSemaphore(2)
    monkeypatch.setattr(module, "_slots", slots)
    assert slots.acquire(False) and slots.acquire(False)
    with pytest.raises(ClipboardReadError, match="busy"):
        read_text(threading.Event())
    slots.release()
    slots.release()


def test_missing_output_pipe_reaps_helper_and_releases_capacity(monkeypatch):
    import carveracontroller.machine.clipboard_text as module

    class Helper:
        stdout = None
        running = True
        waited = False

        def poll(self):
            return None if self.running else -9

        def kill(self):
            self.running = False

        def wait(self):
            self.waited = True
            return -9

    helper_process = Helper()
    slots = threading.BoundedSemaphore(1)
    monkeypatch.setattr(module, "_slots", slots)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: helper_process)
    with pytest.raises(ClipboardReadError, match="output pipe"):
        read_text(threading.Event())
    assert helper_process.waited and not helper_process.running
    assert slots.acquire(False)
    slots.release()
