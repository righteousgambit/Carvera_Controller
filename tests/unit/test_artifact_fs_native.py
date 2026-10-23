"""Exercise the compiled/signed macOS worker against the portable protocol."""

import base64
import errno
import hashlib
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
    assert receipt["child_pid"] > 0
    assert [row["stage"] for row in receipt["startup_stages"]] == [
        "main_entered",
        "request_read",
        "request_parsed",
        "request_executed",
        "response_encoded",
        "response_written",
    ]
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
    if actual.get("selected") is not None and expected.get("selected") is not None:
        assert actual["selected"].pop("modified") == pytest.approx(expected["selected"].pop("modified"), abs=1e-6)
    assert actual == expected
    return actual


def program_request(directory, **changes):
    return {
        "operation": "program-list",
        "path": str(directory),
        "base": str(directory),
        "navigate": False,
        "initial_candidates": None,
        "collection": None,
        "places_path": str(directory / "program-places.json"),
        **changes,
    }


@pytest.mark.parametrize(
    "content",
    [b"", b"G90\r\nG1 X2\r\n", "(caf\u00e9)\nG0 X0\n".encode(), b"\xff\xfe\x00G1 X2\r\n", bytes(range(256))],
    ids=["empty", "crlf", "utf8", "invalid-utf8", "all-byte-values"],
)
def test_native_program_read_preserves_exact_bytes_and_digest(helper, tmp_path, content):
    path = tmp_path / "program.nc"
    path.write_bytes(content)
    result = parity(helper, {"operation": "program-read", "path": str(path)})
    assert set(result) == {"path", "content_b64"} and result["path"] == str(path)
    assert result["content_b64"] == base64.b64encode(content).decode("ascii")
    captured = base64.b64decode(result["content_b64"], validate=True)
    assert captured == content and hashlib.sha256(captured).digest() == hashlib.sha256(content).digest()
    assert path.read_bytes() == content


def test_native_program_read_boundary_and_actual_over_limit(helper, tmp_path):
    path = tmp_path / "program.nc"
    boundary = bytes(range(256)) * 4096
    path.write_bytes(boundary)
    result = parity(helper, {"operation": "program-read", "path": str(path)})
    assert len(result["content_b64"]) == 4 * ((1048576 + 2) // 3)
    assert base64.b64decode(result["content_b64"], validate=True) == boundary
    path.write_bytes(boundary + b"x")
    request = {"operation": "program-read", "path": str(path)}
    with pytest.raises(ValueError) as expected:
        execute(request)
    assert (
        str(expected.value) == "Quick inspection limit: 1,048,576 bytes. Load a local preview for this larger program."
    )
    assert call(helper, request) == {"result": None, "error": str(expected.value)}
    assert path.read_bytes() == boundary + b"x"


def test_native_program_read_preserves_request_path_and_symlink_traversal(helper, tmp_path):
    nested = tmp_path / "nested/child"
    nested.mkdir(parents=True)
    alias = tmp_path / "alias"
    alias.symlink_to(nested, target_is_directory=True)
    (tmp_path / "nested/program.nc").write_bytes(b"nested\r\n")
    (tmp_path / "program.nc").write_bytes(b"root\n")
    for path in (
        str(alias) + "/../program.nc",
        str(tmp_path) + "//./program.nc/.",
        "/" + str(tmp_path / "program.nc"),
    ):
        result = parity(helper, {"operation": "program-read", "path": path})
        assert result["path"] == path
        assert base64.b64decode(result["content_b64"], validate=True) == Path(path).read_bytes()


@pytest.mark.parametrize(
    "value",
    [
        {"operation": "program-read"},
        {"operation": "program-read", "path": None},
        {"operation": "program-read", "path": ""},
        {"operation": "program-read", "path": "/a\0b"},
        {"operation": "program-read", "path": "/" + "a" * 16384},
        {"operation": "program-read", "path": "relative.nc"},
        {"operation": "program-read", "path": "/unused", "extra": True},
    ],
    ids=["missing-path", "null-path", "empty-path", "nul-path", "over-path-limit", "relative-path", "extra-key"],
)
def test_native_program_read_rejects_invalid_requests(helper, value):
    with pytest.raises(ValueError) as expected:
        execute(value)
    assert call(helper, value) == {"result": None, "error": str(expected.value)}


def test_native_program_read_io_errors_have_no_content(helper, tmp_path):
    for path in (tmp_path / "missing.nc", tmp_path):
        request = {"operation": "program-read", "path": str(path)}
        with pytest.raises(OSError) as expected:
            execute(request)
        actual = call(helper, request)
        assert actual == {"result": None, "error": os.strerror(expected.value.errno)}


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
    for path in (".", "~", "~/", "./~/.", str(tmp_path) + "/../" + tmp_path.name):
        parity(helper, {"operation": "list", "path": path, "suffixes": []})


def test_native_lexical_path_components_preserve_symlink_parent_traversal(helper, tmp_path):
    file = tmp_path / "part.json"
    file.write_text("retain")
    for suffix in ("/", "/.", "//./"):
        parity(helper, {"operation": "list", "path": str(file) + suffix, "suffixes": [".json"]})
        parity(helper, {"operation": "check", "path": str(file) + suffix, "save": False})
    nested = tmp_path / "nested/child"
    nested.mkdir(parents=True)
    link = tmp_path / "alias"
    link.symlink_to(nested, target_is_directory=True)
    result = parity(helper, {"operation": "list", "path": str(link) + "/..", "suffixes": []})
    assert result["path"] == str(tmp_path / "nested")


def test_native_home_expansion_uses_same_environment_as_parent(helper, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path) + "/")
    parity(helper, {"operation": "list", "path": "~", "suffixes": []})
    parity(helper, {"operation": "list", "path": "~/.", "suffixes": []})


