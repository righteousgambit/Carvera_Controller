import pytest

from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_comparison import compare_tools
from carveracontroller.machine.tool_history import TloReport, ToolHistory


def pose(timestamp=10):
    return ObservedPose(timestamp, "Idle", (0, 0, 0), (0, 0, 0), 2, 50.48)


def test_unit_correct_comparison_keeps_tlo_and_nominal_geometry_separate():
    history = ToolHistory()
    history.add_report(2, TloReport((49, 49.01), 0.01, 49.01, 123))
    library = {2: ToolDefinition(2, diameter=6.35, length=76.2, stickout=31)}
    cam = {2: ToolDefinition(2, diameter=0.25)}
    before = history.to_json()
    (row,) = compare_tools(library, cam, history, pose(), connected=True, now=10.1, cam_scale=25.4)
    assert row.cam_diameter_mm == pytest.approx(6.35)
    assert not row.diameter_conflict
    assert row.observed_tlo_mm == 50.48
    assert row.historical_tlo_mm == 49.01
    assert row.stickout_mm == 31
    assert history.to_json() == before


@pytest.mark.parametrize(
    "connected,now,state",
    [(False, 10.1, "disconnected"), (True, 11, "stale or unavailable"), (True, 9, "stale or unavailable")],
)
def test_stale_disconnected_and_future_packets_never_supply_active_length(connected, now, state):
    (row,) = compare_tools({}, {}, ToolHistory(), pose(), connected=connected, now=now)
    assert row.observed_tlo_mm is None
    assert not row.reported_active
    assert row.report_state == state


def test_union_discrepancies_and_missing_data_do_not_create_history():
    history = ToolHistory()
    rows = compare_tools(
        {1: ToolDefinition(1, diameter=6), 3: ToolDefinition(3, diameter=float("nan"))},
        {1: ToolDefinition(1, diameter=4), 4: ToolDefinition(4, diameter=2)},
        history,
        pose(),
        connected=True,
        now=10,
    )
    assert [r.number for r in rows] == [1, 2, 3, 4]
    assert rows[0].diameter_conflict
    assert rows[2].library_diameter_mm is None
    assert rows[3].cam_diameter_mm == 2
    assert history.tools() == []
