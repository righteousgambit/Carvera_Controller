"""Tool-only publication repairs real renderer buffers and never revives old epochs."""

from types import SimpleNamespace

import pytest
from kivy.clock import Clock

from carveracontroller.addons.tool_visualization.profile_loading import prepare_tool_profiles
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.GcodeViewer import ToolDisplayRestoreError


@pytest.fixture
def tool_viewer(kivy_app):
    # A constructor-fresh renderer cannot inherit another session test's cache,
    # pointer instructions, selected program, or asynchronous CAD publication.
    viewer = type(kivy_app.root.gcode_viewer)()
    try:
        viewer.cancel_default_machine_profile()
        Clock.unschedule(viewer._on_frame_tick)
        viewer.configure_machine(stock_size_mm=(20, 30, 10))
        viewer.load_tool_profiles({1: cutter(1, 2), 2: cutter(2, 3)})
        viewer.select_preview_tool(1)
        assert len(viewer.pointer_mesh_instrs) == 2
        yield viewer
    finally:
        viewer.cancel_default_machine_profile()
        Clock.unschedule(viewer._on_frame_tick)
        viewer.clearDisplay()


def cutter(number, diameter):
    return ToolDefinition(
        number, ToolType.FLAT_END_MILL, diameter=diameter, shank_diameter=diameter, flute_length=3, stickout=5
    )


def prepared_replacement(viewer):
    return prepare_tool_profiles(
        {1: cutter(1, 5)}, viewer.library_tool_table_mm, viewer.tool_table, viewer.move_scale_by_positon, 1, False
    )


class RejectVertices:
    """Forward to a real Mesh except for one injected graphics write failure."""

    def __init__(self, mesh, reject=False):
        self.mesh = mesh
        self.reject = reject
        self.index_writes = 0

    @property
    def vertices(self):
        return self.mesh.vertices

    @vertices.setter
    def vertices(self, value):
        if self.reject:
            self.reject = False
            raise RuntimeError("injected pointer vertex failure")
        self.mesh.vertices = value

    @property
    def indices(self):
        return self.mesh.indices

    @indices.setter
    def indices(self, value):
        self.index_writes += 1
        self.mesh.indices = value


def assert_logical_restored(viewer, previous):
    assert viewer.library_tool_table_mm is previous["library"]
    assert viewer.assembly_preview_binding is previous["assembly"]
    assert viewer.preview_tool_override == previous["override"]
    assert viewer._tool_meshes is previous["meshes"]
    assert viewer._default_tool_mesh is previous["fallback"]
    assert viewer._active_tool_number is previous["active"]
    assert tuple(viewer.pointer_mesh_instrs) == previous["instructions"]


def test_failure_after_first_real_pointer_write_restores_tools_and_both_meshes(tool_viewer):
    viewer = tool_viewer
    viewer.assembly_preview_binding = {"number": 1, "assembly_id": "retained"}
    viewer._scene_dirty = viewer._proj_dirty = viewer._machine_fit_dirty = False
    previous = viewer.capture_tool_display()
    epoch = viewer.declaration_epoch
    setup, manager, pose = viewer.machine_setup, viewer.meshmanager, viewer._machine_pose
    prepared = prepared_replacement(viewer)
    viewer.pointer_mesh_instrs[1] = RejectVertices(viewer.pointer_mesh_instrs[1], reject=True)

    with pytest.raises(RuntimeError, match="injected pointer vertex failure"):
        viewer.publish_tool_profiles(prepared)
    # The real production loop already published logical data and changed the
    # first real Mesh before the second Mesh's setter failed.
    assert viewer.library_tool_table_mm is prepared[0]
    assert viewer.assembly_preview_binding is None
    assert list(previous["instructions"][0].vertices) != previous["buffers"][0][1]
    failed_epoch = viewer.declaration_epoch
    assert failed_epoch > epoch

    viewer.restore_tool_display(previous)
    assert viewer.declaration_epoch > failed_epoch
    assert_logical_restored(viewer, previous)
    for mesh, vertices, indices in previous["buffers"]:
        assert list(mesh.vertices) == vertices
        assert list(mesh.indices) == indices
    assert tuple(viewer.pointermesh.children) == previous["pointer_children"]
    assert (viewer.pointermesh in viewer.canvas.children) == previous["pointer_attached"]
    assert (viewer._scene_dirty, viewer._proj_dirty, viewer._machine_fit_dirty) == previous["dirty"]
    assert viewer.machine_setup is setup and viewer.meshmanager is manager and viewer._machine_pose is pose

    # Only an explicit later retry publishes the new cutter.
    viewer.publish_tool_profiles(prepared)
    assert viewer.library_tool_table_mm is prepared[0]
    assert viewer._active_tool_number == 1
    assert list(viewer.pointer_mesh_instrs[0].vertices) != previous["buffers"][0][1]


