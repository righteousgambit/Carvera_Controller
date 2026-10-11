"""Tests for usage counters, probe profiles and saved positions."""

import pytest

from carveracontroller.machine.probe_profiles import ProbeKind, ProbeProfile, ProbeProfiles
from carveracontroller.machine.saved_positions import SavedPosition, SavedPositions
from carveracontroller.machine.usage_counters import (
    DEFAULT_SERVICE_INTERVALS,
    MAX_CREDITED_INTERVAL_SECONDS,
    ServiceInterval,
    UsageCounters,
)

# ------------------------------------------------------------ usage counters


def test_spindle_time_accumulates_only_while_turning():
    counters = UsageCounters()
    counters.observe(0.0, spindle_rpm=0.0)
    counters.observe(1.0, spindle_rpm=0.0)
    assert counters.spindle_seconds == 0.0

    counters.observe(2.0, spindle_rpm=12000.0)
    counters.observe(3.0, spindle_rpm=12000.0)
    assert counters.spindle_seconds == pytest.approx(1.0)


def test_a_single_observation_never_books_time_retrospectively():
    counters = UsageCounters()
    counters.observe(1000.0, spindle_rpm=12000.0)

    assert counters.spindle_seconds == 0.0


def test_long_gaps_are_not_credited():
    """A closed laptop must not book hours of runtime."""
    counters = UsageCounters()
    counters.observe(0.0, spindle_rpm=12000.0)
    counters.observe(MAX_CREDITED_INTERVAL_SECONDS + 60.0, spindle_rpm=12000.0)

    assert counters.spindle_seconds == 0.0


def test_reconnecting_does_not_credit_the_disconnected_gap():
    counters = UsageCounters()
    counters.observe(0.0, spindle_rpm=12000.0)
    counters.reset_session()
    counters.observe(5.0, spindle_rpm=12000.0)

    assert counters.spindle_seconds == 0.0


def test_tool_changes_count_transitions_not_observations():
    counters = UsageCounters()
    for tool in (1, 1, 1, 2, 2, 3):
        counters.observe(0.0, spindle_rpm=0.0, tool=tool)

    assert counters.tool_changes == 2


def test_spindle_hours_are_derived_from_seconds():
    counters = UsageCounters(spindle_seconds=7200.0)
    assert counters.spindle_hours == pytest.approx(2.0)


def test_counters_round_trip_through_json():
    counters = UsageCounters(spindle_seconds=123.5, tool_changes=4, probe_cycles=9)
    counters.start_job()
    counters.complete_job()

    restored = UsageCounters.from_json(counters.to_json())

    assert restored.spindle_seconds == pytest.approx(123.5)
    assert restored.tool_changes == 4
    assert restored.probe_cycles == 9
    assert restored.jobs_started == 1


@pytest.mark.parametrize("text", ["", "junk", "[]", "5"])
def test_unreadable_counters_load_as_zero(text):
    assert UsageCounters.from_json(text).spindle_seconds == 0.0


# --------------------------------------------------------- service intervals


def test_service_falls_due_and_repeats():
    interval = ServiceInterval("Chips", 8.0, "clear chips")

    assert not interval.is_due(UsageCounters(spindle_seconds=3600.0))
    assert interval.is_due(UsageCounters(spindle_seconds=8 * 3600.0))
    assert interval.is_due(UsageCounters(spindle_seconds=16 * 3600.0))


def test_due_in_counts_down_within_the_period():
    interval = ServiceInterval("Chips", 8.0, "clear chips")
    assert interval.due_in(UsageCounters(spindle_seconds=2 * 3600.0)) == pytest.approx(6.0)


def test_default_intervals_are_sane():
    assert DEFAULT_SERVICE_INTERVALS
    for interval in DEFAULT_SERVICE_INTERVALS:
        assert interval.every_hours > 0
        assert interval.task


# ------------------------------------------------------------ probe profiles


def test_a_profile_at_the_firmware_default_is_not_calibrated():
    assert not ProbeProfile("stock").is_calibrated
    assert ProbeProfile("v6", tip_diameter=1.642).is_calibrated


def test_first_profile_added_becomes_active():
    profiles = ProbeProfiles()
    profiles.add(ProbeProfile("mechanical", tip_diameter=1.642))

    assert profiles.active.name == "mechanical"


def test_activating_switches_the_configuration():
    profiles = ProbeProfiles()
    profiles.add(ProbeProfile("mechanical", tip_diameter=1.642))
    profiles.add(ProbeProfile("inductive", ProbeKind.INDUCTIVE, tip_diameter=2.980))

    assert profiles.activate("inductive").tip_diameter == pytest.approx(2.980)


