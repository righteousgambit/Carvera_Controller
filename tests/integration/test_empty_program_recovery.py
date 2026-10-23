"""Failed first/closed-preview imports recover without inventing program geometry."""

from unittest.mock import Mock

import pytest
from kivy.clock import Clock

from carveracontroller import desktop_job_packages as jobs
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.job_packages import JobPackage, save_package
from tests.integration.conftest import pump_frames
from tests.integration.test_completed_program_source import load, until


def test_pristine_viewer_round_trip_keeps_program_geometry_inactive(kivy_app):
    viewer = type(kivy_app.root.gcode_viewer)()
    viewer.configure_machine()
    try:
        previous = viewer.capture_program_display()
        assert previous["tools"] == ({}, None)
        assert not viewer._viewer_meshes_active
        viewer.restore_program_display(previous)
        assert viewer.meshmanager is previous["manager"]
        assert viewer.loaded_program_hash is None
        assert not viewer._viewer_meshes_active
        assert viewer.pointermesh not in viewer.canvas.children
        assert viewer.linemesh not in viewer.canvas.children
        assert not viewer.pointer_mesh_instrs
    finally:
        viewer.cancel_default_machine_profile()
        Clock.unschedule(viewer._on_frame_tick)
        viewer.clearDisplay()


@pytest.fixture
def fresh_empty_viewer(kivy_app, monkeypatch):
    """Mount a constructor-fresh renderer in the real shared app's import path.

    An empty filename does not imply an uninitialized renderer: loading cutter
    profiles legitimately builds a fallback without activating program geometry.
    Keep the first-import gate independent of that preceding session state.
    """
    app, root = kivy_app, kivy_app.root
    workspace = root.desktop_workspace
    monkeypatch.setattr(app, "state", "N/A")
    monkeypatch.setattr(app, "playing", False)
    if app.selected_local_filename:
        assert workspace.close_local_preview()
    original = root.gcode_viewer
    parent, index = original.parent, original.parent.children.index(original)
    viewer = type(original)()
    # This gate covers the program transaction, not asynchronous CAD discovery.
    viewer.cancel_default_machine_profile()
    viewer.configure_machine()
    viewer.high_precision_time_estimate = original.high_precision_time_estimate
    viewer.set_frame_callback(root.gcode_play_call_back)
    viewer.set_play_over_callback(root.gcode_play_over_call_back)
    viewer.set_error_popup_callback(root._on_gcode_cannot_visualise)
    viewer.time_estimate_progress_callback = root._on_time_estimate_progress
    viewer.time_estimate_context_callback = root._time_estimate_context
    viewer.desktop_viewport = True
    viewer.set_display_offset(0, 0)
    parent.remove_widget(original)
    root.gcode_viewer = viewer
    parent.add_widget(viewer, index=index)
    try:
        assert viewer.parent is workspace.model_card
        assert viewer._default_tool_mesh is None
        assert not viewer._tool_meshes and not viewer._viewer_meshes_active
        yield viewer
    finally:
        try:
            until(lambda: not root.loading_file, "Temporary viewer still loading at teardown")
            if workspace.can_close_local_preview():
                assert workspace.close_local_preview()
        finally:
            viewer.cancel_default_machine_profile()
            Clock.unschedule(viewer._on_frame_tick)
            viewer.clearDisplay()
            parent.remove_widget(viewer)
            root.gcode_viewer = original
            parent.add_widget(original, index=index)


