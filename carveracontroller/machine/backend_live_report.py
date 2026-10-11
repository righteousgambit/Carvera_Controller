"""Read-only, lease-bound report projection; never enables commands or writes GUI state.

The backend parser supplies normalized linear mm and separate rotary degrees.
Receipt age is a host observation age, not a firmware sampling timestamp.
Reported tool offsets retain their unspecified firmware reference/units.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from .desktop_control_owner import DesktopControlOwner, reported_state
from .observed_pose import ObservedPose


def finite(value: object) -> float | None:
    if type(value) not in (int, float):
        return None
    try:
        result = float(value)  # type: ignore[arg-type]
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def integer(value: object, low: int, high: int) -> int | None:
    number = finite(value)
    return int(number) if number is not None and number.is_integer() and low <= number <= high else None


def wcs_name(index: object) -> str:
    value = integer(index, 0, 8)
    return "Unknown" if value is None else f"G{54 + value}" if value < 6 else f"G59.{value - 5}"


@dataclass(frozen=True)
class BackendLiveReport:
    status: dict[str, Any] | None = None
    pose: ObservedPose | None = None
    report_age_s: float | None = None
    session_id: str | None = None
    connection_id: str | None = None
    reason: str = "No current backend report"

    @property
    def current(self) -> bool:
        return self.status is not None

    @property
    def raw_tool_offset(self) -> float | None:
        return finite(self.status.get("tool_offset_reported")) if self.status else None


def backend_live_report(
    owner: DesktopControlOwner,
    session_id: str | None,
    state: dict[str, Any],
    profile: dict[str, Any],
    now: float,
) -> BackendLiveReport:
    """Project only the selected lease's latest packet, with no inherited fields."""
    current_time = finite(now)
    if current_time is None or current_time < 0 or not owner.matches(session_id, state):
        return BackendLiveReport(reason="Selected backend connection unavailable or replaced")
    snapshot = state["last_machine_snapshot"]
    if snapshot.get("unknown_outcome") is not False or snapshot.get("transfer_active") is not False:
        return BackendLiveReport(reason="Backend outcome unresolved or binary transfer active")
    mode = reported_state(state)
    if mode is None:
        return BackendLiveReport(reason="Backend status stale, missing or receipt age unknown")
    status = snapshot["status"]
    model = profile.get("model")
    expected_model = {"C1": 1, "CA1": 2}.get(model) if isinstance(model, str) else None
    if expected_model is None or integer(status.get("machine_model"), 1, 2) != expected_model:
        return BackendLiveReport(reason="Reported machine model differs from the selected profile")
    cached_age, child_age = finite(state.get("last_machine_snapshot_age_s")), finite(snapshot.get("status_age_ms"))
    assert cached_age is not None and child_age is not None
    age = cached_age + child_age / 1000
    if age > current_time:
        return BackendLiveReport(reason="Report receipt time precedes the current host clock")
    report = BackendLiveReport(copy.deepcopy(status), None, age, session_id, snapshot["connection_id"], "")
    machine, work = status.get("machine_position"), status.get("work_position")
    if not isinstance(machine, dict) or not isinstance(work, dict) or status.get("linear_units") != "mm":
        return BackendLiveReport(
            report.status, None, age, session_id, report.connection_id, "Pose coordinates or units unknown"
        )
    coordinates = [finite(values.get(axis)) for values in (machine, work) for axis in ("x", "y", "z")]
    rotation, rotary = finite(status.get("rotation_degrees")), finite(machine.get("a"))
    wcs = integer(status.get("active_wcs"), 0, 8)
    if (
        any(value is None or abs(value) > 1e9 for value in coordinates)
        or rotation is None
        or rotary is None
        or wcs is None
        or status.get("rotary_units") != "degrees"
    ):
        return BackendLiveReport(
            report.status,
            None,
            age,
            session_id,
            report.connection_id,
            "Complete XYZ, rotation, rotary and WCS reports required for the live scene",
        )
    assert all(value is not None for value in coordinates)
    pose = ObservedPose(
        current_time - age,
        mode,
        (float(coordinates[0]), float(coordinates[1]), float(coordinates[2])),  # type: ignore[arg-type]
        (float(coordinates[3]), float(coordinates[4]), float(coordinates[5])),  # type: ignore[arg-type]
        integer(status.get("tool"), 0, 255),
        None,
        rotation,
        wcs,
        rotary,
    )
    return BackendLiveReport(report.status, pose, age, session_id, report.connection_id, "")
