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
    assert profile.scene(MachineSetup())["atc"].vertices[:3] == CAD_OFFSET
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


def test_reuse_checks_bytes_and_path_before_skipping_cad_validation(tmp_path, monkeypatch):
    import gzip
    import os
    from unittest.mock import Mock

    source = tmp_path / "machine.json.gz"
    source.write_bytes(gzip.compress(json.dumps(profile_data()).encode(), mtime=0))
    original = MachineProfile.load(source)
    loader = Mock(wraps=MachineProfile.load)
    monkeypatch.setattr(MachineProfile, "load", loader)
    assert MachineProfile.reuse_or_load(source, original) is original
    loader.assert_not_called()

    # Same pathname and restored metadata must not conceal different asset bytes.
    stamp = source.stat()
    data = profile_data()
    data["components"][0]["vertices"][0] = 9
    source.write_bytes(gzip.compress(json.dumps(data).encode(), mtime=0))
    os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    changed = MachineProfile.reuse_or_load(source, original)
    assert changed is not original
    assert changed.asset_sha256 != original.asset_sha256
    assert changed.components[0]["vertices"][0] == 9
    assert original.components[0]["vertices"][0] != 9
    loader.assert_called_once_with(source.resolve())

    # Byte-identical assets at another location keep their own path attribution.
    other = tmp_path / "other.json.gz"
    other.write_bytes(source.read_bytes())
    moved = MachineProfile.reuse_or_load(other, changed)
    assert moved is not changed
    assert moved.asset_path == str(other.resolve())
    assert moved.asset_sha256 == changed.asset_sha256


def test_reuse_rejects_missing_oversized_or_invalid_replacement(tmp_path):
    import gzip

    source = tmp_path / "machine.json.gz"
    source.write_bytes(gzip.compress(json.dumps(profile_data()).encode()))
    original = MachineProfile.load(source)
    source.write_bytes(b"not a gzip profile")
    with pytest.raises((ValueError, OSError)):
        MachineProfile.reuse_or_load(source, original)
    source.write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="size limit"):
        MachineProfile.reuse_or_load(source, original)
    source.unlink()
    with pytest.raises(OSError):
        MachineProfile.reuse_or_load(source, original)


def test_loaded_render_groups_are_immutable_snapshots():
    from dataclasses import FrozenInstanceError

    from carveracontroller.addons.machine_simulation.geometry_snapshot import GeometrySnapshot
    from carveracontroller.machine.scene_inspection import geometry_bounds

    profile = MachineProfile(profile_data())
    for geometry in profile.groups.values():
        assert isinstance(geometry, GeometrySnapshot)
        assert geometry_bounds(geometry) == geometry.bounds
    with pytest.raises(TypeError):
        profile.groups["fixed"] = Geometry()
    with pytest.raises(AttributeError):
        profile.groups = {}
    with pytest.raises(FrozenInstanceError):
        profile.groups["fixed"].vertices = ()


def test_placement_cache_is_bounded_immutable_and_independent_of_stock(monkeypatch):
    data = profile_data()
    data["components"].append(
        {"group": "workholding", "role": "movable", "vertices": list(data["components"][0]["vertices"])}
    )
    profile = MachineProfile(data)
    placement = ((12, 5, 3), 90, 8)
    prepared = profile.prepare_workholding(*placement)
    with pytest.raises(TypeError):
        prepared.vertices[0] = 999
    assert prepared.bounds is not None
    original = profile._placed_workholding
    monkeypatch.setattr(profile, "_placed_workholding", lambda *args: pytest.fail("cached placement recomputed"))
    a = profile.scene(MachineSetup(), *placement)
    b = profile.scene(MachineSetup(stock_size_mm=(10, 20, 30)), *placement)
    assert a["workholding"] is b["workholding"] is prepared
    assert a["stock"] is not b["stock"]
    assert profile.prepare_workholding() is profile.groups["workholding"]
    monkeypatch.setattr(profile, "_placed_workholding", original)
    for x in range(4):
        profile.prepare_workholding((x, 0, 0))
        assert len(profile._placements) <= 2
    assert profile.prepare_workholding(*placement).vertices == prepared.vertices


def test_warm_cache_hit_does_not_wait_for_other_placement_worker(monkeypatch):
    import threading

    profile = MachineProfile(profile_data())
    entered, release = threading.Event(), threading.Event()
    original = profile._placed_workholding
    errors = []

    def blocked(*args):
        entered.set()
        if not release.wait(2):
            errors.append("worker timeout")
        return original(*args)

    monkeypatch.setattr(profile, "_placed_workholding", blocked)
    worker = threading.Thread(target=lambda: profile.prepare_workholding((5, 0, 0)))
    worker.start()
    try:
        assert entered.wait(1)
        assert profile.prepare_workholding() is profile.groups["workholding"]
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive() and not errors
