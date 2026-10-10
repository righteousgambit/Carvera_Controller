import copy

import pytest

from carveracontroller.headless.telemetry import parse_status
from carveracontroller.machine.backend_live_report import backend_live_report, wcs_name
from carveracontroller.machine.desktop_control_owner import DesktopControlOwner


def state():
    return {
        "ready": True,
        "running": True,
        "last_machine_snapshot_age_s": 0.1,
        "last_machine_snapshot": {
            "connected": True,
            "connection_id": "connection",
            "unknown_outcome": False,
            "transfer_active": False,
            "status_age_ms": 100,
            "status": parse_status(
                "<Run|MPos:-190,-125,-100,0,0|WPos:1,2,3,0,0|C:1,4,0,1|R:90|G:0|S:11950,12000,100|F:600,600,80|T:2,47.5>"
            ),
        },
    }


def observe(snapshot=None, *, now=10, session="session", profile=None, owner=None):
    snapshot = state() if snapshot is None else snapshot
    if owner is None:
        owner = DesktopControlOwner()
        owner.claim("session", state(), gui_busy=False)
    return backend_live_report(owner, session, snapshot, {"model": "C1"} if profile is None else profile, now)


def test_bound_complete_backend_pose_uses_one_normalized_packet_and_preserves_unknown_tlo_reference():
    snapshot = state()
    original = copy.deepcopy(snapshot)
    view = observe(snapshot)
    assert view.current and view.pose is not None
    assert view.pose.machine_mm == (-190, -125, -100) and view.pose.work_mm == (1, 2, 3)
    assert view.pose.rotation_deg == 90 and view.pose.wcs_index == 0 and view.pose.rotary_deg == 0
    assert view.pose.tool == 2 and view.pose.tool_length_mm is None
    assert view.raw_tool_offset == 47.5 and view.report_age_s == pytest.approx(0.2)
    assert view.pose.timestamp == pytest.approx(9.8)
    assert view.pose.fresh(10) and not view.pose.fresh(10.7)
    assert view.session_id == "session" and view.connection_id == "connection"
    view.status["machine_position"]["x"] = 999
    assert snapshot == original


@pytest.mark.parametrize(
    "change",
    [
        "session",
        "connection",
        "ready",
        "running",
        "connected",
        "unknown",
        "transfer",
        "clock",
        "stale",
        "future",
        "model",
        "profile",
    ],
)
def test_replaced_unbound_unknown_or_stale_backend_never_projects_a_current_view(change):
    snapshot, session, profile, now = state(), "session", {"model": "C1"}, 10
    if change == "session":
        session = "replacement"
    elif change == "connection":
        snapshot["last_machine_snapshot"]["connection_id"] = "replacement"
    elif change in ("ready", "running"):
        snapshot[change] = False
    elif change == "connected":
        snapshot["last_machine_snapshot"]["connected"] = False
    elif change in ("unknown", "transfer"):
        snapshot["last_machine_snapshot"]["unknown_outcome" if change == "unknown" else "transfer_active"] = True
    elif change == "clock":
        snapshot["last_machine_snapshot_age_s"] = True
    elif change == "stale":
        snapshot["last_machine_snapshot_age_s"] = 1
    elif change == "future":
        now = 0.1
    elif change == "model":
        snapshot["last_machine_snapshot"]["status"]["machine_model"] = 0
    else:
        profile = {"model": "CA1"}
    view = observe(snapshot, now=now, session=session, profile=profile)
    assert not view.current and view.pose is None and view.raw_tool_offset is None and view.reason


@pytest.mark.parametrize("change", ["xyz", "work", "rotation", "rotary", "units", "wcs", "huge"])
def test_partial_pose_keeps_current_independent_metrics_without_borrowing_prior_coordinates(change):
    snapshot = state()
    status = snapshot["last_machine_snapshot"]["status"]
    if change == "xyz":
        status["machine_position"]["x"] = None
    elif change == "work":
        status["work_position"] = None
    elif change == "rotation":
        status["rotation_degrees"] = None
    elif change == "rotary":
        status["machine_position"]["a"] = None
    elif change == "units":
        status["linear_units"] = None
    elif change == "wcs":
        status["active_wcs"] = 0.5
    else:
        status["machine_position"]["x"] = 1e12
    view = observe(snapshot)
    assert view.current and view.pose is None and view.reason
    assert view.status["spindle_rpm"] == 11950 and view.raw_tool_offset == 47.5


