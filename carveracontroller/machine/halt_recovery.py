"""What to do about a halt, not just what it was called.

The firmware reports a halt reason code and the controller renders its name:
"ATC Position Occupied", "Probe Fail". That says what happened and nothing
about what to do next, which is the part an operator standing at a stopped
machine actually needs.

Guidance here is deliberately specific to this machine. Two entries carry a
caution about the work origin because a failed probe can leave the probed
axis's work coordinate sitting at the position where it stopped, so resuming
without checking would cut in the wrong place.

Kivy-free by contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RecoveryAction(Enum):
    """How much intervention the machine needs before it will run again."""

    UNLOCK = "unlock"
    RESET = "reset"
    POWER_CYCLE = "power_cycle"


@dataclass(frozen=True)
class HaltGuidance:
    summary: str
    """One sentence on what actually happened, in plain language."""

    steps: tuple[str, ...]
    """Ordered actions to take, most likely cause first."""

    action: RecoveryAction
    caution: str = ""
    """Something that could go wrong *after* recovery if not checked."""


# Firmware groups halts by how much intervention they need. Below 20 the
# machine only needs unlocking; 21-40 need a reset; above 40 need power.
_RESET_THRESHOLD = 20
_POWER_CYCLE_THRESHOLD = 40

_PROBE_ORIGIN_CAUTION = (
    "Check your work origin before resuming. A probe that stops early can leave the probed "
    "axis's work coordinate at the position it stopped, so the next move may cut in the wrong place."
)

_GUIDANCE: dict[int, HaltGuidance] = {
    1: HaltGuidance(
        "The machine was halted deliberately, either by you or by the program.",
        ("Unlock to continue.", "Re-home if the machine was moved by hand while halted."),
        RecoveryAction.UNLOCK,
    ),
    2: HaltGuidance(
        "Homing did not complete.",
        (
            "Check nothing is obstructing travel, including clamps and the dust shoe.",
            "Check the cover is closed.",
            "Clear chips from the rails and home again.",
        ),
        RecoveryAction.UNLOCK,
    ),
    3: HaltGuidance(
        "A probing cycle did not find the surface within its travel, or triggered unexpectedly.",
        (
            "Confirm the probe is connected and responding in the diagnostics screen.",
            "Check the probe was close enough to the feature before the cycle started.",
            "Check the travel distance was large enough to reach the surface.",
        ),
        RecoveryAction.UNLOCK,
        _PROBE_ORIGIN_CAUTION,
    ),
    4: HaltGuidance(
        "Tool length calibration failed.",
        (
            "Check the tool setter is clean and not obstructed by chips.",
            "Check the tool is seated in the collet and the collet is tight.",
            "Confirm the tool setter triggers in the diagnostics screen.",
        ),
        RecoveryAction.UNLOCK,
    ),
    5: HaltGuidance(
        "The tool changer could not find its home position.",
        ("Clear anything obstructing the tool changer.", "Check no tool is left partly seated in a slot."),
        RecoveryAction.UNLOCK,
    ),
    6: HaltGuidance(
        "The program asked for a tool number the changer does not have.",
        (
            "Check the tool numbers in the program against the tools loaded.",
            "Tools outside the ATC range need a custom tool slot defined, or a manual change.",
        ),
        RecoveryAction.UNLOCK,
    ),
    7: HaltGuidance(
        "The spindle did not release the tool.",
        (
            "Check air pressure is connected and adequate.",
            "Check the collet is not over-tightened or seized.",
            "Clear chips from around the collet nut.",
        ),
        RecoveryAction.UNLOCK,
    ),
    8: HaltGuidance(
        "The tool changer tried to place a tool into a slot that already holds one.",
        (
            "Check which slots are occupied against what the controller believes.",
            "Remove the tool from the target slot, or correct the tool table.",
        ),
        RecoveryAction.UNLOCK,
    ),
    9: HaltGuidance(
        "The spindle exceeded its temperature limit.",
        (
            "Let the spindle cool before restarting.",
            "Check the spindle fan is running and its airflow is not blocked by chips.",
            "Reduce load or add dwell time if this recurs during long jobs.",
        ),
        RecoveryAction.UNLOCK,
    ),
    10: HaltGuidance(
        "The program asked the machine to move beyond its travel.",
        (
            "Check the work origin: an origin set in the wrong place is the usual cause.",
            "Check the program fits the work area from that origin.",
        ),
        RecoveryAction.UNLOCK,
    ),
    11: HaltGuidance(
        "The cover was opened while the machine was running.",
        ("Close the cover.", "Unlock, then resume or restart the job as appropriate."),
        RecoveryAction.UNLOCK,
    ),
    12: HaltGuidance(
        "The wireless probe did not respond, usually a flat battery.",
        (
            "Charge the probe in its tool slot for at least 30 minutes.",
            "Re-pair the probe if it still does not respond.",
        ),
        RecoveryAction.UNLOCK,
        "Probing with a nearly flat wireless probe is how they get damaged: it may not trigger at all.",
    ),
    13: HaltGuidance(
        "The emergency stop button is pressed.",
        ("Twist the emergency stop button to release it.", "Unlock, then re-home before running anything."),
        RecoveryAction.UNLOCK,
    ),
    14: HaltGuidance(
        "The control electronics exceeded their temperature limit.",
        ("Let the machine cool.", "Check ambient temperature and that vents are not obstructed."),
        RecoveryAction.UNLOCK,
    ),
    16: HaltGuidance(
        "The 3D probe triggered outside a probing move, which the firmware treats as a crash.",
        (
            "Inspect the probe and the stylus for damage before doing anything else.",
            "Check for an actual collision with the part or a clamp.",
            "If the probe is intact, a delayed trigger signal can also cause this on wireless probes.",
        ),
        RecoveryAction.UNLOCK,
        _PROBE_ORIGIN_CAUTION,
    ),
    21: HaltGuidance(
        "A hard limit switch was hit.",
        (
            "Move the axis off the switch by hand if needed.",
            "Reset, then re-home.",
            "Check the work origin and soft limits before running again.",
        ),
        RecoveryAction.RESET,
    ),
    22: HaltGuidance(
        "The X axis motor lost position.",
        (
            "Check for binding, obstruction or a crash on that axis.",
            "Reset and re-home, then verify positioning before cutting.",
        ),
        RecoveryAction.RESET,
        "Closed-loop position was lost, so anything cut after the error may be out of position.",
    ),
    23: HaltGuidance(
        "The Y axis motor lost position.",
        (
            "Check for binding, obstruction or a crash on that axis.",
            "Reset and re-home, then verify positioning before cutting.",
        ),
        RecoveryAction.RESET,
        "Closed-loop position was lost, so anything cut after the error may be out of position.",
    ),
    24: HaltGuidance(
        "The Z axis motor lost position.",
        (
            "Check for binding, obstruction or a crash on that axis.",
            "Reset and re-home, then verify tool length offsets before cutting.",
        ),
        RecoveryAction.RESET,
        "Closed-loop position was lost, so anything cut after the error may be out of position.",
    ),
    25: HaltGuidance(
        "The spindle stalled: it could not hold speed against the cutting load.",
        (
            "Check the tool is not jammed in the cut before restarting.",
            "Reduce radial engagement rather than feed rate: this is a 200 W spindle and "
            "engagement is what consumes its headroom.",
            "Watch the spindle load bar on the next attempt; effort rises well before speed falls.",
        ),
        RecoveryAction.RESET,
    ),
    26: HaltGuidance(
        "The SD card could not be read.",
        (
            "Reset the machine.",
            "If it recurs, back up the card contents and check the card itself.",
        ),
        RecoveryAction.RESET,
    ),
    41: HaltGuidance(
        "The spindle driver raised an alarm that only a power cycle will clear.",
        (
            "Switch the machine off at the mains, wait a few seconds, and switch it back on.",
            "If it recurs, stop using the spindle until the cause is found.",
        ),
        RecoveryAction.POWER_CYCLE,
    ),
}


def recovery_action_for(halt_reason: int) -> RecoveryAction:
    """Intervention level implied by the code's range, guidance or not."""
    if halt_reason > _POWER_CYCLE_THRESHOLD:
        return RecoveryAction.POWER_CYCLE
    if halt_reason > _RESET_THRESHOLD:
        return RecoveryAction.RESET
    return RecoveryAction.UNLOCK


def guidance_for(halt_reason: int) -> HaltGuidance | None:
    """Recovery guidance for a halt reason, or None if we have none."""
    return _GUIDANCE.get(halt_reason)


def format_guidance(halt_reason: int) -> str:
    """Render guidance as display text. Empty when there is none to give."""
    guidance = guidance_for(halt_reason)
    if guidance is None:
        return ""

    lines = [guidance.summary, ""]
    lines.extend(f"{n}. {step}" for n, step in enumerate(guidance.steps, start=1))
    if guidance.caution:
        lines.extend(["", guidance.caution])
    return "\n".join(lines)
