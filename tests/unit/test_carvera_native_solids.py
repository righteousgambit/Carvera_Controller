"""Actual OCCT topology: preserve native solids and every source face."""

from collections import Counter

import pytest

pytest.importorskip("OCP")

from OCP.BRep import BRep_Builder
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
from OCP.gp import gp_Dir, gp_Pln, gp_Pnt, gp_Trsf, gp_Vec
from OCP.TopLoc import TopLoc_Location
from OCP.TopoDS import TopoDS_Compound, TopoDS_Shape

from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget, TriangleSolid
from scripts.convert_carvera_profile import native_components


def compound(*shapes):
    result = TopoDS_Compound()
    builder = BRep_Builder()
    builder.MakeCompound(result)
    for shape in shapes:
        builder.Add(result, shape)
    return result


def box(origin, size=(2, 2, 2)):
    return BRepPrimAPI_MakeBox(gp_Pnt(*origin), *size).Shape()


def convert(shape):
    return native_components(shape, name="original", assembly="Bed", group="table", color=(0.5, 0.6, 0.7, 1))


def triangles(component):
    values = component["vertices"]
    return tuple(tuple(tuple(values[i + j : i + j + 3]) for j in (0, 10, 20)) for i in range(0, len(values), 30))


@pytest.mark.parametrize("offset", [(2, 0, 0), (2, 2, 0), (2, 2, 2), (4, 0, 0)])
def test_native_solids_stay_distinct_when_geometric_faces_edges_or_vertices_touch(offset):
    parts = convert(compound(box((0, 0, 0)), box(offset)))
    assert len(parts) == 2 and [p["name"] for p in parts] == ["original · solid 1/2", "original · solid 2/2"]
    ids = []
    budget = SolidBudget()
    for number, part in enumerate(parts, 1):
        assert part["assembly"] == "Bed" and part["group"] == "table"
        topology = part["native_topology"]
        assert topology["solid_index"] == number and topology["solid_count"] == 2
        assert topology["source_component"] == "original" and topology["kind"] == "solid"
        assert topology["source_face_occurrences"] == 12
        ids += topology["source_face_ids"]
        solid = TriangleSolid.validate(triangles(part), budget=budget)
        assert solid.shell_count == 1 and solid.material_volume_mm3 == pytest.approx(8)
        assert part["triangulation"]["triangles"] == 12
    assert len(ids) == len(set(ids)) == 12
    assert sorted(ids) == list(range(1, 13))


def test_native_three_solid_compound_retains_all_faces_and_nonmanifold_aggregate_is_refused():
    parts = convert(compound(box((0, 0, 0)), box((2, 2, 0)), box((4, 4, 0))))
    assert len(parts) == 3 and sum(len(triangles(p)) for p in parts) == 36
    rows = [row for part in parts for row in triangles(part)]
    edges = Counter(tuple(sorted((p, q))) for a, b, c in rows for p, q in ((a, b), (b, c), (c, a)))
    assert 4 in edges.values()
    with pytest.raises(ValueError, match="nonmanifold"):
        TriangleSolid.validate(rows)
    assert sum(TriangleSolid.validate(triangles(part)).material_volume_mm3 for part in parts) == pytest.approx(24)


def test_single_solid_keeps_name_and_full_precise_transformed_coordinates():
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(0.123456789, -0.987654321, 4.111111111))
    (part,) = convert(box((0, 0, 0)).Moved(TopLoc_Location(transform)))
    assert part["name"] == "original"
    assert part["native_topology"]["solid_count"] == 1
    positions = [p for triangle in triangles(part) for p in triangle]
    assert min(p[0] for p in positions) == 0.123456789
    assert min(p[1] for p in positions) == -0.987654321
    assert min(p[2] for p in positions) == 4.111111111
    assert TriangleSolid.validate(triangles(part)).material_volume_mm3 == pytest.approx(8)


def test_source_surface_without_native_solids_is_retained_with_explicit_surface_kind():
    face = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(0, 0, 0), gp_Dir(0, 0, 1)), 0, 2, 0, 3).Face()
    (part,) = convert(face)
    assert part["name"] == "original" and part["native_topology"]["kind"] == "surface"
    assert part["native_topology"]["solid_count"] == 0 and part["native_topology"]["solid_index"] is None
    assert len(triangles(part)) == 2
    with pytest.raises(ValueError, match="open|nonmanifold"):
        TriangleSolid.validate(triangles(part))


def test_orphan_source_face_cannot_be_silently_omitted_beside_a_native_solid():
    face = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(10, 10, 10), gp_Dir(0, 0, 1)), 0, 2, 0, 3).Face()
    with pytest.raises(ValueError, match="cover every source face"):
        convert(compound(box((0, 0, 0)), face))


def test_missing_triangulation_and_empty_shape_refuse_conversion(monkeypatch):
    with pytest.raises(ValueError, match="Empty CAD component"):
        convert(TopoDS_Shape())
    import OCP.BRepMesh as mesher

    monkeypatch.setattr(mesher, "BRepMesh_IncrementalMesh", lambda *args: None)
    with pytest.raises(ValueError, match="no complete triangulation"):
        convert(box((0, 0, 0)))


def test_native_components_load_as_distinct_bodies_without_losing_viewer_geometry():
    from carveracontroller.addons.machine_simulation.profile import MachineProfile

    components = convert(compound(box((0, 0, 0)), box((2, 2, 0)), box((4, 4, 0))))
    for group in ("fixed", "carriage", "spindle"):
        components.extend(
            native_components(box((10, 10, 10)), name=group, assembly=group, group=group, color=(1, 1, 1, 1))
        )
    profile = MachineProfile(
        {
            "schema": 1,
            "units": "mm",
            "model": "Synthetic native solids",
            "source_url": "",
            "source_revision": "synthetic",
            "source_sha256": "synthetic",
            "components": components,
        }
    )
    assert len(profile.components) == 6
    assert len(profile.groups["table"].indices) == 3 * 12 * 3
    assert [c["native_topology"]["solid_index"] for c in profile.components[:3]] == [1, 2, 3]
    assert [c["native_topology"]["source_component"] for c in profile.components[:3]] == ["original"] * 3
    assert profile.geometry_sha256
    with pytest.raises(TypeError, match="immutable"):
        profile.components[0]["native_topology"]["solid_index"] = 7
