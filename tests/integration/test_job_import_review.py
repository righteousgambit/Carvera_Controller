"""Prepared archives require review and fresh declared context before publication."""

import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller import desktop_job_import_review as reviews
from carveracontroller import desktop_job_packages as jobs
from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition, ToolType
from carveracontroller.machine.job_packages import JobPackage, save_package
from tests.integration.conftest import pump_frames


@pytest.fixture
def imported(kivy_app, monkeypatch, tmp_path):
    archive = save_package(
        JobPackage(
            "Prepared block",
            b"G21\n",
            stock={"size_mm": [127, 69.4, 50.8]},
            assets={"setup.txt": b"setup notes"},
            tools=[
                {
                    "id": "shared-tool",
                    "name": "Imported cutter",
                    "shape": "flat_end_mill",
                    "diameter": 3.175,
                    "shank_diameter": 6.35,
                    "number": 1,
                }
            ],
        ),
        tmp_path / "job.cvjob",
    )
    workers = []

    class DeferredThread:
        def __init__(self, target, **_kwargs):
            self.target = target

        def start(self):
            workers.append(self.target)

    proxy = SimpleNamespace(Thread=DeferredThread)
    monkeypatch.setattr(jobs, "threading", proxy)
    monkeypatch.setattr(reviews, "threading", proxy)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    viewer = SimpleNamespace(
        machine_setup=MachineSetup(stock_size_mm=(40, 20, 10)),
        machine_component_profiles={},
        machine_profile=None,
        workholding_offset_mm=(0, 0, 0),
        workholding_rotation_deg=0,
        jaw_offset_mm=0,
        library_tool_table_mm={1: ToolDefinition(1, ToolType.FLAT_END_MILL, diameter=6.35)},
        tool_table={},
        preview_tool_override=None,
        move_scale_by_positon=1,
        tool_unit_scale=1,
        loaded_program_hash="old-hash",
        configure_machine=Mock(),
        configure_workholding=Mock(),
        publish_tool_profiles=Mock(),
        select_preview_tool=Mock(),
    )
    controller = SimpleNamespace(_connection_generation=1, executeCommand=Mock())
    camera = SimpleNamespace(
        registration=None,
        fit_identity=None,
        _input_identity=lambda: ("draft",),
        running=False,
        apply_calibration=Mock(),
    )
    ws = SimpleNamespace(
        app=SimpleNamespace(
            state="Idle", playing=False, selected_local_filename="old.cnc", selected_remote_filename=""
        ),
        selected_machine_profile={"id": "current", "name": "Current"},
        profile_store=SimpleNamespace(
            data={
                "tools": [
                    {
                        "id": "shared-tool",
                        "name": "Local cutter",
                        "shape": "flat_end_mill",
                        "diameter": 6.35,
                        "shank_diameter": 6.35,
                        "number": 1,
                    }
                ]
            }
        ),
        loaded_toolset=None,
        loaded_tool_profiles={},
        camera_registration_panel=camera,
        machine=SimpleNamespace(
            controller=controller,
            gcode_viewer=viewer,
            program_preview_generation=0,
            file_popup=SimpleNamespace(local_rv=SimpleNamespace(curr_selected_file="old.cnc")),
            view_local_file=Mock(),
        ),
        package_note=SimpleNamespace(text=""),
        choose_asset_file=lambda callback, **_kwargs: callback(archive),
    )
    before = reviews.import_context(ws)
    jobs.import_job(ws)
    assert len(workers) == 1
    workers[0]()
    pump_frames(4)
    review = ws._job_import_review
    viewer.configure_machine.assert_not_called()
    yield SimpleNamespace(
        workspace=ws, viewer=viewer, review=review, workers=workers, before=before, archive=archive, tmp_path=tmp_path
    )
    current = getattr(ws, "_job_import_review", None)
    if current is not None:
        current.cancel()
    controller.executeCommand.assert_not_called()


def test_cancel_preserves_program_setup_tools_and_library(imported):
    item = imported
    item.review.section.text = "Stock and work coordinates"
    assert "127" in item.review.incoming.text and "40" in item.review.current.text
    item.review.cancel_button.dispatch("on_release")
    assert item.review.closed
    assert reviews.import_context(item.workspace) == item.before
    assert item.workspace.machine.file_popup.local_rv.curr_selected_file == "old.cnc"
    item.viewer.publish_tool_profiles.assert_not_called()
    item.workspace.machine.view_local_file.assert_not_called()


