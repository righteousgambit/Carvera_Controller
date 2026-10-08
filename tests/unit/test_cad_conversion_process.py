"""Real converter child processes are reaped before success/cancellation returns."""

import os
import sys
import threading
import time

import pytest

from carveracontroller.addons.tool_visualization.conversion_process import convert_process


def command(tmp_path, text):
    script = tmp_path / "child.py"
    script.write_text(text)
    return [sys.executable, str(script)]


def test_real_obj_conversion_validates_registered_geometry(tmp_path):
    from carveracontroller.addons.tool_visualization import converter
    from carveracontroller.addons.tool_visualization.cad_assets import load_tool_asset

    source, output = tmp_path / "tool.obj", tmp_path / "tool.json.gz"
    source.write_text("v 1 2 3\nv 2 2 4\nv 1 3 4\nf 1 2 3\n")
    convert_process(
        [
            sys.executable,
            "-I",
            converter.__file__,
            str(source),
            "--output",
            str(output),
            "--units",
            "mm",
            "--axis=+Z",
            "--tip",
            "1",
            "2",
            "3",
        ],
        output,
        lambda: False,
    )
    assert load_tool_asset(output)["triangles"] == [0, 0, 0, 1, 0, 1, 0, 1, 1]


@pytest.mark.parametrize("ignore_term", [False, True])
def test_cancel_reaps_running_child(tmp_path, ignore_term):
    if ignore_term and sys.platform == "win32":
        pytest.skip("SIGTERM handling is POSIX-specific")
    marker = tmp_path / "pid"
    script = "import os, time, signal\nfrom pathlib import Path\n"
    if ignore_term:
        script += "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
    script += f"Path({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)\n"
    cancelled = threading.Event()
    errors = []

    def work():
        try:
            convert_process(command(tmp_path, script), tmp_path / "unused.json", cancelled.is_set)
        except InterruptedError as exc:
            errors.append(exc)

    thread = threading.Thread(target=work)
    thread.start()
    deadline = time.monotonic() + 5
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert marker.exists()
    pid = int(marker.read_text())
    cancelled.set()
    thread.join(5)
    assert not thread.is_alive() and len(errors) == 1
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_timeout_reaps_child_and_no_output_is_applied(tmp_path):
    marker = tmp_path / "pid"
    child = command(
        tmp_path,
        f"import os,time\nfrom pathlib import Path\nPath({str(marker)!r}).write_text(str(os.getpid()))\ntime.sleep(30)",
    )
    with pytest.raises(TimeoutError, match="timed out"):
        convert_process(child, tmp_path / "unused.json", lambda: False, timeout_s=1)
    with pytest.raises(ProcessLookupError):
        os.kill(int(marker.read_text()), 0)


def test_pre_cancel_launches_nothing(tmp_path):
    marker = tmp_path / "unexpected"
    with pytest.raises(InterruptedError):
        convert_process(
            command(tmp_path, f"from pathlib import Path\nPath({str(marker)!r}).touch()"), marker, lambda: True
        )
    assert not marker.exists()


def test_failure_does_not_expose_child_output(tmp_path):
    child = command(tmp_path, "import sys\nprint('private interpreter output', file=sys.stderr)\nsys.exit(3)")
    with pytest.raises(ValueError, match="check the source") as failure:
        convert_process(child, tmp_path / "unused.json", lambda: False)
    assert "private interpreter output" not in str(failure.value)


def test_cancel_during_validation_rejects_completed_asset(tmp_path, monkeypatch):
    import carveracontroller.addons.tool_visualization.cad_assets as assets

    cancelled = threading.Event()
    monkeypatch.setattr(assets, "load_tool_asset", lambda _path: cancelled.set())
    with pytest.raises(InterruptedError):
        convert_process(command(tmp_path, "pass"), tmp_path / "asset.json", cancelled.is_set)


def test_successful_exit_with_invalid_geometry_is_rejected(tmp_path):
    output = tmp_path / "invalid.json"
    child = command(tmp_path, f"from pathlib import Path\nPath({str(output)!r}).write_text('{{}}')")
    with pytest.raises(ValueError, match="Unsupported tool asset schema"):
        convert_process(child, output, lambda: False)
