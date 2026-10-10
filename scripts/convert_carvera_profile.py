"""Convert the community C1 v9 STEP assembly to an external viewer profile.

Run with cadquery-ocp 8.0.1.0.0. CAD dependencies are conversion-only; the
controller reads the resulting JSON and never executes Fusion postprocessors.
The source CAD stays outside the controller repository and app bundle.
"""

import argparse
import gzip
import hashlib
import json
import math
from collections import Counter
from fractions import Fraction
from pathlib import Path


def triangle_vertices(points, color):
    """Preserve every finite source position; normals are display attributes.

    Rounding positions after checking area can collapse a valid source facet.
    Exact fallback normals also retain subnormal and truly zero-area facets;
    admission may reject the latter, but conversion must not hide them.
    """
    if len(points) != 3 or any(len(p) != 3 for p in points) or len(color) != 4:
        raise ValueError("CAD triangles need three complete points and RGBA")
    if any(type(v) not in (int, float) or not math.isfinite(v) for p in (*points, color) for v in p):
        raise ValueError("CAD triangle coordinates and color must be finite")
    points = tuple(tuple(float(v) for v in p) for p in points)
    a = [points[1][i] - points[0][i] for i in range(3)]
    b = [points[2][i] - points[0][i] for i in range(3)]
    normal = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
    scale = max(abs(v) for v in normal)
    if not scale or not all(math.isfinite(v) for v in normal):
        exact = tuple(tuple(Fraction(v) for v in p) for p in points)
        a, b = ([exact[j][i] - exact[0][i] for i in range(3)] for j in (1, 2))
        cross = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
        largest = max(abs(v) for v in cross)
        normal = [float(v / largest) for v in cross] if largest else [0.0, 0.0, 0.0]
    else:
        normal = [v / scale for v in normal]
    length = math.hypot(*normal)
    normal = [round(v / length, 5) for v in normal] if length else normal
    return [v for p in points for v in (*p, *normal, *color)]


def native_components(shape, *, name, assembly, group, color):
    """Preserve native solids as separate components, with complete face coverage.

    Shared geometric edges between distinct solids do not define a manifold
    aggregate. Split only on original STEP topology, never mesh connectivity,
    coordinate tolerance, welding or guessed closed shells.
    """
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED, TopAbs_SOLID
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    if shape.IsNull():
        raise ValueError(f"Empty CAD component: {name}")
    BRepMesh_IncrementalMesh(shape, 0.6, False, 0.25, True)
    original_faces = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, TopAbs_FACE, original_faces)

    def faces_of(part):
        explorer = TopExp_Explorer(part, TopAbs_FACE)
        faces = []
        while explorer.More():
            face = TopoDS.Face(explorer.Current())
            index = original_faces.FindIndex(face)
            if index == 0:
                raise ValueError(f"Unresolved native CAD face: {name}")
            faces.append((index, face))
            explorer.Next()
        return faces

    expected = Counter(index for index, _ in faces_of(shape))
    solids = TopExp_Explorer(shape, TopAbs_SOLID)
    parts = []
    while solids.More():
        parts.append(solids.Current())
        solids.Next()
    native_count = len(parts)
    # Retain a source surface component if there is no native solid; solid
    # admission remains separate and may explicitly refuse it.
    if not parts:
        parts = [shape]
    face_sets = [faces_of(part) for part in parts]
    observed = Counter(index for faces in face_sets for index, _ in faces)
    if not expected or observed != expected:
        raise ValueError(f"Native CAD solids do not cover every source face exactly: {name}")
    result = []
    for number, faces in enumerate(face_sets, 1):
        vertices = []
        zero_area_faces = 0
        for _, face in faces:
            face_location = TopLoc_Location()
            triangles = BRep_Tool.Triangulation_s(face, face_location)
            if triangles is None or triangles.NbTriangles() == 0:
                raise ValueError(f"CAD face has no complete triangulation: {name}")
            for index in range(1, triangles.NbTriangles() + 1):
                ids = list(triangles.Triangle(index).Get())
                if face.Orientation() == TopAbs_REVERSED:
                    ids[1], ids[2] = ids[2], ids[1]
                points = [triangles.Node(i).Transformed(face_location.Transformation()).Coord() for i in ids]
                row = triangle_vertices(points, color)
                zero_area_faces += not any(row[3:6])
                vertices.extend(row)
        if not vertices:
            raise ValueError(f"Empty CAD component: {name}")
        result.append(
            {
                "name": f"{name} · solid {number}/{native_count}" if native_count > 1 else name,
                "assembly": assembly,
                "group": group,
                "vertices": vertices,
                "native_topology": {
                    "source_component": name,
                    "kind": "solid" if native_count else "surface",
                    "solid_index": number if native_count else None,
                    "solid_count": native_count,
                    "source_face_ids": [index for index, _ in faces],
                    "source_face_occurrences": sum(expected.values()),
                    "coverage": "all original face occurrences retained across native components",
                },
                "triangulation": {
                    "position_storage": "full binary64; no coordinate quantization",
                    "linear_deflection_mm": 0.6,
                    "angular_deflection_rad": 0.25,
                    "triangles": len(vertices) // 30,
                    "zero_area_faces_retained": zero_area_faces,
                },
            }
        )
    return result


