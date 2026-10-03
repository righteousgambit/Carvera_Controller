"""Component choices preserve valid local state and never admit invalid stock."""
import json

import pytest

from carveracontroller.desktop_scene import SceneLibrary


def test_roundtrip_and_replace(tmp_path):
    path = tmp_path / "scene.json"
    library = SceneLibrary(path)
    library.save("fixtures", {"name": "Plate A", "path": "/a.json.gz"})
    library.save("vises", {"name": "Vise B", "path": "/b.json.gz"})
    library.save("stocks", {"name": "Block", "size": [20, 30, 40], "origin": [-10, -15, 0]})
    library.save("stocks", {"name": "Block", "size": [10, 20, 30], "origin": [0, 0, 0]})
    restored = SceneLibrary(path)
    assert restored.data == library.data
    assert len(restored.data["stocks"]) == 1
    assert restored.data["fixtures"][0]["name"] == "Plate A"
    assert restored.data["vises"][0]["name"] == "Vise B"


@pytest.mark.parametrize("size", [[0, 10, 20], [-1, 10, 20], [float("nan"), 10, 20], [10, 20], [True, 10, 20]])
def test_invalid_stock_preserves_file(tmp_path, size):
    path = tmp_path / "scene.json"
    library = SceneLibrary(path)
    library.save("stocks", {"name": "Valid", "size": [10, 20, 30], "origin": [0, 0, 0]})
    before = path.read_bytes()
    with pytest.raises(ValueError):
        library.save("stocks", {"name": "Bad", "size": size, "origin": [0, 0, 0]})
    assert path.read_bytes() == before


@pytest.mark.parametrize("data", [[], {"stocks": {}}, {"vises": [{"name": "Bad"}]}, {"stocks": [{"name": "Bad", "size": [0, 1, 1], "origin": [0, 0, 0]}]}])
def test_corrupt_library_keeps_ui_available_without_overwriting(tmp_path, data):
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(data))
    before = path.read_bytes()
    library = SceneLibrary(path)
    assert library.load_error
    assert not any(library.data.values())
    with pytest.raises(ValueError, match="Repair"):
        library.save("fixtures", {"name": "New", "path": "/a.json.gz"})
    assert path.read_bytes() == before
