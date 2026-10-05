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
