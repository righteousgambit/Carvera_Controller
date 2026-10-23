"""Real embedded library round trips retain simulation ownership without writes."""

import copy
import threading
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.config import Config
from kivy.core.window import Window

from carveracontroller import desktop_tool_profile_loading as loading
from carveracontroller.desktop_view_state import capture_view
from carveracontroller.machine.desktop_profiles import ProfileStore, to_tool_definition
from tests.integration.conftest import pump_frames, set_window_logical_size, set_window_viewport
from tests.integration.test_completed_program_source import load, until

SOURCE = "(operation: Finish)\nG21 G90 G54\nT3 M6\nG0 X1 Y2 Z20\nG1 X5 F100\n"


@pytest.fixture
def assignment(kivy_app, monkeypatch, tmp_path):
    app, ws = kivy_app, kivy_app.root.desktop_workspace
    viewer = ws.machine.gcode_viewer
    ws._cancel_simulation_assignment()
    viewer.cancel_default_machine_profile()
    monkeypatch.setattr(app, "state", "N/A")
    monkeypatch.setattr(app, "playing", False)
    monkeypatch.setattr(ws.machine.controller, "set_program_source", Mock())
    monkeypatch.setattr(ws.machine.controller, "publish_prepared_program_source", Mock())
    commands = Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", commands)
    path = tmp_path / "finish.nc"
    path.write_text(SOURCE)
    program = load(app, path)
    viewer.configure_machine(stock_size_mm=(20, 20, 10), stock_model=None)
    viewer.clear_machine_component()
    store = ProfileStore(tmp_path / "profiles.json")

    def saved(name, diameter):
        return store.save_tool(
            {
                "name": name,
                "number": 1,
                "shape": "flat_end_mill",
                "diameter": diameter,
                "shank_diameter": 6,
                "length": 40,
                "flute_length": 12,
                "stickout": 20,
            }
        )

    first, chosen = saved("Current rougher", 6), saved("Saved finisher", 3)
    viewer.load_tool_profiles({1: to_tool_definition(first)})
    viewer.select_preview_tool(None)
    monkeypatch.setattr(ws, "loaded_toolset", {"id": "bank", "name": "Saved bank", "slots": {"1": first["id"]}})
    monkeypatch.setattr(ws, "loaded_tool_profiles", {}, raising=False)
    monkeypatch.setattr(ws, "profile_store", store)
    ws._open_profiles()
    library = ws.profile_library
    monkeypatch.setattr(library, "store", store)
    library.select_kind("tools")
    ws.select("Job")
    ws.program_tasks.show("Simulation")
    ws.simulation_panel.scope.text = "Selected operation"
    ws.operation_panel.select(program.operations[0])
    ws.program_tasks.show("Simulation")
    pump_frames(4)
    ws.program_tasks.scroll.scroll_y = 0.4
    write = Mock()
    monkeypatch.setattr(Config, "write", write)
    fixture = SimpleNamespace(
        app=app,
        ws=ws,
        viewer=viewer,
        store=store,
        first=first,
        chosen=chosen,
        library=library,
        program=program,
        path=path,
        write=write,
        commands=commands,
    )
    try:
        yield fixture
    finally:
        ws._cancel_simulation_assignment()
        if hasattr(ws, "tool_profile_loads"):
            until(lambda: not ws.tool_profile_loads.active, "Cutter worker did not retire")
        library.set_simulation_assignment(None)
        viewer.select_preview_tool(None)
        viewer.load_tool_profiles({})
        ws.loaded_toolset = None
        ws.loaded_tool_profiles = {}


def open_assignment(fixture):
    ws = fixture.ws
    ws.select("Job")
    ws.program_tasks.show("Simulation")
    context = ws.simulation_panel.review_simulation_tool(3)
    assert context is not None, ws.simulation_panel.note.text
    assert ws.tool_comparison.selected == 3
    assert ws.tool_comparison.library_action.text == "Choose cutter for T3"
    ws.tool_comparison.library_action.dispatch("on_release")
    assert ws.active_section == "Profiles"
    assert fixture.library.simulation_assignment is context
    fixture.library._edit(fixture.chosen)
    assert not fixture.library.apply_button.disabled
    assert "T3" in fixture.library.apply_button.text
    return context


def wait(fixture):
    until(lambda: not fixture.ws.tool_profile_loads.active, "Cutter preparation did not finish")


