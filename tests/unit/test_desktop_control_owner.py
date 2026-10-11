from copy import deepcopy

import pytest

from carveracontroller.machine.desktop_control_owner import DesktopControlOwner, reported_state


def snapshot():
    return {
        "ready": True,
        "running": True,
        "last_machine_snapshot_age_s": 0.2,
        "last_machine_snapshot": {
            "connection_id": "connection-one",
            "connected": True,
            "unknown_outcome": False,
            "status_age_ms": 200,
            "status": {"state": "Hold"},
        },
    }


def test_exact_owner_binding_never_adopts_a_new_connection_or_falls_back_on_loss():
    owner = DesktopControlOwner()
    state = snapshot()
    owner.claim("child-one", state, gui_busy=False)
    assert owner.matches("child-one", state) and owner.backend_selected
    for child, changed in (
        ("child-two", state),
        ("child-one", {**state, "ready": False}),
        ("child-one", {**state, "running": False}),
        (
            "child-one",
            {**state, "last_machine_snapshot": {**state["last_machine_snapshot"], "connection_id": "connection-two"}},
        ),
    ):
        assert not owner.matches(child, changed) and owner.backend_selected
    assert owner.binding.connection_id == "connection-one"


@pytest.mark.parametrize(
    "change", ["gui", "not_ready", "not_running", "disconnected", "missing_id", "malformed_snapshot"]
)
def test_claim_requires_an_explicit_current_connected_child_and_no_existing_gui_owner(change):
    owner, state = DesktopControlOwner(), snapshot()
    if change == "not_ready":
        state["ready"] = False
    elif change == "not_running":
        state["running"] = False
    elif change == "disconnected":
        state["last_machine_snapshot"]["connected"] = False
    elif change == "missing_id":
        state["last_machine_snapshot"].pop("connection_id")
    elif change == "malformed_snapshot":
        state["last_machine_snapshot"] = None
    with pytest.raises(ValueError):
        owner.claim("child-one", state, gui_busy=change == "gui")
    assert owner.binding is None


def test_explicit_release_requires_original_child_disconnection_or_completed_shutdown():
    owner, state = DesktopControlOwner(), snapshot()
    owner.claim("child-one", state, gui_busy=False)
    with pytest.raises(ValueError):
        owner.release("child-one", state)
    with pytest.raises(ValueError):
        owner.release("child-two", {"running": False})
    disconnected = deepcopy(state)
    disconnected["last_machine_snapshot"]["connected"] = False
    disconnected["last_machine_snapshot"]["unknown_outcome"] = True
    with pytest.raises(ValueError):
        owner.release("child-one", disconnected)
    disconnected["last_machine_snapshot"]["unknown_outcome"] = False
    owner.release("child-one", disconnected)
    assert not owner.backend_selected
    owner.claim("child-one", state, gui_busy=False)
    owner.release("child-one", {"running": False})
    assert not owner.backend_selected


@pytest.mark.parametrize(
    "age,report_age",
    [(None, 1), (True, 1), (float("nan"), 1), (-1, 1), (0.7, 200), (0, None), (0, -1), (0, float("inf"))],
)
def test_missing_nonfinite_or_old_report_age_cannot_inherit_gui_state(age, report_age):
    state = snapshot()
    state["last_machine_snapshot_age_s"] = age
    state["last_machine_snapshot"]["status_age_ms"] = report_age
    assert reported_state(state) is None


def test_report_age_uses_both_clocks_without_mutating_the_original_snapshot():
    state = snapshot()
    before = deepcopy(state)
    assert reported_state(state) == "Hold" and state == before
    state["last_machine_snapshot"]["status"] = {"state": "Unknown"}
    assert reported_state(state) is None
