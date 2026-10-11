"""Convert local STEP/STL/OBJ to bounded data-only tool meshes.

Specify source units, tool axis toward the shank, and tip coordinates explicitly.
Holder conversions use --origin collet and the collet-face centre as --tip.
STEP support needs cadquery-ocp; runtime never imports that dependency.
"""

import argparse
import gzip
import hashlib
import json
import struct
from pathlib import Path


def source_triangles(path, tolerance=0.15):
    suffix = path.suffix.lower()
    if suffix == ".obj":
        vertices, triangles = [], []
        for line in path.read_text().splitlines():
            tokens = line.split()
            if not tokens:
                continue
            if tokens[0] == "v":
                vertices.append([float(v) for v in tokens[1:4]])
            elif tokens[0] == "f":
                ids = [int(v.split("/")[0]) for v in tokens[1:]]
                face = [vertices[i - 1 if i > 0 else i] for i in ids]
                for i in range(1, len(face) - 1):
                    triangles.extend((*face[0], *face[i], *face[i + 1]))
        return triangles
    if suffix == ".stl":
        raw = path.read_bytes()
        if len(raw) >= 84 and len(raw) == 84 + struct.unpack_from("<I", raw, 80)[0] * 50:
            triangles = []
            for offset in range(84, len(raw), 50):
                triangles.extend(struct.unpack_from("<9f", raw, offset + 12))
            return triangles
        points = []
        for line in raw.decode("ascii").splitlines():
            tokens = line.split()
            if tokens and tokens[0] == "vertex":
                points.extend(float(v) for v in tokens[1:4])
        return points
    if suffix not in (".step", ".stp"):
        raise ValueError("Expected STEP, STL or OBJ")
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPControl import STEPControl_Reader
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    reader = STEPControl_Reader()
    if reader.ReadFile(str(path)) != IFSelect_RetDone or not reader.TransferRoots():
        raise ValueError("STEP transfer failed")
    shape = reader.OneShape()
    BRepMesh_IncrementalMesh(shape, tolerance, False, 0.25, True)
    faces = TopExp_Explorer(shape, TopAbs_FACE)
    points = []
    while faces.More():
        face = TopoDS.Face(faces.Current())
        location = TopLoc_Location()
        mesh = BRep_Tool.Triangulation_s(face, location)
        if mesh is not None:
            for i in range(1, mesh.NbTriangles() + 1):
                ids = list(mesh.Triangle(i).Get())
                if face.Orientation() == TopAbs_REVERSED:
                    ids[1], ids[2] = ids[2], ids[1]
                for index in ids:
                    points.extend(mesh.Node(index).Transformed(location.Transformation()).Coord())
        faces.Next()
    return points


def convert(path, units, axis, tip, origin="tip", source_url="", tolerance=0.15):
    # Right-handed rotations only: avoid mirroring handed/fluted tools.
    transforms = {
        "+Z": lambda x, y, z: (x, y, z),
        "-Z": lambda x, y, z: (x, -y, -z),
        "+X": lambda x, y, z: (-z, y, x),
        "-X": lambda x, y, z: (z, y, -x),
        "+Y": lambda x, y, z: (x, -z, y),
        "-Y": lambda x, y, z: (x, z, -y),
    }
    if path.suffix.lower() in (".step", ".stp") and units != "mm":
        raise ValueError("STEP readers resolve embedded units into mm; use --units mm")
    points = source_triangles(path, tolerance)
    scale = 25.4 if units == "in" else 1.0
    normalized = []
    for i in range(0, len(points), 3):
        p = [(points[i + j] - tip[j]) * scale for j in range(3)]
        normalized.extend(transforms[axis](*p))
    return {
        "schema": "carvera-tool-mesh-v1",
        "units": "mm",
        "axis": "+Z",
        "origin": origin,
        "source": {
            "filename": path.name,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "url": source_url,
            "units": units,
            "axis": axis,
            "tip": list(tip),
        },
        "triangles": normalized,
    }


def main():
    import sys

    # A selected CAD interpreter reads shipped source from the signed desktop
    # bundle. Bytecode caches would mutate sealed resources and invalidate it.
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--units", required=True, choices=["mm", "in"])
    parser.add_argument("--axis", required=True, choices=["+X", "-X", "+Y", "-Y", "+Z", "-Z"])
    parser.add_argument("--tip", required=True, nargs=3, type=float)
    parser.add_argument("--origin", default="tip", choices=["tip", "collet"])
    parser.add_argument("--source-url", default="")
    parser.add_argument("--tolerance", type=float, default=0.15)
    args = parser.parse_args()
    data = convert(args.source, args.units, args.axis, args.tip, args.origin, args.source_url, args.tolerance)
    # Validate before writing output, including the unsigned-16-bit index bound.
    import importlib.util
    import tempfile

    # Direct data-loader import avoids package __init__ importing Kivy in CAD-only Python.
    # The selected CAD interpreter need not have the controller installed or
    # inherit its development PYTHONPATH. Resolve shared data validation from
    # this source/bundle, not from the input CAD file's directory.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    spec = importlib.util.spec_from_file_location("tool_cad_assets", Path(__file__).with_name("cad_assets.py"))
    assets = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(assets)
    load_tool_asset = assets.load_tool_asset

    with tempfile.NamedTemporaryFile(suffix=".json") as check:
        check.write(json.dumps(data).encode())
        check.flush()
        load_tool_asset(check.name)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    opener = gzip.open if args.output.suffix == ".gz" else open
    with opener(args.output, "wt") as output:
        json.dump(data, output, separators=(",", ":"), allow_nan=False)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "vertices": len(data["triangles"]) // 3,
                "source_sha256": data["source"]["sha256"],
            }
        )
    )


if __name__ == "__main__":
    main()
