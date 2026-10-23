"""Program metadata runs inside the bounded standalone filesystem service."""

import copy
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from carveracontroller.machine import artifact_fs_worker as worker
from carveracontroller.machine.artifact_fs import filesystem_request, validate_response
from carveracontroller.machine.program_places import ProgramPlaces


def request(folder, **changes):
    return {
        "operation": "program-list",
        "path": str(folder),
        "base": str(folder),
        "navigate": False,
        "initial_candidates": None,
        "collection": None,
        "places_path": str(folder / "places.json"),
        **changes,
    }


def test_real_program_helper_preserves_lexical_paths_order_and_explicit_file_selection(tmp_path):
    folder = tmp_path / "target"
    folder.mkdir()
    (folder / "z folder").mkdir()
    for name in ("part.nc", "B.NC", "a.nc", ".hidden.nc", "unsupported.png"):
        (folder / name).write_text("G21\n")
    alias = tmp_path / "alias"
    alias.symlink_to(folder, target_is_directory=True)
    query = request(tmp_path, path=str(alias))
    result = filesystem_request(query)
    assert result == worker.execute(query)
    assert result["path"] == str(alias)
    assert [row["name"] for row in result["entries"]] == ["z folder", "a.nc", "B.NC", "part.nc"]
    assert all(row["path"].startswith(str(alias) + "/") for row in result["entries"])
    selected = filesystem_request({**query, "path": "alias/.hidden.nc", "navigate": True})
    assert selected["selected"]["path"] == str(alias / ".hidden.nc")
    assert selected["message"] is None
    unsupported = filesystem_request({**query, "path": "alias/unsupported.png", "navigate": True})
    assert unsupported["path"] == str(alias) and unsupported["selected"] is None
    assert unsupported["message"] == "Unsupported program file: unsupported.png"
    missing = filesystem_request({**query, "path": str(alias / "missing.nc"), "navigate": True})
    assert missing["entries"] == [] and missing["message"].startswith("Cannot read folder:")


def test_startup_falls_back_only_when_hint_is_missing_or_not_directory(tmp_path, monkeypatch):
    healthy = tmp_path / "healthy"
    healthy.mkdir()
    (healthy / "part.nc").write_text("G21\n")
    missing = tmp_path / "missing"
    query = request(tmp_path, path=str(missing), initial_candidates=[str(missing), str(healthy)])
    assert filesystem_request(query)["path"] == str(healthy)
    original_stat, original_scan = Path.stat, worker.os.scandir

    def refused_stat(path, *args, **kwargs):
        if path == missing:
            raise PermissionError("denied saved folder")
        return original_stat(path, *args, **kwargs)

    def refused_scan(path):
        if path == missing:
            raise PermissionError("denied saved folder")
        return original_scan(path)

    monkeypatch.setattr(Path, "stat", refused_stat)
    monkeypatch.setattr(worker.os, "scandir", refused_scan)
    result = worker.execute(query)
    assert result["path"] == str(missing)
    assert result["entries"] == [] and "denied saved folder" in result["message"]


@pytest.mark.parametrize("collection", ["recent", "favorites"])
def test_collections_preserve_missing_entries_order_and_duplicate_basenames(tmp_path, collection):
    first, second, missing = (tmp_path / name / "same.nc" for name in ("first", "second", "gone"))
    for path in (first, second):
        path.parent.mkdir()
        path.write_text("G21\n")
    directory = tmp_path / "folder.nc"
    directory.mkdir()
    references = [str(second), str(missing), str(first), str(directory)]
    store = ProgramPlaces(tmp_path / "places.json")
    store._save(references if collection == "recent" else [], references if collection == "favorites" else [])
    before = store.path.read_bytes()
    result = filesystem_request(request(tmp_path, collection=collection))
    assert [row["path"] for row in result["entries"]] == references
    assert [row["available"] for row in result["entries"]] == [True, False, True, False]
    assert result["entries"][1]["size"] == result["entries"][1]["modified"] == 0
    assert not any(row["is_dir"] for row in result["entries"])
    assert result["selected"] is result["message"] is None
    assert store.path.read_bytes() == before


