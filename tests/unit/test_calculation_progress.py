"""Progress timestamps describe worker stages, never qualification or an ETA."""

from carveracontroller.machine.calculation_progress import CalculationProgress, calculation_status


def test_phase_timing_progress_and_delivery_are_detached_and_frozen():
    now = [10.0]
    progress = CalculationProgress("CAD verification", clock=lambda: now[0])
    now[0] = 12
    progress.phase("Material removal", 20)
    now[0] = 13
    progress.advance(7, source_line=42)
    now[0] = 15
    snapshot = progress.snapshot()
    assert snapshot["elapsed_s"] == 5
    assert snapshot["phase_elapsed_s"] == 3
    assert snapshot["progress_age_s"] == 2
    assert snapshot["phases"] == [{"phase": "CAD verification", "elapsed_s": 2}]
    status = calculation_status(snapshot)
    assert "7/20 segments · line 42" in status
    assert "last progress 2.0s ago" in status
    assert "ETA" not in status
    snapshot["phases"][0]["phase"] = "Changed outside owner"
    assert progress.snapshot()["phases"][0]["phase"] == "CAD verification"
    progress.phase("Waiting for workbench delivery")
    now[0] = 18
    progress.finish("delivered")
    finished = progress.snapshot()
    assert finished["status"] == "delivered"
    assert finished["elapsed_s"] == 8 and finished["phase_elapsed_s"] == 3
    now[0] = 100
    progress.phase("Obsolete worker")
    progress.advance(999)
    progress.finish("incorrect second completion")
    assert progress.snapshot() == finished


def test_cancellation_is_a_request_and_phase_history_is_bounded():
    now = [0.0]
    progress = CalculationProgress("Preparation", clock=lambda: now[0])
    for index in range(30):
        now[0] += 1
        progress.phase(f"Phase {index}")
    snapshot = progress.snapshot()
    assert len(snapshot["phases"]) == 16
    assert snapshot["phases"][0]["phase"] == "Phase 13"
    assert snapshot["status"] == "running"
    message = calculation_status(snapshot, cancelling=True)
    assert message.startswith("Cancel requested · Phase 29")
    assert "cancelled" not in message
