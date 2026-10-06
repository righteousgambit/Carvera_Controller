import json
from dataclasses import replace

import pytest

from carveracontroller.addons.cad_identity import asset_digest
from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SweptTool,
    ToolGeometry,
    Vec3,
)
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.assembly_envelopes import assembly_envelopes, cad_envelopes
from carveracontroller.machine.simulation_preview import simulation_tools


def obstacle(low, high):
    return AABB(Vec3(*low), Vec3(*high))


def asset(tmp_path, origin, triangles):
    path = tmp_path / f"{origin}.json"
    path.write_text(
        json.dumps(
            {"schema": "carvera-tool-mesh-v1", "units": "mm", "axis": "+Z", "origin": origin, "triangles": triangles}
        )
    )
    return path


def test_vertical_narrow_phase_rejects_stationary_and_diagonal_box_corners():
    tool = ToolGeometry(2, 2, 2, 3)
    sweep = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool)
    corner = obstacle((0.8, 0.8, 0.5), (0.9, 0.9, 1))
    assert sweep.component_bounds()[0][1].intersects(corner)
    assert not sweep.intersects_section(sweep.sections()[0], corner)
    diagonal = SweptTool(Vec3(-5, -5, 0), Vec3(5, 5, 0), tool)
    remote = obstacle((-4, 4, 0.5), (-3, 5, 1))
    assert diagonal.component_bounds()[0][1].intersects(remote)
    assert not diagonal.intersects_section(diagonal.sections()[0], remote)


def test_continuous_contact_and_z_time_coupling():
    tool = ToolGeometry(2, 1, 2, 2)
    sweep = SweptTool(Vec3(-10, 0, 0), Vec3(10, 0, 10), tool)
    section = sweep.sections()[0]
    assert sweep.intersects_section(section, obstacle((-0.1, -0.1, 5), (0.1, 0.1, 5.1)))
    # The XY center passes here only while the tool is much lower.
    missed = obstacle((-9, -0.1, 9), (-8.9, 0.1, 9.1))
    assert sweep.section_bounds(section).intersects(missed)
    assert not sweep.intersects_section(section, missed)
    reverse = SweptTool(sweep.end, sweep.start, tool)
    assert not reverse.intersects_section(section, missed)


def test_tangent_and_zero_duration_z_overlap_are_contacts():
    tool = ToolGeometry(2, 1, 2, 2)
    sweep = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool)
    assert sweep.intersects_section(sweep.sections()[0], obstacle((1, -0.1, 1), (2, 0.1, 2)))
    vertical = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 10), tool)
    assert vertical.intersects_section(vertical.sections()[0], obstacle((-0.1, -0.1, 11), (0.1, 0.1, 12)))


def test_tilted_sweep_narrow_phase_rejects_box_corner_without_physical_qualification():
    tool = ToolGeometry(2, 2, 2, 3)
    sweep = SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool, Vec3(1, 0, 0))
    scene = CollisionScene((CollisionObstacle("jaw", obstacle((0.5, 0.8, 0.8), (1, 0.9, 0.9))),))
    result = scene.check_sweep(sweep)
    assert result.candidates == ()
    assert not result.qualified
    touching = CollisionScene((CollisionObstacle("jaw", obstacle((0.5, 0.5, 0.5), (1, 0.6, 0.6))),))
    contact = touching.check_sweep(sweep)
    assert contact.candidates == (("cutter", "jaw"),)
    assert "zero lower bound" in contact.contacts[0].method
    assert not contact.qualified


def test_holder_cad_flare_is_registered_and_reported_without_duplicate_hits(tmp_path):
    holder = asset(tmp_path, "collet", [1, 0, 0, 6, 0, 4, 0, 6, 4])
    definition = ToolDefinition(
        1,
        ToolType.FLAT_END_MILL,
        diameter=2,
        shank_diameter=2,
        flute_length=2,
        stickout=10,
        holder_geometry_path=str(holder),
        holder_geometry_sha256=asset_digest(holder),
    )
    tool = simulation_tools({1: definition}, {"1"})["1"]
    sections = tuple(s for s in tool.noncutting_sections if s.component == "holder")
    assert min(s.low_mm for s in sections) == 10
    assert max(s.high_mm for s in sections) == 14
    assert max(s.radius_mm for s in sections) == 6
    scene = CollisionScene((CollisionObstacle("jaw", obstacle((4, -0.1, 13), (4.1, 0.1, 14))),))
    result = scene.check_sweep(SweptTool(Vec3(-10, 0, 0), Vec3(10, 0, 0), tool))
    assert result.candidates == (("holder", "jaw"),)
    assert len(result.contacts[0].sections) > 1
    assert asset_digest(holder) in result.contacts[0].sections[0].source
    assert not result.qualified
    holder.write_text(holder.read_text().replace("6", "7"))
    with pytest.raises(ValueError, match="CAD bytes changed"):
        simulation_tools({1: definition}, {"1"})


