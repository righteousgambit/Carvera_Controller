"""Quick inspection captures bounded bytes through the standalone filesystem helper."""

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from carveracontroller.machine import artifact_fs
from carveracontroller.machine.artifact_fs_worker import PROGRAM_MAX_BYTES, execute, validate_request
from carveracontroller.machine.program_preview import inspect_program, inspect_program_bytes


@pytest.mark.parametrize(
    "content",
    [b"", b"G21 G90 G54\r\nG0 X0 Y0 Z1\r\nG1 X3 F100\r\n", "(café)\nG20\n".encode(), b"\x00\xff\x80\r\n"],
    ids=["empty", "crlf", "utf8", "binary"],
)
def test_real_capture_retains_exact_bytes_and_lexical_path(tmp_path, content):
    folder = tmp_path / "folder"
    folder.mkdir()
    source = tmp_path / "part.nc"
    source.write_bytes(content)
    path = str(folder / ".." / source.name)
    request = {"operation": "program-read", "path": path}
    result = artifact_fs.filesystem_request(request)
    assert result == execute(request)
    assert result == {"path": path, "content_b64": base64.b64encode(content).decode("ascii")}
    assert artifact_fs.read_program_bytes(path) == content


@pytest.mark.parametrize("size", [PROGRAM_MAX_BYTES - 1, PROGRAM_MAX_BYTES, PROGRAM_MAX_BYTES + 1])
def test_capture_enforces_actual_byte_limit_without_publishing_prefix(tmp_path, size):
    source = tmp_path / "part.nc"
    source.write_bytes(b"x" * size)
    if size > PROGRAM_MAX_BYTES:
        with pytest.raises(ValueError, match="Quick inspection limit: 1,048,576 bytes"):
            artifact_fs.read_program_bytes(source)
    else:
        assert artifact_fs.read_program_bytes(source) == b"x" * size


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "program-read", "path": "part.nc"},
        {"operation": "program-read", "path": "/part.nc", "byte_limit": 1},
        {"operation": "program-read", "path": "/part.nc", "save": False},
        {"operation": "program-read", "path": ""},
        {"operation": "program-read", "path": "/bad\0.nc"},
    ],
    ids=["relative", "limit-override", "unknown-field", "empty", "nul"],
)
def test_capture_request_has_fixed_bound_and_no_parent_path_resolution(payload):
    with pytest.raises(ValueError):
        validate_request(payload)


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"path": "/part.nc", "content_b64": "", "extra": True},
        {"path": "/neighbor.nc", "content_b64": ""},
        {"path": "/part.nc", "content_b64": None},
        {"path": "/part.nc", "content_b64": "%%%="},
        {"path": "/part.nc", "content_b64": "Zw==\n"},
        {"path": "/part.nc", "content_b64": "Zg"},
        {"path": "/part.nc", "content_b64": "Zh=="},
        {"path": "/part.nc", "content_b64": "é"},
        {"path": "/part.nc", "content_b64": base64.b64encode(b"x" * (PROGRAM_MAX_BYTES + 1)).decode()},
    ],
    ids=[
        "missing",
        "extra",
        "other-path",
        "wrong-type",
        "alphabet",
        "whitespace",
        "padding",
        "pad-bits",
        "nonascii",
        "oversize",
    ],
)
def test_capture_response_rejects_wrong_identity_malformed_and_oversized_content(result):
    with pytest.raises(ValueError, match="invalid metadata"):
        artifact_fs.validate_response(
            {"result": result, "error": None}, {"operation": "program-read", "path": "/part.nc"}
        )


def test_capture_and_parse_use_the_same_bytes_after_source_changes(tmp_path, monkeypatch):
    path = tmp_path / "part.nc"
    raw = b"(Operation: retained)\r\nG21 G90 G17 G94 G54\r\nT7 M6\r\nG0 X0 Y0 Z1\r\nG1 X8 F100\r\n"
    path.write_bytes(raw)
    expected = inspect_program(path)
    captured = artifact_fs.read_program_bytes(path)
    path.write_bytes(b"G20\nT99\n")
    path.unlink()

    def no_reopen(*args, **kwargs):
        raise AssertionError("Captured-byte parsing must not reopen a filesystem path")

    monkeypatch.setattr(Path, "open", no_reopen)
    inspected = inspect_program_bytes(captured)
    assert inspected == expected
    assert inspected.digest == hashlib.sha256(raw).hexdigest()
    assert inspected.tool_ids == (7,)


@pytest.mark.parametrize(
    "content, kwargs, error",
    [
        (b"G21\xff", {}, UnicodeError),
        (b"G21\n" * 3, {"line_limit": 2}, ValueError),
        (b"G21\n", {"byte_limit": 3}, ValueError),
    ],
    ids=["encoding", "line-limit", "byte-limit"],
)
def test_captured_parser_retains_encoding_and_complete_input_limits(content, kwargs, error):
    with pytest.raises(error):
        inspect_program_bytes(content, **kwargs)


def test_missing_program_is_an_error_not_empty_content(tmp_path):
    with pytest.raises(ValueError):
        artifact_fs.read_program_bytes(tmp_path / "missing.nc")


def test_captured_parser_cooperatively_cancels_inside_real_motion_parsing():
    content = b"G21 G90 G91.1 G17 G94 G54\nG0 X10 Y0 Z0\n" + b"G2 X10 Y0 I-10 J0 F100\n" * 4998
    checks = 0

    def cancelled():
        nonlocal checks
        checks += 1
        return checks >= 50

    # Reaching fifty checkpoints requires the real parser's internal loop;
    # inspection's own checks cannot satisfy this cancellation by themselves.
    with pytest.raises(InterruptedError, match="cancelled"):
        inspect_program_bytes(content, cancelled=cancelled)
    assert checks == 50
    healthy = b"G21 G90 G54\nG0 X0 Y0 Z0\nG1 X2 F100\n"
    result = inspect_program_bytes(healthy)
    assert result.digest == hashlib.sha256(healthy).hexdigest()
    assert result.segments[-1].end_mm == (2, 0, 0)


def test_program_capture_worker_boots_without_controller_or_ui(tmp_path):
    path = tmp_path / "part.nc"
    path.write_bytes(b"G21\n")
    worker = Path(artifact_fs.__file__).with_name("artifact_fs_worker.py")
    process = subprocess.run(
        [sys.executable, "-v", str(worker)],
        input=json.dumps({"operation": "program-read", "path": str(path)}),
        capture_output=True,
        text=True,
        timeout=3,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["result"]["content_b64"] == "RzIxCg=="
    assert "kivy" not in process.stderr.lower()
    assert "carveracontroller.main" not in process.stderr
    assert "import 'subprocess'" not in process.stderr
    assert "import 'threading'" not in process.stderr
