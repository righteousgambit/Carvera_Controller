"""Native live metrics must use the latest qualified packet, including its units."""

import time

import pytest

from carveracontroller.CNC import CNC
from carveracontroller.machine.sensor_run_recording import RunEvidence, parse_numeric_fields
from tests.integration.conftest import apply_machine_state

FRAME = "<Idle|MPos:1,2,3,90|WPos:4,5,6,45|C:0,4,0,1|S:12000,12000,100|F:100,200,80|T:2,30|G:0>"


def packet(frame=FRAME, age=0.1):
    state, fields = parse_numeric_fields(frame, status=True)
    evidence = RunEvidence()
    evidence.observe(frame, state, fields, 10)
    return evidence.snapshot(10 + age)


@pytest.fixture
def live_workspace(kivy_app, connected_idle_state, monkeypatch):
    apply_machine_state(kivy_app)
    ws = kivy_app.root.desktop_workspace
    monkeypatch.setattr(ws.machine.controller, "_status_reacquire_started_at", None)
    return ws


def show(ws, monkeypatch, context):
    monkeypatch.setattr(ws.machine.controller, "sensor_context_snapshot", lambda: context)
    ws.refresh(0)


def test_inch_report_is_displayed_in_normalized_workspace_units(live_workspace, monkeypatch):
    ws = live_workspace
    show(ws, monkeypatch, packet(FRAME.replace("C:0,4,0,1", "C:0,4,1,1")))
    assert ws.position_values["X"].text == "101.600"
    assert ws.machine_values["X"].text == "Machine 25.400"
    assert ws.feed_metric.value.text == "2,540"
    assert ws.tool_metric.detail.text == "Length offset 30.000 mm"


@pytest.mark.parametrize("kind", ["partial", "invalid", "stale", "reacquiring", "unknown_units"])
def test_unavailable_fields_never_display_previous_global_values(live_workspace, monkeypatch, kind):
    ws = live_workspace
    for key, value in {"curspindle": 9999, "curfeed": 999, "tool": 7, "tlo": 999, "wx": 999}.items():
        monkeypatch.setitem(CNC.vars, key, value)
    context = packet()
    if kind == "partial":
        context = packet("<Idle|MPos:2,3,4|WPos:5,6,7|C:0,4,0,1>")
    elif kind == "invalid":
        context["field_validity"].update(spindle_status=False, tool_status=False)
    elif kind == "stale":
        context["arrival_age_s"] = 0.81
    elif kind == "reacquiring":
        monkeypatch.setattr(ws.machine.controller, "stream", object())
        monkeypatch.setattr(ws.machine.controller, "_status_reacquire_started_at", 10)
    else:
        context = packet(FRAME.replace("|C:0,4,0,1", ""))
    show(ws, monkeypatch, context)
    if kind != "unknown_units":
        assert ws.rpm_metric.value.text == "Unknown"
        assert ws.tool_metric.value.text == "Unknown"
    if kind != "invalid":
        assert ws.feed_metric.value.text == "Unknown"
    if kind in ("stale", "reacquiring", "unknown_units"):
        assert ws.position_values["X"].text == "Unknown"
        assert ws.machine_values["X"].text == "Machine Unknown"


@pytest.mark.parametrize("eligible", [False, True])
def test_monitor_display_requires_recipe_eligibility(live_workspace, monkeypatch, eligible):
    from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample

    ws = live_workspace
    monitor = AdaptiveMonitor()
    now = time.monotonic()
    monitor.observe(Sample(now, "Run", 11900, 12000, 0.5, 600, 100, (0, 0, 0)))
    state = dict(monitor.snapshot(now))
    state.update(
        baseline={"rpm": 12000, "samples": 100, "rpm_range": 10},
        persistence=None,
        proposed_override=85,
        proposal_eligible=eligible,
        proposal_blocker=None if eligible else "qualified cutter recipe required",
    )
    monkeypatch.setattr(ws, "monitor_evidence", lambda: (state, [], True))
    ws._refresh_monitor(True)
    assert ws.monitor_feed.value.text == ("85%" if eligible else "—")
    assert ("Shadow proposal" if eligible else "qualified cutter recipe required") in ws.monitor_feed.detail.text
