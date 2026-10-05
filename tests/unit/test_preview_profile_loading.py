"""Local mm tool overrides must survive program changes without altering CAM data."""

import copy

import pytest
from kivy.clock import Clock

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.GcodeViewer import GCodeViewer


@pytest.fixture
def viewer():
    item = GCodeViewer()
    item.high_precision_time_estimate = False
    item.tool_table = {}
    try:
        yield item
    finally:
        Clock.unschedule(item._on_frame_tick)


def cutter(number=1, diameter=6.35):
    return ToolDefinition(
        number=number,
        tool_type=ToolType.FLAT_END_MILL,
        diameter=diameter,
        shank_diameter=diameter,
        length=40,
        flute_length=12,
    )


def load_path(viewer, tool=1, size=20):
    viewer.begin_new_file_load()
    viewer.load_array([[0, 0, 0, 0, 1, 1, tool, 600], [size, 0, -1, 0, 1, 2, tool, 600]])


def radius(mesh):
    vertices = mesh[0]
    return max((vertices[i] ** 2 + vertices[i + 1] ** 2) ** 0.5 for i in range(0, len(vertices), 12))


@pytest.mark.parametrize("file_unit_scale", [1, 25.4])
def test_library_mm_not_multiplied_by_inch_file_units(viewer, file_unit_scale):
    viewer.tool_unit_scale = file_unit_scale
    cam = cutter(diameter=0.125 if file_unit_scale == 25.4 else 3.175)
    table = {1: cam, 2: copy.deepcopy(cam)}
    original = copy.deepcopy(table)
    viewer.tool_table = table
    load_path(viewer)
    viewer.load_tool_profiles({1: cutter()})
    scale = viewer.move_scale_by_positon
    assert radius(viewer._tool_meshes[1]) == pytest.approx(3.175 * scale)
    assert radius(viewer._tool_meshes[2]) == pytest.approx(original[2].shank_diameter / 2 * scale * file_unit_scale)
    assert table == original
    assert viewer.tool_table is table


def test_existing_pointer_updates_without_tool_number_change(viewer):
    viewer.tool_table = {1: cutter(diameter=3)}
    load_path(viewer)
    assert viewer._active_tool_number == 1
    old_vertices = list(viewer.pointer_mesh_instrs[0].vertices)
    profile = cutter()
    viewer.load_tool_profiles({1: profile})
    assert viewer._active_tool_number == 1
    assert list(viewer.pointer_mesh_instrs[0].vertices) != old_vertices
    assert list(viewer.pointer_mesh_instrs[0].vertices) == viewer._tool_meshes[1][0]
    assert list(viewer.pointer_mesh_instrs[1].vertices) == viewer._tool_meshes[1][0]
    profile.diameter = 99
    assert viewer.library_tool_table_mm[1].diameter == 6.35


def test_clear_and_new_program_keep_library_but_rebuild_scale(viewer):
    viewer.load_tool_profiles({1: cutter()})
    load_path(viewer, size=20)
    old_radius = radius(viewer._tool_meshes[1])
    viewer.clearDisplay()
    assert viewer.library_tool_table_mm[1].diameter == 6.35
    assert not viewer.pointer_mesh_instrs
    viewer.tool_unit_scale = 25.4
    viewer.tool_table = {1: cutter(diameter=0.1)}
    load_path(viewer, size=80)
    assert radius(viewer._tool_meshes[1]) == pytest.approx(3.175 * viewer.move_scale_by_positon)
    assert radius(viewer._tool_meshes[1]) < old_radius


def test_merge_replace_and_clear_overrides_restore_cam(viewer):
    viewer.tool_table = {1: cutter(diameter=3)}
    load_path(viewer)
    viewer.load_tool_profiles({1: cutter()})
    viewer.load_tool_profiles({2: cutter(2, 8)}, replace=False)
    assert set(viewer.library_tool_table_mm) == {1, 2}
    viewer.load_tool_profiles({2: cutter(2, 8)})
    assert set(viewer.library_tool_table_mm) == {2}
    assert radius(viewer._tool_meshes[1]) == pytest.approx(1.5 * viewer.move_scale_by_positon)
    viewer.load_tool_profiles({})
    assert not viewer.library_tool_table_mm
    assert set(viewer._tool_meshes) == {1}


@pytest.mark.parametrize(
    "definitions",
    [{True: cutter()}, {0: cutter()}, {1: "wrong"}, {1: cutter(diameter=float("nan"))}, {1: cutter(diameter=0)}],
)
def test_invalid_overrides_leave_previous_geometry_and_data(viewer, definitions):
    viewer.load_tool_profiles({1: cutter()})
    before = copy.deepcopy(viewer.library_tool_table_mm)
    meshes = viewer._tool_meshes
    with pytest.raises(ValueError):
        viewer.load_tool_profiles(definitions)
    assert viewer.library_tool_table_mm == before
    assert viewer._tool_meshes is meshes


