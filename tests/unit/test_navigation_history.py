from types import SimpleNamespace

import pytest

from carveracontroller.desktop_operations import OperationPanel
from carveracontroller.machine.navigation_history import NavigationHistory
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.simulation_bookmarks import VIEW_FIELDS


def test_bounded_history_branches_copies_and_commits_only_after_restore():
    history = NavigationHistory(3)
    point = {"line": 1, "view": {"zoom": 2}}
    history.record(point)
    point["view"]["zoom"] = 99
    assert history.items[0]["view"]["zoom"] == 2
    for line in (2, 3, 4):
        history.record({"line": line})
    assert [p["line"] for p in history.items] == [2, 3, 4]
    index, candidate = history.candidate(-1)
    candidate["line"] = 99
    assert history.index == 2 and history.items[1]["line"] == 3
    history.commit(index)
    assert history.can_back and history.can_forward
    history.record({"line": 5})
    assert [p["line"] for p in history.items] == [2, 3, 5]
    assert not history.can_forward
    with pytest.raises(ValueError):
        history.commit(0)
    history.clear()
    assert not history.can_back and history.candidate(1) is None


@pytest.fixture
def panel(monkeypatch):
    calls = []
    viewer = SimpleNamespace(**dict.fromkeys(VIEW_FIELDS, 1.0))
    viewer._ortho_projection = False
    viewer.set_distance_by_lineidx = lambda *args: calls.append(("seek", args))
    viewer.update_proj = lambda: calls.append(("projection",))
    viewer.update_view = lambda: calls.append(("view",))
    viewer.canvas = SimpleNamespace(ask_update=lambda: calls.append(("redraw",)))
    workspace = SimpleNamespace(
        machine=SimpleNamespace(gcode_viewer=viewer),
        setup="A",
        enter_preview=lambda: calls.append(("preview",)),
    )
    monkeypatch.setattr(
        "carveracontroller.desktop_bookmarks.capture_bookmark_context", lambda ws: ("machine", ws.setup)
    )
    item = OperationPanel(workspace)
    item.generation = 1
    item._loaded(1, ProgramOperations.from_text("G21 G90 G17 G94\nG0 X0 Y0 Z0\nG1 X10 F100\nG1 X20"), None)
    return item, viewer, calls


def test_back_forward_restore_selection_and_departure_framing(panel):
    item, viewer, calls = panel
    item.inspect_line(2, seek=True)
    assert calls[:2] == [("preview",), ("seek", (2, 0))]
    viewer.m_xRot = 25
    item.inspect_line(3, seek=True)
    viewer.m_xRot = 45
    item.navigate_history(-1)
    assert item.selected_line == 2 and viewer.m_xRot == 25
    assert item.back_action.disabled
    assert not item.forward_action.disabled
    item.navigate_history(1)
    assert item.selected_line == 3 and viewer.m_xRot == 45
    item.navigate_history(-1)
    item.inspect_line(4, seek=True)
    assert item.forward_action.disabled
    assert [point["line"] for point in item.history.items] == [2, 4]
    assert all(call[0] in ("preview", "seek", "projection", "view", "redraw") for call in calls)
    item.load(None)
    assert item.history.items == [] and item.back_action.disabled and item.forward_action.disabled


def test_changed_setup_refuses_navigation_without_seek_or_cursor_commit(panel):
    item, viewer, calls = panel
    item.inspect_line(2, seek=True)
    item.inspect_line(3, seek=True)
    item.workspace.setup = "B"
    before = list(calls)
    item.navigate_history(-1)
    assert calls == before and item.selected_line == 3 and item.history.index == 1
    assert "setup changed" in item.history_note.text


def test_playback_does_not_fill_history(panel):
    item, _, _ = panel
    item.workspace.active_section = "Job"
    item.inspect_line(2, seek=True)
    item.observe_preview_line(3)
    assert len(item.history.items) == 1
