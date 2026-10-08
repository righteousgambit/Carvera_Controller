"""Tests for pre-job checks."""

import os

import pytest

from carveracontroller.machine.preflight import (
    UNCALIBRATED_TIP_DIAMETER,
    CheckStatus,
    PreflightState,
    blocking,
    run_preflight,
)

_GOOD_PROGRAM = ["G90 G94", "G17", "G21", "M6 T1", "S12000 M3", "G1 X10 F800"]


def _named(checks, name):
    return next(c for c in checks if c.name == name)


def _state(**overrides):
    base = {
        "connected": True,
        "machine_state": "Idle",
        "probe_tip_diameter": 1.642,
        "work_offsets": (-150.0, -90.0, -20.0),
        "available_tools": (1, 2, 3),
        "program_lines": _GOOD_PROGRAM,
    }
    base.update(overrides)
    return PreflightState(**base)


def test_a_correct_setup_passes_everything():
    checks = run_preflight(_state())

    assert all(c.status is CheckStatus.PASS for c in checks), [
        (c.name, c.status, c.detail) for c in checks if c.status is not CheckStatus.PASS
    ]
    assert blocking(checks) == []


# ------------------------------------------------------------ machine ready


def test_disconnected_blocks():
    checks = run_preflight(_state(connected=False))

    assert _named(checks, "Machine ready").status is CheckStatus.FAIL
    assert blocking(checks)


def test_alarm_state_blocks():
    assert _named(run_preflight(_state(machine_state="Alarm")), "Machine ready").status is CheckStatus.FAIL


def test_running_machine_warns_rather_than_blocking():
    checks = run_preflight(_state(machine_state="Run"))

    assert _named(checks, "Machine ready").status is CheckStatus.WARN
    assert blocking(checks) == []


# ------------------------------------------------------------- work origin


def test_origin_at_machine_zero_warns():
    check = _named(run_preflight(_state(work_offsets=(0.0, 0.0, 0.0))), "Work origin")

    assert check.status is CheckStatus.WARN
    assert "never set" in check.remedy


def test_unknown_offsets_are_skipped_not_failed():
    assert _named(run_preflight(_state(work_offsets=None)), "Work origin").status is CheckStatus.SKIP


# ------------------------------------------------------- probe calibration


def test_default_tip_diameter_warns():
    """The single most common silent accuracy loss on this machine."""
    check = _named(run_preflight(_state(probe_tip_diameter=UNCALIBRATED_TIP_DIAMETER)), "Probe tip diameter")

    assert check.status is CheckStatus.WARN
    assert "config-set" in check.remedy


def test_calibrated_tip_diameter_passes():
    check = _named(run_preflight(_state(probe_tip_diameter=1.642)), "Probe tip diameter")

    assert check.status is CheckStatus.PASS
    assert "1.642" in check.detail


def test_unknown_tip_diameter_is_skipped():
    assert _named(run_preflight(_state(probe_tip_diameter=None)), "Probe tip diameter").status is CheckStatus.SKIP


# ------------------------------------------------------------------- tools


def test_missing_tool_blocks():
    check = _named(run_preflight(_state(available_tools=(2, 3))), "Tools")

    assert check.status is CheckStatus.FAIL
    assert "T1" in check.detail


def test_program_without_tool_changes_passes():
    checks = run_preflight(_state(program_lines=["G90", "G21", "G17", "S12000 M3", "G1 X1 F100"]))
    assert _named(checks, "Tools").status is CheckStatus.PASS


def test_unknown_loaded_tools_are_skipped_not_failed():
    assert _named(run_preflight(_state(available_tools=())), "Tools").status is CheckStatus.SKIP


# ----------------------------------------------------------------- program


def test_program_errors_block():
    check = _named(run_preflight(_state(program_lines=_GOOD_PROGRAM + ["G1 X1 F9000"])), "Program")

    assert check.status is CheckStatus.FAIL
    assert "line" in check.detail


def test_program_warnings_do_not_block():
    checks = run_preflight(_state(program_lines=["M6 T1", "S12000 M3", "G1 X1 F100"]))

    assert _named(checks, "Program").status is CheckStatus.WARN
    assert blocking(checks) == []


def test_program_summary_counts_further_issues():
    lines = ["M6 T1", "S18000 M3", "G1 X1 F9000"]
    detail = _named(run_preflight(_state(program_lines=lines)), "Program").detail

    assert "other" in detail


def test_no_program_loaded_is_skipped():
    checks = run_preflight(_state(program_lines=()))

    for name in ("Tools", "Program"):
        assert _named(checks, name).status is CheckStatus.SKIP


def test_a_real_program_passes_the_program_check():
    path = os.path.join(os.path.dirname(__file__), "..", "resources", "Face 4x4 stock.cnc")
    with open(path) as handle:
        lines = handle.read().splitlines()

    checks = run_preflight(_state(program_lines=lines, available_tools=(1,)))

    assert _named(checks, "Program").status is CheckStatus.PASS
    assert _named(checks, "Tools").status is CheckStatus.PASS


@pytest.mark.parametrize("state", [_state(), _state(connected=False)])
def test_every_check_is_always_reported(state):
    """The panel must not silently drop rows depending on state."""
    names = [c.name for c in run_preflight(state)]

    assert names == ["Machine ready", "Work origin", "Probe tip diameter", "Tools", "Program"]
