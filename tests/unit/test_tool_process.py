import json

import pytest

from carveracontroller.machine.desktop_profiles import validate_record
from carveracontroller.machine.surface_planning import FacingParameters
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_passport import passport_sections
from carveracontroller.machine.tool_process import review_facing_recipe


def fixture(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    design = validate_record(
        "tools",
        {
            "id": "design",
            "name": "Flat",
            "diameter": 4,
            "shank_diameter": 6.35,
            "flute_length": 10,
            "length": 75,
            "stickout": 40,
        },
    )
    assembly = store.create_assembly("Physical", "Holder", 28, design["id"])
    assembly = store.assembly(assembly["id"])
    parameters = FacingParameters(
        ((0, 0), (10, 0), (10, 10), (0, 10)), 0, -0.7, 4, 2, 0.3, 300, 80, 12000, 5, material="6061", tool_id="2"
    )
    path = tmp_path / "recipe.cvface"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "parameters": parameters.to_dict(),
                "tool_geometry": {"diameter": 4, "flute_length": 10, "stickout": 28},
            }
        )
    )
    return store, design, assembly, path


def test_link_persists_exact_content_and_old_revision_status(tmp_path):
    store, design, assembly, path = fixture(tmp_path)
    review = review_facing_recipe(path, assembly, design)
    event = store.link_facing_recipe(assembly["id"], assembly["revision_id"], review, "6061 starting parameters")
    restored = ToolCustodyStore(store.path)
    assert not restored.error
    assert restored.events[-1] == event
    assert any(
        "Current definition" in row
        for row in passport_sections(restored, assembly["id"], {"tools": [design]})["Recipes"]
    )
    restored.revise(assembly["id"], assembly["revision_id"], "Physical", "Holder", 30, design["id"], "Reseated")
    assert any(
        "Older assembly" in row for row in passport_sections(restored, assembly["id"], {"tools": [design]})["Recipes"]
    )
    before = restored.path.read_bytes()
    with pytest.raises(ValueError, match="changed since recipe review"):
        restored.link_facing_recipe(assembly["id"], assembly["revision_id"], review, "Stale review")
    assert restored.path.read_bytes() == before


def test_file_change_and_catalog_seating_are_not_accepted(tmp_path):
    store, design, assembly, path = fixture(tmp_path)
    review = review_facing_recipe(path, assembly, design)
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError, match="file changed"):
        review_facing_recipe(path, assembly, design, review["sha256"])
    record = json.loads(path.read_text())
    record["tool_geometry"]["stickout"] = 40
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="physical assembly"):
        review_facing_recipe(path, assembly, design)


def test_unknown_or_wrong_cutter_and_corrupt_identity_rejected(tmp_path):
    store, design, assembly, path = fixture(tmp_path)
    with pytest.raises(ValueError, match="physical assembly"):
        review_facing_recipe(path, dict(assembly, stickout_mm=None), design)
    with pytest.raises(ValueError, match="flat end mill"):
        review_facing_recipe(path, assembly, dict(design, shape="ball_end_mill"))
    review = review_facing_recipe(path, assembly, design)
    with pytest.raises(ValueError, match="content identity"):
        store.link_facing_recipe(assembly["id"], assembly["revision_id"], dict(review, sha256="bad"), "Reason")