def test_native_program_listing_preserves_lexical_paths_and_program_sorting(helper, tmp_path):
    nested = tmp_path / "nested/child"
    nested.mkdir(parents=True)
    (tmp_path / "alias").symlink_to(nested, target_is_directory=True)
    (tmp_path / "broken.nc").symlink_to(tmp_path / "absent")
    for name in ("part.NC", "ß.nc", "ss.nc", "𐐀.gcode", "\ue000.tap", ".hidden.nc", "unrelated.json", ".nc"):
        (tmp_path / name).write_text("G1 X2\n")
    request = program_request(tmp_path)
    result = parity(helper, request)
    names = [entry["name"] for entry in result["entries"]]
    assert names[:2] == ["alias", "nested"]
    # Case-insensitive APFS can coalesce these full-casefold equivalents.
    if {"ss.nc", "ß.nc"}.issubset(names):
        assert names.index("ss.nc") < names.index("ß.nc")
    assert not {"broken.nc", ".hidden.nc", "unrelated.json", ".nc"}.intersection(names)
    assert result["places"] == {"recent": [], "favorites": [], "error": None}
    traversed = parity(helper, {**request, "path": "alias/.."})
    assert traversed["path"] == str(tmp_path / "alias/..")
    assert [entry["name"] for entry in traversed["entries"]] == ["child"]
    for path in (str(tmp_path) + "//./", "/" + str(tmp_path), "///" + str(tmp_path).lstrip("/")):
        parity(helper, {**request, "path": path})


@pytest.mark.parametrize("name", ["part.NC", ".hidden.gcode", "unsupported.json"])
def test_native_program_full_or_relative_file_navigation(helper, tmp_path, name):
    file = tmp_path / name
    file.write_text("G1 X2\n")
    for path in (name, str(file), "./" + name + "/."):
        result = parity(helper, program_request(tmp_path, path=path, navigate=True))
        assert result["path"] == str(tmp_path)
        if name.endswith(".json"):
            assert result["selected"] is None and result["message"] == "Unsupported program file: " + name
        else:
            assert result["selected"]["path"] == str(file)
            assert result["selected"]["available"] and result["message"] is None


def test_native_program_typed_case_alias_preserves_selected_spelling(helper, tmp_path):
    stored = tmp_path / "part.NC"
    stored.write_text("G1 X2\n")
    typed = tmp_path / "PART.nc"
    if not typed.exists() or not typed.samefile(stored):
        pytest.skip("Requires a case-insensitive volume")
    result = parity(helper, program_request(tmp_path, path=str(typed), navigate=True))
    assert result["selected"]["name"] == "PART.nc" and result["selected"]["path"] == str(typed)
    assert [entry["name"] for entry in result["entries"]] == ["part.NC"]
    assert result["message"] is None


