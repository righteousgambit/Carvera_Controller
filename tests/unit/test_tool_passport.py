from carveracontroller.machine.tool_custody import ToolCustodyStore
from carveracontroller.machine.tool_history import TloReport
from carveracontroller.machine.tool_passport import passport_sections


def test_passport_keeps_physical_seating_and_revision_attribution(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Physical A", "Holder A", 28, "design")
    raw = store.capture(2, TloReport((50, 50.01), 0.01, 50.01, 123), "source:2222")
    store.link(raw["id"], assembly["id"], "Checked inventory tag", assembly["id"])
    store.assign("machine", 2, assembly["id"], assembly["id"])
    store.revise(assembly["id"], assembly["id"], "Physical A", "Holder B", 30, "design", "Reseated")
    profiles = {
        "tools": [
            {
                "id": "design",
                "name": "Cutter",
                "shape": "ball_end_mill",
                "length": 75,
                "stickout": 40,
                "holder_geometry_path": "catalog-holder.json",
            }
        ],
        "machines": [{"id": "machine", "name": "Workshop"}],
    }
    before = store.path.read_bytes()
    sections = passport_sections(store, assembly["id"], profiles)
    assert "Stickout: 30 mm" in sections["Geometry"]
    assert any("45 mm" in row for row in sections["Geometry"])
    assert "Physical holder CAD: Not supplied" in sections["Assets"]
    assert any("Older definition" in row for row in sections["Measurements"])
    assert any("Checked inventory tag" in row for row in sections["Measurements"])
    assert any("Workshop / T2" in row and "reconcile" in row for row in sections["Locations"])
    assert store.path.read_bytes() == before


def test_missing_design_and_unknown_dimensions_remain_inspectable(tmp_path):
    store = ToolCustodyStore(tmp_path / "custody.json")
    assembly = store.create_assembly("Unlinked")
    sections = passport_sections(store, assembly["id"], {})
    assert "Stickout: Unknown" in sections["Geometry"]
    assert "No declared location." in sections["Locations"]
    assert any("unavailable" in row for row in sections["Geometry"])
    assert all("Select" in rows[0] for rows in passport_sections(store, "missing", {}).values())
