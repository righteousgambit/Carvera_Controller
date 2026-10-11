import json
import math

import pytest

from carveracontroller.machine.desktop_profiles import ProfileError, ProfileStore, to_tool_definition, validate_record


def engraver(**changes):
    return {
        "id": "fiducial-t4",
        "name": "Harvey 47645",
        "number": 4,
        "shape": "chamfer_mill",
        "diameter": 6.35,
        "shank_diameter": 6.35,
        "length": 63.5,
        "stickout": 12,
        "tip_diameter": 0.254,
        "taper_angle_deg": 45,
        **changes,
    }


def test_tip_and_half_angle_survive_store_export_import_and_inch_conversion(tmp_path):
    store = ProfileStore(tmp_path / "saved.json")
    store.save_tool(engraver())
    store.save_toolset({"name": "Engraving", "slots": {"4": "fiducial-t4"}})
    store.export_file(tmp_path / "export.json")
    target = ProfileStore(tmp_path / "imported.json")
    target.import_file(tmp_path / "export.json")
    saved = next(t for t in target.data["tools"] if t["id"] == "fiducial-t4")
    assert saved["tip_diameter"] == 0.254
    assert saved["taper_angle_deg"] == 45
    metric, imperial = [to_tool_definition(saved, units=u) for u in ("mm", "in")]
    assert metric.tip_diameter == 0.254
    assert imperial.tip_diameter == pytest.approx(0.01)
    assert imperial.diameter == pytest.approx(0.25)
    assert metric.taper_angle_deg == imperial.taper_angle_deg == 45
    bank = next(t for t in target.data["toolsets"] if t["name"] == "Engraving")
    assert target.toolset_definitions(bank)[0].tip_diameter == 0.254


def test_legacy_profile_does_not_acquire_new_fingerprint_fields():
    record = engraver()
    del record["tip_diameter"]
    del record["taper_angle_deg"]
    validated = validate_record("tools", record)
    assert "tip_diameter" not in validated and "taper_angle_deg" not in validated
    assert to_tool_definition(validated).tip_diameter is None
    assert to_tool_definition(validated).taper_angle_deg is None
    assert to_tool_definition(engraver(tip_diameter=0)).tip_diameter == 0


@pytest.mark.parametrize(
    "changes",
    [
        {"tip_diameter": -1},
        {"tip_diameter": 6.36},
        {"tip_diameter": True},
        {"tip_diameter": math.nan},
        {"tip_diameter": math.inf},
        {"taper_angle_deg": 0},
        {"taper_angle_deg": 90},
        {"taper_angle_deg": -1},
        {"taper_angle_deg": True},
        {"taper_angle_deg": math.nan},
        {"taper_angle_deg": math.inf},
        {"taper_angle_deg": "45"},
    ],
)
def test_invalid_geometry_cannot_overwrite_persisted_profile(tmp_path, changes):
    store = ProfileStore(tmp_path / "saved.json")
    store.save_tool(engraver())
    before = store.path.read_bytes()
    with pytest.raises(ProfileError):
        store.save_tool(engraver(**changes))
    assert store.path.read_bytes() == before


def test_procedural_engraver_uses_flat_tip_and_half_angle():
    from carveracontroller.addons.tool_visualization.mesh_builder import tool_profile

    profile = tool_profile(to_tool_definition(engraver()))
    assert profile[0] == pytest.approx((0, 0.127))
    assert any(z == pytest.approx(3.048) and r == pytest.approx(3.175) for z, r in profile)