def test_activating_something_unknown_leaves_the_active_profile_alone():
    profiles = ProbeProfiles()
    profiles.add(ProbeProfile("mechanical", tip_diameter=1.642))

    assert profiles.activate("nope").name == "mechanical"


def test_removing_the_active_profile_promotes_another():
    profiles = ProbeProfiles()
    profiles.add(ProbeProfile("a", tip_diameter=1.1))
    profiles.add(ProbeProfile("b", tip_diameter=2.2))
    profiles.remove("a")

    assert profiles.active.name == "b"


def test_removing_the_last_profile_leaves_none_active():
    profiles = ProbeProfiles()
    profiles.add(ProbeProfile("only", tip_diameter=1.1))
    profiles.remove("only")

    assert profiles.active is None


def test_config_commands_persist_both_probe_settings():
    commands = ProbeProfile("v6", tip_diameter=1.642, tlo_correction=0.25).config_commands()

    assert any("probe_tip_diameter 1.6420" in c for c in commands)
    assert any("three_axis_probe_tlo_correction 0.2500" in c for c in commands)


def test_profiles_round_trip_with_the_active_selection():
    profiles = ProbeProfiles()
    profiles.add(ProbeProfile("mechanical", tip_diameter=1.642))
    profiles.add(ProbeProfile("inductive", ProbeKind.INDUCTIVE, tip_diameter=2.98, normally_closed=True))
    profiles.activate("inductive")

    restored = ProbeProfiles.from_json(profiles.to_json())

    assert restored.names() == ["inductive", "mechanical"]
    assert restored.active.name == "inductive"
    assert restored.active.normally_closed


def test_an_unknown_probe_kind_falls_back_rather_than_raising():
    profile = ProbeProfile.from_dict({"name": "x", "kind": "telepathic"})
    assert profile.kind is ProbeKind.MECHANICAL


# ----------------------------------------------------------- saved positions


def test_moves_retract_z_before_travelling():
    """Travelling to a preset while down in a part destroys fixtures."""
    lines = SavedPosition("chip clear", x=-10.0, y=-200.0).to_gcode()

    assert lines[0].startswith("G53 G0 Z")
    assert "X-10.000" in lines[1]


def test_positions_are_in_machine_coordinates():
    """They must survive a change of work origin."""
    for line in SavedPosition("p", x=1.0, y=2.0, z=3.0).to_gcode():
        assert line.startswith("G53")


def test_a_z_only_position_does_not_retract_first():
    assert SavedPosition("up", z=-5.0).to_gcode() == ["G53 G0 Z-5.000"]


def test_an_empty_position_produces_no_moves():
    assert SavedPosition("nothing").to_gcode() == []


def test_retraction_can_be_disabled_deliberately():
    lines = SavedPosition("p", x=1.0).to_gcode(safe_z_first=False)
    assert len(lines) == 1


def test_positions_round_trip():
    positions = SavedPositions()
    positions.save(SavedPosition("chip clear", x=-10.0, y=-200.0, note="bed back"))
    positions.save(SavedPosition("inspect", x=-180.0, y=-60.0))

    restored = SavedPositions.from_json(positions.to_json())

    assert restored.names() == ["chip clear", "inspect"]
    assert restored.get("chip clear").note == "bed back"
    assert restored.get("inspect").z is None


@pytest.mark.parametrize("text", ["", "junk", "[]", '{"positions": 3}'])
def test_unreadable_positions_load_empty(text):
    assert SavedPositions.from_json(text).names() == []


def test_the_interval_before_spin_up_is_not_credited():
    """The interval belongs to the state at its start, not its end."""
    counters = UsageCounters()
    counters.observe(0.0, spindle_rpm=0.0)
    counters.observe(10.0, spindle_rpm=0.0)
    counters.observe(11.0, spindle_rpm=12000.0)

    assert counters.spindle_seconds == 0.0, "booked idle time as runtime"


def test_the_interval_after_spin_down_is_credited():
    """The spindle was turning for that interval, so it counts."""
    counters = UsageCounters()
    counters.observe(0.0, spindle_rpm=12000.0)
    counters.observe(1.0, spindle_rpm=0.0)

    assert counters.spindle_seconds == pytest.approx(1.0)


def test_service_is_due_exactly_on_the_interval():
    """Landing on a multiple means due now, not a fresh period."""
    interval = ServiceInterval("Chips", 8.0, "clear chips")

    assert interval.due_in(UsageCounters(spindle_seconds=8 * 3600.0)) == 0.0
    assert interval.is_due(UsageCounters(spindle_seconds=8 * 3600.0))


def test_a_brand_new_machine_is_not_immediately_due():
    interval = ServiceInterval("Chips", 8.0, "clear chips")
    assert not interval.is_due(UsageCounters(spindle_seconds=0.0))
