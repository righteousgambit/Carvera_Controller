"""CAD data validation and coordinate invariants without physical hardware."""

import copy

import pytest

from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup
from carveracontroller.addons.machine_simulation.profile import CAD_HEAD, CAD_OFFSET, MachineProfile, triangle_batches


def profile_data():
    triangle = [
        0,
        0,
        0,
        0,
        0,
        1,
        0.5,
        0.5,
        0.5,
        1,
        1,
        0,
        0,
        0,
        0,
        1,
        0.5,
        0.5,
        0.5,
        1,
        0,
        1,
        0,
        0,
        0,
        1,
        0.5,
        0.5,
        0.5,
        1,
    ]
    return {
        "schema": 1,
        "units": "mm",
        "model": "Fixture CAD",
        "source_url": "https://example.com/model",
        "source_revision": "fixture",
        "source_sha256": "fixture",
        "components": [
            {"group": group, "vertices": list(triangle)} for group in ("fixed", "table", "carriage", "spindle")
        ],
    }


@pytest.mark.parametrize("point", [(0, 0, 0), (47, -23, 11), (-80, 38, -14)])
def test_imported_motion_preserves_tool_to_stock_and_collet_attachment(point):
    profile = MachineProfile(profile_data())
    setup = MachineSetup()
    pose = profile.pose(setup, point, tool_length_mm=46)
    stock_point = (7, 5, -18)
    stock = setup.machine_point(stock_point)
    relative = [pose["tool_machine_mm"][i] - stock[i] - pose["table"][i] for i in range(3)]
    assert relative == pytest.approx([point[i] - stock_point[i] for i in range(3)])
    moved_head = [CAD_HEAD[i] + CAD_OFFSET[i] + pose["spindle"][i] for i in range(3)]
    assert moved_head == pytest.approx(
        [pose["tool_machine_mm"][0], pose["tool_machine_mm"][1], pose["tool_machine_mm"][2] + 46]
    )


@pytest.mark.parametrize("fault", ["units", "missing_group", "nan", "partial_triangle", "unknown_group"])
def test_malformed_profile_rejected(fault):
    data = copy.deepcopy(profile_data())
    if fault == "units":
        data["units"] = "inches"
    if fault == "missing_group":
        data["components"].pop()
    if fault == "nan":
        data["components"][0]["vertices"][0] = float("nan")
    if fault == "partial_triangle":
        data["components"][0]["vertices"].pop()
    if fault == "unknown_group":
        data["components"][0]["group"] = "rotary"
    with pytest.raises(ValueError):
        MachineProfile(data)


def test_mesh_batches_preserve_triangles_across_unsigned_short_limit():
    mesh = Geometry()
    for i in range(22000):
        mesh.triangle(((i, 0, 0), (i, 1, 0), (i, 0, 1)), (1, 0, 0), (1, 1, 1, 1))
    batches = list(triangle_batches(mesh))
    assert len(batches) == 2
    assert sum(len(indices) for _vertices, indices in batches) == 66000
    assert all(len(indices) % 3 == 0 and max(indices) < 65536 for _vertices, indices in batches)
    assert [v for vertices, _indices in batches for v in vertices] == mesh.vertices
