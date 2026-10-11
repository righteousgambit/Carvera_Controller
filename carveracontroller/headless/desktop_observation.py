"""Detached display of actual backend snapshots; never grants command readiness."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            result = float(value)
        except OverflowError:
            return None
        if math.isfinite(result):
            return result
    return None


def _age(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None


def _report_age(snapshot_age: float | None, report_ms: object) -> float | None:
    report_age = _age(report_ms)
    if snapshot_age is None or report_age is None:
        return None
    total = snapshot_age + report_age / 1000
    return total if math.isfinite(total) else None


def _format(value: object, suffix: str = "") -> str:
    number = _number(value)
    return "unknown" if number is None else f"{number:g}{suffix}"


def _freshness(kind: str, age: float | None, active: bool) -> str:
    if not active:
        return f"{kind}: retained report · current receipt unavailable"
    if age is None:
        return f"{kind}: receipt age unknown"
    return f"{kind}: {'recent' if age <= 2 else 'stale'} · host receipt age {age:.1f}s"


@dataclass(frozen=True)
class BackendObservation:
    connected: bool | None
    connection_id: str | None
    unknown_outcome: bool | None
    transfer_active: bool | None
    summary: str
    telemetry: str


def describe_backend(state: dict[str, Any]) -> BackendObservation:
    """Each report stands alone; missing fields never inherit a previous packet.

    Report age combines the child receipt age with age of the cached IPC result.
    Neither clock measures physical exposure or completed motion. Two seconds
    controls the display's recent/stale label only, not execution admission.
    """
    snapshot = state.get("last_machine_snapshot")
    if not isinstance(snapshot, dict):
        return BackendObservation(
            None, None, None, None, "No machine snapshot observed.", "No machine reports observed."
        )
    connected = snapshot.get("connected") if type(snapshot.get("connected")) is bool else None
    identity = snapshot.get("connection_id")
    connection_id = identity if isinstance(identity, str) and 0 < len(identity) <= 100 else None
    unknown = snapshot.get("unknown_outcome") if type(snapshot.get("unknown_outcome")) is bool else None
    transfer = snapshot.get("transfer_active") if type(snapshot.get("transfer_active")) is bool else None
    active = (
        connected is True and state.get("ready") is True and state.get("running") is True and connection_id is not None
    )
    summary = (
        f"Reported connection: {'connected' if connected is True else 'disconnected' if connected is False else 'unknown'}\n"
        f"Unresolved command outcome: {'reported' if unknown is True else 'none reported' if unknown is False else 'unknown'}\n"
        f"Transfer: {'reported active' if transfer is True else 'none reported active' if transfer is False else 'unknown'}"
    )
    status, diagnostics = snapshot.get("status"), snapshot.get("diagnostics")
    status = status if isinstance(status, dict) else {}
    diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
    snapshot_age = _age(state.get("last_machine_snapshot_age_s"))
    lines = [
        "Backend reports · independent of the current job controller",
        _freshness("Position / spindle", _report_age(snapshot_age, snapshot.get("status_age_ms")), active)
        if status
        else "Position / spindle: no report received",
    ]
    if status:
        reported = status.get("state")
        lines.append(
            "Reported state: " + (reported if isinstance(reported, str) and len(reported) <= 32 else "unknown")
        )
        for key, title in (("machine_position", "Machine"), ("work_position", "Work")):
            position = status.get(key)
            position = position if isinstance(position, dict) else {}
            linear = status.get("linear_units") == "mm"
            lines.append(
                title
                + " · "
                + " / ".join(
                    f"{axis.upper()} {_format(position.get(axis), ' mm') if linear else 'unknown'}"
                    for axis in ("x", "y", "z")
                )
            )
            lines.append(
                title
                + " rotary · "
                + " / ".join(
                    f"{axis.upper()} {_format(position.get(axis), '°') if status.get('rotary_units') == 'degrees' else 'unknown'}"
                    for axis in ("a", "b")
                )
            )
        lines.append(
            f"Spindle · actual {_format(status.get('spindle_rpm'), ' RPM')} / target {_format(status.get('spindle_target_rpm'), ' RPM')}"
        )
        lines.append(
            f"Feed · {_format(status.get('feed_mm_per_min'), ' mm/min')} / override {_format(status.get('feed_override_percent'), '%')}"
        )
        lines.append("Reported tool: " + _format(status.get("tool")))
    lines.append(
        _freshness("Machine inputs", _report_age(snapshot_age, snapshot.get("diagnostics_age_ms")), active)
        if diagnostics
        else "Machine inputs: no report received"
    )
    if diagnostics:
        for key, title in (
            ("spindle_enabled", "Spindle enabled"),
            ("cover_input", "Cover input"),
            ("stop_input", "Stop input"),
            ("probe_triggered", "Probe input"),
            ("setter_triggered", "Setter input"),
        ):
            value = diagnostics.get(key)
            lines.append(f"{title}: {'reported 1' if value is True else 'reported 0' if value is False else 'unknown'}")
    if not state.get("ready") or not state.get("running"):
        lines.append("Backend unavailable · retained values are historical")
    return BackendObservation(connected, connection_id, unknown, transfer, summary, "\n".join(lines))
