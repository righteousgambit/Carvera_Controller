from carveracontroller.desktop_commands import Command, search_commands


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
