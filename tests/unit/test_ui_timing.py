import pytest

from carveracontroller.machine.ui_timing import NavigationTimings


def test_phase_callback_clock_and_flip_are_separate_observations():
    now = [10.0]
    timings = NavigationTimings(clock=lambda: now[0])
    record = timings.begin("Job", "Setup")
    with timings.phase(record, "history_depart"):
        now[0] += 0.01
    now[0] += 0.02
    timings.finish(record, completed=True)
    now[0] += 0.3
    timings.observe(record, "clock_turn_s", current="Setup")
    now[0] += 0.2
    timings.observe(record, "window_flip_s", current="Setup")
    assert record["phases_s"]["history_depart"] == pytest.approx(0.01)
    assert record["callback_s"] == pytest.approx(0.03)
    assert record["clock_turn_s"] == pytest.approx(0.33)
    assert record["window_flip_s"] == pytest.approx(0.53)
    # Later notifications must not overwrite the first observation.
    now[0] += 1
    timings.observe(record, "window_flip_s", current="Setup")
    assert record["window_flip_s"] == pytest.approx(0.53)


def test_superseded_failed_and_mismatched_targets_cannot_claim_a_flip():
    timings = NavigationTimings()
    old = timings.begin("Job", "Setup")
    timings.finish(old, completed=True)
    failed = timings.begin("Setup", "Scene")
    with pytest.raises(RuntimeError), timings.phase(failed, "activation"):
        raise RuntimeError("not recorded in diagnostics")
    timings.finish(failed, completed=False)
    timings.observe(old, "window_flip_s", current="Setup")
    timings.observe(failed, "window_flip_s", current="Scene")
    assert old["superseded"] and old["window_flip_s"] is None
    assert failed["window_flip_s"] is None and "activation" in failed["phases_s"]
    current = timings.begin("Scene", "Job")
    timings.finish(current, completed=True)
    timings.observe(current, "clock_turn_s", current="Setup")
    assert current["superseded"] and current["clock_turn_s"] is None


def test_retention_is_bounded_and_exports_are_independent():
    timings = NavigationTimings(limit=2)
    for _ in range(4):
        record = timings.begin("Job", "Setup")
        timings.finish(record, completed=True)
    snapshot = timings.snapshot()
    assert snapshot["evicted"] == 2
    assert [record["sequence"] for record in snapshot["records"]] == [3, 4]
    snapshot["records"][-1]["phases_s"]["fake"] = 99
    assert "fake" not in timings.records[-1]["phases_s"]
    with pytest.raises(ValueError):
        timings.observe(record, "presentation", current="Setup")


@pytest.mark.parametrize("limit", [0, 1001, True, 1.5])
def test_invalid_retention_rejected(limit):
    with pytest.raises(ValueError):
        NavigationTimings(limit=limit)


def test_rare_slow_observations_survive_refresh_eviction_and_export_mutation():
    now = [0.0]
    timings = NavigationTimings(limit=2, clock=lambda: now[0])
    slow = timings.begin("refresh", "Setup")
    with timings.phase(slow, "setup"):
        now[0] += 3
    timings.finish(slow, completed=True)
    now[0] += 1
    timings.observe(slow, "clock_turn_s", current="Setup")
    now[0] += 2
    timings.observe(slow, "window_flip_s", current="Setup")
    for _ in range(10):
        now[0] += 0.2
        fast = timings.begin("refresh", "Monitor")
        now[0] += 0.001
        timings.finish(fast, completed=True)
        timings.observe(fast, "window_flip_s", current="Monitor")
    snapshot = timings.snapshot()
    assert slow not in snapshot["records"]
    assert len(snapshot["slowest"]) == 3
    for kind, expected in (("callback_s", 3), ("clock_turn_s", 4), ("window_flip_s", 6)):
        assert snapshot["slowest"][kind]["sequence"] == 1
        assert snapshot["slowest"][kind][kind] == expected
    assert snapshot["longest_start_interval"]["interval_s"] == pytest.approx(6.2)
    assert snapshot["longest_start_interval"]["previous_target"] == "Setup"
    assert snapshot["longest_start_interval"]["target"] == "Monitor"
    snapshot["slowest"]["callback_s"]["phases_s"]["setup"] = 99
    snapshot["longest_start_interval"]["interval_s"] = 99
    assert timings.slowest["callback_s"]["phases_s"]["setup"] == 3
    assert timings.longest_start_interval["interval_s"] == pytest.approx(6.2)


def test_failed_slow_callback_is_retained_without_claiming_render_success():
    now = [0.0]
    timings = NavigationTimings(limit=1, clock=lambda: now[0])
    failed = timings.begin("Job", "Setup")
    now[0] = 10
    timings.finish(failed, completed=False)
    timings.observe(failed, "window_flip_s", current="Setup")
    fast = timings.begin("Setup", "Job")
    now[0] += 0.01
    timings.finish(fast, completed=True)
    snapshot = timings.snapshot()
    assert snapshot["slowest"]["callback_s"]["completed"] is False
    assert "window_flip_s" not in snapshot["slowest"]
