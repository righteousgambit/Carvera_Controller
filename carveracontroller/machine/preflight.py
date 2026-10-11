"""Checks to run before starting a job.

These catch the setup mistakes that are invisible until the part is wrong:
an unpersisted probe tip diameter, a work origin still sitting at machine
zero, a program calling a tool that is not loaded. None of them stop the
machine on their own, so nothing here blocks a job -- it reports, and the
operator decides.

Kivy-free by contract.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import Enum

from .program_check import ProgramIssue, Severity, check_program, tools_used

# The firmware's fallback when zprobe.probe_tip_diameter was never persisted.
# M460 reports a measured value but does not save it, so a machine sitting at
# exactly the default has almost certainly lost a calibration.
UNCALIBRATED_TIP_DIAMETER = 2.0
_TIP_DIAMETER_EPSILON = 1e-6


class CheckStatus(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"
    """Could not be determined, usually because the machine is not connected."""


@dataclass(frozen=True)
class PreflightCheck:
    name: str
    status: CheckStatus
    detail: str
    remedy: str = ""

    @property
    def needs_attention(self) -> bool:
        return self.status in (CheckStatus.WARN, CheckStatus.FAIL)


@dataclass
class PreflightState:
    """Everything the checks need, gathered from the machine and the job."""

    connected: bool = False
    machine_state: str = ""
    probe_tip_diameter: float | None = None
    work_offsets: tuple[float, float, float] | None = None
    available_tools: Sequence[int] = field(default_factory=tuple)
    program_lines: Sequence[str] = field(default_factory=tuple)


def run_preflight(state: PreflightState) -> list[PreflightCheck]:
    """Run every check, in the order an operator would want to read them."""
    return [
        _check_machine_ready(state),
        _check_work_origin(state),
        _check_probe_calibration(state),
        _check_tools_available(state),
        _check_program(state),
    ]


def blocking(checks: Iterable[PreflightCheck]) -> list[PreflightCheck]:
    """Checks that should stop an operator, as opposed to informing them."""
    return [c for c in checks if c.status is CheckStatus.FAIL]


def _check_machine_ready(state: PreflightState) -> PreflightCheck:
    name = "Machine ready"
    if not state.connected:
        return PreflightCheck(name, CheckStatus.FAIL, "Not connected to a machine.", "Connect first.")
    if state.machine_state in ("Alarm", "Sleep"):
        return PreflightCheck(
            name,
            CheckStatus.FAIL,
            f"Machine is in {state.machine_state}.",
            "Clear the halt and re-home before starting a job.",
        )
    if state.machine_state and state.machine_state not in ("Idle", "Pause"):
        return PreflightCheck(
            name, CheckStatus.WARN, f"Machine is {state.machine_state}, not idle.", "Wait for it to finish."
        )
    return PreflightCheck(name, CheckStatus.PASS, "Idle and connected.")


def _check_work_origin(state: PreflightState) -> PreflightCheck:
    name = "Work origin"
    if state.work_offsets is None:
        return PreflightCheck(name, CheckStatus.SKIP, "Work offsets unknown.")
    if all(abs(v) < 1e-6 for v in state.work_offsets):
        return PreflightCheck(
            name,
            CheckStatus.WARN,
            "Work origin is the same as machine zero.",
            "That is legitimate for some setups, but it usually means the origin was never set.",
        )
    x, y, z = state.work_offsets
    return PreflightCheck(name, CheckStatus.PASS, f"Set to X{x:.3f} Y{y:.3f} Z{z:.3f}.")


def _check_probe_calibration(state: PreflightState) -> PreflightCheck:
    name = "Probe tip diameter"
    if state.probe_tip_diameter is None:
        return PreflightCheck(name, CheckStatus.SKIP, "Not read from the machine.")
    if abs(state.probe_tip_diameter - UNCALIBRATED_TIP_DIAMETER) < _TIP_DIAMETER_EPSILON:
        return PreflightCheck(
            name,
            CheckStatus.WARN,
            f"Still at the {UNCALIBRATED_TIP_DIAMETER:.1f} mm default.",
            "M460 reports a measured diameter but does not save it. If you calibrated and did not "
            "run config-set sd zprobe.probe_tip_diameter, the value was lost on the last power cycle "
            "and every probed feature will be off by the error.",
        )
    return PreflightCheck(name, CheckStatus.PASS, f"{state.probe_tip_diameter:.3f} mm, calibrated.")


def _check_tools_available(state: PreflightState) -> PreflightCheck:
    name = "Tools"
    if not state.program_lines:
        return PreflightCheck(name, CheckStatus.SKIP, "No program loaded.")

    required = tools_used(state.program_lines)
    if not required:
        return PreflightCheck(name, CheckStatus.PASS, "Program does not change tools.")
    if not state.available_tools:
        return PreflightCheck(name, CheckStatus.SKIP, "Loaded tools unknown.")

    missing = [t for t in required if t not in state.available_tools]
    if missing:
        listed = ", ".join(f"T{t}" for t in missing)
        return PreflightCheck(
            name,
            CheckStatus.FAIL,
            f"Program calls {listed}, which is not loaded.",
            "Load the tool, or the job will stop at the change.",
        )
    return PreflightCheck(name, CheckStatus.PASS, f"All {len(required)} tools loaded.")


def _check_program(state: PreflightState) -> PreflightCheck:
    name = "Program"
    if not state.program_lines:
        return PreflightCheck(name, CheckStatus.SKIP, "No program loaded.")

    issues = check_program(state.program_lines)
    errors = [i for i in issues if i.severity is Severity.ERROR]
    warnings = [i for i in issues if i.severity is Severity.WARNING]

    if errors:
        return PreflightCheck(
            name,
            CheckStatus.FAIL,
            _summarise(errors),
            "The machine cannot run this as posted.",
        )
    if warnings:
        return PreflightCheck(name, CheckStatus.WARN, _summarise(warnings))
    return PreflightCheck(name, CheckStatus.PASS, "No problems found.")


def _summarise(issues: Sequence[ProgramIssue]) -> str:
    first = issues[0]
    where = f"line {first.line_number}" if first.line_number else "the program header"
    text = f"{first.message} ({where})"
    if len(issues) > 1:
        text += f" and {len(issues) - 1} other."
    return text
