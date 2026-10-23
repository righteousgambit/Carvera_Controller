"""Failed first/closed-preview imports recover without inventing program geometry."""

from unittest.mock import Mock

import pytest

from carveracontroller import desktop_job_packages as jobs
from carveracontroller.GcodeViewer import GcodeViewer
from carveracontroller.machine.job_packages import JobPackage, save_package
from tests.integration.conftest import pump_frames
from tests.integration.test_completed_program_source import load, until


def test_pristine_viewer_round_trip_keeps_program_geometry_inactive(kivy_app):
    viewer = GcodeViewer()
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
        viewer.clearDisplay()


@pytest.mark.parametrize("fault", ["tools", "commit"])
def test_actual_import_failure_after_close_recovers_empty_view_and_allows_retry(kivy_app, monkeypatch, tmp_path, fault):
    app, root = kivy_app, kivy_app.root
    workspace, viewer = root.desktop_workspace, root.gcode_viewer
    send, source, evidence = Mock(), Mock(), Mock()
    monkeypatch.setattr(root.controller, "executeCommand", send)
    monkeypatch.setattr(root.controller, "set_program_source", source)
    monkeypatch.setattr(root.controller, "publish_prepared_program_source", evidence)
    monkeypatch.setattr(app, "state", "N/A")
    monkeypatch.setattr(app, "playing", False)
    original_visibility = viewer.machine_visible
    old = tmp_path / "previous.nc"
    old.write_text("G21 G90\nG0 X1 Y2 Z3\nG1 X5 F100\n")
    load(app, old)
    assert workspace.close_local_preview()
    viewer.set_machine_visible(True)
    assert viewer._default_tool_mesh is None and not viewer._viewer_meshes_active
    before = viewer.capture_program_display()
    setup = viewer.machine_setup
    archive = save_package(
        JobPackage("Empty recovery", b"G21 G90\nG0 X3 Y4 Z10\nG1 X9 F100\n"), tmp_path / "empty.cvjob"
    )
    monkeypatch.setattr(jobs.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(workspace, "choose_asset_file", lambda selected, **_kwargs: selected(archive))

    def open_review():
        previous = getattr(workspace, "_job_import_review", None)
        jobs.import_job(workspace)
        until(
            lambda: getattr(workspace, "_job_import_review", None) is not previous,
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
