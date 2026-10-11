import json

import pytest

from carveracontroller.machine.desktop_profiles import validate_record
from carveracontroller.machine.surface_planning import FacingParameters
from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_passport import passport_sections
from carveracontroller.machine.tool_process import review_facing_recipe, review_hole_recipe


def hole_fixture(tmp_path):
    from carveracontroller.machine.hole_planning import Hole, HoleTool, HoleWorkflow, ThreadSpec

    store = ToolCustodyStore(tmp_path / "holes-custody.json")
    design = validate_record(
        "tools",
        {
            "id": "thread-design",
            "name": "Single form",
            "shape": "thread_mill",
            "diameter": 3,
            "flute_length": 2,
            "shank_diameter": 6.35,
            "stickout": 40,
        },
    )
    assembly = store.create_assembly("Thread assembly", "Holder", 12, design["id"])
    assembly = store.assembly(assembly["id"])
    workflow = HoleWorkflow(
        (Hole(10, 20, 8, 6),),
        {"drill": HoleTool(2, "drill", 5.1054, 15, 20), "threadmill": HoleTool(3, "threadmill", 3, 2, 12)},
        ThreadSpec.named("1/4-20"),
        5,
        0,
        -15,
        200,
        80,
        12000,
    )
    path = tmp_path / "recipe.cvholes"
    path.write_text(json.dumps({"schema": "carvera-hole-recipe", "version": 1, "workflow": workflow.to_dict()}))
    return store, design, assembly, path


def test_hole_link_persists_stage_and_rejects_changed_content(tmp_path):
    store, design, assembly, path = hole_fixture(tmp_path)
    recipe, workflow = review_hole_recipe(path, assembly, design, "threadmill", prepared=True)
    assert recipe["stage"] == "threadmill" and recipe["hole_count"] == 1
    assert recipe["tool_id"] == "3" and len(workflow.plan().stages) == 2
    event = store.link_hole_recipe(
        assembly["id"], assembly["revision_id"], recipe, "6061 trial preparation; no cut yet"
    )
    restored = ToolCustodyStore(store.path)
    assert not restored.error and restored.events[-1] == event
    rows = passport_sections(restored, assembly["id"], {"tools": [design]})["Recipes"]
    assert any("threadmill" in row and "1/4-20" in row for row in rows)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="file changed"):
        review_hole_recipe(path, assembly, design, "threadmill", recipe["sha256"])


@pytest.mark.parametrize(
    "change,stage,message",
    [
        (None, "drill", "shape"),
        (None, "chamfer", "stage present"),
        (14, "threadmill", "dimensions"),
        (None, "tap", "stage present"),
    ],
)
def test_hole_stage_identity_and_physical_seating(tmp_path, change, stage, message):
    _, design, assembly, path = hole_fixture(tmp_path)
    if change is not None:
        assembly = dict(assembly, stickout_mm=change)
    with pytest.raises(ValueError, match=message):
        review_hole_recipe(path, assembly, design, stage)


def test_hole_link_stale_revision_preserves_original_record(tmp_path):
    store, design, assembly, path = hole_fixture(tmp_path)
    recipe = review_hole_recipe(path, assembly, design, "threadmill")
    store.link_hole_recipe(assembly["id"], assembly["revision_id"], recipe, "Reviewed process")
    store.revise(assembly["id"], assembly["revision_id"], "Reseated", "Holder", 13, design["id"], "New seating")
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="changed since recipe review"):
        store.link_hole_recipe(assembly["id"], assembly["revision_id"], recipe, "Stale review")
    assert store.path.read_bytes() == before
    assert any(
        "Older assembly" in row for row in passport_sections(store, assembly["id"], {"tools": [design]})["Recipes"]
    )


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


def test_multiform_recipe_binds_complete_stack_to_physical_assembly(tmp_path):
    from dataclasses import replace

    from carveracontroller.machine.hole_planning import HoleWorkflow

    store, design, assembly, path = hole_fixture(tmp_path)
    design = validate_record(
        "tools", {**design, "thread_pitch": 1.27, "thread_teeth": 6, "thread_tip_offset": 0.25, "flute_length": 8}
    )
    workflow = HoleWorkflow.from_dict(json.loads(path.read_text())["workflow"])
    cutter = replace(
        workflow.tools["threadmill"],
        thread_pitch_mm=1.27,
        thread_teeth=6,
        thread_tip_offset_mm=0.25,
        cutting_length_mm=8,
    )
    workflow = replace(workflow, tools={**workflow.tools, "threadmill": cutter})
    path.write_text(json.dumps({"schema": "carvera-hole-recipe", "version": 1, "workflow": workflow.to_dict()}))
    summary, restored = review_hole_recipe(path, assembly, design, "threadmill", prepared=True)
    assert restored == workflow and summary["stage"] == "threadmill"
    with pytest.raises(ValueError, match="dimensions differ"):
        review_hole_recipe(path, assembly, {**design, "thread_teeth": 5}, "threadmill")
