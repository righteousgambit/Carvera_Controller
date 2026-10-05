"""Bounded macOS text pasteboard reads, without SDL or UI-thread calls."""

import os
import selectors
import subprocess
import threading
import time

_slots = threading.BoundedSemaphore(2)


class ClipboardReadError(ValueError):
    """A paste could not be read safely; messages never contain clipboard data."""


def read_text(cancel, timeout=2.0, max_bytes=1024 * 1024, command=None):
    """Read text on a worker. Retain a slot until the helper has been reaped."""
    if not _slots.acquire(blocking=False):
        raise ClipboardReadError("Clipboard is busy; try paste again.")
    process = None
    try:
        if cancel.is_set():
            raise ClipboardReadError("Paste cancelled.")
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(
            command or ["/usr/bin/pbpaste", "-Prefer", "txt"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
        output = bytearray()
        os.set_blocking(process.stdout.fileno(), False)
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if cancel.is_set():
                    raise ClipboardReadError("Paste cancelled.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ClipboardReadError("Clipboard timed out; try paste again.")
                if not selector.select(min(0.05, remaining)):
                    continue
                chunk = os.read(process.stdout.fileno(), min(65536, max_bytes + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > max_bytes:
                    raise ClipboardReadError("Clipboard text is too large.")
        try:
            result = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            raise ClipboardReadError("Clipboard timed out; try paste again.") from None
        if cancel.is_set():
            raise ClipboardReadError("Paste cancelled.")
        if result:
            raise ClipboardReadError("Clipboard could not be read.")
        return output.decode("utf-8", errors="replace")
    except OSError:
        raise ClipboardReadError("Clipboard could not be read.") from None
    finally:
        try:
            if process is not None:
                if process.poll() is None:
                    try:
                        process.kill()
                    except ProcessLookupError:
                        pass  # It exited between poll and kill.
                # Only the worker waits. Even a slow-to-reap helper occupies one
                # of two slots instead of allowing unbounded replacements.
                process.wait()
                process.stdout.close()
        finally:
            _slots.release()
