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
from pathlib import Path


def main():
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.collections import Sequence_TDF_Label
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("step", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--saunders-inch", type=Path, help="Add the manufacturer's imperial C1 plate at a draft bed registration")
    args = parser.parse_args()
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
        BRepMesh_IncrementalMesh(shape, 0.6, False, 0.25, True)
        faces = TopExp_Explorer(shape, TopAbs_FACE)
        vertices = []
        while faces.More():
            face = TopoDS.Face(faces.Current())
            face_location = TopLoc_Location()
            triangles = BRep_Tool.Triangulation_s(face, face_location)
            if triangles is not None:
                for index in range(1, triangles.NbTriangles() + 1):
                    ids = list(triangles.Triangle(index).Get())
                    if face.Orientation() == TopAbs_REVERSED:
                        ids[1], ids[2] = ids[2], ids[1]
                    points = [triangles.Node(i).Transformed(face_location.Transformation()).Coord() for i in ids]
                    a = [points[1][i] - points[0][i] for i in range(3)]
                    b = [points[2][i] - points[0][i] for i in range(3)]
                    normal = [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
                    length = math.sqrt(sum(v * v for v in normal))
                    if length > 1e-12:
                        for point in points:
                            vertices.extend(
                                round(v, 5) for v in (*point, *(n / length for n in normal), *colors[owner])
                            )
            faces.Next()
        if not vertices:
            raise ValueError(f"Empty CAD component: {name}")
        components.append({"name": name, "assembly": owner, "group": mapping[owner], "vertices": vertices})

    for index in range(1, roots.Length() + 1):
        visit(roots.Value(index), TopLoc_Location())
    fixture_metadata = None
    if args.saunders_inch:
        fixture_stage = True
        mapping["INCH Plate"] = "table"
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
            c for c in components[:original_count]
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
    profile = {
        "schema": 1,
        "model": "Carvera C1 · Community CAD v9" + (" + Saunders 1/4-inch" if fixture_metadata else ""),
        "units": "mm",
        "source_revision": args.revision,
        "source_url": "https://github.com/Carvera-Community/Carvera_Community_Profiles/blob/"
        + args.revision
        + "/Machine_Design_Files/CarveraC1_3%20Axis_MachineModel%20v9.step",
        "source_sha256": hashlib.sha256(args.step.read_bytes()).hexdigest(),
        "components": components,
        "fixture": fixture_metadata,
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
