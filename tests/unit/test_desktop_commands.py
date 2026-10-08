import pytest

from carveracontroller.desktop_commands import Command, search_command_page, search_commands


def test_search_requires_all_words_and_prefers_title():
    actions = [
        Command("a", "Tool library", "Manage profiles", lambda: None, "cutter"),
        Command("b", "Profiles", "Includes tool library", lambda: None),
    ]
    assert [a.id for a in search_commands(actions, "tool library")] == ["a", "b"]
    assert search_commands(actions, "tool missing") == []
    assert search_commands(actions, "CUTTER")[0].id == "a"


def test_structured_tool_and_line_search_does_not_match_prefixes():
    entries = [
        Command("a", "Operation", "T1 lines 2–9", lambda: None, "tool:T1 line:2"),
        Command("b", "Operation", "T10 lines 20–29", lambda: None, "tool:T10 line:20"),
    ]
    for query in ("T1", "tool:T1", "line:2"):
        assert search_commands(entries, query) == [entries[0]]


@pytest.mark.parametrize("query", ['"Feature 1001"', "'FEATURE 1001'", '"Feature 1001', "operation:1002"])
def test_precise_search_disambiguates_name_from_operation_and_source_line_numbers(query):
    entries = [
        Command("wrong-operation", "Operation 1001 · Feature 1000", "lines 2001–2002", lambda: None, "operation:1001"),
        Command("target", "Operation 1002 · Feature 1001", "lines 2003–2004", lambda: None, "operation:1002"),
        Command("wrong-line", "Operation 501 · Feature 0500", "lines 1001–1002", lambda: None, "operation:501"),
        Command("prefix", "Operation 10020 · Feature 10010", "", lambda: None, "operation:10020"),
    ]
    expected = [entries[1]]
    # Quoted text is a contiguous phrase; operation:N is a whole exact token.
    assert search_commands(entries, query) == expected
    page, count = search_command_page(iter(entries), query, limit=1)
    assert page == expected[:1] and count == len(expected)


def test_search_preserves_apostrophes_backslashes_and_combines_phrase_with_exact_tool():
    entries = [
        Command("a", "O'Brien tool", r"C:\tools\ball nose", lambda: None, "T1"),
        Command("b", "O'Brien tool", r"C:\tools\ball nose", lambda: None, "T10"),
    ]
    for query in ["O'Brien T1", r'C:\tools\ "ball nose" T1', '"" T1']:
        assert search_commands(entries, query) == [entries[0]]
        assert search_command_page(entries, query) == ([entries[0]], 1)


def test_invocation_rechecks_current_machine_state():
    state = {"reason": ""}
    calls = []
    command = Command(
        "probe", "Probe", "Find center", lambda: calls.append("open"), availability=lambda: state["reason"]
    )
    assert command.availability() == ""
    state["reason"] = "Machine running"
    assert not command.invoke()
    assert calls == []
    state["reason"] = ""
    assert command.invoke()
    assert calls == ["open"]


def test_job_entity_search_routes_exact_operation_and_rejects_replaced_analysis():
    from types import SimpleNamespace

    from carveracontroller.desktop_commands import job_operation_commands
    from carveracontroller.machine.program_operations import ProgramOperations

    program = ProgramOperations.from_text(
        "G21 G90 G54\n(OPERATION: Rough pocket)\nT1 M6\nG0 X0 Y0 Z5\nG1 Z-1 F100\n"
        "(OPERATION: Finish wall)\nT2 M6\nG1 X10 F150\nM30\n"
    )
    calls = []
    panel = SimpleNamespace(program=program, select=lambda op: calls.append(op.id))
    workspace = SimpleNamespace(
        operation_panel=panel,
        select=lambda page: calls.append(page),
        program_tasks=SimpleNamespace(choose=lambda task: calls.append(task)),
    )
    entries = job_operation_commands(workspace)
    match = search_commands(entries, "finish T2")[0]
    operation = next(op for op in program.operations if op.name == "Finish wall")
    assert program.file_hash in match.id
    assert match.invoke()
    assert calls == ["Job", "Operations", operation.id]
    assert search_commands(entries, f"line:{operation.start_line}") == [match]
    assert search_commands(entries, f"operation:{program.operations.index(operation) + 1}") == [match]
    # Even identical bytes re-analyzed are a different navigation snapshot.
    panel.program = ProgramOperations.from_text("\n".join(program.lines))
    assert not match.invoke()
    assert calls == ["Job", "Operations", operation.id]
    panel.program = None
    assert job_operation_commands(workspace) == []