@pytest.mark.parametrize("visible_name,is_dir", [(b"bad\xff.NC", False), (b"bad\xff-folder", True)])
def test_native_program_invalid_utf8_filename_policy(helper, tmp_path, visible_name, is_dir):
    (tmp_path / "part.nc").write_text("G1 X2\n")
    directory = os.open(tmp_path, os.O_RDONLY)
    try:
        try:
            os.close(os.open(b"unrelated\xff.txt", os.O_CREAT | os.O_EXCL | os.O_WRONLY, dir_fd=directory))
        except OSError as error:
            if error.errno == errno.EILSEQ:
                pytest.skip("Filesystem rejects invalid UTF-8 filenames")
            raise
        healthy = parity(helper, program_request(tmp_path))
        assert [entry["name"] for entry in healthy["entries"]] == ["part.nc"]
        assert healthy["message"] is None
        if is_dir:
            os.mkdir(visible_name, dir_fd=directory)
        else:
            os.close(os.open(visible_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, dir_fd=directory))
        result = parity(helper, program_request(tmp_path))
        assert result["entries"] == [] and result["selected"] is None
        assert result["message"] == "Cannot read folder: Folder contains an unsupported filename"
    finally:
        os.close(directory)


def test_native_program_initial_hints_and_home_expansion(helper, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path) + "/")
    (tmp_path / "part.nc").write_text("G0 X0\n")
    for path in ("~", "~/.", "./~/."):
        result = parity(helper, program_request(tmp_path, path=path))
        assert result["path"] == str(tmp_path)
    request = program_request(
        tmp_path,
        path="initial-display",
        initial_candidates=[str(tmp_path / "missing"), str(tmp_path / "part.nc"), "~"],
    )
    assert parity(helper, request)["path"] == str(tmp_path)
    assert parity(helper, {**request, "collection": "recent"})["path"] == str(tmp_path)


def test_native_program_initial_stat_error_does_not_fall_back(helper, tmp_path):
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    request = program_request(tmp_path, initial_candidates=[str(loop), str(tmp_path)])
    actual = call(helper, request)
    assert actual["error"] is None
    expected = execute(request)
    for result in (actual["result"], expected):
        assert result.pop("message").startswith("Cannot read folder: ")
        assert result["path"] == str(loop) and result["entries"] == []
    assert actual["result"] == expected


def test_native_program_home_expansion_failure_uses_error_envelope(helper, tmp_path):
    request = program_request(tmp_path, path="~carvera-no-such-user-20261023/program.nc")
    with pytest.raises(ValueError, match="^Cannot read path: "):
        execute(request)
    actual = call(helper, request)
    assert actual["result"] is None and actual["error"].startswith("Cannot read path: ")


def test_native_program_negative_fractional_timestamp_for_listing_and_selection(helper, tmp_path):
    file = tmp_path / "part.nc"
    file.write_text("G1 X2\n")
    os.utime(file, ns=(-123456789, -123456789))
    assert file.stat().st_mtime < 0
    parity(helper, program_request(tmp_path))
    parity(helper, program_request(tmp_path, path=str(file), navigate=True))


def test_native_program_collections_preserve_order_metadata_and_normalized_references(helper, tmp_path):
    (tmp_path / "nested").mkdir()
    present = tmp_path / "same.nc"
    second = tmp_path / "nested/same.nc"
    hidden = tmp_path / ".hidden.nc"
    missing = tmp_path / "missing.nc"
    directory = tmp_path / "folder.nc"
    directory.mkdir()
    for file in (present, second, hidden):
        file.write_text("G1 X2\n")
    places = tmp_path / "program-places.json"
    places.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "recent": [str(second), str(tmp_path / "nested/../same.nc"), str(missing), str(directory)],
                "favorites": [str(hidden), "/" + str(present)],
            }
        )
    )
    original = places.read_bytes()
    recent = parity(helper, program_request(tmp_path, collection="recent"))
    assert [entry["path"] for entry in recent["entries"]] == [str(second), str(present), str(missing), str(directory)]
    assert [entry["available"] for entry in recent["entries"]] == [True, True, False, False]
    assert recent["entries"][2]["size"] == 0
    assert recent["entries"][3]["size"] == directory.stat().st_size
    assert not any(entry["is_dir"] for entry in recent["entries"])
    favorites = parity(helper, program_request(tmp_path, collection="favorites"))
    assert [entry["name"] for entry in favorites["entries"]] == [hidden.name, present.name]
    assert favorites["entries"][1]["path"].startswith("//")
    for suffix in ("/", "/.", "//./"):
        normalized = parity(helper, program_request(tmp_path, collection="favorites", places_path=str(places) + suffix))
        assert normalized == favorites
    assert places.read_bytes() == original


