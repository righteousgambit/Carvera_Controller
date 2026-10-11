import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from carveracontroller.machine.artifact_fs import execute, filesystem_request


def test_frozen_macos_uses_dedicated_worker_and_refuses_escape(tmp_path, monkeypatch):
    from carveracontroller.machine.artifact_fs import macos_worker_executable, worker_command

    bundle = tmp_path / "controller.app"
    executable = bundle / "Contents/MacOS/carveracontroller"
    helper = macos_worker_executable(bundle)
    helper.parent.mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(sys, "executable", str(executable))
    with pytest.raises(ValueError, match="helper is unavailable"):
        worker_command()
    helper.write_text("#!/bin/sh\nprintf '%s\\n' '{\"result\": {}, \"error\": null}'\n")
    helper.chmod(0o755)
    assert worker_command() == [str(helper)]
    assert filesystem_request({"operation": "check", "path": str(tmp_path / "absent"), "save": True}) == {}
    outside = tmp_path / "outside"
    outside.write_bytes(helper.read_bytes())
    helper.unlink()
    helper.symlink_to(outside)
    with pytest.raises(ValueError, match="helper is unavailable"):
        worker_command()


def test_other_frozen_platform_retains_early_worker_dispatch(monkeypatch):
    from carveracontroller.machine.artifact_fs import worker_command

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    assert worker_command() == [sys.executable, "--artifact-fs-worker"]


def test_real_helper_lists_resolved_locations_and_checks_without_mutation(tmp_path):
    (tmp_path / "nested").mkdir()
    file = tmp_path / "part.JSON"
    file.write_text("original")
    (tmp_path / "irrelevant.nc").write_text("M2")
    (tmp_path / ".hidden.json").write_text("{}")
    link = tmp_path / "alias"
    link.symlink_to(tmp_path / "nested", target_is_directory=True)
    request = {"operation": "list", "path": str(file), "suffixes": [".json"]}
    result = filesystem_request(request)
    assert result == execute(request)
    assert result["filename"] == file.name
    assert [item["name"] for item in result["entries"]] == ["alias", "nested", "part.JSON"]
    assert filesystem_request({**request, "path": str(link)})["path"] == str(tmp_path / "nested")
    with pytest.raises(ValueError, match="already exists"):
        filesystem_request({"operation": "check", "path": str(file), "save": True})
    assert filesystem_request({"operation": "check", "path": str(file), "save": False}) == {}
    assert file.read_text() == "original"
    with pytest.raises(ValueError, match="existing file"):
        filesystem_request({"operation": "check", "path": str(tmp_path / "missing.json"), "save": False})


