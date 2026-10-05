from carveracontroller.desktop_commands import Command, search_commands


def test_search_requires_all_words_and_prefers_title():
    actions = [
        Command("a", "Tool library", "Manage profiles", lambda: None, "cutter"),
        Command("b", "Profiles", "Includes tool library", lambda: None),
    ]
    assert [a.id for a in search_commands(actions, "tool library")] == ["a", "b"]
    assert search_commands(actions, "tool missing") == []
    assert search_commands(actions, "CUTTER")[0].id == "a"


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
