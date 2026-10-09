"""Independent agreement between captured body frames and viewer CAD poses."""

from dataclasses import replace
from types import SimpleNamespace

import pytest

from carveracontroller.addons.machine_simulation.model import Geometry, MachineSetup
from carveracontroller.addons.machine_simulation.profile import CAD_OFFSET, MachineProfile
from carveracontroller.addons.manufacturing_simulation import Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.geometry_changes import capture_context
from carveracontroller.machine.joint_clearance import (
    bodies_from_record,
    body_transform,
    corners,
    review_joint_clearance,
)
from carveracontroller.machine.joint_clearance_archive import load_joint_review, save_joint_review
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.repeat_parts import RepeatPartPlan, StockInstance
from carveracontroller.machine.scene_joint_clearance import build_scene_clearance, capture_scene_clearance


def scene_viewer(xshift=0):
    components = []
    for i, group in enumerate(("fixed", "table", "carriage", "spindle", "fixture", "workholding", "atc")):
        mesh = Geometry()
        mesh.box((10 + i * 10 + xshift, 20, 30), (15 + i * 10 + xshift, 27, 39), (0.5, 0.5, 0.5, 1))
        components.append(
            {
                "group": group,
                "vertices": mesh.vertices,
                "assembly": group,
                "workholding_role": "movable" if group == "workholding" else "fixed",
            }
        )
    profile = MachineProfile(
        {
            "schema": 1,
            "units": "mm",
            "model": "Carvera C1 synthetic geometry",
            "source_url": "",
            "source_revision": "synthetic",
            "source_sha256": "synthetic",
            "components": components,
            "workholding": {"pivot_mm": [50, 20, 30]},
        }
    )
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6, shank_diameter=6, flute_length=10, stickout=30)
    return SimpleNamespace(
        machine_profile=profile,
        machine_component_profiles={},
        machine_setup=MachineSetup(
            stock_size_mm=(20, 10, 5), stock_origin_mm=(-2, 3, -5), stock_rotation_deg=31, stock_tilt_deg=(20, -10)
        ),
        workholding_offset_mm=(11, -4, 2),
        workholding_rotation_deg=37,
        jaw_offset_mm=8,
        library_tool_table_mm={1: definition},
        assembly_preview_binding=None,
        repeat_stock_plan=None,
    )


def capture(viewer):
    return capture_scene_clearance(
        viewer.machine_profile,
        viewer.machine_component_profiles,
        viewer.machine_setup,
        (viewer.workholding_offset_mm, viewer.workholding_rotation_deg, viewer.jaw_offset_mm),
        viewer.library_tool_table_mm[1],
        1,
        viewer.repeat_stock_plan,
        capture_context(viewer, None, verify_assets=False),
    )


def bounds(points):
    return tuple(min(p[a] for p in points) for a in range(3)), tuple(max(p[a] for p in points) for a in range(3))


@pytest.mark.parametrize("state", [(-180, -120, -110), (-25, -235, -10), (-350, -5, -135)])
def test_component_frames_match_independent_viewer_pose_at_multiple_machine_positions(state):
    viewer = scene_viewer()
    record = build_scene_clearance(capture(viewer))
    machine = machine_from_record(record)
    bodies, excluded = bodies_from_record(record, machine)
    assert not excluded and len(bodies) == 10
    mx, my, mz = state
    joints = {"X": mx, "Y": my, "Z": mz}
    pose = viewer.machine_profile.pose(viewer.machine_setup, viewer.machine_setup.work_point(state), 30)
    geometry = viewer.machine_profile.scene(
        viewer.machine_setup, viewer.workholding_offset_mm, viewer.workholding_rotation_deg, viewer.jaw_offset_mm
    )
    for body in bodies:
        name = body.name.split()[0]
        actual = bounds([body_transform(machine, body, joints).apply(p).tuple for p in corners(body.bounds)])
        if name.startswith("T"):
            assert actual[0][:2] == pytest.approx((pose["tool_machine_mm"][0] - 3, pose["tool_machine_mm"][1] - 3))
            assert actual[1][:2] == pytest.approx((pose["tool_machine_mm"][0] + 3, pose["tool_machine_mm"][1] + 3))
            assert actual[0][2] == pytest.approx(mz + (0 if "cutter" in body.name else 10))
            assert actual[1][2] == pytest.approx(mz + (10 if "cutter" in body.name else 30))
        else:
            source = geometry["stock" if name == "stock" else name]
            shift = (
                pose["table"]
                if name in ("stock", "table", "fixture", "workholding", "atc")
                else pose.get(name, (0, 0, 0))
            )
            expected = bounds(
                [tuple(source.vertices[i + a] + shift[a] for a in range(3)) for i in range(0, len(source.vertices), 10)]
            )
            assert actual[0] == pytest.approx(expected[0])
            assert actual[1] == pytest.approx(expected[1])
    assert "No holder" in record["scene_source"]["notes"][-1]


