import gzip
import json

import pytest

from carveracontroller.addons.tool_visualization.cad_assets import asset_summary, load_asset
from carveracontroller.addons.tool_visualization.mesh_builder import build_tool_meshes
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from scripts.convert_tool_profile import convert


def asset(tmp_path, triangles=None, **kwargs):
    path = tmp_path / "cutter.json.gz"
    data = {
        "schema": "carvera-tool-mesh-v1",
        "units": "mm",
        "axis": "+Z",
        "origin": "tip",
        "triangles": triangles or [0, 0, 0, 1, 0, 2, 0, 1, 2],
    }
    data.update(kwargs)
    with gzip.open(path, "wt") as f:
        json.dump(data, f)
    return str(path)


def test_asset_bounds_scale_and_precise_mesh(tmp_path):
    path = asset(tmp_path)
    tool = ToolDefinition(1, geometry_path=path, geometry_unit_scale=1 / 25.4)
    meshes, _ = build_tool_meshes({1: tool}, scale=0.1)
    vertices, indices, fmt = meshes[1]
    assert len(vertices) == 36
    assert indices == [0, 1, 2]
    assert vertices[12] == pytest.approx(0.1 / 25.4)
    assert vertices[14] == pytest.approx(0.2 / 25.4)
    assert sum(f[1] for f in fmt) == 12
    summary = asset_summary(path)
    assert summary["bounds_mm"] == [[0, 0, 0], [1, 1, 2]]
    assert len(summary["sha256"]) == 64


def test_holder_registration_and_stickout_clipping(tmp_path):
    path = asset(tmp_path)
    holder = tmp_path / "holder.json"
    holder.write_text(
        json.dumps(
            {
                "schema": "carvera-tool-mesh-v1",
                "units": "mm",
                "axis": "+Z",
                "origin": "collet",
                "triangles": [0, 0, 0, 2, 0, 1, 0, 2, 1],
            }
        )
    )
    tool = ToolDefinition(1, geometry_path=path, holder_geometry_path=str(holder), stickout=1)
    meshes, _ = build_tool_meshes({1: tool})
    vertices = meshes[1][0]
    assert max(vertices[2::12]) == 2
    assert max(vertices[:36][2::12]) == 1
    tool.stickout = None
    with pytest.raises(ValueError, match="stickout"):
        build_tool_meshes({1: tool})


@pytest.mark.parametrize(
    "mutation",
    [
        {"units": "in"},
        {"axis": "unknown"},
        {"origin": "unknown"},
        {"triangles": [1, 2]},
        {"triangles": [0, 0, -1, 1, 0, 2, 0, 1, 2]},
        {"triangles": [0, 0, 0, 1, 0, float("nan"), 0, 1, 2]},
    ],
)
def test_reject_invalid_assets(tmp_path, mutation):
    with pytest.raises(ValueError):
        load_asset(asset(tmp_path, **mutation))


def test_reject_index_overflow(tmp_path):
    with pytest.raises(ValueError, match="index limit"):
        load_asset(asset(tmp_path, triangles=[0, 0, 0] * 65538))


def test_obj_conversion_requires_explicit_registration_and_converts_inches(tmp_path):
    source = tmp_path / "tool.obj"
    source.write_text("v 1 2 3\nv 2 2 4\nv 1 3 4\nf 1 2 3\n")
    data = convert(source, "in", "+Z", [1, 2, 3])
    assert data["triangles"] == [0, 0, 0, 25.4, 0, 25.4, 0, 25.4, 25.4]
    assert data["source"]["tip"] == [1, 2, 3]
    assert len(data["source"]["sha256"]) == 64


def test_axis_rotation_is_right_handed(tmp_path):
    source = tmp_path / "tool.obj"
    source.write_text("v 0 0 0\nv 2 1 0\nv 2 0 1\nf 1 2 3\n")
    data = convert(source, "mm", "+X", [0, 0, 0])
    assert data["triangles"] == [0, 0, 0, 0, 1, 2, -1, 0, 2]


def test_binary_stl_conversion(tmp_path):
    import struct

    source = tmp_path / "tool.stl"
    triangle = [0, 0, 1, 0, 0, 0, 1, 0, 2, 0, 1, 2]
    source.write_bytes(b"x" * 80 + struct.pack("<I", 1) + struct.pack("<12fH", *triangle, 0))
    data = convert(source, "mm", "+Z", [0, 0, 0])
    assert data["triangles"] == [0, 0, 0, 1, 0, 2, 0, 1, 2]


def test_holder_can_attach_to_dimension_based_cutter(tmp_path):
    from carveracontroller.addons.tool_visualization.tool_definition import ToolType

    path = asset(tmp_path, origin="collet")
    tool = ToolDefinition(
        1, tool_type=ToolType.FLAT_END_MILL, diameter=6.35, length=76.2, stickout=35, holder_geometry_path=path
    )
    meshes, _ = build_tool_meshes({1: tool})
    assert max(meshes[1][0][2::12]) == 37