@pytest.mark.parametrize("width", [780, 1600])
def test_saved_t1_is_assigned_only_to_requested_t3_and_returns_same_review(assignment, monkeypatch, width):
    f = assignment
    previous_viewport = Window.width, Window.height
    try:
        set_window_logical_size(width, 960)
        f.ws.program_tasks.scroll.scroll_y = 0.4
        original = f.viewer.library_tool_table_mm[1]
        operation, line = f.ws.operation_panel.selected_operation, f.ws.operation_panel.selected_line
        view = capture_view(f.viewer)
        stored, preferences = f.store.path.read_bytes(), dict(Config.items("carvera"))
        context = open_assignment(f)
        calculate = Mock()
        monkeypatch.setattr(f.ws.simulation_panel, "start", calculate)
        f.library.apply_button.dispatch("on_release")
        wait(f)
        until(lambda: not context.active, "Review return did not settle")
        assert f.ws.active_section == "Job" and f.ws.program_tasks.active == "Simulation"
        assert f.ws.operation_panel.program is f.program
        assert f.ws.operation_panel.selected_operation is operation and f.ws.operation_panel.selected_line == line
        assert f.ws.simulation_panel.scope.text == "Selected operation"
        assert f.ws.program_tasks.scroll.scroll_y == pytest.approx(0.4)
        assert capture_view(f.viewer) == view
        assert set(f.viewer.library_tool_table_mm) == {1, 3}
        assert f.viewer.library_tool_table_mm[1] == original
        assert f.viewer.library_tool_table_mm[3].diameter == 3
        assert f.ws.loaded_toolset is None
        assert f.ws.loaded_tool_profiles == {1: f.first, 3: f.chosen}
        assert "custom tool selection" in f.ws.profile_status.text
        from carveracontroller.desktop_job_packages import capture_recording_job

        job = capture_recording_job(f.ws, include_camera=False)
        assert job.toolsets == []
        assert {item["number"] for item in job.tools} == {1, 3}
        assert f.store.path.read_bytes() == stored and dict(Config.items("carvera")) == preferences
        f.write.assert_not_called()
        f.commands.assert_not_called()
        calculate.assert_not_called()
    finally:
        set_window_viewport(*previous_viewport)


