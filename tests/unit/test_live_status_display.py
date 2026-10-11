from copy import deepcopy

import pytest

from carveracontroller.machine.live_status_display import live_status_display
from carveracontroller.machine.sensor_run_recording import RunEvidence, parse_numeric_fields


def context(frame, age=0.1):
    state, fields = parse_numeric_fields(frame, status=True)
    evidence = RunEvidence()
    evidence.observe(frame, state, fields, 10)
    return evidence.snapshot(10 + age)


FRAME = "<Idle|MPos:1,2,3,90|WPos:4,5,6,45|C:0,4,0,1|S:12000,12000,100|F:100,200,80|T:2,30|G:0>"


def test_current_packet_normalized_values_and_real_zero_are_retained():
    display = live_status_display(context(FRAME.replace("S:12000,12000", "S:0,0")), connected=True)
    assert display.fresh and display.spindle_rpm == 0 and display.spindle_target_rpm == 0
    assert display.feed_mm_min == 100 and display.feed_override_percent == 80
    assert display.tool == 2 and display.tool_offset_mm == 30 and display.wcs == 0
    assert display.machine_position == (1, 2, 3, 90)


def test_inch_packet_is_converted_once_and_rotary_remains_degrees():
    display = live_status_display(context(FRAME.replace("C:0,4,0,1", "C:0,4,1,1")), connected=True)
    assert display.machine_position == pytest.approx((25.4, 50.8, 76.2, 90))
    assert display.work_position == pytest.approx((101.6, 127, 152.4, 45))
    assert display.feed_mm_min == 2540
    assert display.tool_offset_mm == 30  # Firmware TLO is mm regardless of coordinate mode.


@pytest.mark.parametrize("age", [None, -1, 0.81, float("nan"), float("inf"), True, 10**400])
def test_invalid_or_stale_report_cannot_retain_live_values(age):
    packet = context(FRAME)
    packet["arrival_age_s"] = age
    display = live_status_display(packet, connected=True)
    assert not display.fresh
    assert display.spindle_rpm is None and display.machine_position is None and display.tool is None


@pytest.mark.parametrize("connected,reacquiring", [(False, False), (True, True)])
def test_disconnection_and_reacquisition_withhold_prior_report(connected, reacquiring):
    assert not live_status_display(context(FRAME), connected=connected, reacquiring=reacquiring).fresh


def test_missing_fields_in_latest_packet_cannot_inherit_prior_values():
    evidence = RunEvidence()
    for frame in (FRAME, "<Idle|MPos:2,3,4|WPos:5,6,7|C:0,4,0,1>"):
        state, fields = parse_numeric_fields(frame, status=True)
        evidence.observe(frame, state, fields, 10)
    display = live_status_display(evidence.snapshot(10.1), connected=True)
    assert display.fresh and display.machine_position == (2, 3, 4)
    assert display.spindle_rpm is None and display.feed_mm_min is None
    assert display.tool is None and display.tool_offset_mm is None and display.wcs is None


def test_source_validity_withholds_numeric_placeholders():
    packet = context(FRAME)
    packet["field_validity"].update(spindle_status=False, tool_status=False)
    display = live_status_display(packet, connected=True)
    assert display.spindle_rpm is None and display.spindle_target_rpm is None
    assert display.tool is None and display.tool_offset_mm is None
    assert display.feed_mm_min == 100


def test_unknown_units_withhold_positions_and_feed_but_not_rpm():
    display = live_status_display(context(FRAME.replace("|C:0,4,0,1", "")), connected=True)
    assert display.machine_position is None and display.work_position is None and display.feed_mm_min is None
    assert display.spindle_rpm == 12000


def test_display_does_not_mutate_recorded_context():
    packet = context(FRAME)
    original = deepcopy(packet)
    live_status_display(packet, connected=True)
    assert packet == original
