"""Local program references persist without importing UI or touching hardware."""

import json

import pytest

from carveracontroller.machine.program_places import ProgramPlaces


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