@pytest.mark.parametrize(
    "change",
    [
        "editor_aba",
        "selection_aba",
        "saved_aba",
        "delete",
        "store_owner",
        "page_aba",
        "close_reopen",
        "target_aba",
        "scene_aba",
        "tool_aba",
        "same_path_reload",
        "mesh_owner",
        "settings_aba",
        "task_aba",
    ],
)
def test_late_geometry_never_publishes_over_changed_context(assignment, monkeypatch, change):
    f = assignment
    context = open_assignment(f)
    entered, release = threading.Event(), threading.Event()
    original_prepare = loading.prepare_tool_profiles

    def blocked(*args):
        entered.set()
        assert release.wait(15)
        return original_prepare(*args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", blocked)
    before, meshes = f.viewer.library_tool_table_mm, f.viewer._tool_meshes
    f.library.apply()
    assert entered.wait(2)
    try:
        if change == "editor_aba":
            field = f.library.fields["name"]
            old = field.text
            field.text = "Changed"
            field.text = old
        elif change == "selection_aba":
            f.library._edit(f.first)
            f.library._edit(f.chosen)
        elif change == "saved_aba":
            f.store.save_tool(dict(f.chosen, name="Changed"))
            f.store.save_tool(f.chosen)
        elif change == "delete":
            f.store.delete("tools", f.chosen["id"])
        elif change == "store_owner":
            monkeypatch.setattr(f.library, "store", ProfileStore(f.store.path))
        elif change == "page_aba":
            f.ws.select("Position", record_navigation=False)
            f.ws.select("Profiles", record_navigation=False)
        elif change == "close_reopen":
            f.ws.close_profile_library()
            f.ws._open_profiles()
        elif change == "target_aba":
            f.ws.tool_comparison.choose(1)
            f.ws.tool_comparison.choose(3)
        elif change == "scene_aba":
            old = f.viewer.workholding_offset_mm
            f.viewer.workholding_offset_mm = (1, 2, 3)
            f.viewer.workholding_offset_mm = old
        elif change == "tool_aba":
            f.viewer.select_preview_tool(1)
            f.viewer.select_preview_tool(None)
        elif change == "same_path_reload":
            load(f.app, f.path)
        elif change == "mesh_owner":
            monkeypatch.setattr(f.viewer, "meshmanager", copy.copy(f.viewer.meshmanager))
        elif change == "settings_aba":
            f.ws.simulation_panel.resolution.text = "1"
            f.ws.simulation_panel.resolution.text = "2"
        elif change == "task_aba":
            with context.navigation():
                f.ws.select("Job")
            f.ws.program_tasks.show("Operations")
            f.ws.program_tasks.show("Simulation")
            f.ws.select("Profiles")
        expected_page = f.ws.active_section
        latest_status = f.library.status.text
    finally:
        release.set()
    wait(f)
    assert set(f.viewer.library_tool_table_mm) == {1}
    if change != "same_path_reload":
        assert f.viewer.library_tool_table_mm is before and f.viewer._tool_meshes is meshes
    assert f.ws.active_section == expected_page
    if change in ("scene_aba", "tool_aba", "same_path_reload", "mesh_owner"):
        assert not context.active and f.library.apply_button.disabled
        assert "Review this cutter again" in f.library.status.text
        assert not context._bindings and not context._origin_bindings
    elif not context.active or context._request is None and change in ("editor_aba", "selection_aba"):
        assert f.library.status.text == latest_status
    f.write.assert_not_called()
    f.commands.assert_not_called()


def test_dirty_or_new_cutter_never_implicitly_saves_or_loads(assignment, monkeypatch):
    f = assignment
    open_assignment(f)
    original = f.store.path.read_bytes()
    request = Mock()
    monkeypatch.setattr(f.ws, "_request_tool_profiles", request)
    f.library.fields["name"].text = "Unsaved new name"
    assert f.library.apply_button.disabled
    f.library.apply()
    assert f.store.path.read_bytes() == original
    f.library.new()
    assert f.library.apply_button.disabled
    f.library.apply()
    request.assert_not_called()
    assert f.store.path.read_bytes() == original


@pytest.mark.parametrize("failure", ["preparation", "start", "publish", "restore"])
def test_failures_retain_prior_preview_and_allow_only_explicit_retry(assignment, monkeypatch, failure):
    f = assignment
    context = open_assignment(f)
    before = f.viewer.capture_tool_display()
    bank = copy.deepcopy(f.ws.loaded_toolset)
    real_publish, real_restore = f.viewer.publish_tool_profiles, f.viewer.restore_tool_display

    def broken_publish(prepared):
        real_publish(prepared)
        raise RuntimeError("injected publication failure")

    with monkeypatch.context() as patch:
        if failure == "preparation":
            patch.setattr(loading, "prepare_tool_profiles", Mock(side_effect=RuntimeError("injected preparation")))
        elif failure == "start":
            patch.setattr(loading.threading.Thread, "start", Mock(side_effect=RuntimeError("injected startup")))
        else:
            patch.setattr(f.viewer, "publish_tool_profiles", broken_publish)
            if failure == "restore":

                def incomplete(snapshot):
                    real_restore(snapshot)
                    raise RuntimeError("injected redraw incomplete")

                patch.setattr(f.viewer, "restore_tool_display", incomplete)
        f.library.apply()
        wait(f)
        assert not context.pending
        assert f.ws.active_section == "Profiles"
        assert "assignment failed" in f.library.status.text
        assert f.viewer.library_tool_table_mm is before["library"]
        assert f.viewer._tool_meshes is before["meshes"]
        assert f.ws.loaded_toolset == bank and f.ws.loaded_tool_profiles == {}
        if failure == "restore":
            assert "restoration incomplete" in f.library.status.text
            assert f.library.apply_button.disabled and not context.active
    if failure != "restore":
        f.library.apply()
        wait(f)
        assert set(f.viewer.library_tool_table_mm) == {1, 3}
    f.write.assert_not_called()
    f.commands.assert_not_called()


def test_pending_new_preview_cannot_create_assignment_even_before_loading_flag(assignment, monkeypatch):
    f = assignment
    monkeypatch.setattr(f.ws.machine, "program_preview_generation", f.ws.machine.program_preview_generation + 1)
    assert not f.ws.machine.loading_file
    assert f.ws.simulation_panel.review_simulation_tool(3) is None
    assert "complete local" in f.ws.simulation_panel.note.text


@pytest.mark.parametrize("intent", ["scroll", "scroll_aba", "page_aba", "task_aba"])
def test_postcommit_scroll_return_yields_to_later_intent(assignment, monkeypatch, intent):
    f = assignment
    context = open_assignment(f)
    original_return = context._return_to_review

    def return_then_user_intent():
        original_return()
        if intent == "scroll":
            f.ws.program_tasks.scroll.scroll_y = 0.65
        elif intent == "scroll_aba":
            old = f.ws.program_tasks.scroll.scroll_y
            f.ws.program_tasks.scroll.scroll_y = 0.65
            f.ws.program_tasks.scroll.scroll_y = old
        elif intent == "page_aba":
            f.ws.select("Position", record_navigation=False)
            f.ws.select("Job", record_navigation=False)
        else:
            f.ws.program_tasks.show("Operations")
            f.ws.program_tasks.show("Simulation")

    monkeypatch.setattr(context, "_return_to_review", return_then_user_intent)
    f.library.apply()
    wait(f)
    final_scroll = f.ws.program_tasks.scroll.scroll_y
    pump_frames(4)
    assert set(f.viewer.library_tool_table_mm) == {1, 3}
    assert not context.active and context._scroll_binding is None and context._return_event is None
    assert f.ws.program_tasks.scroll.scroll_y == final_scroll
    if intent == "scroll":
        assert final_scroll == pytest.approx(0.65)
    assert "custom tool selection" in f.ws.profile_status.text


@pytest.mark.parametrize("failure", ["refresh", "scroll", "chrome"])
def test_postcommit_ui_failure_reports_applied_and_retires_controls(assignment, monkeypatch, failure):
    f = assignment
    context = open_assignment(f)
    with monkeypatch.context() as patch:
        if failure == "refresh":
            original_refresh = f.ws.simulation_panel.refresh_inputs
            failed = False

            def fail_once_after_commit():
                nonlocal failed
                if 3 in f.viewer.library_tool_table_mm and not failed:
                    failed = True
                    raise RuntimeError("refresh fault")
                original_refresh()

            patch.setattr(f.ws.simulation_panel, "refresh_inputs", fail_once_after_commit)
        elif failure == "scroll":
            patch.setattr(f.ws.program_tasks.scroll.effect_y, "reset", Mock(side_effect=RuntimeError("scroll fault")))
        else:
            original = f.library.refresh_context_action

            def fail_after_commit():
                if 3 in f.viewer.library_tool_table_mm:
                    raise RuntimeError("chrome fault")
                original()

            patch.setattr(f.library, "refresh_context_action", fail_after_commit)
        f.library.apply()
        wait(f)
        until(lambda: not context.active, "Post-commit failure did not retire return")
        assert set(f.viewer.library_tool_table_mm) == {1, 3}
        assert f.ws.loaded_toolset is None and f.ws.loaded_tool_profiles[3] == f.chosen
        assert "applied" in f.library.status.text and "could not be restored" in f.library.status.text
        assert f.library.apply_button.disabled
        assert not context.pending and context._return_event is None and context._scroll_binding is None
        assert not context._bindings and not context._origin_bindings


def test_queued_successor_worker_start_failure_retires_pending_assignment(assignment, monkeypatch):
    f = assignment
    context = open_assignment(f)
    entered, release = threading.Event(), threading.Event()
    prepare, start = loading.prepare_tool_profiles, loading.threading.Thread.start
    starts = []

    def blocked(*args):
        entered.set()
        assert release.wait(15)
        return prepare(*args)

    def fail_second_worker(thread):
        if thread.name == "tool-profile-prepare":
            starts.append(thread)
            if len(starts) == 2:
                raise RuntimeError("queued worker startup failed")
        return start(thread)

    monkeypatch.setattr(loading, "prepare_tool_profiles", blocked)
    monkeypatch.setattr(loading.threading.Thread, "start", fail_second_worker)
    before = f.viewer.capture_tool_display()
    summary = f.ws.tool_library_summary.text
    f.library.apply()
    assert entered.wait(2)
    try:
        f.library._edit(f.chosen)
        assert not context.pending
        f.library.apply()
        assert context.pending and f.ws.tool_profile_loads.pending is not None
    finally:
        release.set()
    wait(f)
    assert len(starts) == 2 and not context.pending
    assert "queued worker startup failed" in f.library.status.text
    assert not f.library.apply_button.disabled
    assert f.viewer.library_tool_table_mm is before["library"]
    assert f.viewer._tool_meshes is before["meshes"]
    assert f.ws.tool_library_summary.text == summary
    assert f.ws.active_section == "Profiles"


def test_newer_generic_tool_request_supersedes_context_without_status_or_focus_theft(assignment, monkeypatch):
    f = assignment
    context = open_assignment(f)
    entered, release = threading.Event(), threading.Event()
    prepare = loading.prepare_tool_profiles

    def blocked(*args):
        entered.set()
        assert release.wait(15)
        return prepare(*args)

    monkeypatch.setattr(loading, "prepare_tool_profiles", blocked)
    f.library.apply()
    assert entered.wait(2)
    try:
        f.ws.request_tool_profile(f.chosen, slot=4)
        assert not context.active
        f.ws.select("Position")
    finally:
        release.set()
    wait(f)
    assert set(f.viewer.library_tool_table_mm) == {1, 4}
    assert f.ws.active_section == "Position"
    assert "T4" in f.ws.profile_status.text
    f.write.assert_called_once()  # Only the deliberately requested generic load writes preferences.


def test_success_retires_prior_simulation_results_without_recalculating(assignment, monkeypatch):
    from carveracontroller.machine.geometry_changes import capture_context, digest_context

    f = assignment
    panel = f.ws.simulation_panel
    previous = capture_context(f.viewer, f.program, verify_assets=False)
    monkeypatch.setattr(panel, "rest_context", previous)
    monkeypatch.setattr(panel, "clearance_inputs", previous)
    monkeypatch.setattr(panel, "clearance_identity", (previous["program"], digest_context(previous)))
    monkeypatch.setattr(panel, "clearance_stale", False)
    hide, calculate = Mock(), Mock()
    monkeypatch.setattr(panel, "hide_single_residual", hide)
    monkeypatch.setattr(panel, "start", calculate)
    open_assignment(f)
    f.library.apply()
    wait(f)
    assert panel.clearance_stale and panel.clearance_card.inspect.disabled
    assert panel.clearance_card.source_action.disabled
    hide.assert_called()
    calculate.assert_not_called()


def test_cancelled_tool_review_clears_contextual_button_without_refreshing_rows(assignment):
    f = assignment
    comparison = f.ws.tool_comparison
    context = f.ws.simulation_panel.review_simulation_tool(3)
    rows, signature = comparison.rows, comparison._signature
    assert comparison.library_action.text == "Choose cutter for T3"
    f.ws.select("Position")
    assert not context.active
    assert comparison.rows is rows and comparison._signature == signature
    assert comparison.library_action.text == "Edit cutter library"
    f.ws.select("Setup")
    f.ws.setup_tasks.show("Tools")
    comparison.library_action.dispatch("on_release")
    assert f.library.simulation_assignment is None
    assert set(f.viewer.library_tool_table_mm) == {1}
    f.write.assert_not_called()
    f.commands.assert_not_called()


def test_older_retirement_does_not_clear_newer_contextual_button(assignment):
    f = assignment
    first = open_assignment(f)
    second = open_assignment(f)
    assert not first.active and second.active
    first.cancel()
    assert f.ws.tool_comparison.library_action.text == "Choose cutter for T3"
    assert f.library.simulation_assignment is second and not f.library.apply_button.disabled
    f.library.apply()
    wait(f)
    until(lambda: not second.active, "Return did not finish")
    assert f.ws.tool_comparison.library_action.text == "Edit cutter library"


def test_stale_contextual_caption_never_falls_through_to_generic_library(assignment, monkeypatch):
    f = assignment
    context = f.ws.simulation_panel.review_simulation_tool(3)
    context.cancel()
    comparison = f.ws.tool_comparison
    comparison.library_action.text = "Choose cutter for T3"
    generic = Mock()
    monkeypatch.setattr(f.ws, "_open_profiles", generic)
    comparison.library_action.dispatch("on_release")
    generic.assert_not_called()
    assert comparison.library_action.text == "Edit cutter library"
    assert "review ended" in comparison.detail.text
    assert set(f.viewer.library_tool_table_mm) == {1}