def test_restore_attempts_remaining_buffers_and_reports_incomplete_redraw(tool_viewer):
    viewer = tool_viewer
    reject = RejectVertices(viewer.pointer_mesh_instrs[1])
    viewer.pointer_mesh_instrs[1] = reject
    viewer.assembly_preview_binding = {"number": 1, "assembly_id": "retained"}
    previous = viewer.capture_tool_display()
    viewer.publish_tool_profiles(prepared_replacement(viewer))
    reject.reject = True
    writes = reject.index_writes
    epoch = viewer.declaration_epoch

    with pytest.raises(ToolDisplayRestoreError, match="pointer 1 vertices") as raised:
        viewer.restore_tool_display(previous)
    assert_logical_restored(viewer, previous)
    assert viewer.declaration_epoch > epoch and viewer._scene_dirty
    assert isinstance(raised.value.__cause__, RuntimeError)
    assert len(raised.value.errors) == 1
    assert reject.index_writes == writes + 1  # Failed vertices do not skip indices.
    first, vertices, indices = previous["buffers"][0]
    assert list(first.vertices) == vertices and list(first.indices) == indices
    # Clearing the transient graphics fault permits a later explicit repair.
    viewer.restore_tool_display(previous)
    for mesh, vertices, indices in previous["buffers"]:
        assert list(mesh.vertices) == vertices and list(mesh.indices) == indices


def test_tool_restore_retires_new_pointer_instructions_without_rebuilding_program(kivy_app):
    viewer = type(kivy_app.root.gcode_viewer)()
    try:
        viewer.cancel_default_machine_profile()
        Clock.unschedule(viewer._on_frame_tick)
        previous = viewer.capture_tool_display()
        assert not previous["instructions"] and previous["fallback"] is None
        manager = viewer.meshmanager
        viewer.load_tool_profiles({1: cutter(1, 2)})
        viewer.select_preview_tool(1)
        assert viewer.pointer_mesh_instrs
        epoch = viewer.declaration_epoch
        viewer.restore_tool_display(previous)
        assert_logical_restored(viewer, previous)
        assert viewer.declaration_epoch > epoch
        assert tuple(viewer.pointermesh.children) == previous["pointer_children"]
        assert (viewer.pointermesh in viewer.canvas.children) == previous["pointer_attached"]
        assert viewer.meshmanager is manager and not viewer._viewer_meshes_active
    finally:
        viewer.cancel_default_machine_profile()
        Clock.unschedule(viewer._on_frame_tick)
        viewer.clearDisplay()


@pytest.mark.parametrize(
    "name",
    [
        "machine_setup",
        "machine_profile",
        "machine_component_profiles",
        "machine_group_visibility",
        "machine_visible",
        "machine_view_scope",
        "cutter_visible",
        "workholding_offset_mm",
        "workholding_rotation_deg",
        "jaw_offset_mm",
        "library_tool_table_mm",
        "assembly_preview_binding",
        "preview_tool_override",
        "repeat_stock_plan",
        "repeat_stock_index",
        "tool_table",
        "tool_unit_scale",
    ],
)
def test_direct_equal_declaration_assignments_are_monotonic(tool_viewer, name):
    viewer = tool_viewer
    original = getattr(viewer, name)
    epoch = viewer.declaration_epoch
    setattr(viewer, name, original)
    assert viewer.declaration_epoch > epoch
    next_epoch = viewer.declaration_epoch
    setattr(viewer, name, original)
    assert viewer.declaration_epoch > next_epoch
    assert getattr(viewer, name) is original