@pytest.mark.parametrize(
    "raw",
    [
        b"broken",
        b"\xff",
        b'{"schema_version":true,"recent":[],"favorites":[]}',
        b"x" * (1024 * 1024 + 1),
        b"[" * 2000 + b"]" * 2000,
    ],
    ids=["invalid-json", "invalid-encoding", "bool-schema", "oversized", "deeply-nested"],
)
def test_corrupt_places_never_blocks_ordinary_listing_or_erases_references(tmp_path, raw):
    path = tmp_path / "places.json"
    path.write_bytes(raw)
    (tmp_path / "part.nc").write_text("G21\n")
    result = filesystem_request(request(tmp_path))
    store = ProgramPlaces(path)
    assert result["places"] == {"recent": [], "favorites": [], "error": store.error}
    assert result["message"] is None and [row["name"] for row in result["entries"]] == ["part.nc"]
    collection = filesystem_request(request(tmp_path, collection="favorites"))
    assert collection["entries"] == [] and collection["selected"] is None
    assert collection["message"] == "Program shortcuts unavailable: " + store.error
    assert path.read_bytes() == raw


def test_program_cap_counts_filtered_children_and_refuses_partial_listing(tmp_path, monkeypatch):
    for name in (".hidden", "unrelated.png", "part.nc"):
        (tmp_path / name).touch()
    monkeypatch.setattr(worker, "MAX_ITEMS", 2)
    result = worker.execute(request(tmp_path))
    assert result["entries"] == [] and result["selected"] is None
    assert "more than 20,000 items" in result["message"]


@pytest.mark.parametrize("suffix,is_dir", [(".txt", False), (".nc", False), ("", True)])
def test_unrepresentable_names_skip_unrelated_files_but_report_programs_or_folders(
    tmp_path, monkeypatch, suffix, is_dir
):
    good = tmp_path / "part.nc"
    good.write_text("G21\n")

    class Child:
        def __init__(self, name, directory=False):
            self.name, self.path, self.directory = name, str(tmp_path / name), directory

        def stat(self):
            return good.stat()

        def is_dir(self):
            return self.directory

    @contextmanager
    def listed(_path):
        # Some filesystems cannot create invalid UTF-8 names. Model exactly the
        # surrogate-escaped DirEntry names returned by Python on capable volumes.
        yield iter([Child("invalid-\udcff" + suffix, is_dir), Child(good.name)])

    monkeypatch.setattr(worker.os, "scandir", listed)
    result = worker.execute(request(tmp_path))
    if suffix == ".txt" and not is_dir:
        assert result["message"] is None and [row["name"] for row in result["entries"]] == ["part.nc"]
    else:
        assert result["message"] == "Cannot read folder: Folder contains an unsupported filename"
        assert result["entries"] == [] and result["selected"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"base": "relative"},
        {"places_path": "relative.json"},
        {"navigate": 1},
        {"collection": "other"},
        {"initial_candidates": []},
        {"initial_candidates": ["/one"] * 4},
        {"initial_candidates": ["bad\0path"]},
        {"path": "a" * 16385},
        {"extra": True},
    ],
)
def test_program_request_rejects_invalid_or_unbounded_fields(tmp_path, change):
    with pytest.raises(ValueError):
        worker.validate_request(request(tmp_path, **change))


@pytest.mark.parametrize(
    "fault",
    [
        "extra",
        "relative_path",
        "row_escape",
        "name_mismatch",
        "duplicate",
        "hidden",
        "unsupported",
        "unavailable",
        "bool_size",
        "negative_size",
        "nonfinite",
        "missing_field",
        "selected_directory",
        "selected_without_navigation",
        "places_schema",
        "places_limit",
        "places_duplicate",
        "places_not_normalized",
        "places_error_with_references",
        "message_type",
    ],
)
def test_program_response_rejects_malformed_metadata_before_browser_publication(tmp_path, fault):
    (tmp_path / "part.nc").write_text("G21\n")
    query = request(tmp_path)
    result = worker.execute(query)
    row = result["entries"][0]
    if fault == "extra":
        result["extra"] = True
    elif fault == "relative_path":
        result["path"] = "relative"
    elif fault == "row_escape":
        row["path"] = str(tmp_path.parent / row["name"])
    elif fault == "name_mismatch":
        row["name"] = "other.nc"
    elif fault == "duplicate":
        result["entries"].append(copy.deepcopy(row))
    elif fault in ("hidden", "unsupported"):
        row["name"] = ".hidden.nc" if fault == "hidden" else "part.txt"
        row["path"] = str(tmp_path / row["name"])
    elif fault == "unavailable":
        row["available"] = False
    elif fault in ("bool_size", "negative_size"):
        row["size"] = True if fault == "bool_size" else -1
    elif fault == "nonfinite":
        row["modified"] = float("nan")
    elif fault == "missing_field":
        del row["available"]
    elif fault.startswith("selected"):
        result["selected"] = copy.deepcopy(row)
        if fault == "selected_directory":
            query["navigate"] = True
            result["selected"]["is_dir"] = True
    elif fault == "places_schema":
        result["places"]["schema_version"] = 1
    elif fault == "places_limit":
        result["places"]["recent"] = [str(tmp_path / f"{i}.nc") for i in range(26)]
    elif fault == "places_duplicate":
        result["places"]["recent"] = [row["path"], row["path"]]
    elif fault == "places_not_normalized":
        result["places"]["recent"] = [str(tmp_path) + "/other/../part.nc"]
    elif fault == "places_error_with_references":
        result["places"].update(recent=[row["path"]], error="corrupt")
    else:
        result["message"] = []
    with pytest.raises(ValueError, match="invalid metadata"):
        validate_response({"result": result, "error": None}, query)


