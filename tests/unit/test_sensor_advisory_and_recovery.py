from dataclasses import replace

import pytest

from carveracontroller.machine.adaptive_monitor import AdaptiveMonitor, Sample
from carveracontroller.machine.feed_recipe import FeedRecipe
from carveracontroller.machine.recovery_policy import RecoveryVerification, assess_recovery, recovery_scope


def recipe(**changes):
    values = {
        "cutter": "assembly A",
        "material": "6061",
        "operation": "roughing",
        "rpm": 12000,
        "flutes": 2,
        "programmed_feed_mm_min": 600,
        "chipload_min_mm": 0.02,
        "chipload_max_mm": 0.025,
    }
    values.update(changes)
    return values


def baseline(context=None):
    context = {"operation": "roughing", "commanded_feed_mm_min": 600, **(context or {})}
    monitor = AdaptiveMonitor()
    monitor.configure_recipe(recipe())
    monitor.capture_baseline()
    for n in range(27):
        monitor.observe(Sample(n * 0.2, "Idle", 12000, 12000, 0.3, 0, 100, (0, 0, 0), context or {}))
    return monitor


def test_recipe_floor_is_derived_from_chip_load_and_refuses_rubbing_feed():
    bounds = FeedRecipe(**recipe())
    assert bounds.minimum_override == 80
    monitor = baseline()
    for n in range(1, 50):
        monitor.observe(
            Sample(
                5.2 + n * 0.2,
                "Run",
                11850,
                12000,
                0.8,
                600,
                100,
                (n, 0, 0),
                {"operation": "roughing", "commanded_feed_mm_min": 600},
            )
        )
    assert monitor.proposed == 80
    result = monitor.observe(replace(monitor.last, timestamp=15.4, override=60))
    assert "below recipe" in result["reason"] or "discontinuity" in result["reason"]


@pytest.mark.parametrize(
    "change",
    [
        {"chipload_min_mm": 0},
        {"flutes": 1.5},
        {"rpm": float("nan")},
        {"material": ""},
        {"chipload_min_mm": 0.1},
        {"chipload_max_mm": 0.001},
    ],
)
def test_invalid_or_unachievable_recipe_is_rejected(change):
    with pytest.raises(ValueError):
        FeedRecipe(**recipe(**change))


def test_missing_recipe_prevents_feed_proposals():
    monitor = baseline()
    monitor.recipe = None
    result = monitor.observe(replace(monitor.last, timestamp=5.4, state="Run", feed=600, rpm=11850))
    assert "recipe required" in result["reason"]
    assert monitor.proposed == 100


@pytest.mark.parametrize(
    "changed",
    [
        {"tool_assembly_id": "B"},
        {"seating_revision": 2},
        {"accessory_commands": {"air": False}},
        {"spindle_temperature": 41},
        {"spindle_temperature": None},
        {"firmware_boot_id": 12},
    ],
)
def test_operating_condition_change_invalidates_unloaded_baseline(changed):
    context = {
        "tool_assembly_id": "A",
        "seating_revision": 1,
        "accessory_commands": {"air": True},
        "spindle_temperature": 35,
        "firmware_boot_id": 11,
    }
    monitor = baseline(context)
    context.update(changed)
    monitor.observe(replace(monitor.last, timestamp=5.4, context=context))
    assert monitor.baseline is None


def test_outcomes_link_only_matching_program_and_operation_proposals():
    context = {"program": {"sha256": "abc"}, "operation": "roughing"}
    monitor = baseline(context)
    monitor.observe(replace(monitor.last, timestamp=5.4, state="Run", feed=600, rpm=11850))
    assert monitor.record_outcome({"program_hash": "abc", "operation": "roughing", "finish": "chatter"})["proposals"]
    assert not monitor.record_outcome({"program_hash": "other", "operation": "roughing", "finish": "smooth"})[
        "proposals"
    ]
    with pytest.raises(ValueError):
        monitor.record_outcome({"program_hash": "abc"})
    assert not monitor.snapshot()["active_control_available"]


def recovery_context():
    return {
        "state": "Idle",
        "halt_reason": 0,
        "telemetry_stale": False,
        "firmware_boot_id": 11,
        "wcs": 0,
        "tool": 1,
        "tlo": 25.2,
        "work_offset": [10, 20, 30],
        "machine_position": [0, 0, -2],
        "work_position": [-10, -20, -32],
        "rotation": 0,
        "modes": [1, 0, 0, 1],
        "machine_filename": "/sd/part.nc",
    }


def verified(context):
    return RecoveryVerification(
        recovery_scope("a" * 64, 8081, context),
        True,
        True,
        True,
        True,
        -2.0,
        "Rehomed, probed origin and setter, checked clamps at machine Z -2",
        program_verified=True,
    )


