"""Read-only write admission diagnostics with individually valid receipt ages."""

import copy

import pytest

from carveracontroller.machine.probe_settings_workflow import require_probe_write_state


def inputs():
    return {
        "report_current": True,
        "report_reason": "",
        "status": {"state": "Idle", "is_playing": False, "spindle_rpm": 0, "spindle_target_rpm": 0},
        "diagnostics": {"spindle_enabled": False},
        "diagnostics_age_ms": 100,
        "cached_age_s": 0.2,
    }


@pytest.mark.parametrize(
    "rpm,age,cached",
    [(0, 0, 0), (0.0, 3000, 0), (-0.0, 2800, 0.2), (0, -0.0, -0.0)],
    ids=["lower-bound", "upper-bound", "signed-zero-combined-bound", "signed-zero-ages"],
)
def test_original_numeric_zero_and_combined_age_boundaries_remain_accepted(rpm, age, cached):
    values = inputs()
    values["status"].update(spindle_rpm=rpm, spindle_target_rpm=rpm)
    values.update(diagnostics_age_ms=age, cached_age_s=cached)
    before = copy.deepcopy(values)
    require_probe_write_state(**values)
    assert values == before


@pytest.mark.parametrize(
    "section,key,value,message",
    [
        (None, "report_current", False, "current matching machine report: model mismatch"),
        ("status", "state", "Run", "Idle machine status"),
        ("status", "is_playing", True, "no job is playing"),
        ("status", "is_playing", 0, "no job is playing"),
        ("status", "spindle_rpm", True, "numeric actual spindle RPM"),
        ("status", "spindle_rpm", None, "numeric actual spindle RPM"),
        ("status", "spindle_rpm", 1, "zero actual spindle RPM"),
        ("status", "spindle_rpm", float("nan"), "finite actual spindle RPM"),
        ("status", "spindle_target_rpm", "0", "numeric target spindle RPM"),
        ("status", "spindle_target_rpm", 1, "zero target spindle RPM"),
        ("status", "spindle_target_rpm", float("inf"), "finite target spindle RPM"),
        ("diagnostics", "spindle_enabled", True, "diagnostics report enabled"),
        ("diagnostics", "spindle_enabled", None, "explicit spindle-disabled diagnostics"),
        ("diagnostics", "spindle_enabled", 0, "explicit spindle-disabled diagnostics"),
        (None, "diagnostics_age_ms", True, "diagnostics age is missing or not numeric"),
        (None, "cached_age_s", "0", "cached snapshot age is missing or not numeric"),
        (None, "diagnostics_age_ms", float("nan"), "diagnostics age is nonfinite"),
        (None, "diagnostics_age_ms", float("inf"), "diagnostics age is nonfinite"),
        (None, "diagnostics_age_ms", -201, "diagnostics age is negative"),
        (None, "diagnostics_age_ms", -100, "diagnostics age is negative"),
        (None, "cached_age_s", -0.05, "cached snapshot age is negative"),
        (None, "cached_age_s", float("nan"), "cached snapshot age is nonfinite"),
        (None, "cached_age_s", float("inf"), "cached snapshot age is nonfinite"),
        (None, "diagnostics_age_ms", 2800.001, "diagnostics are stale"),
        (None, "diagnostics_age_ms", 10**1000, "receipt age is unrepresentable"),
    ],
    ids=[
        "report-reason",
        "not-idle",
        "playing",
        "nonboolean-playing",
        "boolean-rpm",
        "missing-rpm",
        "nonzero-rpm",
        "nan-rpm",
        "text-target",
        "nonzero-target",
        "infinite-target",
        "spindle-enabled",
        "missing-spindle-diagnostic",
        "nonboolean-spindle",
        "boolean-age",
        "text-cached-age",
        "nan-age",
        "infinite-age",
        "negative-age",
        "masked-negative-diagnostics-age",
        "masked-negative-cache-age",
        "nan-cache-age",
        "infinite-cache-age",
        "stale-combined-age",
        "overflow-age",
    ],
)
def test_each_refusal_identifies_its_guard_without_mutating_inputs(section, key, value, message):
    values = inputs()
    values["report_reason"] = "model mismatch"
    if section is None:
        values[key] = value
    else:
        values[section][key] = value
    before = copy.deepcopy(values)
    with pytest.raises(ValueError, match=message):
        require_probe_write_state(**values)
    # NaN is non-reflexive; compare detached representations for rejected input.
    assert repr(values) == repr(before)
