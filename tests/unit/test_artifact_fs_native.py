"""Exercise the compiled/signed macOS worker against the portable protocol."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from carveracontroller.machine.artifact_fs_worker import execute
from scripts.build_adaptive_macos import build_artifact_worker
from scripts.verify_artifact_worker import probe

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Native macOS helper")


@pytest.fixture(scope="module")
def helper(tmp_path_factory):
    root = tmp_path_factory.mktemp("native-helper")
    package = Path(__file__).parents[2] / "carveracontroller"
    executable = build_artifact_worker(package, root, root / "controller.app", os.environ.copy())
    # This is the first execution of this newly compiled helper, with stdin kept
    # open. Warm retries cannot satisfy this assertion or package qualification.
    receipt = probe([str(executable)])
    assert receipt["elapsed_s"] <= 4 and receipt["exit"] == 0
    assert receipt["stdin_retained"] and not receipt["file_created"]
    dependencies = subprocess.check_output(["otool", "-L", str(executable)], text=True)
    assert "Python" not in dependencies and "kivy" not in dependencies.lower()
    assert executable.stat().st_size < 256 * 1024
    return executable


def call(helper, request=None, raw=None):
    result = subprocess.run(
        [str(helper)],
        input=raw if raw is not None else json.dumps(request).encode() + b"\n",
        capture_output=True,
        timeout=4,
    )
    assert result.returncode == 0 and not result.stderr
    assert len(result.stdout) <= 4 * 1024 * 1024
    return json.loads(result.stdout)


def parity(helper, request):
    response = call(helper, request)
    assert response["error"] is None
    actual, expected = response["result"], execute(request)
    for left, right in zip(actual.get("entries", []), expected.get("entries", [])):
        assert left.pop("modified") == pytest.approx(right.pop("modified"), abs=1e-6)
    assert actual == expected
    return actual


def test_native_listing_symlinks_unicode_sorting_and_file_selection(helper, tmp_path):
    (tmp_path / "nested").mkdir()
    (tmp_path / "alias").symlink_to(tmp_path / "nested", target_is_directory=True)
    (tmp_path / "broken.json").symlink_to(tmp_path / "absent")
    for name in (
        "part.JSON",
        "STRASSE.ß",
        "İ.Σ",
        "i\u0307.σ",
        "𐐀.json",
        "\ue000.json",
        "é.json",
        "e\u0301-other.json",
        ".hidden.json",
        "unrelated.nc",
    ):
        (tmp_path / name).write_text("original")
    request = {"operation": "list", "path": str(tmp_path), "suffixes": [".json", ".ss", ".ς"]}
    parity(helper, request)
    selected = parity(helper, {**request, "path": str(tmp_path / "part.JSON")})
    assert selected["filename"] == "part.JSON"
    parity(helper, {**request, "path": str(tmp_path / "alias")})
    parity(helper, {**request, "suffixes": []})
    parity(helper, {**request, "suffixes": [""]})


def test_native_create_fallback_and_checks_preserve_files(helper, tmp_path):
    jobs = tmp_path / "owned/jobs"
    request = {"operation": "list", "path": str(jobs), "suffixes": [".json"], "create": True}
    parity(helper, request)
    assert jobs.is_dir()
    parity(helper, {**request, "path": str(tmp_path / "absent"), "create": False, "fallback": str(jobs)})
    existing = jobs / "part.json"
    existing.write_text("retain")
    parity(helper, {"operation": "check", "path": str(existing), "save": False})
    absent = jobs / "new.json"
    parity(helper, {"operation": "check", "path": str(absent), "save": True})
    assert existing.read_text() == "retain" and not absent.exists()
    assert "already exists" in call(helper, {"operation": "check", "path": str(existing), "save": True})["error"]
    assert "existing file" in call(helper, {"operation": "check", "path": str(absent), "save": False})["error"]


def test_native_relative_and_home_paths(helper, tmp_path):
    for path in (".", "~", "~/", str(tmp_path) + "/../" + tmp_path.name):
        parity(helper, {"operation": "list", "path": path, "suffixes": []})


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        1,
        "list",
        {},
        {"operation": "check", "path": "", "save": True},
        {"operation": "check", "path": "a\0b", "save": True},
        {"operation": "check", "path": "a" * 16385, "save": True},
        {"operation": "check", "path": "/unused", "save": 1},
        {"operation": "check", "path": "/unused", "save": True, "other": False},
        {"operation": "check", "path": "/unused"},
        {"operation": "other", "path": "/unused"},
        {"operation": "list", "path": "/unused", "suffixes": None},
        {"operation": "list", "path": "/unused", "suffixes": ["x"] * 129},
        {"operation": "list", "path": "/unused", "suffixes": ["x" * 257]},
        {"operation": "list", "path": "/unused", "suffixes": [False]},
        {"operation": "list", "path": "/unused", "suffixes": ["\0"]},
        {"operation": "list", "path": "/unused", "suffixes": [], "create": 1},
        {"operation": "list", "path": "/unused", "suffixes": [], "fallback": ""},
        {"operation": "list", "path": "/unused", "suffixes": [], "extra": True},
    ],
)
def test_native_rejects_same_invalid_requests(helper, value):
    with pytest.raises((ValueError, TypeError)) as expected:
        execute(value)
    response = call(helper, value)
    assert response == {"result": None, "error": str(expected.value)}


@pytest.mark.parametrize("raw", [b"", b"{", b"null\n", b"[]", b"x" * 65537 + b"\n"])
def test_native_malformed_or_oversized_frame_is_bounded(helper, raw):
    response = call(helper, raw=raw)
    assert response["result"] is None and response["error"]


def test_native_one_line_does_not_consume_next_request(helper, tmp_path):
    request = {"operation": "check", "path": str(tmp_path / "absent"), "save": True}
    raw = json.dumps(request).encode()
    assert call(helper, raw=raw) == {"result": {}, "error": None}  # Legacy EOF framing.
    assert call(helper, raw=raw + b"\ninvalid next request") == {"result": {}, "error": None}


def test_native_counts_hidden_irrelevant_children_before_filtering(helper, tmp_path):
    for index in range(20001):
        (tmp_path / f".hidden-{index}").touch()
    request = {"operation": "list", "path": str(tmp_path), "suffixes": []}
    with pytest.raises(ValueError, match="20,000"):
        execute(request)
    assert "20,000" in call(helper, request)["error"]


def test_native_response_budget_includes_ascii_unicode_escapes(helper, tmp_path):
    folder = tmp_path
    for _ in range(6):
        folder /= "folder" * 20
    folder.mkdir(parents=True)
    for index in range(5000):
        (folder / (f"{index}-" + "é" * 50 + ".json")).touch()
    request = {"operation": "list", "path": str(folder), "suffixes": [".json"]}
    assert "metadata exceeds limit" in call(helper, request)["error"]