def register_workholding(components, plate_vertices, source_path):
    """Centre manufacturer assembly on plate; registration is explicitly unqualified."""
    points = [c["vertices"][i : i + 3] for c in components for i in range(0, len(c["vertices"]), 10)]
    lows = [min(p[a] for p in points) for a in range(3)]
    highs = [max(p[a] for p in points) for a in range(3)]
    plate_lows = [min(plate_vertices[a::10]) for a in range(3)]
    plate_highs = [max(plate_vertices[a::10]) for a in range(3)]
    offset = [(plate_lows[a] + plate_highs[a] - lows[a] - highs[a]) / 2 for a in range(2)]
    offset.append(plate_highs[2] - lows[2])
    for component in components:
        component["group"] = "workholding"
        component["role"] = "movable" if component["assembly"] == "Adjustable Side Assembly" else "fixed"
        for i in range(0, len(component["vertices"]), 10):
            for a in range(3):
                component["vertices"][i + a] += offset[a]
    return {
        "model": "Saunders Hobby Gen3 Mod Vise · 1/4-inch",
        "source_url": "https://saundersmachineworks.com/products/modular-vise-system-hobby-gen3",
        "source_cad_url": "https://saundersmachineworks.com/cdn/shop/files/Gen3_Hobby_Mod_Vise_Inch.step?v=11563434097434530590",
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "cad_bounds_mm": [lows, highs],
        "cad_translation_mm": offset,
        "rotation_z_deg": 0,
        "adjustable_offset_mm": 0,
        "adjustable_axis": "y",
        "pivot_mm": [(plate_lows[a] + plate_highs[a]) / 2 for a in range(2)] + [plate_highs[2]],
        "registration": "draft: manufacturer jaw opening, assembly centred on plate top; mounting holes unregistered",
        "alignment_confirmed": False,
    }