@pytest.mark.parametrize("fault", ["tools", "commit"])
@pytest.mark.parametrize("entry", ["pristine", "initialized", "closed"])
def test_actual_import_failure_recovers_empty_view_and_allows_retry(
    kivy_app, fresh_empty_viewer, monkeypatch, tmp_path, fault, entry
):
    app, root = kivy_app, kivy_app.root
    workspace, viewer = root.desktop_workspace, root.gcode_viewer
    send, source, evidence = Mock(), Mock(), Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    monkeypatch.setattr(root.controller, "set_program_source", source)
    monkeypatch.setattr(root.controller, "publish_prepared_program_source", evidence)
    assert viewer is fresh_empty_viewer
    original_visibility = viewer.machine_visible
    if entry == "closed":
        old = tmp_path / "previous.nc"
        old.write_text("G21 G90\nG0 X1 Y2 Z3\nG1 X5 F100\n")
        load(app, old)
        assert workspace.close_local_preview()
    elif entry == "initialized":
        viewer.load_tool_profiles(
            {1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=2, shank_diameter=2, flute_length=3, stickout=4)}
        )
    assert app.selected_local_filename == ""
    viewer.set_machine_visible(True)
    assert not viewer._viewer_meshes_active
    if entry == "initialized":
        assert viewer._default_tool_mesh is not None and 1 in viewer._tool_meshes
    else:
        assert viewer._default_tool_mesh is None and not viewer._tool_meshes
    before = viewer.capture_program_display()
    setup = viewer.machine_setup
    library = viewer.library_tool_table_mm
    archive = save_package(
        JobPackage("Empty recovery", b"G21 G90\nG0 X3 Y4 Z10\nG1 X9 F100\n"), tmp_path / "empty.cvjob"
    )
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(workspace, "choose_asset_file", lambda selected, **_kwargs: selected(archive))

    def open_review():
        previous = getattr(workspace, "_job_import_review", None)
        jobs.import_job(workspace)
        until(
            lambda: (
                getattr(workspace, "_job_import_review", None) is not None
                and workspace._job_import_review is not previous
            ),
            "Import review did not arrive: " + workspace.package_note.text,
        )
        return workspace._job_import_review

    try:
        review = open_review()
        with monkeypatch.context() as failure:
            target, attribute = (
                (viewer, "publish_tool_profiles") if fault == "tools" else (jobs.LocalJobTransaction, "commit")
            )
            failure.setattr(target, attribute, Mock(side_effect=RuntimeError("injected precommit failure")))
            review.apply_button.dispatch("on_release")
            until(lambda: workspace.package_note.text.startswith("Import "), workspace.package_note.text)
            assert workspace.package_note.text.startswith("Import not applied · previous local preview restored"), (
                workspace.package_note.text
            )
        assert workspace._job_import_recovery[1] is True
        assert viewer.meshmanager is before["manager"] and viewer.loaded_program_hash is None
        assert viewer.machine_setup == setup
        assert viewer.library_tool_table_mm is library
        recovered = viewer.capture_program_display()
        assert recovered["view"] == before["view"]
        assert recovered["inactive_pose"] == before["inactive_pose"]
        assert recovered["tools"][0] is before["tools"][0]
        assert recovered["tools"][1] is before["tools"][1]
        if entry != "initialized":
            assert recovered["tools"] == ({}, None)
        assert app.selected_local_filename == "" and not root.loading_file
        assert not viewer._viewer_meshes_active and not viewer.pointer_mesh_instrs
        assert viewer.linemesh not in viewer.canvas.children and viewer.pointermesh not in viewer.canvas.children
        assert viewer.machine_visible and viewer._machine_contexts_added
        assert viewer.total_distance == 0 and not viewer.raw_positions
        evidence.assert_not_called()
        open_review().apply_button.dispatch("on_release")
        until(lambda: workspace.package_note.text.startswith("Restored local preview"), workspace.package_note.text)
        assert viewer.loaded_program_hash and viewer._viewer_meshes_active
        assert viewer.pointer_mesh_instrs
        evidence.assert_called_once()
        send.assert_not_called()
    finally:
        root.message_popup.dismiss(animation=False)
        root.progress_popup.dismiss(animation=False)
        if workspace.can_close_local_preview():
            workspace.close_local_preview()
        viewer.set_machine_visible(original_visibility)
        pump_frames(2)
