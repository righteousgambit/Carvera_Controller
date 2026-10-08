"""Bounded evidence for shadow decisions; never dispatch or attribute causality."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from .adaptive_monitor import MonitorEvidence, Sample

STALE_SECONDS = 0.8
BACKOFF_DROOP = 0.012
RECOVERY_DROOP = 0.004
SEVERE_DROOP = 0.05
PWM_BACKOFF = 0.95
PWM_RECOVERY = 0.75
FEED_FLOOR = 40.0
FEED_CEILING = 100.0
BACKOFF_INTERVAL = 0.4
RECOVERY_INTERVAL = 2.0
RESPONSE_WINDOW = 5.0


class ObservedResponse(TypedDict):
    status: str
    explanation: str
    arrival_time: float | None
    elapsed_s: float | None
    override_before: float | None
    override_after: float | None
    rpm_before: float | None
    rpm_after: float | None
    rpm_change: float | None
    feed_before: float | None
    feed_after: float | None


class DecisionExplanation(TypedDict):
    status: str
    limiting_factor: str
    explanation: str
    proposal_percent: float | None
    arrival_age_s: float | None
    raw_droop: float | None
    filtered_droop: float | None
    baseline_rpm: float | None
    rpm: float | None
    pwm: float | None
    reported_override: float | None
    next_adjustment_s: float | None
    machine_position: tuple[float, float, float] | None
    program_line: int | None
    response: ObservedResponse


def _response(history: tuple[Sample, ...]) -> ObservedResponse:
    result: ObservedResponse = {
        "status": "unavailable",
        "explanation": "No recent reported override change in continuous cutting telemetry.",
        "arrival_time": None,
        "elapsed_s": None,
        "override_before": None,
        "override_after": None,
        "rpm_before": None,
        "rpm_after": None,
        "rpm_change": None,
        "feed_before": None,
        "feed_after": None,
    }
    if len(history) < 2:
        return result
    latest = history[-1]
    for index in range(len(history) - 1, 0, -1):
        before, after = history[index - 1], history[index]
        if (
            latest.timestamp - after.timestamp > RESPONSE_WINDOW
            or before.state != "Run"
            or after.state != "Run"
            or before.feed <= 0
            or after.feed <= 0
            or not 0 < after.timestamp - before.timestamp <= STALE_SECONDS
            or abs(before.commanded_rpm - latest.commanded_rpm) > 1
            or abs(after.commanded_rpm - latest.commanded_rpm) > 1
        ):
            break
        if before.override == after.override:
            continue
        elapsed = latest.timestamp - after.timestamp
        result = {
            "status": "observed" if elapsed >= 1.0 else "collecting",
            "explanation": (
                "RPM change after a reported override change; arrival association only. "
                "Shadow proposals send no commands, and this does not establish a causal response."
            ),
            "arrival_time": after.timestamp,
            "elapsed_s": elapsed,
            "override_before": before.override,
            "override_after": after.override,
            "rpm_before": before.rpm,
            "rpm_after": latest.rpm,
            "rpm_change": latest.rpm - before.rpm,
            "feed_before": before.feed,
            "feed_after": latest.feed,
        }
        break
    return result


def explain_decision(
    state: MonitorEvidence, history: tuple[Sample, ...], last_adjustment: float | None, now: float | None
) -> DecisionExplanation:
    """Explain current policy without mutating its filter, dwell timers or proposal."""
    sample = state["sample"]
    baseline = state["baseline"]
    age = now - sample["timestamp"] if now is not None and sample is not None else None
    baseline_rpm = baseline["rpm"] if baseline else None
    raw_droop = (
        max(0.0, (baseline_rpm - sample["rpm"]) / baseline_rpm)
        if sample and baseline_rpm and baseline_rpm > 0
        else None
    )
    unavailable = _response(())
    result: DecisionExplanation = {
        "status": "waiting",
        "limiting_factor": "Unloaded baseline required",
        "explanation": state["reason"],
        "proposal_percent": None,
        "arrival_age_s": age,
        "raw_droop": raw_droop,
        "filtered_droop": state["filtered_droop"] if baseline else None,
        "baseline_rpm": baseline_rpm,
        "rpm": sample["rpm"] if sample else None,
        "pwm": sample["pwm"] if sample else None,
        "reported_override": sample["override"] if sample else None,
        "next_adjustment_s": None,
        "machine_position": sample["position"] if sample else None,
        "program_line": None,
        "response": unavailable,
    }
    if state["fault"]:
        result.update({"status": "blocked", "limiting_factor": "Latched monitor fault"})
    elif age is not None and not 0 <= age <= STALE_SECONDS:
        result.update(
            {
                "status": "blocked",
                "limiting_factor": "Complete telemetry arrival age",
                "explanation": "Complete sample is stale or from a future clock; no current proposal is available.",
            }
        )
    elif state["mode"] != "shadow":
        result.update({"status": "off", "limiting_factor": "Monitor disabled"})
    elif sample is None:
        result["limiting_factor"] = "Complete spindle, feed and position telemetry required"
    elif state["baseline_capture"]["active"]:
        result["limiting_factor"] = "Stationary unloaded baseline capture"
    elif baseline is None:
        pass
    elif sample["state"] != "Run" or sample["feed"] <= 0:
        result["limiting_factor"] = "Outside reported cutting feed"
    else:
        filtered = state["filtered_droop"]
        pwm = sample["pwm"]
        proposal = state["proposed_override"]
        interval = None
        result["proposal_percent"] = proposal
        result["response"] = _response(history)
        if filtered >= BACKOFF_DROOP or (pwm is not None and pwm >= PWM_BACKOFF):
            result["status"] = "would hold" if proposal <= FEED_FLOOR else "backoff"
            result["limiting_factor"] = (
                "40% experimental feed floor"
                if proposal <= FEED_FLOOR
                else "Filtered baseline RPM droop and drive effort"
                if filtered >= BACKOFF_DROOP and pwm is not None and pwm >= PWM_BACKOFF
                else "Filtered baseline RPM droop"
                if filtered >= BACKOFF_DROOP
                else "Drive effort"
            )
            interval = BACKOFF_INTERVAL
        elif filtered < RECOVERY_DROOP and (pwm is None or pwm <= PWM_RECOVERY):
            result["status"] = "recovery" if proposal < FEED_CEILING else "ceiling"
            result["limiting_factor"] = (
                "2 s recovery dwell" if proposal < FEED_CEILING else "100% programmed-feed ceiling"
            )
            interval = RECOVERY_INTERVAL
        else:
            result.update({"status": "retain", "limiting_factor": "Experimental load band"})
        if interval is not None and last_adjustment is not None:
            reference = sample["timestamp"] if now is None else now
            result["next_adjustment_s"] = max(0.0, interval - (reference - last_adjustment))
    if result["proposal_percent"] is None:
        result["response"]["explanation"] = "Current decision is unavailable; no response comparison is shown."
    return result