def test_palette_task_routes_and_pose_actions_are_local_and_capture_each_target():
    from types import SimpleNamespace

    from carveracontroller.desktop_commands import workspace_commands

    calls = []
    noop = lambda: None
    machine = SimpleNamespace(
        gcode_viewer=SimpleNamespace(restore_default_view=noop),
        open_probing_popup=noop,
        open_facing_popup=noop,
        open_cmm_workbench_popup=noop,
    )
    workspace = SimpleNamespace(
        app=SimpleNamespace(state="N/A", is_community_firmware=False),
        machine=machine,
        tool_comparison=SimpleNamespace(focus=noop),
        telemetry_diagnostics=SimpleNamespace(export=noop, _exporting=False),
        _choose_program=noop,
        close_local_preview=noop,
        can_close_local_preview=lambda: False,
        _open_profiles=noop,
        _machine_setup=noop,
        _workholding_setup=noop,
        _toggle_job_camera=noop,
        section_names={"Preview": "Scene"},
        select=lambda section: calls.append(("section", section)),
        program_tasks=SimpleNamespace(choose=lambda task: calls.append(("task", task))),
        set_pose_mode=lambda mode: calls.append(("pose", mode)),
    )
    commands = {command.id: command for command in workspace_commands(workspace)}
    for task in ("Operations", "Simulation", "Run record", "Job package", "View & playback"):
        key = "program.task." + task.casefold().replace(" ", "-")
        assert commands[key].invoke()
        assert calls[-2:] == [("section", "Job"), ("task", task)]
    for mode in ("Live", "Preview", "Compare"):
        assert commands["view.pose." + mode.casefold()].invoke()
        assert calls[-1] == ("pose", mode)
    assert not commands["setup.probe"].invoke()
    assert search_commands(commands.values(), "rest material")[0].id == "program.task.simulation"
    assert search_commands(commands.values(), "portable archive")[0].id == "program.task.job-package"


def test_component_routes_capture_each_target_and_explosion_rechecks_view_mode():
    from types import SimpleNamespace

    from carveracontroller.desktop_commands import workspace_commands
    from carveracontroller.machine.scene_inspection import COMPONENT_TITLES

    calls = []
    noop = lambda: None
    viewer = SimpleNamespace(restore_default_view=noop, pose_mode="Preview")
    workspace = SimpleNamespace(
        app=SimpleNamespace(state="N/A", is_community_firmware=False),
        machine=SimpleNamespace(
            gcode_viewer=viewer, open_probing_popup=noop, open_facing_popup=noop, open_cmm_workbench_popup=noop
        ),
        tool_comparison=SimpleNamespace(focus=noop),
        telemetry_diagnostics=SimpleNamespace(export=noop, _exporting=False),
        _choose_program=noop,
        close_local_preview=noop,
        can_close_local_preview=lambda: False,
        _open_profiles=noop,
        _machine_setup=noop,
        _workholding_setup=noop,
        _toggle_job_camera=noop,
        section_names={"Preview": "Scene"},
        select=lambda page: calls.append(("page", page)),
        set_pose_mode=noop,
        object_inspector=SimpleNamespace(
            select=lambda key: calls.append(("component", key)),
            explode=lambda **kw: calls.append(("explode", kw["assembled"])),
        ),
    )
    commands = {command.id: command for command in workspace_commands(workspace)}
    for component in COMPONENT_TITLES:
        assert commands[f"scene.inspect.{component}"].invoke()
        assert calls[-1] == ("component", component)
    explode = commands["scene.explode"]
    assert explode.availability() == ""
    viewer.pose_mode = "Live"
    before = calls.copy()
    assert not explode.invoke()
    assert calls == before
    viewer.pose_mode = "Compare"
    assert not explode.invoke()
    viewer.pose_mode = "Preview"
    assert explode.invoke()
    assert calls[-2:] == [("page", "Scene"), ("explode", False)]
    viewer.pose_mode = "Live"
    assert commands["scene.reassemble"].invoke()
    assert calls[-2:] == [("page", "Scene"), ("explode", True)]
    assert search_commands(commands.values(), "inspect fixture")[0].id == "scene.inspect.fixture"


