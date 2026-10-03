"""Add the detailed community C1 tool rack to an existing v9 CAD profile.

Conversion only: requires cadquery-ocp. The two models share the bed frame.
Select the original rack, excluding the detailed model's duplicate ATC assembly.
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
    from OCP.IFSelect import IFSelect_RetDone
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
    parser.add_argument("profile", type=Path)
    parser.add_argument("step", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reader = STEPCAFControl_Reader()
    if reader.ReadFile(str(args.step)) != IFSelect_RetDone:
        raise ValueError("Detailed STEP reader failed")
    doc = TDocStd_Document(TCollection_ExtendedString("Carvera ATC"))
    if not reader.Transfer(doc):
        raise ValueError("Detailed STEP transfer failed")
    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    components = []
    selected = {"Tool Holders", "Tool Height Probe", "Touch Probe Holder"}

    def visit(label, location, owner=None):
        attribute = TDataStd_Name()
        name = attribute.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(), attribute) else ""
        if name in ("ATC Holder (1)", "Spindle", "Z-Axis", "Frame"):
            return
        owner = name if name in selected else owner
        children = Sequence_TDF_Label()
        if tool.GetComponents_s(label, children):
            for index in range(1, children.Length() + 1):
                child, referred = children.Value(index), TDF_Label()
                if not tool.GetReferredShape_s(child, referred):
                    raise ValueError("Unresolved STEP component")
                visit(referred, location.Multiplied(tool.GetLocation_s(child)), owner)
            return
        if owner is None:
            return
        shape = tool.GetShape_s(label).Moved(location)
        BRepMesh_IncrementalMesh(shape, 0.2, False, 0.18, True)
        faces, vertices = TopExp_Explorer(shape, TopAbs_FACE), []
        color = (0.20, 0.65, 0.69, 1) if name == "Holders" else (0.70, 0.74, 0.80, 1)
        while faces.More():
            face, face_location = TopoDS.Face(faces.Current()), TopLoc_Location()
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
                            vertices.extend(round(v, 5) for v in (*point, *(n / length for n in normal), *color))
            faces.Next()
        if not vertices:
            raise ValueError(f"Empty ATC component: {name}")
        components.append({"name": name, "assembly": owner, "group": "atc", "vertices": vertices})

    roots = Sequence_TDF_Label()
    tool.GetFreeShapes(roots)
    for index in range(1, roots.Length() + 1):
        visit(roots.Value(index), TopLoc_Location())
    if {c["assembly"] for c in components} != selected:
        raise ValueError("Expected holders, height sensor and probe dock")
    data = json.loads(gzip.decompress(args.profile.read_bytes()))
    data["components"] = [c for c in data["components"] if c["group"] != "atc"] + components
    data["atc"] = {
        "slots": 6,
        "source_revision": args.revision,
        "source_url": "https://github.com/Carvera-Community/Carvera_Community_Profiles/blob/"
        + args.revision
        + "/Machine_Design_Files/CarveraC1_MachineModel%20DETAILED.step",
        "source_sha256": hashlib.sha256(args.step.read_bytes()).hexdigest(),
        "registration": "Community CAD bed frame; physical rack alignment and occupancy unverified",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(gzip.compress(json.dumps(data, separators=(",", ":")).encode()))
    print(json.dumps({"components": len(components), "triangles": sum(len(c["vertices"]) // 30 for c in components)}))


if __name__ == "__main__":
    main()
