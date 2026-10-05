import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from carveracontroller.machine.artifact_fs import execute, filesystem_request


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
    script = Path(__file__).parents[2] / "carveracontroller" / "machine" / "artifact_fs.py"
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
            filesystem_request({}, command=["blocked"], timeout=0)
    with pytest.raises(ValueError, match="still stopping"):
        filesystem_request({}, command=["blocked"], timeout=0)
    assert len(children) == 2
    children[0].returncode = -9
    with pytest.raises(ValueError, match="timed out"):
        filesystem_request({}, command=["blocked"], timeout=0)
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


def test_worker_uses_parent_pipes_when_windowed_streams_are_none(tmp_path):
    import json

    script = Path(__file__).parents[2] / "carveracontroller" / "machine" / "artifact_fs.py"
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
            filesystem_request({"operation": "check", "path": str(tmp_path / "new.json"), "save": True}, timeout=1)
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
            filesystem_request({}, cancelled=cancelled.is_set, timeout=1)
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
        filesystem_request({}, timeout=0.1)
    assert 0.09 <= time.monotonic() - start < 0.5
    assert not semaphore.acquire(blocking=False)


def test_slot_wait_consumes_the_request_deadline(tmp_path, monkeypatch):
    from carveracontroller.machine import artifact_fs as module

    semaphore = threading.BoundedSemaphore(2)
    semaphore.acquire()
    semaphore.acquire()
    monkeypatch.setattr(module, "_slots", semaphore)
    monkeypatch.setattr(module, "_retired", [])
    timer = threading.Timer(0.2, semaphore.release)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(ValueError, match="timed out"):
            filesystem_request({}, command=[sys.executable, "-c", "import time; time.sleep(20)"], timeout=0.3)
    finally:
        timer.join()
    assert time.monotonic() - start < 0.6
    assert semaphore.acquire(blocking=False)
    assert not semaphore.acquire(blocking=False)