def test_helper_timeout_and_cancel_terminate_the_same_child(tmp_path, monkeypatch):
    original = subprocess.Popen
    children = []

    def track(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", track)
    command = [sys.executable, "-c", "import time; time.sleep(20)"]
    request = {"operation": "list", "path": str(tmp_path), "suffixes": [".json"]}
    start = time.monotonic()
    with pytest.raises(ValueError, match="timed out"):
        filesystem_request(request, command=command, timeout=0.15)
    assert time.monotonic() - start < 1
    assert len(children) == 1 and children[0].poll() is not None
    cancelled = threading.Event()
    timer = threading.Timer(0.1, cancelled.set)
    timer.start()
    try:
        with pytest.raises(ValueError, match="cancelled"):
            filesystem_request(request, command=command, cancelled=cancelled.is_set)
    finally:
        timer.join()
    assert len(children) == 2 and children[1].poll() is not None


def test_helper_can_create_jobs_or_use_explicit_fallback(tmp_path):
    jobs = tmp_path / "owned" / "jobs"
    request = {"operation": "list", "path": str(jobs), "suffixes": [".json"], "create": True}
    assert filesystem_request(request)["path"] == str(jobs)
    assert jobs.is_dir()
    fallback = {**request, "path": str(tmp_path / "missing"), "create": False, "fallback": str(tmp_path)}
    assert filesystem_request(fallback)["path"] == str(tmp_path)


def test_worker_does_not_initialize_kivy_or_controller(tmp_path):
    script = Path(__file__).parents[2] / "carveracontroller" / "machine" / "artifact_fs_worker.py"
    # Verbose import tracing is evidence that the real worker imports neither UI
    # nor controller; an engine test alone would not cover bootstrap isolation.
    process = subprocess.run(
        [sys.executable, "-v", str(script)],
        input='{"operation":"check","path":"' + str(tmp_path / "new.json") + '","save":true}',
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert process.returncode == 0 and '"error": null' in process.stdout
    assert "kivy" not in process.stderr.lower()
    assert "carveracontroller.main" not in process.stderr
    assert "import 'subprocess'" not in process.stderr
    assert "import 'threading'" not in process.stderr
    assert "import '_posixsubprocess'" not in process.stderr


def test_unreaped_helpers_retain_slots_instead_of_accumulating(monkeypatch):
    from carveracontroller.machine import artifact_fs as module

    class KernelBlocked:
        stdin = stdout = None
        returncode = None

        def poll(self):
            return self.returncode

        def kill(self):
            pass

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("blocked", timeout)

    children = []

    def launch(*_, **__):
        child = KernelBlocked()
        children.append(child)
        return child

    monkeypatch.setattr(module, "_slots", threading.BoundedSemaphore(2))
    monkeypatch.setattr(module, "_retired", [])
    monkeypatch.setattr(module.subprocess, "Popen", launch)
    for _ in range(2):
        with pytest.raises(ValueError, match="timed out"):
            filesystem_request({"operation": "check", "path": "/unused", "save": True}, command=["blocked"], timeout=0)
    with pytest.raises(ValueError, match="still stopping"):
        filesystem_request({"operation": "check", "path": "/unused", "save": True}, command=["blocked"], timeout=0)
    assert len(children) == 2
    children[0].returncode = -9
    with pytest.raises(ValueError, match="timed out"):
        filesystem_request({"operation": "check", "path": "/unused", "save": True}, command=["blocked"], timeout=0)
    assert len(children) == 3 and len(module._retired) == 2


def test_application_worker_flag_dispatches_before_ui_imports(tmp_path):
    import json

    process = subprocess.run(
        [sys.executable, "-v", "-m", "carveracontroller", "--artifact-fs-worker"],
        input=json.dumps({"operation": "check", "path": str(tmp_path / "new.json"), "save": True}),
        capture_output=True,
        text=True,
        timeout=3,
        cwd=Path(__file__).parents[2],
    )
    assert process.returncode == 0 and json.loads(process.stdout)["error"] is None
    assert "kivy" not in process.stderr.lower()
    assert "carveracontroller.main" not in process.stderr
    assert "import 'subprocess'" not in process.stderr
    assert "import 'threading'" not in process.stderr
    assert "import '_posixsubprocess'" not in process.stderr


def test_worker_uses_parent_pipes_when_windowed_streams_are_none(tmp_path):
    import json

    script = Path(__file__).parents[2] / "carveracontroller" / "machine" / "artifact_fs_worker.py"
    bootstrap = "import sys,runpy; sys.stdin=sys.stdout=None; runpy.run_path(sys.argv[1],run_name='__main__')"
    process = subprocess.run(
        [sys.executable, "-c", bootstrap, str(script)],
        input=json.dumps({"operation": "check", "path": str(tmp_path / "new.json"), "save": True}),
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert process.returncode == 0 and json.loads(process.stdout)["error"] is None


def test_slot_wait_reaps_exiting_helper_without_manual_retry(tmp_path, monkeypatch):
    from carveracontroller.machine import artifact_fs as module

    exited = threading.Event()

    class Retiring:
        def poll(self):
            return -9 if exited.is_set() else None

    semaphore = threading.BoundedSemaphore(2)
    semaphore.acquire()
    semaphore.acquire()
    monkeypatch.setattr(module, "_slots", semaphore)
    monkeypatch.setattr(module, "_retired", [Retiring()])
    timer = threading.Timer(0.1, exited.set)
    timer.start()
    try:
        assert (
            filesystem_request(
                {"operation": "check", "path": str(tmp_path / "new.json"), "save": True},
                timeout=1,
                # This test owns slot retirement, not Python module startup.
                # Actual worker startup/framing has its independent 4s probe.
                command=[sys.executable, "-S", "-c", 'print(\'{"result": {}, "error": null}\')'],
            )
            == {}
        )
    finally:
        timer.join()
    assert module._retired == []
    assert semaphore.acquire(blocking=False)
    assert not semaphore.acquire(blocking=False)  # Other active slot remains owned.


def test_waiting_request_cancels_without_launch_or_slot_leak(monkeypatch):
    from carveracontroller.machine import artifact_fs as module

    semaphore = threading.BoundedSemaphore(2)
    semaphore.acquire()
    semaphore.acquire()
    monkeypatch.setattr(module, "_slots", semaphore)
    monkeypatch.setattr(module, "_retired", [])
    launches = []
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: launches.append(args))
    cancelled = threading.Event()
    timer = threading.Timer(0.1, cancelled.set)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(ValueError, match="cancelled"):
            filesystem_request(
                {"operation": "check", "path": "/unused", "save": True}, cancelled=cancelled.is_set, timeout=1
            )
    finally:
        timer.join()
    assert time.monotonic() - start < 0.5
    assert not launches and not semaphore.acquire(blocking=False)


def test_active_slot_contention_is_bounded_and_distinct_from_retirement(monkeypatch):
    from carveracontroller.machine import artifact_fs as module

    semaphore = threading.BoundedSemaphore(2)
    semaphore.acquire()
    semaphore.acquire()
    monkeypatch.setattr(module, "_slots", semaphore)
    monkeypatch.setattr(module, "_retired", [])
    start = time.monotonic()
    with pytest.raises(ValueError, match="service busy"):
        filesystem_request({"operation": "check", "path": "/unused", "save": True}, timeout=0.1)
    assert 0.09 <= time.monotonic() - start < 0.5
    assert not semaphore.acquire(blocking=False)


def test_slot_wait_consumes_the_request_deadline(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from carveracontroller.machine import artifact_fs as module

    semaphore = threading.BoundedSemaphore(2)
    semaphore.acquire()
    semaphore.acquire()
    monkeypatch.setattr(module, "_slots", semaphore)
    monkeypatch.setattr(module, "_retired", [])
    clock = [0.0]
    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    acquire = module._acquire_slot
    deadlines, waits = [], []

    def queued(deadline, cancelled):
        deadlines.append(deadline)
        clock[0] += 0.2
        semaphore.release()
        acquire(deadline, cancelled)

    class Stalled:
        stdin = stdout = None
        returncode = None

        def communicate(self, *, input, timeout):
            waits.append(timeout)
            clock[0] += timeout
            raise subprocess.TimeoutExpired("stalled", timeout)

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

        def wait(self, timeout):
            return self.returncode

    monkeypatch.setattr(module, "_acquire_slot", queued)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *_args, **_kwargs: Stalled())
    with pytest.raises(ValueError, match="timed out"):
        filesystem_request({"operation": "check", "path": "/unused", "save": True}, command=["stalled"], timeout=0.3)
    # Queueing consumes 0.2s of the same 0.3s deadline. Resetting the deadline
    # after acquiring a slot would incorrectly give the child another 0.3s.
    assert deadlines == pytest.approx([0.3])
    assert sum(waits) == pytest.approx(0.1)
    assert clock[0] == pytest.approx(0.3)
    assert semaphore.acquire(blocking=False)
    assert not semaphore.acquire(blocking=False)


@pytest.mark.parametrize(
    "kind",
    [
        "envelope",
        "error_type",
        "mixed_error",
        "entries",
        "path",
        "name",
        "size",
        "flag",
        "timestamp",
        "suffix",
        "duplicate",
    ],
)
def test_malformed_helper_metadata_is_recoverable_and_reaped(tmp_path, monkeypatch, kind):
    import copy
    import json

    entry = {"name": "part.json", "path": str(tmp_path / "part.json"), "is_dir": False, "size": 3, "modified": 1.0}
    response = {"result": {"path": str(tmp_path), "filename": None, "entries": [entry]}, "error": None}
    if kind == "envelope":
        response = []
    elif kind == "error_type":
        response = {"result": None, "error": ["bad"]}
    elif kind == "mixed_error":
        response["error"] = "bad"
    elif kind == "entries":
        response["result"]["entries"] = None
    elif kind == "duplicate":
        response["result"]["entries"].append(copy.deepcopy(entry))
    else:
        field, value = {
            "path": ("path", str(tmp_path.parent / "elsewhere.json")),
            "name": ("name", "../part.json"),
            "size": ("size", True),
            "flag": ("is_dir", 1),
            "timestamp": ("modified", float("nan")),
            "suffix": ("name", "part.nc"),
        }[kind]
        entry[field] = value
        if kind == "suffix":
            entry["path"] = str(tmp_path / "part.nc")
    original, children = subprocess.Popen, []

    def tracked(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", tracked)
    command = [sys.executable, "-c", "print(" + repr(json.dumps(response)) + ")"]
    with pytest.raises(ValueError, match="invalid metadata"):
        filesystem_request({"operation": "list", "path": str(tmp_path), "suffixes": [".json"]}, command=command)
    assert len(children) == 1 and children[0].poll() is not None
    # A rejected response releases capacity and the next real request succeeds.
    assert filesystem_request({"operation": "check", "path": str(tmp_path / "new.json"), "save": True}) == {}


def test_invalid_create_request_never_launches_or_creates(tmp_path, monkeypatch):
    from unittest.mock import Mock

    target = tmp_path / "new-folder"
    launch = Mock(side_effect=AssertionError("Invalid request must not launch"))
    monkeypatch.setattr(subprocess, "Popen", launch)
    with pytest.raises(ValueError, match="Invalid folder-list request"):
        filesystem_request({"operation": "list", "path": str(target), "suffixes": [".json"], "create": "yes"})
    launch.assert_not_called()
    assert not target.exists()


def test_cancel_after_helper_response_rejects_publication_and_releases_slot(monkeypatch):
    from carveracontroller.machine import artifact_fs as module

    cancelled = threading.Event()
    slots = threading.BoundedSemaphore(1)

    class Completed:
        stdin = stdout = None
        returncode = 0

        def communicate(self, **_):
            cancelled.set()
            return b'{"result":{},"error":null}', None

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

    monkeypatch.setattr(module, "_slots", slots)
    monkeypatch.setattr(module.subprocess, "Popen", lambda *args, **kwargs: Completed())
    with pytest.raises(ValueError, match="cancelled"):
        filesystem_request({"operation": "check", "path": "/unused", "save": True}, cancelled=cancelled.is_set)
    assert slots.acquire(False)
    slots.release()


def test_uppercase_suffix_filter_and_negative_finite_file_time_are_valid(tmp_path):
    import json

    file = tmp_path / "part.JSON"
    file.write_text("{}")
    request = {"operation": "list", "path": str(tmp_path), "suffixes": [".JSON"]}
    assert filesystem_request(request)["entries"][0]["name"] == "part.JSON"
    response = {
        "result": {
            "path": str(tmp_path),
            "filename": None,
            "entries": [{"name": "part.JSON", "path": str(file), "is_dir": False, "size": 2, "modified": -1.0}],
        },
        "error": None,
    }
    result = filesystem_request(request, command=[sys.executable, "-c", "print(" + repr(json.dumps(response)) + ")"])
    assert result["entries"][0]["modified"] == -1.0


@pytest.mark.parametrize("output", ["", "{", "not json"])
def test_truncated_or_nonjson_helper_output_uses_recoverable_error(tmp_path, output):
    with pytest.raises(ValueError, match="invalid metadata"):
        filesystem_request(
            {"operation": "check", "path": str(tmp_path / "new.json"), "save": True},
            command=[sys.executable, "-c", "print(" + repr(output) + ", end='')"],
        )


def test_worker_answers_complete_frame_without_waiting_for_stdin_eof(tmp_path):
    import json
    import selectors

    script = Path(__file__).parents[2] / "carveracontroller" / "machine" / "artifact_fs_worker.py"
    # Measure framing after the reference implementation is imported. The
    # independent cold-start probe still bounds import + request + exit at 4s.
    bootstrap = (
        "import os,runpy,sys; worker=runpy.run_path(sys.argv[1]); os.write(2,b'ready\\n'); worker['worker_main']()"
    )
    child = subprocess.Popen(
        [sys.executable, "-c", bootstrap, str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stderr, selectors.EVENT_READ)
            assert selector.select(timeout=4), "Reference worker did not finish bootstrap"
        assert child.stderr.readline() == b"ready\n"
        child.stdin.write(
            json.dumps({"operation": "check", "path": str(tmp_path / "new.json"), "save": True}).encode() + b"\n"
        )
        child.stdin.flush()  # Deliberately retain the writer: request framing must suffice.
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=1), "Complete request waits for stdin EOF"
        response = json.loads(child.stdout.readline())
        assert response == {"result": {}, "error": None}
        assert child.wait(timeout=1) == 0
        assert not (tmp_path / "new.json").exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=1)
        child.stdin.close()
        child.stdout.close()
        child.stderr.close()