def test_selected_component_override_all_repeat_stocks_and_identity_changes():
    viewer = scene_viewer()
    replacement = scene_viewer(100).machine_profile
    viewer.machine_component_profiles = {"fixture": replacement}
    viewer.repeat_stock_plan = RepeatPartPlan(
        (
            StockInstance(
                "First", "G54", (-180, -120, -110), (0, 0, 0), (10, 10, 5), stock_orientation_deg=(20, 15, 35)
            ),
            StockInstance(
                "Second", "G55", (-140, -120, -110), (0, 0, 0), (10, 10, 5), stock_orientation_deg=(-20, 10, 45)
            ),
        )
    )
    first = capture(viewer)
    record = build_scene_clearance(first)
    assert record["scene_source"]["geometry"]["fixture"] == replacement.geometry_sha256
    fixture = next(b for b in record["collision_bodies"] if b["name"].startswith("fixture"))
    assert fixture["minimum_mm"][0] == 150 + CAD_OFFSET[0]
    stocks = [b for b in record["collision_bodies"] if b["name"].startswith("stock")]
    assert len(stocks) == 2
    for body, part in zip(stocks, viewer.repeat_stock_plan.parts):
        assert body["minimum_mm"] == part.bounds[0] and tuple(body["maximum_mm"]) == part.bounds[1]
    viewer.jaw_offset_mm += 1
    assert capture(viewer).digest != first.digest
    viewer.library_tool_table_mm[1].stickout = 42
    assert first.definition.stickout == 30 and capture(viewer).digest != first.digest
    assert build_scene_clearance(first) == record


def test_scene_review_exchange_retains_source_and_recomputes_without_original_assets(tmp_path):
    record = build_scene_clearance(capture(scene_viewer()))
    machine = machine_from_record(record)
    bodies, excluded = bodies_from_record(record, machine)
    route = [{"X": -180, "Z": -110, "Y": -120}, {"X": -170, "Z": -105, "Y": -115}]
    report = review_joint_clearance(machine, route, bodies, excluded)
    path = tmp_path / "scene.cvclearance"
    save_joint_review(path, record, route, report)
    loaded = load_joint_review(path)
    assert loaded.record["scene_source"] == record["scene_source"] and loaded.report == report


def test_capture_refuses_missing_profiles_unknown_machine_assets_cancellation_and_budget(tmp_path):
    viewer = scene_viewer()
    viewer.machine_profile = None
    with pytest.raises(ValueError, match="C1 CAD"):
        capture(viewer)
    viewer = scene_viewer()
    viewer.machine_profile.model = "Other machine"
    with pytest.raises(ValueError, match="C1 CAD"):
        capture(viewer)
    viewer = scene_viewer()
    viewer.machine_setup = MachineSetup()
    with pytest.raises(ValueError, match="stock dimensions"):
        capture(viewer)
    viewer = scene_viewer()
    first = capture(viewer)
    with pytest.raises(InterruptedError):
        build_scene_clearance(first, cancelled=lambda: True)
    source = tmp_path / "changed.json.gz"
    source.write_bytes(b"changed")
    viewer.machine_profile.asset_path = str(source)
    viewer.machine_profile.asset_sha256 = "0" * 64
    with pytest.raises(ValueError, match="bytes changed"):
        build_scene_clearance(capture(viewer))
    viewer = scene_viewer()
    viewer.library_tool_table_mm[2] = ToolDefinition(2, geometry_path="/absent", geometry_sha256="f" * 64)
    assert build_scene_clearance(capture(viewer))  # unrelated tool assets are not captured
    profile = viewer.machine_profile
    # Repeat a validated immutable component enough times; source identities are
    # untouched, and no silent truncation is permitted.
    profile._components = profile.components + (profile.components[0],) * 32
    with pytest.raises(ValueError, match="more than 32"):
        build_scene_clearance(capture(viewer))


@pytest.mark.parametrize(
    "fault",
    [
        lambda s: s.update(tool_number=True),
        lambda s: s.update(scene_digest="bad"),
        lambda s: s["geometry"].pop("atc"),
        lambda s: s.update(notes=["x" * 513]),
    ],
)
def test_scene_source_contract_rejects_malformed_provenance(fault):
    record = build_scene_clearance(capture(scene_viewer()))
    fault(record["scene_source"])
    with pytest.raises(ValueError):
        machine_from_record(record)
