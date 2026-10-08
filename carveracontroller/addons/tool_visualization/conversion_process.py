"""Cancellable local CAD conversion with a bounded child-process lifecycle."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable, Sequence
from pathlib import Path


def _stop(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired as exc:
            raise OSError("CAD converter exit could not be confirmed") from exc


def convert_process(
    command: Sequence[str], output: Path, cancelled: Callable[[], bool], *, timeout_s: float = 120
) -> None:
    """Publish nothing; the caller owns accepting the validated output."""
    from carveracontroller.addons.tool_visualization.cad_assets import load_tool_asset

    if cancelled():
        raise InterruptedError("CAD conversion cancelled")
    # Converter output is not a UI diagnostic. Avoid retaining unbounded output
    # from the selected interpreter or exposing its environment in the dialog.
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout_s
    try:
        while process.poll() is None:
            if cancelled():
                raise InterruptedError("CAD conversion cancelled")
            if time.monotonic() >= deadline:
                raise TimeoutError("CAD conversion timed out; check the source and selected CAD Python interpreter.")
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
        if cancelled():
            raise InterruptedError("CAD conversion cancelled")
        if process.returncode:
            raise ValueError(
                "CAD conversion failed; check the source, axis, units and selected CAD Python interpreter."
            )
        load_tool_asset(output)
        if cancelled():
            raise InterruptedError("CAD conversion cancelled")
    finally:
        _stop(process)
