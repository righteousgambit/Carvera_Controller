"""Local program references persist without importing UI or touching hardware."""

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from carveracontroller.machine.program_places import ProgramPlaces


def test_deferred_store_does_not_touch_filesystem_until_worker_load(tmp_path, monkeypatch):
    def blocked_read(_self):
        raise AssertionError("Constructor performed a filesystem read")

    monkeypatch.setattr(ProgramPlaces, "_read", blocked_read)
    monkeypatch.setattr(Path, "resolve", blocked_read)
    store = ProgramPlaces(tmp_path / "places.json", load=False)
    assert store.recent == [] and store.favorites == [] and store.error is None


@pytest.mark.parametrize("alias", ["same", "relative", "symlink_parent"])
def test_separate_instances_preserve_updates_while_prior_replace_is_pending(tmp_path, monkeypatch, alias):
    directory = tmp_path / "store"
    directory.mkdir()
    path = directory / "places.json"
    second_path = path
    if alias == "relative":
        monkeypatch.chdir(tmp_path)
        second_path = Path("store") / "places.json"
    elif alias == "symlink_parent":
        shortcut = tmp_path / "shortcut"
        shortcut.symlink_to(directory, target_is_directory=True)
        second_path = shortcut / "places.json"
    first, second = ProgramPlaces(path, load=False), ProgramPlaces(second_path, load=False)
    recent, favorite = tmp_path / "recent.nc", tmp_path / "favorite.nc"
    entered, release, attempted, finished = (threading.Event() for _ in range(4))
    original = ProgramPlaces._save

    def held_save(store, recents, favorites):
        if store is first:
            entered.set()
            assert release.wait(5)
        original(store, recents, favorites)

    def add_favorite():
        attempted.set()
        second.toggle_favorite(favorite)
        finished.set()

    monkeypatch.setattr(ProgramPlaces, "_save", held_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first_result = workers.submit(first.record_recent, recent)
        try:
            assert entered.wait(1)
            second_result = workers.submit(add_favorite)
            assert attempted.wait(1)
            assert not finished.wait(0.2), "A second writer passed an unfinished read/modify/save transaction"
        finally:
            release.set()
        first_result.result(timeout=2)
        second_result.result(timeout=2)
    stored = ProgramPlaces(path)
    assert stored.recent == [str(recent)]
    assert stored.favorites == [str(favorite)]


def test_independent_stores_can_save_while_another_store_is_blocked(tmp_path, monkeypatch):
    first = ProgramPlaces(tmp_path / "first.json", load=False)
    second = ProgramPlaces(tmp_path / "second.json", load=False)
    recent, favorite = tmp_path / "recent.nc", tmp_path / "favorite.nc"
    entered, release = threading.Event(), threading.Event()
    original = ProgramPlaces._save

    def held_save(store, recents, favorites):
        if store is first:
            entered.set()
            assert release.wait(5)
        original(store, recents, favorites)

    monkeypatch.setattr(ProgramPlaces, "_save", held_save)
    with ThreadPoolExecutor(max_workers=2) as workers:
        pending = workers.submit(first.record_recent, recent)
        try:
            assert entered.wait(1)
            workers.submit(second.toggle_favorite, favorite).result(timeout=1)
            assert ProgramPlaces(second.path).favorites == [str(favorite)]
            assert not first.path.exists()
        finally:
            release.set()
        pending.result(timeout=2)
    assert ProgramPlaces(first.path).recent == [str(recent)]


@pytest.mark.parametrize("failure", [False, True])
def test_write_ownership_includes_readback_and_releases_on_failure(tmp_path, monkeypatch, failure):
    path = tmp_path / "places.json"
    first, second = ProgramPlaces(path, load=False), ProgramPlaces(path, load=False)
    recent, favorite = tmp_path / "recent.nc", tmp_path / "favorite.nc"
    entered, release, attempted, finished = (threading.Event() for _ in range(4))
    original = Path.read_text

    def held_readback(target, *args, **kwargs):
        if target == path and not entered.is_set():
            entered.set()
            assert release.wait(5)
            if failure:
                raise OSError("readback unavailable")
        return original(target, *args, **kwargs)

    def add_favorite():
        attempted.set()
        second.toggle_favorite(favorite)
        finished.set()

    monkeypatch.setattr(Path, "read_text", held_readback)
    with ThreadPoolExecutor(max_workers=2) as workers:
        first_result = workers.submit(first.record_recent, recent)
        try:
            assert entered.wait(1)
            second_result = workers.submit(add_favorite)
            assert attempted.wait(1)
            assert not finished.wait(0.2), "A second writer replaced a store before the first readback"
        finally:
            release.set()
        if failure:
            with pytest.raises(OSError, match="readback unavailable"):
                first_result.result(timeout=2)
            assert first.recent == []
        else:
            first_result.result(timeout=2)
            assert first.recent == [str(recent)]
        second_result.result(timeout=2)
    stored = ProgramPlaces(path)
    assert stored.recent == [str(recent)]
    assert stored.favorites == [str(favorite)]


def test_recent_inspections_are_bounded_ordered_and_reloadable(tmp_path):
    store = ProgramPlaces(tmp_path / "places.json")
    for n in range(30):
        store.record_recent(tmp_path / f"part-{n}.nc")
    store.record_recent(tmp_path / "part-10.nc")
    restored = ProgramPlaces(store.path)
    assert len(restored.recent) == 25
    assert restored.recent[0] == str(tmp_path / "part-10.nc")
    assert restored.recent.count(restored.recent[0]) == 1
    assert not restored.favorites


def test_favorites_preserve_same_named_files_and_external_changes(tmp_path):
    path = tmp_path / "places.json"
    first, second = ProgramPlaces(path), ProgramPlaces(path)
    a, b = tmp_path / "a/part.nc", tmp_path / "b/part.nc"
    first.toggle_favorite(a)
    second.toggle_favorite(b)
    first.record_recent(a)
    assert ProgramPlaces(path).favorites == [str(a), str(b)]
    first.toggle_favorite(a)
    assert ProgramPlaces(path).favorites == [str(b)]
    assert ProgramPlaces(path).recent == [str(a)]


@pytest.mark.parametrize(
    "document", ["broken json", '{"schema_version":2}', '{"schema_version":1,"recent":[17],"favorites":[]}']
)
def test_invalid_store_is_preserved_and_cannot_be_overwritten(tmp_path, document):
    path = tmp_path / "places.json"
    path.write_text(document)
    store = ProgramPlaces(path)
    assert store.error and store.recent == [] and store.favorites == []
    with pytest.raises(ValueError):
        store.toggle_favorite(tmp_path / "part.nc")
    assert path.read_text() == document


def test_failed_replace_preserves_prior_store_and_memory(tmp_path, monkeypatch):
    store = ProgramPlaces(tmp_path / "places.json")
    store.toggle_favorite(tmp_path / "part.nc")
    before = store.path.read_bytes()

    def reject(*_args):
        raise OSError("storage unavailable")

    monkeypatch.setattr("carveracontroller.machine.program_places.os.replace", reject)
    with pytest.raises(OSError):
        store.record_recent(tmp_path / "other.nc")
    assert store.path.read_bytes() == before
    assert store.recent == []
    assert not list(tmp_path.glob("*.tmp"))


def test_unsupported_and_relative_references_are_rejected(tmp_path):
    store = ProgramPlaces(tmp_path / "places.json")
    for path in ("relative.nc", str(tmp_path / "image.png"), str(tmp_path / "bad\x00.nc")):
        with pytest.raises(ValueError):
            store.record_recent(path)
    assert not store.path.exists()


def test_existing_corruption_is_detected_before_mutation(tmp_path):
    store = ProgramPlaces(tmp_path / "places.json")
    store.record_recent(tmp_path / "part.NC")
    store.path.write_text(json.dumps({"schema_version": 1, "recent": [], "favorites": ["relative.nc"]}))
    with pytest.raises(ValueError):
        store.toggle_favorite(tmp_path / "other.nc")
    assert store.recent == [str(tmp_path / "part.NC")]


def test_actual_read_is_bounded_when_store_grows_after_prior_inspection(tmp_path, monkeypatch):
    import io
    from pathlib import Path

    path = tmp_path / "places.json"
    original = b'{"schema_version":1,"recent":[],"favorites":[]}'
    path.write_bytes(original)
    store = ProgramPlaces(path)
    store.MAX_BYTES = 64
    stream = io.BytesIO(original + b" " * 100000)
    open_path = Path.open
    requested = []

    class GrowingStream(io.BytesIO):
        def read(self, size=-1):
            requested.append(size)
            return stream.read(size)

    def opened(self, mode="r", *args, **kwargs):
        if self == path and mode == "rb":
            return GrowingStream()
        return open_path(self, mode, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    with pytest.raises(ValueError, match="exceed"):
        store.reload()
    assert requested == [65] and stream.tell() == 65
    assert store.recent == [] and store.favorites == []
    monkeypatch.setattr(Path, "open", open_path)
    assert path.read_bytes() == original


@pytest.mark.parametrize("payload", [b"\xff", b'{"schema_version":true,"recent":[],"favorites":[]}'])
def test_invalid_encoding_or_schema_preserves_store_bytes(tmp_path, payload):
    path = tmp_path / "places.json"
    path.write_bytes(payload)
    store = ProgramPlaces(path)
    assert store.error
    with pytest.raises(ValueError):
        store.record_recent(tmp_path / "part.nc")
    assert path.read_bytes() == payload