@pytest.mark.parametrize(
    "change", ["stock", "vise", "tools", "inventory", "machine", "reload", "remote", "camera", "connection", "repeat"]
)
def test_review_apply_rejects_changed_context(imported, change):
    ws, viewer = imported.workspace, imported.viewer
    if change == "stock":
        viewer.machine_setup = replace(viewer.machine_setup, stock_origin_mm=(1, 2, 3))
    elif change == "vise":
        viewer.workholding_offset_mm = (5, 6, 7)
    elif change == "tools":
        viewer.library_tool_table_mm[1] = replace(viewer.library_tool_table_mm[1], diameter=3)
    elif change == "inventory":
        ws.profile_store.data["tools"][0]["diameter"] = 4
    elif change == "machine":
        ws.selected_machine_profile["name"] = "Changed same ID"
    elif change == "reload":
        ws.machine.program_preview_generation += 1
    elif change == "remote":
        ws.app.selected_remote_filename = "/sd/new.cnc"
    elif change == "repeat":
        viewer.repeat_stock_index = 1
    elif change == "camera":
        ws.camera_registration_panel._input_identity = lambda: ("edited",)
    else:
        ws.machine.controller._connection_generation += 1
    imported.review.apply_button.dispatch("on_release")
    assert "changed" in imported.review.note.text
    assert len(imported.workers) == 1
    viewer.configure_machine.assert_not_called()
    ws.machine.view_local_file.assert_not_called()


@pytest.mark.parametrize("change", ["context", "activity", "cancel"])
def test_changes_during_apply_verification_cannot_publish(imported, change):
    review, ws = imported.review, imported.workspace
    review.apply()
    assert review.checking and len(imported.workers) == 2
    if change == "context":
        ws.machine.program_preview_generation += 1
    elif change == "activity":
        ws.app.state = "Run"
    else:
        review.cancel_button.dispatch("on_release")
    imported.workers[1]()
    pump_frames(4)
    imported.viewer.configure_machine.assert_not_called()
    ws.machine.view_local_file.assert_not_called()
    if change == "cancel":
        assert review.closed and "cancelled" in ws.package_note.text
    else:
        assert "changed" in review.note.text


def test_staged_byte_changes_rejected_even_with_same_size_and_mtime(imported):
    path = imported.review.prepared[5]
    before = path.stat()
    path.write_bytes(b"G20\n")
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    imported.review.apply()
    imported.workers[1]()
    pump_frames(4)
    assert "bytes changed" in imported.review.note.text
    assert reviews.import_context(imported.workspace) == imported.before
    imported.viewer.configure_machine.assert_not_called()


def test_review_apply_publishes_only_prepared_tool_geometry(imported, monkeypatch):
    from carveracontroller.addons.tool_visualization import profile_loading

    monkeypatch.setattr(
        profile_loading, "prepare_tool_profiles", Mock(side_effect=AssertionError("No UI geometry reads"))
    )
    imported.review.apply_button.dispatch("on_release")
    imported.viewer.configure_machine.assert_not_called()
    imported.workers[1]()
    pump_frames(4)
    assert imported.review.closed
    imported.viewer.configure_machine.assert_called_once()
    imported.viewer.publish_tool_profiles.assert_called_once()
    imported.viewer.select_preview_tool.assert_called_once_with(None)
    profile_loading.prepare_tool_profiles.assert_not_called()
    assert imported.workspace.loaded_tool_profiles == {}
    assert "program preview loading" in imported.workspace.package_note.text


def test_review_pages_and_search_keep_full_values_bounded(imported):
    review = imported.review
    before = [f"Old tool field {i}" for i in range(181)]
    after = [f"Imported tool field {i}" for i in range(181)]
    review.sections["Preview cutters and toolset"] = before, after
    review.section.text = "Preview cutters and toolset"
    assert review.page_note.text == "Page 1 / 4"
    review.next.dispatch("on_release")
    assert review.page == 1 and "field 60" in review.incoming.text
    assert "field 120" not in review.incoming.text
    review.query.text = "field 180"
    review.find()
    assert review.page == 3 and "match line 181" in review.page_note.text
    review.query.text = "missing value"
    review.find()
    assert "No matching" in review.page_note.text