def test_cad_holder_does_not_move_spindle_collet_attachment(viewer, tmp_path):
    import json

    from carveracontroller.addons.machine_simulation.profile import CAD_HEAD, CAD_OFFSET, MachineProfile
    from tests.unit.test_machine_profile import profile_data

    shape = [0, 0, 0, 1, 0, 10, 0, 1, 10]
    cutter_path = tmp_path / "cutter.json"
    holder_path = tmp_path / "holder.json"
    for path, origin in ((cutter_path, "tip"), (holder_path, "collet")):
        path.write_text(
            json.dumps(
                {"schema": "carvera-tool-mesh-v1", "units": "mm", "axis": "+Z", "origin": origin, "triangles": shape}
            )
        )
    tool = cutter()
    tool.stickout = 35
    tool.geometry_path = str(cutter_path)
    tool.holder_geometry_path = str(holder_path)
    viewer.machine_profile = MachineProfile(profile_data())
    load_path(viewer)
    viewer.load_tool_profiles({1: tool})
    pose = viewer._machine_pose_for((0, 0, 0))
    head_z = CAD_HEAD[2] + CAD_OFFSET[2] + pose["spindle"][2]
    assert head_z - pose["tool_machine_mm"][2] == pytest.approx(35)
    assert max(viewer._tool_meshes[1][0][2::12]) / viewer.move_scale_by_positon == pytest.approx(45)


def test_missing_cad_keeps_previous_loaded_preview(viewer, tmp_path):
    viewer.load_tool_profiles({1: cutter()})
    old_mesh = viewer._tool_meshes
    broken = cutter()
    broken.geometry_path = str(tmp_path / "missing.json")
    with pytest.raises(OSError):
        viewer.load_tool_profiles({1: broken})
    assert viewer._tool_meshes is old_mesh
    assert not viewer.library_tool_table_mm[1].geometry_path


def test_workarea_scene_controls_and_invalid_placement_preserve_state(viewer):
    assert viewer.machine_view_scope == "machine"
    assert viewer.machine_group_visibility["fixed"]
    viewer.set_machine_view_scope("machine")
    assert viewer.machine_group_visibility["fixed"]
    viewer.set_machine_group_visible("fixture", False)
    viewer.set_machine_view_scope("workarea")
    assert not viewer.machine_group_visibility["fixed"]
    assert not viewer.machine_group_visibility["fixture"]
    viewer.configure_workholding((10, 20, 5), 90, 6)
    with pytest.raises(ValueError):
        viewer.configure_workholding((float("nan"), 0, 0))
    assert viewer.workholding_offset_mm == (10, 20, 5)
    assert viewer.get_machine_simulation_info()["jaw_offset_mm"] == 6


def test_full_machine_fit_respects_short_and_narrow_viewports(viewer):
    from carveracontroller.addons.machine_simulation.profile import MachineProfile
    from carveracontroller.GcodeViewer import DEFAULT_ZOOM, PROJ_NEAR
    from tests.unit.test_machine_profile import profile_data

    data = profile_data()
    # A tall, deep chassis with all bounding extremes represented.
    vertices = data["components"][0]["vertices"]
    vertices[10:13] = [400, 0, 0]
    vertices[20:23] = [0, 400, 600]
    viewer.machine_profile = MachineProfile(data)
    viewer.machine_visible = True
    viewer.machine_group_visibility = dict.fromkeys(viewer.machine_group_visibility, True)
    for width, height in ((800, 300), (300, 800)):
        viewer.restore_default_view()
        viewer.size = (width, height)
        viewer._on_frame_tick(0)
        assert not viewer._machine_fit_dirty
        visible_height = viewer.m_distance * DEFAULT_ZOOM / PROJ_NEAR
        assert visible_height >= 600 * 0.866 + 400 * 0.5
        assert visible_height * width / height >= 400


def test_static_cutter_tip_uses_program_frame_with_work_offset(viewer):
    viewer.configure_machine(work_offset_mm=(-170, -100, -100))
    viewer.load_tool_profiles({1: cutter()})
    viewer.select_preview_tool(1)
    viewer.set_machine_visible(True)
    viewer._on_frame_tick(0)
    offset = viewer.pointermesh["offset"]
    assert offset == pytest.approx(
        (-viewer.lines_center[0], viewer._machine_pose["table"][1] - viewer.lines_center[1], -viewer.lines_center[2])
    )


def test_rendered_batches_preserve_registered_positions_normals_and_source(viewer, monkeypatch):
    from carveracontroller.addons.machine_simulation.model import Geometry

    geometry = Geometry()
    geometry.triangle(((2, 3, 4), (5, 6, 7), (8, 9, 10)), (0, 0, 1), (0.2, 0.4, 0.6, 1))
    geometry.indices = [2, 0, 1, 2, 1, 0]
    original = list(geometry.vertices)
    viewer.configure_machine(work_offset_mm=(-17, 20, -3))
    viewer.move_scale_by_positon = 0.25
    meshes = []
    monkeypatch.setattr("carveracontroller.GcodeViewer.Mesh", lambda **kw: meshes.append(kw))
    viewer._build_machine_scene({"fixture": geometry})
    expected = []
    for index in geometry.indices:
        vertex = original[index * 10 : index * 10 + 10]
        expected.extend([value * 0.25 for value in viewer.machine_setup.work_point(vertex[:3])])
        expected.extend(vertex[3:])
    assert meshes[0]["vertices"] == expected
    assert meshes[0]["indices"] == list(range(6))
    assert geometry.vertices == original
    assert viewer._inspection_geometry["fixture"] is geometry
    geometry.vertices[0] = float("nan")
    with pytest.raises(ValueError, match="Nonfinite"):
        viewer._build_machine_scene({"fixture": geometry})
