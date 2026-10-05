"""CAD data validation and coordinate invariants without physical hardware."""

import copy
import json

import pytest

from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup
from carveracontroller.addons.machine_simulation.profile import CAD_HEAD, CAD_OFFSET, MachineProfile, triangle_batches


def test_cached_geometry_is_canonical_and_cannot_be_mutated_through_input_or_profile():
    data = profile_data()
    profile = MachineProfile(data)
    encoded = profile.geometry_json
    assert encoded == json.dumps(
        {"components": profile.components, "workholding": profile.workholding, "atc": profile.atc},
        sort_keys=True,
        allow_nan=False,
        separators=(",", ":"),
    )
    data["components"][0]["vertices"][0] = 999
    assert profile.components[0]["vertices"][0] != 999
    with pytest.raises(TypeError):
        profile.components[0]["vertices"][0] = 999
    with pytest.raises(TypeError):
        profile.components[0]["group"] = "fixture"
    with pytest.raises(AttributeError):
        profile.components = ()
    assert profile.geometry_json is encoded


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


def test_configured_atc_target_matches_axis_reference_at_pickup_pose():
    profile = MachineProfile(profile_data())
    setup = MachineSetup()
    position = (-100, -40, -50)
    pickup = profile.pose(setup, setup.work_point(position), tool_length_mm=0)
    target = profile.configured_atc_target(position, pickup["table"])
    assert target == pytest.approx(pickup["tool_machine_mm"])
    shifted = profile.configured_atc_target(position, (0, 30, 0))
    assert shifted == (-100, -10, -50)
    for invalid in ((0, 0), (0, float("nan"), 0), (0, True, 0)):
        with pytest.raises(ValueError):
            profile.configured_atc_target(invalid, (0, 0, 0))


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


def test_optional_atc_geometry_keeps_original_bed_coordinates():
    data = profile_data()
    rack = copy.deepcopy(data["components"][0])
    rack["group"] = "atc"
    data["components"].append(rack)
    data["atc"] = {"slots": 6}
    profile = MachineProfile(data)
    assert profile.atc["slots"] == 6
    assert profile.scene(MachineSetup())["atc"].vertices[:3] == list(CAD_OFFSET)
    assert not MachineProfile(profile_data()).groups["atc"].indices


@pytest.mark.parametrize("angle", [0, 90, -35, 360])
def test_editor_envelopes_match_rendered_workholding_placement(angle):
    from carveracontroller.addons.machine_simulation.workholding import component_envelopes, projected_envelopes

    data = profile_data()
    data["workholding"] = {"pivot_mm": (20, 30, 5)}
    components = []
    for low, high, role in (((10, 20, 0), (50, 30, 10), "fixed"), ((10, 40, 0), (50, 50, 10), "movable")):
        mesh = Geometry()
        mesh.box(low, high, (1, 1, 1, 1))
        components.append({"group": "workholding", "role": role, "vertices": mesh.vertices})
    data["components"].extend(components)
    profile = MachineProfile(data)
    envelopes, pivot = component_envelopes(profile)
    offset, jaw = (12, -8, 4), 6.35
    projected = projected_envelopes(envelopes, pivot, offset, angle, jaw)
    scene = profile.scene(MachineSetup(), offset, angle, jaw)["workholding"].vertices
    start = 0
    for component, (corners, _) in zip(components, projected):
        end = start + len(component["vertices"])
        for axis in range(3):
            actual = [v - CAD_OFFSET[axis] - pivot[axis] for v in scene[start + axis : end : 10]]
            nominal = [p[axis] for p in corners]
            assert min(actual) == pytest.approx(min(nominal))
            assert max(actual) == pytest.approx(max(nominal))
        start = end


def test_vise_registration_seats_actual_assembly_and_keeps_jaw_roles(tmp_path):
    from scripts.convert_carvera_profile import register_workholding

    source = tmp_path / "vise.step"
    source.write_bytes(b"manufacturer fixture")
    triangle = profile_data()["components"][0]["vertices"]
    fixed = {"assembly": "Fixed Side Assembly", "vertices": list(triangle)}
    movable = {"assembly": "Adjustable Side Assembly", "vertices": list(triangle)}
    # Distinct movable side position must survive initial placement.
    for i in range(0, len(movable["vertices"]), 10):
        movable["vertices"][i + 1] -= 10
    plate = list(triangle)
    for i in range(0, len(plate), 10):
        plate[i] *= 100
        plate[i + 1] *= 80
        plate[i + 2] = 12
    result = register_workholding([fixed, movable], plate, source)
    assert fixed["group"] == movable["group"] == "workholding"
    assert fixed["role"] == "fixed"
    assert movable["role"] == "movable"
    assert min(fixed["vertices"][2::10]) == pytest.approx(12)
    assert movable["vertices"][1] - fixed["vertices"][1] == pytest.approx(-10)
    assert result["alignment_confirmed"] is False
    assert result["adjustable_axis"] == "y"
    assert "unregistered" in result["registration"]
    assert len(result["source_sha256"]) == 64


def test_vise_adjustment_rotates_movable_jaw_axis_without_moving_fixture():
    data = profile_data()
    fixed = {"group": "workholding", "role": "fixed", "vertices": list(data["components"][0]["vertices"])}
    movable = {"group": "workholding", "role": "movable", "vertices": list(fixed["vertices"])}
    fixture = {"group": "fixture", "vertices": list(fixed["vertices"])}
    data["components"].extend([fixed, movable, fixture])
    data["workholding"] = {"pivot_mm": (0, 0, 0), "cad_translation_mm": (0, 0, 0)}
    profile = MachineProfile(data)
    neutral = profile.scene(MachineSetup())
    rotated = profile.scene(
        MachineSetup(), workholding_offset_mm=(12, 5, 3), workholding_rotation_deg=90, jaw_offset_mm=8
    )
    assert rotated["fixture"].vertices == neutral["fixture"].vertices
    values = rotated["workholding"].vertices
    fixed_point = values[:3]
    movable_point = values[30:33]
    assert fixed_point == pytest.approx([CAD_OFFSET[0] + 12, CAD_OFFSET[1] + 5, CAD_OFFSET[2] + 3])
    assert [movable_point[i] - fixed_point[i] for i in range(3)] == pytest.approx([-8, 0, 0])
    assert rotated["table"].vertices == neutral["table"].vertices