def test_cached_receipt_age_does_not_restart_when_the_view_is_read_again():
    snapshot = state()
    first = observe(snapshot, now=10)
    snapshot["last_machine_snapshot_age_s"] = 0.2
    second = observe(snapshot, now=10.1)
    assert second.pose.timestamp == pytest.approx(first.pose.timestamp)
    snapshot["last_machine_snapshot_age_s"] = 1
    assert observe(snapshot, now=11).pose is None


def test_inch_linear_normalization_and_degrees_are_separate_from_reported_tool_offset():
    snapshot = state()
    snapshot["last_machine_snapshot"]["status"] = parse_status(
        "<Idle|MPos:1,2,3,45|WPos:4,5,6,45|C:1,4,1,1|R:0|G:8|T:3,47.5>"
    )
    view = observe(snapshot)
    assert view.pose.machine_mm == pytest.approx((25.4, 50.8, 76.2))
    assert view.pose.work_mm == pytest.approx((101.6, 127, 152.4))
    assert view.pose.rotary_deg == 45 and view.pose.wcs_index == 8
    assert view.raw_tool_offset == 47.5 and view.pose.tool_length_mm is None


@pytest.mark.parametrize("value", [None, True, -1, 0.5, float("nan"), float("inf"), 10**400])
def test_unknown_or_invalid_tool_number_does_not_become_a_visualized_cutter(value):
    snapshot = state()
    snapshot["last_machine_snapshot"]["status"]["tool"] = value
    assert observe(snapshot).pose.tool is None


@pytest.mark.parametrize(
    "index,label", [(0, "G54"), (5, "G59"), (6, "G59.1"), (8, "G59.3"), (9, "Unknown"), (True, "Unknown")]
)
def test_wcs_names_follow_the_actual_firmware_indexes(index, label):
    assert wcs_name(index) == label


def test_backend_camera_owner_is_additive_and_preserves_legacy_gui_references():
    from dataclasses import replace

    from carveracontroller.machine.camera_calibration_file import CalibrationReference
    from tests.unit.test_camera_calibration_file import reference

    legacy = reference()
    assert "backend_owner" not in legacy.to_dict()
    assert CalibrationReference.from_dict(legacy.to_dict()).backend_owner is None
    captured = replace(legacy, backend_owner=("session", "connection"))
    decoded = CalibrationReference.from_dict(captured.to_dict())
    assert decoded.backend_owner == ("session", "connection")
    assert decoded.machine_mm == legacy.machine_mm
    assert decoded.frame.jpeg == legacy.frame.jpeg
    assert decoded.to_dict()["timing_qualification"] == legacy.to_dict()["timing_qualification"]


@pytest.mark.parametrize(
    "owner",
    [
        None,
        {},
        [],
        {"session_id": "session"},
        {"session_id": "session", "connection_id": "connection", "extra": 1},
        {"session_id": "", "connection_id": "connection"},
        {"session_id": "session", "connection_id": "x" * 101},
        {"session_id": True, "connection_id": "connection"},
        {"session_id": "session", "connection_id": "bad\nidentity"},
        {"session_id": "séssion", "connection_id": "connection"},
    ],
)
def test_present_malformed_backend_camera_owner_is_rejected_without_legacy_fallback(owner):
    from carveracontroller.machine.camera_calibration_file import CalibrationReference
    from tests.unit.test_camera_calibration_file import reference

    data = reference().to_dict()
    data["backend_owner"] = owner
    with pytest.raises(ValueError, match="backend reference owner"):
        CalibrationReference.from_dict(data)