def test_native_program_places_symlink_loop_matches_existing_missing_store_behavior(helper, tmp_path):
    places = tmp_path / "program-places.json"
    places.symlink_to(places)
    for collection in (None, "recent", "favorites"):
        result = parity(helper, program_request(tmp_path, collection=collection))
        assert result["places"] == {"recent": [], "favorites": [], "error": None}
        assert result["message"] is None and result["entries"] == []


@pytest.mark.parametrize(
    "document,error",
    [
        ({}, "Invalid program-reference document"),
        ({"schema_version": True, "recent": [], "favorites": []}, "Unsupported program-reference schema"),
        ({"schema_version": 1.0, "recent": [], "favorites": []}, "Unsupported program-reference schema"),
        ({"schema_version": 2, "recent": [], "favorites": []}, "Unsupported program-reference schema"),
        ({"schema_version": 1, "recent": None, "favorites": []}, "Invalid recent program references"),
        ({"schema_version": 1, "recent": ["/part.nc"] * 26, "favorites": []}, "Invalid recent program references"),
        ({"schema_version": 1, "recent": [], "favorites": ["/part.nc"] * 101}, "Invalid favorites program references"),
        ({"schema_version": 1, "recent": [None], "favorites": []}, "Invalid local program reference"),
        ({"schema_version": 1, "recent": ["/a\0.nc"], "favorites": []}, "Invalid local program reference"),
        (
            {"schema_version": 1, "recent": ["/" + "a" * 4096 + ".nc"], "favorites": []},
            "Invalid local program reference",
        ),
        (
            {"schema_version": 1, "recent": ["part.nc"], "favorites": []},
            "Program references require an absolute supported program path",
        ),
        (
            {"schema_version": 1, "recent": ["/.nc"], "favorites": []},
            "Program references require an absolute supported program path",
        ),
        (
            {"schema_version": 1, "recent": ["/part.json"], "favorites": []},
            "Program references require an absolute supported program path",
        ),
        (
            {"schema_version": 1, "recent": ["/a/../part.nc", "/part.nc"], "favorites": []},
            "Duplicate recent program references",
        ),
        (
            {"schema_version": 1, "recent": [], "favorites": ["/part.nc", "/part.nc"]},
            "Duplicate favorites program references",
        ),
    ],
)
def test_native_program_corrupt_places_keep_directory_usable(helper, tmp_path, document, error):
    places = tmp_path / "program-places.json"
    places.write_text(json.dumps(document))
    (tmp_path / "part.nc").write_text("G0 X0\n")
    original = places.read_bytes()
    ordinary = parity(helper, program_request(tmp_path))
    assert [entry["name"] for entry in ordinary["entries"]] == ["part.nc"]
    assert ordinary["message"] is None
    assert ordinary["places"] == {"recent": [], "favorites": [], "error": error}
    collection = parity(helper, program_request(tmp_path, collection="favorites"))
    assert collection["entries"] == [] and collection["selected"] is None
    assert collection["message"] == "Program shortcuts unavailable: " + error
    assert places.read_bytes() == original


@pytest.mark.parametrize(
    "raw",
    [b"{", b"\xff", b"\xef\xbb\xbf{}", b" " * (1024 * 1024 + 1), b"[" * 2000 + b"]" * 2000],
    ids=["malformed-json", "invalid-utf8", "utf8-bom", "over-byte-limit", "deeply-nested"],
)
def test_native_program_places_read_has_shared_decode_and_byte_limits(helper, tmp_path, raw):
    places = tmp_path / "program-places.json"
    places.write_bytes(raw)
    result = parity(helper, program_request(tmp_path, collection="recent"))
    error = "Program references exceed 1 MiB" if len(raw) > 1024 * 1024 else "Invalid program-reference document"
    assert result["places"]["error"] == error
    assert result["message"] == "Program shortcuts unavailable: " + error
    assert places.read_bytes() == raw


