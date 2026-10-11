import ast
import hashlib
import importlib.util
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from carveracontroller.machine.camera_origin_patch import prepare_origin
from carveracontroller.machine.webcam import fetch_frame
from scripts.prepare_camera_origin import prepare
from tests.unit.test_webcam import jpeg

# Portable structure fixture. Exact deployed-source qualification is retained
# separately; this fixture does not claim to be the Ubuntu service source.
FIXTURE = b"""import http.server,threading,time
from pathlib import Path
condition=threading.Condition()
latest=None
last_frame=0
last_frame_utc=0
ffmpeg=None
TEST_FRAME=None
allowed_client=True
commands=[]
def query(*args):
    commands.append(args)
    raise AssertionError('Unexpected camera control')
def capture():
    global latest,last_frame,last_frame_utc,ffmpeg
    for a in range(1):
        for b in range(1):
            for c in range(1):
                frame=TEST_FRAME
                with condition:
                    latest=frame;last_frame=time.monotonic();last_frame_utc=time.time();condition.notify_all()
class Handler(http.server.BaseHTTPRequestHandler):
    def allowed(self): return allowed_client
    def log_message(self,*args): pass
    def data(self,code,body,kind='application/json',captured=None):
        self.send_response(code);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        if kind=='image/jpeg': self.send_header('X-Camera-Frame-Time',str(captured))
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if not self.allowed(): self.send_error(403);return
        if self.path!='/snapshot.jpg': self.send_error(404);return
        with condition:
            frame=latest;captured=last_frame_utc
        if frame is None or time.monotonic()-last_frame>=3: self.send_error(503);return
        self.data(200,frame,'image/jpeg',captured=captured)
    def do_POST(self):
        if not self.allowed(): self.send_error(403);return
        self.send_error(400)
"""


@pytest.fixture
def patched_origin(monkeypatch):
    patched = prepare_origin(FIXTURE, hashlib.sha256(FIXTURE).hexdigest())
    from carveracontroller.machine import camera_origin

    monkeypatch.setitem(__import__("sys").modules, "camera_origin", camera_origin)
    namespace = {"__name__": "portable_origin_fixture"}
    exec(compile(patched, "portable-origin-fixture.py", "exec"), namespace)
    namespace["TEST_FRAME"] = jpeg()
    namespace["capture"]()
    server = ThreadingHTTPServer(("127.0.0.1", 0), namespace["Handler"])
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield namespace, f"http://127.0.0.1:{server.server_port}", patched
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)
        assert not worker.is_alive()


def test_instrumented_capture_and_actual_http_handler_deliver_client_clock_evidence(patched_origin):
    namespace, url, _patched = patched_origin
    frame = fetch_frame(url + "/snapshot.jpg", 1)
    assert frame.clock.frame_time_basis == "jpeg-assembled"
    assert frame.clock.offset_bounds[0] <= 0 <= frame.clock.offset_bounds[1]
    assert frame.captured_at == namespace["last_frame_utc"]
    assert frame.jpeg == jpeg() and frame.age() < 2
    assert namespace["commands"] == []


def test_legacy_browser_without_nonce_retains_same_jpeg_and_timestamp(patched_origin):
    namespace, url, _patched = patched_origin
    with urlopen(url + "/snapshot.jpg", timeout=2) as response:
        assert response.read() == jpeg()
        assert float(response.headers["X-Camera-Frame-Time"]) == namespace["last_frame_utc"]
        assert response.headers.get("X-Camera-Clock-ID") is None
        assert response.headers["Cache-Control"] == "no-store"
    assert namespace["commands"] == []


@pytest.mark.parametrize(
    "scenario,code", [("forbidden", 403), ("missing", 503), ("stale", 503), ("path", 404), ("post", 400)]
)
def test_existing_refusals_never_expose_a_timed_jpeg_or_issue_control(patched_origin, scenario, code):
    namespace, url, _patched = patched_origin
    path, method = "/snapshot.jpg", "GET"
    if scenario == "forbidden":
        namespace["allowed_client"] = False
    elif scenario == "missing":
        namespace["latest"] = None
    elif scenario == "stale":
        namespace["last_frame"] = time.monotonic() - 10
    elif scenario == "path":
        path = "/private"
    elif scenario == "post":
        method = "POST"
    with pytest.raises(HTTPError) as caught:
        urlopen(Request(url + path, method=method), timeout=2)
    assert caught.value.code == code
    assert caught.value.headers.get("X-Camera-Clock-ID") is None
    caught.value.close()
    assert namespace["commands"] == []


def test_patch_preserves_original_non_timing_methods_and_refuses_non_unique_structure(patched_origin):
    _namespace, _url, patched = patched_origin

    def methods(source):
        handler = next(x for x in ast.parse(source).body if isinstance(x, ast.ClassDef))
        return {x.name: ast.dump(x, include_attributes=False) for x in handler.body if isinstance(x, ast.FunctionDef)}

    before, after = methods(FIXTURE), methods(patched)
    assert all(before[name] == after[name] for name in ("allowed", "log_message", "do_POST"))
    changed = FIXTURE + b"\ncondition=threading.Condition()\n"
    with pytest.raises(ValueError, match="structure"):
        prepare_origin(changed, hashlib.sha256(changed).hexdigest())


def test_cli_refuses_unreviewed_source_symlink_and_existing_output(tmp_path, monkeypatch):
    source = tmp_path / "viewer.py"
    source.write_bytes(FIXTURE)
    output = tmp_path / "output"
    with pytest.raises(ValueError, match="changed"):
        prepare(source, output)
    assert not output.exists()
    link = tmp_path / "link.py"
    link.symlink_to(source)
    with pytest.raises(ValueError, match="regular"):
        prepare(link, output)
    monkeypatch.setattr(
        "scripts.prepare_camera_origin.prepare_origin",
        lambda data: prepare_origin(data, hashlib.sha256(data).hexdigest()),
    )
    report = prepare(source, output)
    assert report["original_sha256"] == hashlib.sha256(FIXTURE).hexdigest()
    assert all(
        hashlib.sha256((output / name).read_bytes()).hexdigest() == digest for name, digest in report["files"].items()
    )
    support = output / "camera_origin.py"
    spec = importlib.util.spec_from_file_location("standalone_camera_origin_test", support)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(__import__("sys").modules, spec.name, module)
    spec.loader.exec_module(module)
    assert module.CameraOriginClock().begin("a" * 32) is not None
    with pytest.raises(FileExistsError):
        prepare(source, output)
    assert report["files"]["viewer.py"] == hashlib.sha256((output / "viewer.py").read_bytes()).hexdigest()