def test_unrelated_saved_tool_edit_preserves_review(imported):
    imported.workspace.profile_store.data["tools"].append({"id": "unrelated-tool", "name": "Unrelated"})
    imported.review.apply()
    assert imported.review.checking
    imported.workers[1]()
    pump_frames(4)
    assert imported.review.closed
    imported.viewer.publish_tool_profiles.assert_called_once()
    imported.viewer.select_preview_tool.assert_called_once_with(None)


def test_inventory_review_shows_both_conflicting_definitions(imported):
    imported.review.section.text = "Inventory reconciliation"
    assert "Local cutter" in imported.review.current.text
    assert "Imported cutter" in imported.review.incoming.text
    assert "shared-tool" in imported.review.incoming.text
    imported.review.cancel()
    assert imported.workspace.profile_store.data["tools"][0]["diameter"] == 6.35


def test_changed_embedded_asset_blocks_apply(imported):
    path = next(iter(imported.review.loaded.asset_paths.values()))
    path.write_bytes(b"different bytes")
    imported.review.apply()
    imported.workers[1]()
    pump_frames(4)
    assert "bytes changed" in imported.review.note.text
    imported.viewer.publish_tool_profiles.assert_not_called()


def test_escape_dismissal_preserves_current_preview(imported):
    imported.review.popup.dismiss(animation=False)
    assert imported.review.closed
    assert getattr(imported.workspace, "_job_import_review", None) is None
    assert reviews.import_context(imported.workspace) == imported.before
    imported.viewer.configure_machine.assert_not_called()


def test_review_resize_keeps_apply_cancel_visible(imported):
    from kivy.core.window import Window
    from kivy.metrics import dp

    from tests.integration.conftest import set_window_viewport

    original = Window.width, Window.height
    try:
        for width, height in ((1000, 800), (480, 600), (480, 420)):
            set_window_viewport(dp(width), dp(height))
            pump_frames(12)
            review = imported.review
            assert review.popup.width <= Window.width * 0.95
            assert review.popup.height <= Window.height * 0.91
            assert review.panes.orientation == ("vertical" if review.panes.width < dp(620) else "horizontal")
            for button in (review.apply_button, review.cancel_button):
                assert button.height > dp(25)
                x, y = button.to_window(*button.center)
                assert review.popup.x <= x <= review.popup.right
                assert review.popup.y <= y <= review.popup.top
            if review.view_mode.text == "Compare":
                assert review.current.height > dp(70) and review.incoming.height > dp(70)
            else:
                assert review.incoming.height > dp(70)
                review.view_mode.text = "Current"
                pump_frames(4)
                assert review.current.height > dp(70)
                review.view_mode.text = "Imported"
        pump_frames(4)
        review.popup.export_to_png(str(imported.tmp_path / "job-review-compact.png"))
    finally:
        set_window_viewport(*original)
        pump_frames(4)