@pytest.mark.parametrize(
    "changes",
    [
        {"extra": True},
        {"base": "relative"},
        {"base": None},
        {"base": ""},
        {"base": "/a\0b"},
        {"base": "/" + "a" * 16384},
        {"places_path": "relative"},
        {"places_path": None},
        {"places_path": "/a\0b"},
        {"navigate": 1},
        {"navigate": None},
        {"collection": "other"},
        {"collection": []},
        {"initial_candidates": []},
        {"initial_candidates": ["/"] * 4},
        {"initial_candidates": "/"},
        {"initial_candidates": [None]},
        {"initial_candidates": [""]},
        {"initial_candidates": ["a\0b"]},
        {"initial_candidates": ["a" * 16385]},
    ],
)
def test_native_program_rejects_invalid_request_fields(helper, tmp_path, changes):
    request = program_request(tmp_path, **changes)
    with pytest.raises(ValueError) as expected:
        execute(request)
    assert call(helper, request) == {"result": None, "error": str(expected.value)}


@pytest.mark.parametrize("field", ["base", "navigate", "initial_candidates", "collection", "places_path"])
def test_native_program_rejects_missing_request_fields(helper, tmp_path, field):
    request = program_request(tmp_path)
    del request[field]
    with pytest.raises(ValueError) as expected:
        execute(request)
    assert call(helper, request) == {"result": None, "error": str(expected.value)}


def test_native_program_missing_folder_retains_error_location(helper, tmp_path):
    request = program_request(tmp_path, path="missing")
    actual = call(helper, request)
    assert actual["error"] is None
    expected = execute(request)
    for result in (actual["result"], expected):
        assert result.pop("message").startswith("Cannot read folder: ")
    assert actual["result"] == expected
    assert expected["path"] == str(tmp_path / "missing") and expected["entries"] == []


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


@pytest.mark.parametrize(
    "raw",
    [b"", b"{", b"null\n", b"[]", b"x" * 65537 + b"\n"],
    ids=["empty", "unterminated-object", "null", "array", "over-size-limit"],
)
def test_native_malformed_or_oversized_frame_is_bounded(helper, raw):
    response = call(helper, raw=raw)
    assert response["result"] is None and response["error"]


def test_native_one_line_does_not_consume_next_request(helper, tmp_path):
    request = {"operation": "check", "path": str(tmp_path / "absent"), "save": True}
    raw = json.dumps(request).encode()
    assert call(helper, raw=raw) == {"result": {}, "error": None}  # Legacy EOF framing.
    assert call(helper, raw=raw + b"\ninvalid next request") == {"result": {}, "error": None}


@pytest.mark.timeout(180)  # Fixture allocation only; call() still enforces 4s.
def test_native_counts_hidden_irrelevant_children_before_filtering(helper, tmp_path):
    directory = os.open(tmp_path, os.O_RDONLY)
    try:
        for index in range(20001):
            os.close(os.open(f".hidden-{index}", os.O_CREAT | os.O_EXCL | os.O_WRONLY, dir_fd=directory))
    finally:
        os.close(directory)
    request = {"operation": "list", "path": str(tmp_path), "suffixes": []}
    with pytest.raises(ValueError, match="20,000"):
        execute(request)
    assert "20,000" in call(helper, request)["error"]
    result = parity(helper, program_request(tmp_path))
    assert result["entries"] == [] and result["selected"] is None
    assert result["message"] == "Cannot read folder: Folder has more than 20,000 items; enter a narrower folder"


@pytest.mark.timeout(180)  # Fixture allocation only; call() still enforces 4s.
def test_native_response_budget_includes_ascii_unicode_escapes(helper, tmp_path):
    folder = tmp_path
    for _ in range(6):
        folder /= "folder" * 20
    folder.mkdir(parents=True)
    directory = os.open(folder, os.O_RDONLY)
    try:
        for index in range(5000):
            name = f"{index}-" + "é" * 50 + ".nc"
            os.close(os.open(name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, dir_fd=directory))
    finally:
        os.close(directory)
    request = {"operation": "list", "path": str(folder), "suffixes": [".nc"]}
    assert "metadata exceeds limit" in call(helper, request)["error"]
    assert "metadata exceeds limit" in call(helper, program_request(folder))["error"]
