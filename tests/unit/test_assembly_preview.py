import pytest

from carveracontroller.machine.assembly_preview import assembly_definition, design_fingerprint


def profile():
    return {
        "id": "design",
        "name": "Ball",
        "number": 1,
        "diameter": 6.35,
        "shank_diameter": 6.35,
        "flute_length": 10,
        "length": 75,
        "stickout": 40,
        "holder_geometry_path": "/catalog-holder.json",
    }


def test_assembly_resolves_own_geometry_without_borrowing_catalog_seating():
    catalog = profile()
    assembly = {"profile_id": "design", "name": "Physical #2", "stickout_mm": 28}
    definition = assembly_definition(assembly, catalog, 6)
    assert definition.number == 6
    assert definition.stickout == 28
    assert definition.holder_geometry_path == ""
    assert catalog["stickout"] == 40
    assert catalog["holder_geometry_path"] == "/catalog-holder.json"
    assembly["stickout_mm"] = None
    assert assembly_definition(assembly, catalog).stickout is None
    assembly["profile_id"] = "wrong"
    with pytest.raises(ValueError, match="different cutter"):
        assembly_definition(assembly, catalog)


def test_revision_and_design_geometry_must_remain_consistent():
    catalog = profile()
    before = design_fingerprint(catalog)
    assembly = {"profile_id": "design", "name": "A", "stickout_mm": 5}
    with pytest.raises(ValueError, match="flute length"):
        assembly_definition(assembly, catalog)
    catalog["flute_length"] = 4
    assert design_fingerprint(catalog) != before
    assert assembly_definition(assembly, catalog).stickout == 5