def test_recovery_requires_exact_scope_and_all_operator_checks():
    context = recovery_context()
    assert not assess_recovery("a" * 64, 8081, context)["allowed"]
    verification = verified(context)
    assert assess_recovery("a" * 64, 8081, context, verification)["allowed"]
    assert not assess_recovery("a" * 64, 8082, context, verification)["allowed"]
    assert not assess_recovery("d" * 64, 8081, context, verification)["allowed"]
    assert not assess_recovery("a" * 64, 8081, context, replace(verification, origin_verified=False))["allowed"]


@pytest.mark.parametrize(
    "change",
    [
        {"firmware_boot_id": 12},
        {"tool": 2},
        {"tlo": 25.3},
        {"wcs": 1},
        {"work_offset": [0, 0, 0]},
        {"telemetry_stale": True},
        {"state": "Run"},
        {"halt_reason": 24},
    ],
)
def test_changed_or_stale_recovery_state_cannot_reuse_verification(change):
    context = recovery_context()
    verification = verified(context)
    context.update(change)
    assert not assess_recovery("a" * 64, 8081, context, verification)["allowed"]


def test_verification_requires_actual_boolean_and_finite_clearance():
    with pytest.raises(ValueError):
        replace(verified(recovery_context()), clearance_machine_z_mm=float("inf"))
    with pytest.raises(ValueError):
        replace(verified(recovery_context()), position_verified="yes")


@pytest.mark.parametrize(
    "changed",
    [
        {"assembly_id": "B"},
        {"seat_revision": "reseated"},
        {"assembly_revision_id": "revision B"},
        {"assignment_id": "different"},
    ],
)
def test_production_declaration_names_invalidate_baseline(changed):
    context = {
        "assembly_id": "A",
        "seat_revision": "seat A",
        "assembly_revision_id": "revision A",
        "assignment_id": "same",
    }
    monitor = baseline(context)
    context.update(changed)
    monitor.observe(replace(monitor.last, timestamp=5.4, context=context))
    assert monitor.baseline is None


@pytest.mark.parametrize(
    "change",
    [{"operation": None}, {"operation": "finishing"}, {"commanded_feed_mm_min": 300}, {"commanded_feed_mm_min": None}],
)
def test_unknown_or_mismatched_executing_recipe_cannot_propose_rubbing_feed(change):
    monitor = baseline()
    context = dict(monitor.last.context, **change)
    result = monitor.observe(replace(monitor.last, timestamp=5.4, state="Run", feed=300, rpm=11850, context=context))
    assert monitor.proposed == 100
    assert "recipe required" in result["reason"]


@pytest.mark.parametrize(
    "change",
    [{"machine_position": [1, 0, -2]}, {"work_position": [-9, -20, -32]}, {"rotation": 45}, {"modes": [0, 0, 1, 0]}],
)
def test_jog_rotation_or_mode_changes_invalidate_recovery_verification(change):
    context = recovery_context()
    verification = verified(context)
    context.update(change)
    assert not assess_recovery("a" * 64, 8081, context, verification)["allowed"]


@pytest.mark.parametrize(
    "change",
    [
        {"halt_reason": None},
        {"halt_reason": False},
        {"tlo": float("nan")},
        {"rotation": None},
        {"wcs": True},
        {"wcs": -1},
        {"tool": 0},
        {"firmware_boot_id": "boot"},
        {"modes": None},
        {"modes": [1, 0, 999, 1]},
        {"work_offset": [1, 2, float("inf")]},
        {"machine_filename": None},
        {"machine_filename": "file\nresume"},
        {"telemetry_stale": 0},
        {"raw_inputs": {"spindle_alarm": True}},
        {"raw_inputs": {"cover": False}},
    ],
)
def test_unknown_or_invalid_recovery_evidence_cannot_be_operator_overridden(change):
    context = recovery_context()
    context.update(change)
    try:
        verification = verified(context)
    except ValueError:
        verification = None
    assert not assess_recovery("a" * 64, 8081, context, verification)["allowed"]


def test_boolean_line_and_clearance_are_not_numeric_verification():
    assert not assess_recovery("a" * 64, True, recovery_context())["allowed"]
    with pytest.raises(ValueError):
        replace(verified(recovery_context()), clearance_machine_z_mm=True)


@pytest.mark.parametrize(
    "change",
    [
        {"assembly_id": "new assembly"},
        {"seat_revision": "reseated"},
        {"connection_generation": 2},
        {"connection_address": "another machine"},
    ],
)
def test_custody_and_connection_changes_invalidate_prior_verification(change):
    context = recovery_context()
    verification = verified(context)
    context.update(change)
    assert not assess_recovery("a" * 64, 8081, context, verification)["allowed"]


def test_raw_cover_true_is_closed_not_an_alarm():
    context = recovery_context()
    context["raw_inputs"] = {"cover": True}
    assert assess_recovery("a" * 64, 8081, context, verified(context))["allowed"]