def test_inspection_search_exact_receipts_and_stale_store_guard(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from carveracontroller.desktop_commands import inspection_commands
    from carveracontroller.machine.surface_inspection import SurfaceInspectionStore
    from tests.unit.test_surface_inspection import feature, receipt

    store = SurfaceInspectionStore(tmp_path / "search.json")
    identity = feature(store)
    first = receipt(store, identity, 4.02, source_ref="gage-first")
    second = receipt(store, identity, 4.03, source_ref="gage-second")
    ws = SimpleNamespace(surface_inspection_store=store)
    calls = []
    monkeypatch.setattr(
        "carveracontroller.desktop_surface_inspection.open_surface_inspections",
        lambda workspace, feature_id, receipt_id=None: calls.append((workspace, feature_id, receipt_id)),
    )
    entries = inspection_commands(ws, store, store.features)
    assert len(entries) == 3
    command = search_commands(entries, f"receipt:{first}")[0]
    assert command.invoke() and calls == [(ws, identity, first)]
    assert search_commands(entries, "gage-second probe-A")[0].id == f"inspection.receipt.{second}"
    assert len(search_commands(entries, f"feature:{identity}")) == 3
    assert search_commands(entries, f"receipt:{first[:-1]}") == []
    before = store.path.read_bytes()
    receipt(store, identity, 4.04)
    assert not command.invoke() and len(calls) == 1
    assert store.path.read_bytes() != before
    assert inspection_commands(ws, store, store.features, lambda: True) == []
    ws.surface_inspection_store = SurfaceInspectionStore(store.path)
    assert not command.invoke()


def test_streamed_search_counts_all_results_keeps_bounded_page_and_cancels():
    import weakref

    from carveracontroller.desktop_commands import search_command_page

    alive = weakref.WeakSet()
    peak = 0

    def records():
        nonlocal peak
        for index in range(10000):
            command = Command(str(index), f"Receipt {index:05d}", "retained", lambda: None)
            alive.add(command)
            peak = max(peak, len(alive))
            yield command

    page, count = search_command_page(records(), "receipt")
    assert count == 10000 and [item.id for item in page] == [str(i) for i in range(40)]
    assert peak < 50
    assert search_command_page(records(), "receipt", cancelled=lambda: True) == ([], 0)
    entries = [
        Command("a", "Tool library", "profiles", lambda: None),
        Command("b", "Profiles", "tool library", lambda: None),
    ]
    assert search_command_page(iter(entries), "tool library") == (search_commands(entries, "tool library"), 2)


def test_recorded_alarm_search_routes_exact_identity_and_rejects_changed_observation():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from carveracontroller.desktop_commands import iter_alarm_commands, search_command_page
    from carveracontroller.machine.run_recording import RecordingReplay, RunRecording

    record = RunRecording()
    record.capture_status("Idle", {}, 10, 1000, 1)
    record.capture_status("Alarm:2", {"MPos": [1, 2, 3]}, 11, 1001, 1)
    record.capture_status("Alarm", {}, 12, 1002, 2)
    record.capture_status("Alarming text", {}, 13, 1003, 2)
    replay = RecordingReplay(record.export_bytes())
    panel = SimpleNamespace(replay=replay, seek_recorded_event=Mock())
    ws = SimpleNamespace(run_recording_panel=panel)
    events = replay.payload["events"]
    entries = list(iter_alarm_commands(ws, panel, replay, events))
    assert len(entries) == 2
    matches, count = search_command_page(entries, "alarm sequence:2 connection:1")
    assert count == 1 and matches == [entries[0]]
    assert not search_commands(entries, "sequence:20")
    assert entries[0].invoke()
    panel.seek_recorded_event.assert_called_once_with(replay, 1)
    panel.seek_recorded_event.reset_mock()
    events[1]["data"]["fields"]["MPos"][0] = 100
    assert not entries[0].invoke()
    panel.replay = RecordingReplay(record.export_bytes())
    assert not entries[1].invoke()
    panel.seek_recorded_event.assert_not_called()
    assert not list(iter_alarm_commands(ws, panel, replay, events, cancelled=lambda: True))


def test_recording_workflow_search_rechecks_buffer_replay_and_camera_selection():
    from types import SimpleNamespace
    from unittest.mock import Mock

    from carveracontroller.desktop_commands import recording_workflow_commands

    replay = SimpleNamespace(payload={"session_id": "record-one"})
    archive = SimpleNamespace(header={"recording_session_id": "record-one"})
    panel = SimpleNamespace(
        replay=replay,
        camera_archive=archive,
        busy=False,
        export=Mock(),
        import_recording=Mock(),
        export_camera=Mock(),
        camera_section=SimpleNamespace(expanded=False, toggle=Mock()),
    )
    controller = SimpleNamespace(run_recording=object())
    ws = SimpleNamespace(
        run_recording_panel=panel,
        machine=SimpleNamespace(controller=controller),
        select=Mock(),
        program_tasks=SimpleNamespace(choose=Mock()),
    )
    commands = recording_workflow_commands(ws)
    export = search_commands(commands, "export recording")[0]
    assert export.id == "recording.export" and export.invoke()
    panel.export.assert_called_once()
    ws.select.assert_called_with("Job")
    ws.program_tasks.choose.assert_called_with("Run record")
    panel.export.reset_mock()
    controller.run_recording = object()
    assert not export.invoke()
    panel.export.assert_not_called()
    export = search_commands(recording_workflow_commands(ws), "export camera")[0]
    assert export.invoke()
    panel.camera_section.toggle.dispatch.assert_called_once_with("on_release")
    panel.export_camera.assert_called_once()
    panel.export_camera.reset_mock()
    panel.camera_archive = SimpleNamespace(header={"recording_session_id": "record-two"})
    assert not export.invoke()
    panel.export_camera.assert_not_called()
    panel.replay = SimpleNamespace(payload={"session_id": "record-two"})
    assert not commands[0].invoke()


def test_exact_tool_search_clears_filter_and_rejects_changed_geometry_and_program():
    from copy import deepcopy
    from types import SimpleNamespace

    from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
    from carveracontroller.desktop_commands import iter_tool_commands
    from carveracontroller.machine.program_operations import ProgramOperations

    calls = []
    program = ProgramOperations.from_text("G21 G90\nT3 M6\nG0 Z5\nM30")
    library = {
        1: ToolDefinition(1, description="Aluminum rougher", vendor="Titan", product_id="TC67423"),
        10: ToolDefinition(10, description="Aluminum finisher"),
    }
    cam = {2: ToolDefinition(2, description="Ball nose")}
    viewer = SimpleNamespace(library_tool_table_mm=library, tool_table=cam)
    panel = SimpleNamespace(program=program)
    search = SimpleNamespace(text="hidden by old filter")
    workspace = SimpleNamespace(
        machine=SimpleNamespace(gcode_viewer=viewer),
        tool_comparison=SimpleNamespace(
            search=search,
            choose=lambda number: calls.append(("choose", number, search.text)),
            focus=lambda: calls.append("focus"),
        ),
    )
    entries = list(iter_tool_commands(workspace, panel, program, deepcopy(library), deepcopy(cam)))
    exact = search_commands(entries, "tool:T1")
    assert len(exact) == 1 and exact[0].id == "job.tool.1"
    assert search_commands(entries, "Titan TC67423") == exact
    assert "CAM geometry" in search_commands(entries, "T2")[0].detail
    assert "geometry missing" in search_commands(entries, "T3")[0].detail
    assert all("physical identity unverified" in entry.detail for entry in entries)
    assert exact[0].invoke()
    assert calls == [("choose", 1, ""), "focus"]
    viewer.tool_unit_scale = 25.4
    assert not exact[0].invoke()
    viewer.tool_unit_scale = 1.0
    library[1].diameter = 6.35
    assert not exact[0].invoke()  # In-place editing invalidates the captured geometry.
    assert len(calls) == 2
    panel.program = ProgramOperations.from_text("G21 G90\nM30")
    assert not search_commands(entries, "T2")[0].invoke()
    assert list(iter_tool_commands(workspace, panel, panel.program, library, cam, lambda: True)) == []