@pytest.mark.parametrize("failure", [RuntimeError(), ValueError(), MemoryError()])
def test_preparation_failure_releases_worker_and_preserves_preview(imported, monkeypatch, failure):
    imported.review.cancel()

    def fail(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(jobs, "load_package", fail)
    jobs.import_job(imported.workspace)
    imported.workers[-1]()
    pump_frames(4)
    assert not imported.workspace._job_import_active
    assert type(failure).__name__ in imported.workspace.package_note.text
    imported.viewer.configure_machine.assert_not_called()
    assert reviews.import_context(imported.workspace) == imported.before


def test_preparation_queue_runs_only_latest_pending_selection(imported):
    imported.review.cancel()
    ws = imported.workspace
    jobs.import_job(ws)
    first_generation = ws._job_import_generation
    jobs.import_job(ws)
    jobs.import_job(ws)
    assert ws._job_import_generation == first_generation + 2
    assert len(imported.workers) == 2
    imported.workers[1]()
    pump_frames(4)
    assert len(imported.workers) == 3
    assert ws._job_import_review is None
    imported.workers[2]()
    pump_frames(4)
    assert ws._job_import_review.generation == ws._job_import_generation
    assert not ws._job_import_active
    imported.viewer.configure_machine.assert_not_called()


@pytest.mark.parametrize("stage", ["preparation", "verification"])
def test_worker_start_failure_releases_state_and_allows_retry(imported, monkeypatch, stage):
    class FailedThread:
        def __init__(self, **_kwargs):
            pass

        def start(self):
            raise RuntimeError("worker unavailable")

    proxy = SimpleNamespace(Thread=FailedThread)
    if stage == "preparation":
        imported.review.cancel()
        monkeypatch.setattr(jobs, "threading", proxy)
        jobs.import_job(imported.workspace)
        assert not imported.workspace._job_import_active
        assert "worker unavailable" in imported.workspace.package_note.text
    else:
        monkeypatch.setattr(reviews, "threading", proxy)
        imported.review.apply()
        assert not imported.review.checking
        assert not imported.review.apply_button.disabled
        assert "worker unavailable" in imported.review.note.text
    imported.viewer.configure_machine.assert_not_called()


def test_new_import_cancels_old_verification_without_overwriting_new_status(imported):
    old = imported.review
    old.apply()
    jobs.import_job(imported.workspace)
    assert old.closed and old.cancel_event.is_set()
    imported.workers[2]()
    pump_frames(4)
    newer = imported.workspace._job_import_review
    assert newer is not None and newer is not old
    status = imported.workspace.package_note.text
    imported.workers[1]()
    pump_frames(4)
    assert imported.workspace._job_import_review is newer
    assert imported.workspace.package_note.text == status
    imported.viewer.configure_machine.assert_not_called()


@pytest.mark.parametrize("close", ["button", "dismiss"])
def test_partial_publication_failure_does_not_claim_cancel_restored_preview(imported, close):
    imported.viewer.select_preview_tool.side_effect = ValueError("renderer unavailable")
    imported.review.apply()
    imported.workers[1]()
    pump_frames(4)
    assert imported.review.publication_failed
    assert imported.review.cancel_button.text == "Close review"
    assert imported.review.apply_button.disabled
    imported.viewer.publish_tool_profiles.assert_called_once()
    if close == "button":
        imported.review.cancel_button.dispatch("on_release")
    else:
        imported.review.popup.dismiss(animation=False)
    assert "partially updated" in imported.workspace.package_note.text
    assert "current preview retained" not in imported.workspace.package_note.text
    imported.workspace.machine.view_local_file.assert_not_called()


def test_published_program_lines_are_immutable_reviewed_content(imported):
    imported.review.apply()
    imported.workers[1]()
    imported.review.prepared[5].write_bytes(b"G20 X999\n")
    pump_frames(4)
    call = imported.workspace.machine.view_local_file.call_args
    assert call.kwargs["program_lines"] == ("G21\n",)
    assert callable(call.kwargs["on_loaded"])


@pytest.mark.parametrize("outcome", ["success", "failure", "wrong_hash", "superseded", "new_import"])
def test_import_completion_waits_for_matching_loader_result(imported, outcome):
    import hashlib

    ws = imported.workspace
    imported.review.apply()
    imported.workers[1]()
    pump_frames(4)
    assert "program preview loading" in ws.package_note.text
    callback = ws.machine.view_local_file.call_args.kwargs["on_loaded"]
    ws.app.selected_local_filename = str(imported.review.prepared[5])
    imported.viewer.loaded_program_hash = hashlib.sha256(b"G21\n").hexdigest()
    if outcome == "wrong_hash":
        imported.viewer.loaded_program_hash = "wrong"
    elif outcome == "superseded":
        ws.app.selected_local_filename = "another.cnc"
    elif outcome == "new_import":
        ws._job_import_generation += 1
        ws.package_note.text = "New import preparing"
    callback(outcome != "failure", "loader failure" if outcome == "failure" else "")
    if outcome == "success":
        assert "Restored local preview" in ws.package_note.text
    elif outcome == "superseded":
        assert "superseded" in ws.package_note.text
    elif outcome == "new_import":
        assert ws.package_note.text == "New import preparing"
    else:
        assert "failed or was cancelled" in ws.package_note.text
        assert "Restored" not in ws.package_note.text


def test_invalid_utf8_archive_fails_during_preparation_before_local_changes(imported):
    imported.review.cancel()
    archive = save_package(JobPackage("Invalid program", b"\xff\xfe"), imported.tmp_path / "invalid.cvjob")
    imported.workspace.choose_asset_file = lambda callback, **_kwargs: callback(archive)
    jobs.import_job(imported.workspace)
    imported.workers[-1]()
    pump_frames(4)
    assert "Import failed" in imported.workspace.package_note.text
    assert "utf-8" in imported.workspace.package_note.text
    assert not imported.workspace._job_import_active
    assert imported.workspace._job_import_review is None
    imported.viewer.configure_machine.assert_not_called()
    imported.workspace.machine.view_local_file.assert_not_called()


def test_render_failure_is_rejected_during_preparation_before_preview_publication(imported):
    import copy

    from carveracontroller.CNC import CNC

    item, ws = imported, imported.workspace
    archive = save_package(
        JobPackage("Unrepresentable arc", ("G0 X1 Y0 Z10\nG2 X1 Y0 I-1" + "0" * 100 + " J0\n").encode()),
        item.tmp_path / "unrepresentable.cvjob",
    )
    before = copy.deepcopy(CNC.vars)
    ws.choose_asset_file = lambda selected, **_kwargs: selected(archive)
    jobs.import_job(ws)
    item.workers[-1]()
    pump_frames(4)
    assert "Program preview failed at line 2" in ws.package_note.text
    assert CNC.vars == before
    assert ws._job_import_review is None
    item.viewer.configure_machine.assert_not_called()
    item.viewer.publish_tool_profiles.assert_not_called()
    ws.camera_registration_panel.apply_calibration.assert_not_called()
    ws.machine.view_local_file.assert_not_called()


@pytest.mark.parametrize("setting", ["clearance_z", "wcoz", "inch", "accuracy"])
def test_parser_input_change_requires_new_review_before_apply(imported, monkeypatch, setting):
    from carveracontroller.CNC import CNC

    if setting in ("clearance_z", "wcoz"):
        monkeypatch.setitem(CNC.vars, setting, CNC.vars.get(setting, 0.0) + 1)
    else:
        monkeypatch.setattr(CNC, setting, not CNC.inch if setting == "inch" else CNC.accuracy * 2)
    imported.review.apply()
    assert "changed" in imported.review.note.text
    assert len(imported.workers) == 1
    imported.viewer.configure_machine.assert_not_called()


def test_legacy_preparation_runs_in_worker_without_blocking_ui_or_mutating_telemetry(imported, monkeypatch):
    import copy
    import threading

    from carveracontroller.CNC import CNC

    item, ws = imported, imported.workspace
    ws.choose_asset_file = lambda selected, **_kwargs: selected(item.archive)
    jobs.import_job(ws)
    entered, release = threading.Event(), threading.Event()
    original = CNC.parseLine
    ui = threading.get_ident()
    before = copy.deepcopy(CNC.vars)

    def blocked(parser, *args):
        assert threading.get_ident() != ui
        entered.set()
        assert release.wait(3)
        return original(parser, *args)

    monkeypatch.setattr(CNC, "parseLine", blocked)
    thread = threading.Thread(target=item.workers[-1])
    pulses = []
    pulse = jobs.Clock.schedule_interval(lambda _dt: pulses.append(True), 0)
    thread.start()
    try:
        assert entered.wait(2)
        pump_frames(8, sleep=0.01)
        assert len(pulses) >= 3 and CNC.vars == before
        item.viewer.configure_machine.assert_not_called()
    finally:
        release.set()
        pulse.cancel()
        thread.join(3)
    assert not thread.is_alive()
    pump_frames(4)
    assert ws._job_import_review is not None and CNC.vars == before


def test_invalid_cached_parser_inputs_fail_on_worker_without_ui_exception(imported, monkeypatch):
    from carveracontroller.CNC import CNC

    item, ws = imported, imported.workspace
    monkeypatch.setitem(CNC.vars, "clearance_z", None)
    ws.choose_asset_file = lambda selected, **_kwargs: selected(item.archive)
    jobs.import_job(ws)
    assert len(item.workers) == 2
    item.workers[-1]()
    pump_frames(4)
    assert "Preview parser values must be finite" in ws.package_note.text
    item.viewer.configure_machine.assert_not_called()


def test_review_exposes_captured_renderer_inputs_and_preparation_result(imported):
    review = imported.review
    assert "Preview preparation" in review.sections
    review.section.text = "Preview preparation"
    assert "clearance_z" in review.incoming.text and "accuracy" in review.incoming.text
    assert "generated_vertices" in review.incoming.text
    assert "not interpreter" in review.incoming.text
