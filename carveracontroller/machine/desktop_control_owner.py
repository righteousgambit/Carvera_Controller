"""Explicit desktop control binding; losing a backend never selects another owner."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ControlBinding:
    session_id: str
    connection_id: str


class DesktopControlOwner:
    def __init__(self) -> None:
        self.binding: ControlBinding | None = None

    @property
    def backend_selected(self) -> bool:
        return self.binding is not None

    def matches(self, session_id: str | None, state: dict[str, Any]) -> bool:
        snapshot = state.get("last_machine_snapshot")
        return bool(
            self.binding
            and self.binding.session_id == session_id
            and isinstance(snapshot, dict)
            and snapshot.get("connection_id") == self.binding.connection_id
            and snapshot.get("connected") is True
            and state.get("ready") is True
            and state.get("running") is True
        )

    def claim(self, session_id: str, state: dict[str, Any], *, gui_busy: bool) -> None:
        if self.binding is not None or gui_busy:
            raise ValueError("Disconnect the existing job controller before handing off workbench controls")
        snapshot = state.get("last_machine_snapshot")
        if not isinstance(snapshot, dict):
            raise ValueError("Connect the current backend before handing off workbench controls")
        identity = snapshot.get("connection_id")
        if (
            not isinstance(session_id, str)
            or not 0 < len(session_id) <= 100
            or not isinstance(identity, str)
            or not 0 < len(identity) <= 100
            or snapshot.get("connected") is not True
            or state.get("ready") is not True
            or state.get("running") is not True
        ):
            raise ValueError("Connect the current backend before handing off workbench controls")
        self.binding = ControlBinding(session_id, identity)

    def release(self, session_id: str | None, state: dict[str, Any]) -> None:
        if self.binding is None:
            return
        snapshot = state.get("last_machine_snapshot")
        stopped = state.get("running") is False and session_id in (None, self.binding.session_id)
        disconnected = (
            session_id == self.binding.session_id
            and state.get("ready") is True
            and isinstance(snapshot, dict)
            and snapshot.get("connected") is False
            and snapshot.get("unknown_outcome") is False
        )
        if not stopped and not disconnected:
            raise ValueError("Disconnect or stop the backend before returning controls to the job controller")
        self.binding = None


def reported_state(state: dict[str, Any], max_age_s: float = 0.8) -> str | None:
    """Require both cached IPC age and the child status receipt age; never uses GUI state."""
    snapshot = state.get("last_machine_snapshot")
    if not isinstance(snapshot, dict):
        return None
    status = snapshot.get("status")
    if not isinstance(status, dict):
        return None
    ages = []
    for value in (state.get("last_machine_snapshot_age_s"), snapshot.get("status_age_ms")):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        try:
            age = float(value)
        except OverflowError:
            return None
        if not math.isfinite(age) or age < 0:
            return None
        ages.append(age)
    if ages[0] + ages[1] / 1000 > max_age_s:
        return None
    value = status.get("state")
    return value if value in ("Idle", "Run", "Home", "Hold", "Pause", "Wait", "Tool", "Alarm", "Sleep") else None
