"""Explain retained packet quality without granting live execution authority."""

from __future__ import annotations

import math
from dataclasses import dataclass

from carveracontroller.machine.run_recording import RecordingReplay


@dataclass(frozen=True)
class RecordingCheck:
    code: str
    detail: str


@dataclass(frozen=True)
class RecordingChecks:
    sample_age_seconds: float | None
    reported_tool: int | None
    checks: tuple[RecordingCheck, ...]


def inspect_receipt(
    replay: RecordingReplay,
    index: int,
    recorded_at: float | None = None,
    *,
    expected_tool: int | None = None,
    max_age_seconds: float = 0.8,
) -> RecordingChecks:
    """Inspect the selected event, including boundaries at duplicate timestamps.

    Age is time since desktop receipt within this archive, not device latency.
    Tool comparison uses a user-entered logical number, never physical identity
    or an inferred executed program line. No field is borrowed from another packet.
    """
    events = replay.payload["events"]
    if type(index) is not int or not 0 <= index < len(events):
        raise ValueError("Choose a retained event")
    if expected_tool is not None and (type(expected_tool) is not int or not 0 <= expected_tool <= 9999):
        raise ValueError("Expected logical tool must be an integer from 0 to 9999")
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, (int, float))
        or not 0 < max_age_seconds <= 3600
        or not math.isfinite(max_age_seconds)
    ):
        raise ValueError("Receipt freshness budget must be greater than zero and at most 3600 seconds")
    event = events[index]
    stamp = event["monotonic_at"] if recorded_at is None else recorded_at
    if (
        isinstance(stamp, bool)
        or not isinstance(stamp, (int, float))
        or not event["monotonic_at"] <= stamp <= events[-1]["monotonic_at"]
        or (index + 1 < len(events) and stamp > events[index + 1]["monotonic_at"])
        or not math.isfinite(stamp)
    ):
        raise ValueError("Review time must belong to the selected receipt interval")
    kind = event["kind"]
    if kind == "gap":
        return RecordingChecks(
            None,
            None,
            (RecordingCheck("gap", f"Missing telemetry: {event['data']['duration_seconds']:g} s; motion unknown."),),
        )
    if kind == "connection_boundary":
        return RecordingChecks(
            None,
            None,
            (
                RecordingCheck(
                    "connection_boundary",
                    f"Connection generation changed from {event['data']['previous_generation']} to {event['generation']}; continuity unknown.",
                ),
            ),
        )
    age = stamp - event["monotonic_at"]
    checks = []
    following = events[index + 1] if index + 1 < len(events) else None
    if following and following["kind"] != "status" and age > 0:
        checks.append(
            RecordingCheck("missing_interval", "Inside a missing telemetry / connection interval; motion unknown.")
        )
    if stamp > event["monotonic_at"] + max_age_seconds:
        checks.append(
            RecordingCheck(
                "stale",
                f"Last receipt is {age:.3f} s old at this review time; exceeds the {max_age_seconds:g} s review budget.",
            )
        )
    state = event["data"]["state"]
    if state.casefold().startswith("alarm"):
        checks.append(
            RecordingCheck("alarm", "Archived controller reported " + state + "; no recovery action inferred.")
        )
    elif state.casefold() in ("disconnected", "n/a"):
        checks.append(
            RecordingCheck(
                "disconnected", "Archived controller reported " + state + "; motion and connection continuity unknown."
            )
        )
    raw_tool = event["data"]["fields"].get("T", [])
    tool = int(raw_tool[0]) if raw_tool and 0 <= raw_tool[0] <= 9999 and int(raw_tool[0]) == raw_tool[0] else None
    if tool is None:
        checks.append(
            RecordingCheck(
                "tool_unknown", "Logical tool unavailable in this packet; physical assembly identity unverified."
            )
        )
    elif expected_tool is not None and tool != expected_tool:
        checks.append(
            RecordingCheck(
                "tool_mismatch",
                f"Packet reports logical T{tool}; review expectation is T{expected_tool}. Physical identity and executed-line association remain unverified.",
            )
        )
    if replay.machine_point(index) is None:
        checks.append(
            RecordingCheck(
                "position_unknown", "Packet has no usable C1 XYZ and unit flags; recorded position unavailable."
            )
        )
    return RecordingChecks(age, tool, tuple(checks))
