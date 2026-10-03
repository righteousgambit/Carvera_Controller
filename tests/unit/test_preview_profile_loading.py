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
    return ToolDefinition(number=number, tool_type=ToolType.FLAT_END_MILL, diameter=diameter,
                          shank_diameter=diameter, length=40, flute_length=12)


def load_path(viewer, tool=1, size=20):
    viewer.begin_new_file_load()
    viewer.load_array([[0, 0, 0, 0, 1, 1, tool, 600], [size, 0, -1, 0, 1, 2, tool, 600]])


def radius(mesh):
    vertices = mesh[0]
    return max((vertices[i] ** 2 + vertices[i+1] ** 2) ** .5 for i in range(0, len(vertices), 12))


@pytest.mark.parametrize("file_unit_scale", [1, 25.4])
def test_library_mm_not_multiplied_by_inch_file_units(viewer, file_unit_scale):
    viewer.tool_unit_scale = file_unit_scale
    cam = cutter(diameter=.125 if file_unit_scale == 25.4 else 3.175)
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
    viewer.tool_table = {1: cutter(diameter=.1)}
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


@pytest.mark.parametrize("definitions", [{True: cutter()}, {0: cutter()}, {1: "wrong"},
                                          {1: cutter(diameter=float("nan"))}, {1: cutter(diameter=0)}])
def test_invalid_overrides_leave_previous_geometry_and_data(viewer, definitions):
    viewer.load_tool_profiles({1: cutter()})
    before = copy.deepcopy(viewer.library_tool_table_mm)
    meshes = viewer._tool_meshes
    with pytest.raises(ValueError):
        viewer.load_tool_profiles(definitions)
    assert viewer.library_tool_table_mm == before
    assert viewer._tool_meshes is meshes