def main():
    from OCP.collections import Sequence_TDF_Label
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument(
        "--saunders-inch", type=Path, help="Add the manufacturer's imperial C1 plate at a draft bed registration"
    )
    parser.add_argument(
        "--mod-vise-inch", type=Path, help="Add actual Hobby Gen3 vise assembly at explicit draft placement"
    )
    args = parser.parse_args()
    if args.mod_vise_inch and not args.saunders_inch:
        parser.error("--mod-vise-inch requires --saunders-inch")
    reader = STEPCAFControl_Reader()
    from OCP.IFSelect import IFSelect_RetDone

    if reader.ReadFile(str(args.step)) != IFSelect_RetDone:
        raise ValueError("STEP reader failed")
    doc = TDocStd_Document(TCollection_ExtendedString("Carvera"))
    if not reader.Transfer(doc):
        raise ValueError("STEP assembly transfer failed")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    roots = Sequence_TDF_Label()
    tool.GetFreeShapes(roots)
    components = []
    mapping = {"Frame": "fixed", "Bed": "table", "Z-Axis": "carriage", "Spindle": "spindle"}
    colors = {
        "Frame": (0.26, 0.32, 0.40, 1),
        "Bed": (0.60, 0.67, 0.73, 1),
        "Z-Axis": (0.26, 0.49, 0.55, 1),
        "Spindle": (0.72, 0.76, 0.80, 1),
        "INCH Plate": (0.69, 0.72, 0.77, 1),
    }
    fixture_stage = False

    def visit(label, location, inherited=None):
        attribute = TDataStd_Name()
        name = attribute.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attribute) else ""
        if fixture_stage and name == "METRIC Plate":
            return
        owner = name if name in mapping else inherited
        children = Sequence_TDF_Label()
        if tool.GetComponents_s(label, children):
            for index in range(1, children.Length() + 1):
                child = children.Value(index)
                referred = TDF_Label()
                if not tool.GetReferredShape_s(child, referred):
                    raise ValueError("Unresolved STEP component")
                visit(referred, location.Multiplied(tool.GetLocation_s(child)), owner)
            return
        if owner is None:
            raise ValueError(f"Unmapped CAD component: {name}")
        shape = tool.GetShape_s(label).Moved(location)
        components.extend(
            native_components(shape, name=name, assembly=owner, group=mapping[owner], color=colors[owner])
        )

    for index in range(1, roots.Length() + 1):
        visit(roots.Value(index), TopLoc_Location())
    fixture_metadata = None
    if args.saunders_inch:
        fixture_stage = True
        mapping["INCH Plate"] = "fixture"
        original_count = len(components)
        reader = STEPCAFControl_Reader()
        if reader.ReadFile(str(args.saunders_inch)) != IFSelect_RetDone:
            raise ValueError("Saunders STEP reader failed")
        fixture_doc = TDocStd_Document(TCollection_ExtendedString("Saunders"))
        if not reader.Transfer(fixture_doc):
            raise ValueError("Saunders STEP transfer failed")
        tool = XCAFDoc_DocumentTool.ShapeTool_s(fixture_doc.Main())
        fixture_roots = Sequence_TDF_Label()
        tool.GetFreeShapes(fixture_roots)
        for index in range(1, fixture_roots.Length() + 1):
            visit(fixture_roots.Value(index), TopLoc_Location())
        plates = components[original_count:]
        if len(plates) != 1 or plates[0]["assembly"] != "INCH Plate":
            raise ValueError("Expected exactly one imperial Saunders plate")
        vertices = plates[0]["vertices"]
        lows = [min(vertices[axis::10]) for axis in range(3)]
        highs = [max(vertices[axis::10]) for axis in range(3)]
        # Centre it over the original 356 x 240 mm MDF envelope and seat its
        # bottom at the former MDF bottom. This is an explicit draft placement,
        # not an assertion of the physical stand-off height or mounting origin.
        offset = [(326 - lows[0] - highs[0]) / 2, (210 - lows[1] - highs[1]) / 2, -3.175 - lows[2]]
        for index in range(0, len(vertices), 10):
            for axis in range(3):
                vertices[index + axis] += offset[axis]
        components = [
            c
            for c in components[:original_count]
            if not (c["assembly"] == "Bed" and ("WasteBoard" in c["name"] or c["name"] == "Anchor1"))
        ] + plates
        fixture_metadata = {
            "model": "Saunders Carvera imperial 1/4-inch plate",
            "source_url": "https://saundersmachineworks.com/products/makera-carvera-fixture-tooling-plate",
            "source_sha256": hashlib.sha256(args.saunders_inch.read_bytes()).hexdigest(),
            "cad_bounds_mm": [lows, highs],
            "cad_translation_mm": offset,
            "registration": "draft: centred on MDF envelope; bottom at former MDF bottom",
            "alignment_confirmed": False,
        }
    workholding_metadata = None
    if args.mod_vise_inch:
        mapping.update({"Fixed Side Assembly": "workholding", "Adjustable Side Assembly": "workholding"})
        colors.update({"Fixed Side Assembly": (0.58, 0.63, 0.69, 1), "Adjustable Side Assembly": (0.68, 0.73, 0.79, 1)})
        original_count = len(components)
        reader = STEPCAFControl_Reader()
        if reader.ReadFile(str(args.mod_vise_inch)) != IFSelect_RetDone:
            raise ValueError("Mod Vise STEP reader failed")
        vise_doc = TDocStd_Document(TCollection_ExtendedString("ModVise"))
        if not reader.Transfer(vise_doc):
            raise ValueError("Mod Vise STEP transfer failed")
        tool = XCAFDoc_DocumentTool.ShapeTool_s(vise_doc.Main())
        vise_roots = Sequence_TDF_Label()
        tool.GetFreeShapes(vise_roots)
        for index in range(1, vise_roots.Length() + 1):
            visit(vise_roots.Value(index), TopLoc_Location())
        vise = components[original_count:]
        if len(vise) != 4 or {c["assembly"] for c in vise} != {"Fixed Side Assembly", "Adjustable Side Assembly"}:
            raise ValueError("Expected fixed and adjustable Gen3 Hobby vise bases and top jaws")
        workholding_metadata = register_workholding(vise, plates[0]["vertices"], args.mod_vise_inch)
    profile = {
        "schema": 1,
        "model": "Carvera C1 · Community CAD v9"
        + (" + Saunders 1/4-inch" if fixture_metadata else "")
        + (" + Hobby Gen3 Mod Vise" if workholding_metadata else ""),
        "units": "mm",
        "source_revision": args.revision,
        "source_url": "https://github.com/Carvera-Community/Carvera_Community_Profiles/blob/"
        + args.revision
        + "/Machine_Design_Files/CarveraC1_3%20Axis_MachineModel%20v9.step",
        "source_sha256": hashlib.sha256(args.step.read_bytes()).hexdigest(),
        "components": components,
        "fixture": fixture_metadata,
        "workholding": workholding_metadata,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(profile, separators=(",", ":")).encode(), mtime=0))
    for c in components:
        points = [c["vertices"][i : i + 3] for i in range(0, len(c["vertices"]), 10)]
        print(
            c["assembly"],
            c["name"],
            len(points) // 3,
            [min(p[i] for p in points) for i in range(3)],
            [max(p[i] for p in points) for i in range(3)],
        )


if __name__ == "__main__":
    main()