def test_collection_response_requires_exact_reference_order_and_paths(tmp_path):
    refs = [str(tmp_path / "one/part.nc"), str(tmp_path / "two/part.nc")]
    ProgramPlaces(tmp_path / "places.json")._save([], refs)
    query = request(tmp_path, collection="favorites")
    result = worker.execute(query)
    assert validate_response({"result": result, "error": None}, query) == result
    result["entries"].reverse()
    with pytest.raises(ValueError, match="invalid metadata"):
        validate_response({"result": result, "error": None}, query)


@pytest.mark.parametrize("target", ["first.nc", "unsupported.png", ".", "~/first.nc", "~somebody/first.nc"])
def test_selected_response_cannot_substitute_another_requested_program(tmp_path, target):
    for name in ("first.nc", "second.nc", "unsupported.png"):
        (tmp_path / name).write_text("G21\n")
    result = worker.execute(request(tmp_path, path=str(tmp_path / "first.nc"), navigate=True))
    result["selected"] = next(row for row in result["entries"] if row["name"] == "second.nc")
    query = request(tmp_path, path=target, navigate=True)
    with pytest.raises(ValueError, match="invalid metadata"):
        validate_response({"result": result, "error": None}, query)


def test_requested_selection_can_be_absent_from_independent_directory_enumeration(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in ("part.nc", ".hidden.nc"):
        (tmp_path / name).write_text("G21\n")
    query = request(tmp_path, path="~/part.nc", navigate=True)
    result = filesystem_request(query)
    result["entries"] = []
    assert validate_response({"result": result, "error": None}, query)["selected"] == result["selected"]
    hidden = filesystem_request({**query, "path": "~/.hidden.nc"})
    assert hidden["selected"]["path"] == str(tmp_path / ".hidden.nc")
    assert all(row["name"] != ".hidden.nc" for row in hidden["entries"])


def test_case_insensitive_file_alias_keeps_typed_selection_path(tmp_path):
    actual, typed = tmp_path / "part.NC", tmp_path / "PART.nc"
    actual.write_text("G21\n")
    if not typed.is_file():
        pytest.skip("Requires case-insensitive filesystem")
    result = filesystem_request(request(tmp_path, path=str(typed), navigate=True))
    assert result["selected"]["path"] == str(typed)
    assert [row["name"] for row in result["entries"]] == [actual.name]


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO models a blocked store read")
def test_places_read_is_inside_helper_deadline_and_leaves_healthy_request_usable(tmp_path):
    os.mkfifo(tmp_path / "places.json")
    started = time.monotonic()
    with pytest.raises(ValueError, match="timed out"):
        filesystem_request(request(tmp_path), timeout=0.3)
    assert time.monotonic() - started < 1.5
    result = filesystem_request(request(tmp_path, places_path=str(tmp_path / "healthy-places.json")))
    assert result["message"] is None and result["places"]["error"] is None


def test_standalone_program_operation_has_no_package_ui_or_controller_bootstrap(tmp_path):
    script = Path(worker.__file__)
    process = subprocess.run(
        [sys.executable, "-v", str(script)],
        input=json.dumps(request(tmp_path)),
        capture_output=True,
        text=True,
        timeout=4,
    )
    assert process.returncode == 0 and json.loads(process.stdout)["error"] is None
    assert "kivy" not in process.stderr.lower() and "carveracontroller" not in process.stderr