def test_validated_scene_mutations_invalidate_aba_but_invalid_requests_do_not(tool_viewer):
    viewer = tool_viewer
    old = viewer.machine_setup
    epoch = viewer.declaration_epoch
    viewer.configure_machine(stock_size_mm=(11, 12, 13))
    changed = viewer.declaration_epoch
    assert changed > epoch
    viewer.machine_setup = old
    assert viewer.declaration_epoch > changed

    epoch = viewer.declaration_epoch
    viewer.configure_workholding((1, 2, 3), 90, 4)
    changed = viewer.declaration_epoch
    viewer.configure_workholding()
    assert viewer.declaration_epoch > changed > epoch
    epoch = viewer.declaration_epoch
    with pytest.raises(ValueError):
        viewer.configure_workholding((float("nan"), 0, 0))
    assert viewer.declaration_epoch == epoch

    component = SimpleNamespace(groups={"fixture": SimpleNamespace(indices=[0, 1, 2])})
    viewer.select_machine_component("fixture", component)
    selected = viewer.declaration_epoch
    viewer.clear_machine_component("fixture")
    assert viewer.declaration_epoch > selected and not viewer.machine_component_profiles
    viewer.select_machine_component("fixture", component)
    selected = viewer.declaration_epoch
    viewer.clear_machine_component()
    assert viewer.declaration_epoch > selected and not viewer.machine_component_profiles


def test_frame_camera_and_derived_buffer_updates_do_not_change_declarations(tool_viewer):
    viewer = tool_viewer
    epoch = viewer.declaration_epoch
    viewer._scene_dirty = viewer._proj_dirty = True
    viewer.m_zoom *= 1.1
    viewer._active_tool_number = object()
    viewer._update_pointer_tool_mesh(0)
    viewer._on_size_change()
    assert viewer.declaration_epoch == epoch


def test_epoch_advances_before_tool_declarations_or_pointer_buffers_change(tool_viewer, monkeypatch):
    viewer = tool_viewer
    previous = viewer.capture_tool_display()
    initial_epoch = viewer.declaration_epoch
    real_advance = viewer._advance_declaration_epoch
    observations = []

    def observe_advance():
        observations.append((viewer.library_tool_table_mm, list(viewer.pointer_mesh_instrs[0].vertices)))
        real_advance()

    monkeypatch.setattr(viewer, "_advance_declaration_epoch", observe_advance)
    viewer.publish_tool_profiles(prepared_replacement(viewer))
    assert observations
    assert observations[0][0] is previous["library"]
    assert observations[0][1] == previous["buffers"][0][1]
    assert viewer.declaration_epoch > initial_epoch


def test_tool_restore_preserves_pointer_order_among_unrelated_canvas_instructions(tool_viewer):
    viewer = tool_viewer
    viewer.canvas.insert(0, viewer.gridmesh)
    viewer.canvas.add(viewer.axisxmesh)
    viewer.canvas.add(viewer.axisymesh)
    previous = viewer.capture_tool_display()
    canvas_children = tuple(viewer.canvas.children)
    assert previous["pointer_attached"]
    assert 0 < previous["pointer_index"] < len(canvas_children) - 1
    viewer.canvas.remove(viewer.pointermesh)
    viewer.restore_tool_display(previous)
    assert tuple(viewer.canvas.children) == canvas_children
    # Also correct a pointer left attached at the wrong draw position.
    viewer.canvas.remove(viewer.pointermesh)
    viewer.canvas.add(viewer.pointermesh)
    viewer.restore_tool_display(previous)
    assert tuple(viewer.canvas.children) == canvas_children