def test_clipped_triangle_envelope_cannot_use_unexposed_shank_or_miss_crossing_edge(tmp_path):
    cutter = asset(tmp_path, "tip", [1, 0, 0, 9, 0, 20, 0, 1, 0])
    sections = cad_envelopes(cutter, asset_digest(cutter), "shank", low=4, high=10, bands=3)
    assert len(sections) == 3
    assert min(s.low_mm for s in sections) == 4
    assert max(s.high_mm for s in sections) == 10
    assert max(s.radius_mm for s in sections) == pytest.approx(5)
    assert sections[0].radius_mm == pytest.approx(3.4)


def test_empty_missing_identity_and_below_tip_registration_rejected(tmp_path):
    holder = asset(tmp_path, "collet", [1, 0, -11, 2, 0, 0, 0, 2, 0])
    with pytest.raises(ValueError, match="byte identity"):
        cad_envelopes(holder, "", "holder")
    with pytest.raises(ValueError, match="below"):
        cad_envelopes(holder, asset_digest(holder), "holder", offset=10)
    with pytest.raises(ValueError, match="bounded"):
        cad_envelopes(holder, asset_digest(holder), "holder", bands=129)
    with pytest.raises(ValueError, match="tip origin"):
        cad_envelopes(holder, asset_digest(holder), "shank", low=1, high=2)


def test_holder_only_envelopes_keep_declared_shank_and_unknown_holder_is_visible():
    tool = ToolGeometry(2, 2, 2, 10, noncutting_sections=(AxialEnvelope("holder", 10, 12, 4),))
    assert {s.component for s in SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool).sections()} == {
        "cutter",
        "shank",
        "holder",
    }
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, flute_length=2, stickout=10)
    assert "Holder geometry missing" in " ".join(simulation_tools({1: definition}, {"1"})["1"].clearance_notes)
    with pytest.raises(ValueError, match="cutting length"):
        replace(tool, noncutting_sections=(AxialEnvelope("shank", 1, 3, 1),))


def test_declared_large_shoulder_is_checked_before_narrow_shank():
    definition = ToolDefinition(
        1, ToolType.FLAT_END_MILL, diameter=8, shank_diameter=2, flute_length=2, shoulder_length=7, stickout=10
    )
    tool = simulation_tools({1: definition}, {"1"})["1"]
    scene = CollisionScene((CollisionObstacle("jaw", obstacle((3, -0.1, 5), (3.1, 0.1, 6))),))
    collision = scene.check_sweep(SweptTool(Vec3(0, 0, 0), Vec3(0, 0, 0), tool))
    assert collision.candidates == (("shank", "jaw"),)
    assert "shoulder/shank" in collision.contacts[0].sections[0].source


@pytest.mark.parametrize(
    "registration",
    ({"offset": float("nan")}, {"low": float("inf")}, {"high": float("nan")}),
)
def test_nonfinite_cad_registration_is_rejected_before_envelope_construction(tmp_path, registration):
    holder = asset(tmp_path, "collet", [1, 0, 0, 6, 0, 4, 0, 6, 4])
    with pytest.raises(ValueError, match="registration and clipping heights must be finite"):
        cad_envelopes(holder, asset_digest(holder), "holder", **registration)


@pytest.mark.parametrize("stickout", (None, 0, -1, float("nan"), float("inf")))
def test_assembly_envelope_requires_known_finite_exposed_stickout(stickout):
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, stickout=stickout)
    with pytest.raises(ValueError, match="finite positive exposed stickout"):
        assembly_envelopes(definition, 1)


@pytest.mark.parametrize("flute", (0, -1, 11, float("nan"), float("inf")))
def test_assembly_envelope_cutting_length_must_fit_exposed_tool(flute):
    definition = ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, stickout=10)
    with pytest.raises(ValueError, match="cutting length"):
        assembly_envelopes(definition, flute)
