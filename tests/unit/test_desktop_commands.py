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
