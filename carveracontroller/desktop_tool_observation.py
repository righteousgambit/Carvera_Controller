"""One read-only tooling observation from the explicitly selected controller."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from carveracontroller.headless.atc_offset import AtcOffsetObservation
from carveracontroller.machine.backend_live_report import BackendLiveReport, finite, integer
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.tool_bank_review import BankRow, OffsetStatus, mapped_offset_status


@dataclass(frozen=True)
class ToolObservation:
    backend_selected: bool
    endpoint: str = ""
    pose: ObservedPose | None = None
    tool: int | None = None
    raw_offset: float | None = None
    current: bool = False
    reason: str = "Current tool report unavailable"
    owner_key: tuple[str | None, str | None] = (None, None)
    connection_current: bool | None = None
    atc_offset: AtcOffsetObservation | None = None

    @property
    def signature(self) -> tuple[Any, ...]:
        return (
            self.backend_selected,
            self.owner_key,
            self.endpoint,
            self.current,
            self.tool,
            self.pose.tool_length_mm if self.pose else None,
            self.raw_offset,
            self.reason,
            self.connection_current,
            self.atc_offset.receipt_json if self.atc_offset else None,
        )

    def compare_offset(self, row: BankRow, now: float) -> OffsetStatus:
        result = mapped_offset_status(row, self.pose, now)
        if self.backend_selected and self.current and self.tool == row["controller_tool"]:
            value = f"{self.raw_offset:g}" if self.raw_offset is not None else "Unknown"
            result["detail"] += f" · backend raw offset {value}; firmware units/reference unknown, no mm comparison"
        if (
            self.atc_offset is not None
            and self.atc_offset.fresh(now)
            and self.atc_offset.receipt["tool"] == row["controller_tool"]
        ):
            offset_value = self.atc_offset.receipt
            result["detail"] += (
                f" · independent fresh M499 ATC offset {offset_value['atc_offset_mm']:g} mm / reference MZ {offset_value['reference_mz_mm']:g} mm; Robot compensation and physical identity unverified"
            )
        return result


def observe_tool(workspace: Any, now: float) -> ToolObservation:
    """Never reads the GUI controller when a backend owner is selected.

    A missing, stale or replaced backend stays unavailable. A raw firmware
    offset never becomes an established millimetre calibration value.
    """
    owner = getattr(workspace, "control_owner", None)
    if owner is not None and owner.backend_selected:
        binding = owner.binding
        key = (binding.session_id, binding.connection_id)
        read = getattr(workspace, "backend_report", None)
        report = read() if callable(read) else None
        if not isinstance(report, BackendLiveReport) or not report.current:
            return ToolObservation(
                True,
                reason=report.reason if isinstance(report, BackendLiveReport) else "Backend report unavailable",
                owner_key=key,
            )
        panel = getattr(workspace, "backend_panel", None)
        client = getattr(panel, "client", None)
        if (
            getattr(workspace, "control_owner", None) is not owner
            or owner.binding is not binding
            or (report.session_id, report.connection_id) != key
            or getattr(client, "session_id", None) != report.session_id
            or getattr(panel, "closed", True)
            or getattr(panel, "stopping", True)
        ):
            return ToolObservation(True, reason="Selected backend changed during tooling report", owner_key=key)
        host, port = getattr(client, "host", None), getattr(client, "port", None)
        endpoint = f"{host}:{port}" if isinstance(host, str) and type(port) is int and 1 <= port <= 65535 else ""
        pose = replace(report.pose, tool_length_mm=None) if report.pose is not None else None
        assert report.status is not None
        offset_panel = getattr(workspace, "tool_measurement_panel", None)
        offset = getattr(offset_panel, "atc_offset_observation", None)
        if not isinstance(offset, AtcOffsetObservation) or not offset.fresh_for(
            key,
            getattr(workspace, "selected_machine_profile", None) or {},
            integer(report.status.get("tool"), 0, 255),
            now,
        ):
            offset = None
        return ToolObservation(
            True,
            endpoint,
            pose,
            integer(report.status.get("tool"), 0, 255),
            report.raw_tool_offset,
            True,
            report.reason,
            key,
            True,
            offset,
        )
    controller = workspace.machine.controller
    candidate = getattr(controller, "observed_pose", None)
    connected = getattr(workspace, "connected", None)
    # Legacy read-only consumers can supply a fresh packet without connection
    # availability. Keep their numeric comparison separate from that unknown;
    # an explicit disconnect always retires the current packet.
    connection_current = connected if type(connected) is bool else None
    current = bool(connection_current is not False and isinstance(candidate, ObservedPose) and candidate.fresh(now))
    pose = (
        replace(candidate, tool_length_mm=finite(candidate.tool_length_mm))
        if current and isinstance(candidate, ObservedPose)
        else None
    )
    return ToolObservation(
        False,
        str(getattr(controller, "connection_address", "") or ""),
        pose,
        pose.tool if pose else None,
        current=current,
        reason=(
            "GUI connection availability unknown; numeric packet comparison only" if connection_current is None else ""
        )
        if current
        else "GUI controller disconnected or tool report stale",
        connection_current=connection_current,
    )
